import { describe, expect, it } from 'vitest';
import { computeVisibleFieldsAndGroups, computeMaxAvailableDepth } from './fieldGrouping';

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

  it('should strip itemFields when depth is insufficient', () => {
    const fields = [
      {
        name: 'items',
        label: 'Items',
        itemFields: [{ name: 'id' }, { name: 'name' }],
      },
    ];

    // Items at depth 1, but itemFields need depth 2
    const result = computeVisibleFieldsAndGroups(fields, 1);

    expect(result.visibleFields).toHaveLength(1);
    expect(result.visibleFields[0].itemFields).toBeUndefined();
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
