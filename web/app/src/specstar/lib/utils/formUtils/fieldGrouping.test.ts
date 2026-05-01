import { describe, expect, it } from 'vitest';
import {
  computeVisibleFieldsAndGroups,
  computeMaxAvailableDepth,
  groupFieldsByParent,
} from './fieldGrouping';

describe('computeVisibleFieldsAndGroups', () => {
  it('should return all fields as visible when formDepth is max', () => {
    const fields = [
      { name: 'name', label: 'Name' },
      { name: 'user.email', label: 'Email' },
      { name: 'user.profile.bio', label: 'Bio' },
    ];

    const result = computeVisibleFieldsAndGroups(fields, 3);

    expect(result.visibleFields).toHaveLength(3);
    expect(result.collapsedGroups).toHaveLength(0);
    expect(result.collapsedGroupFields.size).toBe(0);
  });

  it('should collapse all nested fields when formDepth is 1', () => {
    const fields = [
      { name: 'id', label: 'ID' },
      { name: 'user.name', label: 'Name' },
      { name: 'user.email', label: 'Email' },
      { name: 'user.profile.bio', label: 'Bio' },
    ];

    const result = computeVisibleFieldsAndGroups(fields, 1);

    expect(result.visibleFields).toHaveLength(1);
    expect(result.visibleFields[0].name).toBe('id');
    expect(result.collapsedGroups).toHaveLength(1);
    expect(result.collapsedGroups[0]).toEqual({ path: 'user', label: 'User' });
    expect(result.collapsedGroupFields.get('user')).toHaveLength(3);
  });

  it('should handle formDepth=2 correctly', () => {
    const fields = [
      { name: 'id', label: 'ID' },
      { name: 'user.name', label: 'Name' },
      { name: 'user.profile.bio', label: 'Bio' },
      { name: 'user.profile.avatar', label: 'Avatar' },
    ];

    const result = computeVisibleFieldsAndGroups(fields, 2);

    expect(result.visibleFields).toHaveLength(2);
    expect(result.visibleFields.map((f) => f.name)).toEqual(['id', 'user.name']);
    expect(result.collapsedGroups).toHaveLength(1);
    expect(result.collapsedGroups[0]).toEqual({ path: 'user.profile', label: 'Profile' });
    expect(result.collapsedGroupFields.get('user.profile')).toHaveLength(2);
  });

  it('should add depth-insufficient itemFields field to collapsedGroups (renders as JSON textarea)', () => {
    const fields = [
      {
        name: 'items',
        label: 'Items',
        itemFields: [{ name: 'id' }, { name: 'name' }],
      },
    ];

    // Items at depth 1, but itemFields need depth 2 → collapse as JSON textarea
    const result = computeVisibleFieldsAndGroups(fields, 1);

    expect(result.visibleFields).toHaveLength(0);
    expect(result.collapsedGroups).toHaveLength(1);
    expect(result.collapsedGroups[0].path).toBe('items');
  });

  it('should preserve itemFields when depth is sufficient', () => {
    const fields = [
      {
        name: 'items',
        label: 'Items',
        itemFields: [{ name: 'id' }, { name: 'name' }],
      },
    ];

    // Items at depth 1, and formDepth=2 allows itemFields
    const result = computeVisibleFieldsAndGroups(fields, 2);

    expect(result.visibleFields).toHaveLength(1);
    expect(result.visibleFields[0].itemFields).toHaveLength(2);
  });

  it('should not create collapsed group for already visible object field', () => {
    const fields = [
      { name: 'metadata', label: 'Metadata', type: 'object' },
      { name: 'metadata.key1', label: 'Key 1' },
      { name: 'metadata.key2', label: 'Key 2' },
    ];

    const result = computeVisibleFieldsAndGroups(fields, 1);

    // 'metadata' is visible, so don't create a collapsed group for it
    expect(result.visibleFields).toHaveLength(1);
    expect(result.visibleFields[0].name).toBe('metadata');
    expect(result.collapsedGroups).toHaveLength(0); // Not 1, because 'metadata' is already visible
  });

  it('should handle empty fields array', () => {
    const result = computeVisibleFieldsAndGroups([], 1);

    expect(result.visibleFields).toHaveLength(0);
    expect(result.collapsedGroups).toHaveLength(0);
    expect(result.collapsedGroupFields.size).toBe(0);
  });

  it('should group deeply nested fields correctly', () => {
    const fields = [{ name: 'a.b.c.d.e.f', label: 'Deep' }];

    const result = computeVisibleFieldsAndGroups(fields, 2);

    expect(result.visibleFields).toHaveLength(0);
    expect(result.collapsedGroups).toHaveLength(1);
    expect(result.collapsedGroups[0]).toEqual({ path: 'a.b', label: 'B' });
    expect(result.collapsedGroupFields.get('a.b')).toHaveLength(1);
  });

  it('should handle multiple fields collapsing to same parent', () => {
    const fields = [
      { name: 'user.profile.bio', label: 'Bio' },
      { name: 'user.profile.avatar', label: 'Avatar' },
      { name: 'user.profile.location', label: 'Location' },
    ];

    const result = computeVisibleFieldsAndGroups(fields, 1);

    expect(result.visibleFields).toHaveLength(0);
    expect(result.collapsedGroups).toHaveLength(1);
    expect(result.collapsedGroups[0].path).toBe('user');
    expect(result.collapsedGroupFields.get('user')).toHaveLength(3);
  });

  it('should use toLabel for collapsed group labels', () => {
    const fields = [{ name: 'api_key.secret_value', label: 'Secret' }];

    const result = computeVisibleFieldsAndGroups(fields, 1);

    expect(result.collapsedGroups[0].label).toBe('Api Key'); // snake_case → Title Case
  });
});

describe('computeMaxAvailableDepth', () => {
  it('should return 1 for flat fields', () => {
    const fields = [{ name: 'id' }, { name: 'name' }, { name: 'email' }];

    expect(computeMaxAvailableDepth(fields)).toBe(1);
  });

  it('should return max depth for nested fields', () => {
    const fields = [
      { name: 'id' }, // depth 1
      { name: 'user.name' }, // depth 2
      { name: 'user.profile.bio' }, // depth 3
    ];

    expect(computeMaxAvailableDepth(fields)).toBe(3);
  });

  it('should add 1 for fields with itemFields', () => {
    const fields = [
      { name: 'items', itemFields: [{ name: 'id' }] }, // depth 1 + 1 = 2
    ];

    expect(computeMaxAvailableDepth(fields)).toBe(2);
  });

  it('should use higher depth from itemFields', () => {
    const fields = [
      { name: 'data.items', itemFields: [{ name: 'id' }] }, // depth 2 + 1 = 3
      { name: 'simple.field' }, // depth 2
    ];

    expect(computeMaxAvailableDepth(fields)).toBe(3);
  });

  it('should return 1 for empty fields', () => {
    expect(computeMaxAvailableDepth([])).toBe(1);
  });

  it('should handle deeply nested fields', () => {
    const fields = [
      { name: 'a.b.c.d.e.f.g.h.i.j' }, // depth 10
    ];

    expect(computeMaxAvailableDepth(fields)).toBe(10);
  });

  it('should handle fields with empty itemFields array', () => {
    const fields = [
      { name: 'items', itemFields: [] }, // depth 1 (itemFields empty, no +1)
    ];

    expect(computeMaxAvailableDepth(fields)).toBe(1);
  });

  it('should use max across multiple fields', () => {
    const fields = [
      { name: 'a' }, // depth 1
      { name: 'b.c' }, // depth 2
      { name: 'd.e.f' }, // depth 3
      { name: 'items', itemFields: [{ name: 'x' }] }, // depth 1 + 1 = 2
    ];

    expect(computeMaxAvailableDepth(fields)).toBe(3);
  });
});

// ============================================================================
// groupFieldsByParent
// ============================================================================
describe('groupFieldsByParent', () => {
  it('should return single null-parent group for flat fields (no dots)', () => {
    const fields = [
      { name: 'id', label: 'ID' },
      { name: 'name', label: 'Name' },
      { name: 'email', label: 'Email' },
    ];

    const groups = groupFieldsByParent(fields);

    expect(groups).toHaveLength(1);
    expect(groups[0].parentPath).toBeNull();
    expect(groups[0].parentLabel).toBeNull();
    expect(groups[0].fields).toHaveLength(3);
  });

  it('should group nested fields by shared parent', () => {
    const fields = [
      { name: 'id', label: 'ID' },
      { name: 'user.email', label: 'Email' },
      { name: 'user.name', label: 'Name' },
      { name: 'address.city', label: 'City' },
      { name: 'address.zip', label: 'Zip' },
    ];

    const groups = groupFieldsByParent(fields);

    expect(groups).toHaveLength(3);
    // First group: flat fields
    expect(groups[0].parentPath).toBeNull();
    expect(groups[0].fields.map((f: any) => f.name)).toEqual(['id']);
    // Second group: user.*
    expect(groups[1].parentPath).toBe('user');
    expect(groups[1].parentLabel).toBe('User');
    expect(groups[1].fields.map((f: any) => f.name)).toEqual(['user.email', 'user.name']);
    // Third group: address.*
    expect(groups[2].parentPath).toBe('address');
    expect(groups[2].parentLabel).toBe('Address');
    expect(groups[2].fields.map((f: any) => f.name)).toEqual(['address.city', 'address.zip']);
  });

  it('should handle deeply nested fields — groups by immediate parent', () => {
    const fields = [
      { name: 'payload.event_x2.type', label: 'Type' },
      { name: 'payload.event_x2.good', label: 'Good' },
      { name: 'payload.event_x2.great', label: 'Great' },
      { name: 'payload.event_x.good', label: 'Good' },
      { name: 'payload.event_x.great', label: 'Great' },
    ];

    const groups = groupFieldsByParent(fields);

    expect(groups).toHaveLength(2);
    expect(groups[0].parentPath).toBe('payload.event_x2');
    expect(groups[0].parentLabel).toBe('Event X2');
    expect(groups[0].fields).toHaveLength(3);
    expect(groups[1].parentPath).toBe('payload.event_x');
    expect(groups[1].parentLabel).toBe('Event X');
    expect(groups[1].fields).toHaveLength(2);
  });

  it('should merge interleaved flat and nested fields by parent', () => {
    const fields = [
      { name: 'title', label: 'Title' },
      { name: 'user.name', label: 'Name' },
      { name: 'description', label: 'Description' },
    ];

    const groups = groupFieldsByParent(fields);

    // 2 groups: flat fields merged, user.* separate
    expect(groups).toHaveLength(2);
    expect(groups[0].parentPath).toBeNull();
    expect(groups[0].fields.map((f: any) => f.name)).toEqual(['title', 'description']);
    expect(groups[1].parentPath).toBe('user');
    expect(groups[1].fields.map((f: any) => f.name)).toEqual(['user.name']);
  });

  it('should return empty array for empty fields', () => {
    const groups = groupFieldsByParent([]);
    expect(groups).toHaveLength(0);
  });

  it('should use toLabel for parent label from snake_case', () => {
    const fields = [{ name: 'api_key.secret_value', label: 'Secret Value' }];

    const groups = groupFieldsByParent(fields);

    expect(groups[0].parentLabel).toBe('Api Key');
  });

  it('should nest sub-groups inside parent group (no duplicate keys)', () => {
    // Real scenario: payload.event_body.* fields split payload.* direct children
    const fields = [
      { name: 'payload.event_type', label: 'Event Type' },
      { name: 'payload.character_name', label: 'Character Name' },
      { name: 'payload.character_id', label: 'Character Id' },
      { name: 'payload.event_body.good', label: 'Good' },
      { name: 'payload.event_body.great', label: 'Great' },
      { name: 'payload.description', label: 'Description' },
      { name: 'payload.reward_gold', label: 'Reward Gold' },
      { name: 'payload.reward_exp', label: 'Reward Exp' },
      { name: 'payload.extra_data', label: 'Extra Data' },
    ];

    const groups = groupFieldsByParent(fields);

    // 1 root group: payload (event_body nested as child)
    expect(groups).toHaveLength(1);

    const payload = groups[0];
    expect(payload.parentPath).toBe('payload');
    expect(payload.parentLabel).toBe('Payload');
    expect(payload.fields.map((f: any) => f.name)).toEqual([
      'payload.event_type',
      'payload.character_name',
      'payload.character_id',
      'payload.description',
      'payload.reward_gold',
      'payload.reward_exp',
      'payload.extra_data',
    ]);

    // event_body nested as child of payload
    expect(payload.children).toHaveLength(1);
    expect(payload.children[0].parentPath).toBe('payload.event_body');
    expect(payload.children[0].parentLabel).toBe('Event Body');
    expect(payload.children[0].fields.map((f: any) => f.name)).toEqual([
      'payload.event_body.good',
      'payload.event_body.great',
    ]);
  });

  it('should merge non-consecutive top-level fields split by nested fields', () => {
    const fields = [
      { name: 'title', label: 'Title' },
      { name: 'user.name', label: 'Name' },
      { name: 'user.email', label: 'Email' },
      { name: 'description', label: 'Description' },
    ];

    const groups = groupFieldsByParent(fields);

    // top-level fields merged, user group in between (by first-appearance order)
    expect(groups).toHaveLength(2);
    expect(groups[0].parentPath).toBeNull();
    expect(groups[0].fields.map((f: any) => f.name)).toEqual(['title', 'description']);
    expect(groups[1].parentPath).toBe('user');
    expect(groups[1].fields.map((f: any) => f.name)).toEqual(['user.name', 'user.email']);
  });

  it('should nest event_x2 and event_x inside payload when payload has direct fields', () => {
    const fields = [
      { name: 'payload.event_type', label: 'Event Type' },
      { name: 'payload.character_name', label: 'Character Name' },
      { name: 'payload.event_x2.type', label: 'Type' },
      { name: 'payload.event_x2.good', label: 'Good' },
      { name: 'payload.event_x2.great', label: 'Great' },
      { name: 'payload.event_x.good', label: 'Good' },
      { name: 'payload.event_x.great', label: 'Great' },
      { name: 'payload.description', label: 'Description' },
    ];

    const groups = groupFieldsByParent(fields);

    // 1 root group: payload
    expect(groups).toHaveLength(1);
    const payload = groups[0];
    expect(payload.parentPath).toBe('payload');
    expect(payload.fields.map((f: any) => f.name)).toEqual([
      'payload.event_type',
      'payload.character_name',
      'payload.description',
    ]);

    // 2 nested children: event_x2 and event_x
    expect(payload.children).toHaveLength(2);
    expect(payload.children[0].parentPath).toBe('payload.event_x2');
    expect(payload.children[0].parentLabel).toBe('Event X2');
    expect(payload.children[0].fields).toHaveLength(3);
    expect(payload.children[1].parentPath).toBe('payload.event_x');
    expect(payload.children[1].parentLabel).toBe('Event X');
    expect(payload.children[1].fields).toHaveLength(2);
  });

  it('should NOT nest groups when parent group does not exist', () => {
    // Only deep fields, no direct payload.* fields → no payload group to nest into
    const fields = [
      { name: 'payload.event_x2.type', label: 'Type' },
      { name: 'payload.event_x2.good', label: 'Good' },
      { name: 'payload.event_x.good', label: 'Good' },
    ];

    const groups = groupFieldsByParent(fields);

    // No payload group → event_x2 and event_x stay flat at root
    expect(groups).toHaveLength(2);
    expect(groups[0].parentPath).toBe('payload.event_x2');
    expect(groups[0].children).toHaveLength(0);
    expect(groups[1].parentPath).toBe('payload.event_x');
    expect(groups[1].children).toHaveLength(0);
  });

  it('should have empty children array for leaf groups', () => {
    const fields = [
      { name: 'id', label: 'ID' },
      { name: 'user.email', label: 'Email' },
    ];

    const groups = groupFieldsByParent(fields);

    expect(groups).toHaveLength(2);
    expect(groups[0].children).toHaveLength(0);
    expect(groups[1].children).toHaveLength(0);
  });
});
