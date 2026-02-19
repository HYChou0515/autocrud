/**
 * useFieldDepth — Tests for the stripItemFields behaviour.
 *
 * The core depth computation functions (computeMaxAvailableDepth,
 * computeVisibleFieldsAndGroups) are already tested in fieldGrouping.test.ts.
 * These tests focus on the detail-specific stripItemFields logic.
 */

import { describe, it, expect } from 'vitest';
import { computeMaxAvailableDepth, computeVisibleFieldsAndGroups } from '@/lib/utils/formUtils';
import type { ResourceField } from '@/lib/resources';

/** Minimal helper to create a ResourceField. */
function makeField(overrides: Partial<ResourceField> & { name: string }): ResourceField {
  return {
    label: overrides.name,
    type: 'string',
    isArray: false,
    isRequired: false,
    isNullable: false,
    ...overrides,
  };
}

/**
 * Simulate the stripItemFields transformation from useFieldDepth hook.
 * This mirrors the exact logic in useFieldDepth.ts for testability.
 */
function computeWithStripItemFields(fields: ResourceField[], depth: number) {
  const result = computeVisibleFieldsAndGroups(fields, depth);
  const visible = result.visibleFields as ResourceField[];

  const visibleNames = new Set(visible.map((f) => f.name));
  const groupPaths = new Set(result.collapsedGroups.map((g) => g.path));

  for (const field of fields) {
    const fieldDepth = field.name.split('.').length;
    if (
      field.itemFields &&
      field.itemFields.length > 0 &&
      fieldDepth <= depth &&
      fieldDepth + 1 > depth &&
      !visibleNames.has(field.name) &&
      groupPaths.has(field.name)
    ) {
      visible.push({ ...field, itemFields: undefined });
      groupPaths.delete(field.name);
    }
  }

  const filteredGroups = result.collapsedGroups.filter(
    (g) =>
      !fields.some(
        (f) =>
          f.name === g.path &&
          f.itemFields &&
          f.itemFields.length > 0 &&
          f.name.split('.').length <= depth &&
          f.name.split('.').length + 1 > depth,
      ),
  );

  // Re-sort
  const fieldOrder = new Map(fields.map((f, i) => [f.name, i]));
  visible.sort((a, b) => (fieldOrder.get(a.name) ?? 0) - (fieldOrder.get(b.name) ?? 0));

  return { visibleFields: visible, collapsedGroups: filteredGroups };
}

describe('useFieldDepth — stripItemFields logic', () => {
  const itemSubFields = [
    makeField({ name: 'sub_name', type: 'string' }),
    makeField({ name: 'sub_value', type: 'number' }),
  ];

  const fields: ResourceField[] = [
    makeField({ name: 'name', type: 'string' }),
    makeField({ name: 'items', type: 'array', isArray: true, itemFields: itemSubFields }),
    makeField({ name: 'nested.deep', type: 'string' }),
  ];

  it('at depth=1, itemFields field becomes a collapsed group (default behaviour)', () => {
    const result = computeVisibleFieldsAndGroups(fields, 1);
    expect(result.visibleFields.map((f) => f.name)).toEqual(['name']);
    // 'items' and 'nested' become collapsed groups
    expect(result.collapsedGroups.map((g) => g.path)).toContain('items');
    expect(result.collapsedGroups.map((g) => g.path)).toContain('nested');
  });

  it('at depth=1 with stripItemFields, itemFields field is still visible but stripped', () => {
    const result = computeWithStripItemFields(fields, 1);
    expect(result.visibleFields.map((f) => f.name)).toContain('name');
    expect(result.visibleFields.map((f) => f.name)).toContain('items');
    // The items field should have itemFields stripped
    const itemsField = result.visibleFields.find((f) => f.name === 'items');
    expect(itemsField).toBeDefined();
    expect(itemsField!.itemFields).toBeUndefined();
    // 'items' should not be in collapsed groups anymore
    expect(result.collapsedGroups.map((g) => g.path)).not.toContain('items');
    // 'nested' should still be a collapsed group
    expect(result.collapsedGroups.map((g) => g.path)).toContain('nested');
  });

  it('at depth=2 (sufficient), itemFields are preserved regardless of stripItemFields', () => {
    const result = computeWithStripItemFields(fields, 2);
    const itemsField = result.visibleFields.find((f) => f.name === 'items');
    expect(itemsField).toBeDefined();
    // itemFields should be preserved since depth is sufficient
    expect(itemsField!.itemFields).toEqual(itemSubFields);
  });

  it('preserves field order after stripItemFields transformation', () => {
    const result = computeWithStripItemFields(fields, 1);
    const names = result.visibleFields.map((f) => f.name);
    expect(names.indexOf('name')).toBeLessThan(names.indexOf('items'));
  });

  it('computeMaxAvailableDepth accounts for itemFields', () => {
    expect(computeMaxAvailableDepth(fields)).toBe(2);
    // 'name' is depth 1, 'items' is depth 1 but +1 for itemFields = 2. 'nested.deep' = 2
  });
});

describe('useFieldDepth — basic field grouping', () => {
  const simpleFields: ResourceField[] = [
    makeField({ name: 'a', type: 'string' }),
    makeField({ name: 'b', type: 'number' }),
    makeField({ name: 'c.d', type: 'string' }),
    makeField({ name: 'c.e', type: 'string' }),
  ];

  it('at max depth, all fields are visible and no groups are collapsed', () => {
    const maxDepth = computeMaxAvailableDepth(simpleFields);
    const result = computeWithStripItemFields(simpleFields, maxDepth);
    expect(result.visibleFields.length).toBe(4);
    expect(result.collapsedGroups.length).toBe(0);
  });

  it('at depth=1, nested fields are collapsed', () => {
    const result = computeWithStripItemFields(simpleFields, 1);
    expect(result.visibleFields.map((f) => f.name)).toEqual(['a', 'b']);
    expect(result.collapsedGroups.map((g) => g.path)).toEqual(['c']);
  });
});
