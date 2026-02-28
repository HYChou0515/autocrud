import { describe, it, expect, vi } from 'vitest';
import {
  collapseFieldToJson,
  expandFieldFromJson,
  safeGetArrayItems,
  safeGetJsonString,
  restoreCollapsedChildren,
  computeDepthTransitionUpdates,
} from './depthTransition';
import type { ResourceFieldMinimal } from './fieldTypeRegistry';

// Mock the fieldTypeRegistry module for controlled handler behavior
vi.mock('./fieldTypeRegistry', () => {
  const handlers: Record<string, any> = {
    string: {
      defaultVariant: { type: 'text' },
      emptyValue: '',
      toFormValue: (v: any) => (v != null ? String(v) : ''),
      toApiValue: (v: any) => v,
      fromJsonValue: (v: any) => (v != null ? String(v) : ''),
    },
    number: {
      defaultVariant: { type: 'number' },
      emptyValue: '',
      toFormValue: (v: any) => (v != null ? v : ''),
      toApiValue: (v: any) => v,
      fromJsonValue: (v: any) => (v != null ? v : ''),
    },
    boolean: {
      defaultVariant: { type: 'switch' },
      emptyValue: false,
      toFormValue: (v: any) => (v != null ? Boolean(v) : false),
      toApiValue: (v: any) => v,
      fromJsonValue: (v: any) => (v != null ? Boolean(v) : false),
    },
    date: {
      defaultVariant: { type: 'date' },
      emptyValue: null,
      toFormValue: (v: any) => {
        if (v instanceof Date) return v;
        if (typeof v === 'string' && v) return new Date(v);
        return null;
      },
      toApiValue: (v: any) => (v instanceof Date ? v.toISOString() : v),
      fromJsonValue: (v: any) => {
        if (typeof v === 'string' && v) return new Date(v);
        return null;
      },
    },
    object: {
      defaultVariant: { type: 'json' },
      emptyValue: '{}',
      toFormValue: (v: any) =>
        v != null && typeof v === 'object' ? JSON.stringify(v, null, 2) : '{}',
      toApiValue: (v: any) => v,
      fromJsonValue: (v: any) => (v != null ? JSON.stringify(v, null, 2) : '{}'),
    },
    binary: {
      defaultVariant: { type: 'binary' },
      emptyValue: null,
      toFormValue: (v: any) => v ?? null,
      toApiValue: (v: any) => v,
      fromJsonValue: (v: any) => v ?? null,
    },
  };

  return {
    getHandler: (type?: string) => handlers[type || 'string'] || handlers.string,
    getEmptyValue: (field: any) => {
      const handler = handlers[field.type || 'string'] || handlers.string;
      return handler.emptyValue;
    },
  };
});

// ============================================================================
// collapseFieldToJson
// ============================================================================

describe('collapseFieldToJson', () => {
  it('should stringify an array value with formatting', () => {
    const field: ResourceFieldMinimal = {
      name: 'items',
      label: 'Items',
      itemFields: [{ name: 'id', label: 'ID', type: 'number' }],
    };
    const result = collapseFieldToJson([{ id: 1 }, { id: 2 }], field);
    expect(result).toBe(JSON.stringify([{ id: 1 }, { id: 2 }], null, 2));
  });

  it('should stringify a plain object value', () => {
    const field: ResourceFieldMinimal = { name: 'meta', label: 'Meta', type: 'object' };
    const result = collapseFieldToJson({ key: 'val' }, field);
    expect(result).toBe(JSON.stringify({ key: 'val' }, null, 2));
  });

  it('should return "[]" for null when field has itemFields', () => {
    const field: ResourceFieldMinimal = {
      name: 'items',
      label: 'Items',
      itemFields: [{ name: 'id', label: 'ID' }],
    };
    expect(collapseFieldToJson(null, field)).toBe('[]');
  });

  it('should return "[]" for undefined when field has itemFields', () => {
    const field: ResourceFieldMinimal = {
      name: 'items',
      label: 'Items',
      itemFields: [{ name: 'id', label: 'ID' }],
    };
    expect(collapseFieldToJson(undefined, field)).toBe('[]');
  });

  it('should return "{}" for null when field is a plain object', () => {
    const field: ResourceFieldMinimal = { name: 'meta', label: 'Meta', type: 'object' };
    expect(collapseFieldToJson(null, field)).toBe('{}');
  });

  it('should return "{}" for undefined when field is a plain object', () => {
    const field: ResourceFieldMinimal = { name: 'meta', label: 'Meta', type: 'object' };
    expect(collapseFieldToJson(undefined, field)).toBe('{}');
  });

  it('should return string value as-is (already collapsed)', () => {
    const field: ResourceFieldMinimal = { name: 'meta', label: 'Meta', type: 'object' };
    const jsonStr = '{"already":"collapsed"}';
    expect(collapseFieldToJson(jsonStr, field)).toBe(jsonStr);
  });

  it('should handle empty array', () => {
    const field: ResourceFieldMinimal = {
      name: 'items',
      label: 'Items',
      itemFields: [{ name: 'id', label: 'ID' }],
    };
    expect(collapseFieldToJson([], field)).toBe('[]');
  });

  it('should handle empty object', () => {
    const field: ResourceFieldMinimal = { name: 'meta', label: 'Meta', type: 'object' };
    expect(collapseFieldToJson({}, field)).toBe('{}');
  });

  it('should stringify number 0 (truthy edge case)', () => {
    const field: ResourceFieldMinimal = { name: 'val', label: 'Val' };
    expect(collapseFieldToJson(0, field)).toBe('0');
  });

  it('should stringify false (truthy edge case)', () => {
    const field: ResourceFieldMinimal = { name: 'val', label: 'Val' };
    expect(collapseFieldToJson(false, field)).toBe('false');
  });

  it('should return "{}" for field without itemFields and null value', () => {
    const field: ResourceFieldMinimal = { name: 'data', label: 'Data' };
    // No itemFields, no itemFields.length → empty object
    expect(collapseFieldToJson(null, field)).toBe('{}');
  });
});

// ============================================================================
// expandFieldFromJson
// ============================================================================

describe('expandFieldFromJson', () => {
  it('should parse a JSON array and process itemFields through handlers', () => {
    const field: ResourceFieldMinimal = {
      name: 'items',
      label: 'Items',
      itemFields: [
        { name: 'name', label: 'Name', type: 'string' },
        { name: 'count', label: 'Count', type: 'number' },
      ],
    };
    const result = expandFieldFromJson('[{"name":"alice","count":5}]', field);
    expect(result).toEqual([{ name: 'alice', count: 5 }]);
  });

  it('should convert date sub-fields through date handler', () => {
    const field: ResourceFieldMinimal = {
      name: 'events',
      label: 'Events',
      itemFields: [
        { name: 'title', label: 'Title', type: 'string' },
        { name: 'date', label: 'Date', type: 'date' },
      ],
    };
    const result = expandFieldFromJson('[{"title":"Party","date":"2024-06-15T00:00:00Z"}]', field);
    expect(result).toHaveLength(1);
    expect(result[0].title).toBe('Party');
    expect(result[0].date).toBeInstanceOf(Date);
  });

  it('should handle missing sub-field values in items', () => {
    const field: ResourceFieldMinimal = {
      name: 'items',
      label: 'Items',
      itemFields: [
        { name: 'name', label: 'Name', type: 'string' },
        { name: 'count', label: 'Count', type: 'number' },
      ],
    };
    const result = expandFieldFromJson('[{"name":"alice"}]', field);
    expect(result).toEqual([{ name: 'alice', count: '' }]);
  });

  it('should return empty array when parsed value is not an array for itemFields field', () => {
    const field: ResourceFieldMinimal = {
      name: 'items',
      label: 'Items',
      itemFields: [{ name: 'id', label: 'ID', type: 'string' }],
    };
    const result = expandFieldFromJson('{"not":"array"}', field);
    expect(result).toEqual([]);
  });

  it('should parse and return plain object when field has no itemFields', () => {
    const field: ResourceFieldMinimal = { name: 'meta', label: 'Meta', type: 'object' };
    const result = expandFieldFromJson('{"key":"val","num":42}', field);
    expect(result).toEqual({ key: 'val', num: 42 });
  });

  it('should return undefined for invalid JSON', () => {
    const field: ResourceFieldMinimal = { name: 'meta', label: 'Meta', type: 'object' };
    expect(expandFieldFromJson('not valid json', field)).toBeUndefined();
  });

  it('should return undefined for malformed JSON', () => {
    const field: ResourceFieldMinimal = { name: 'meta', label: 'Meta', type: 'object' };
    expect(expandFieldFromJson('{key: val}', field)).toBeUndefined();
  });

  it('should use "[]" default for empty string when field has itemFields', () => {
    const field: ResourceFieldMinimal = {
      name: 'items',
      label: 'Items',
      itemFields: [{ name: 'id', label: 'ID', type: 'string' }],
    };
    const result = expandFieldFromJson('', field);
    expect(result).toEqual([]);
  });

  it('should use "{}" default for empty string when field has no itemFields', () => {
    const field: ResourceFieldMinimal = { name: 'meta', label: 'Meta', type: 'object' };
    const result = expandFieldFromJson('', field);
    expect(result).toEqual({});
  });

  it('should handle multiple items with different sub-field types', () => {
    const field: ResourceFieldMinimal = {
      name: 'records',
      label: 'Records',
      itemFields: [
        { name: 'name', label: 'Name', type: 'string' },
        { name: 'active', label: 'Active', type: 'boolean' },
        { name: 'score', label: 'Score', type: 'number' },
      ],
    };
    const json = JSON.stringify([
      { name: 'Alice', active: true, score: 100 },
      { name: 'Bob', active: false, score: 0 },
    ]);
    const result = expandFieldFromJson(json, field);
    expect(result).toEqual([
      { name: 'Alice', active: true, score: 100 },
      { name: 'Bob', active: false, score: 0 },
    ]);
  });

  it('should handle null items in the array', () => {
    const field: ResourceFieldMinimal = {
      name: 'items',
      label: 'Items',
      itemFields: [{ name: 'name', label: 'Name', type: 'string' }],
    };
    const result = expandFieldFromJson('[null, {"name":"a"}]', field);
    expect(result).toHaveLength(2);
    expect(result[0]).toEqual({ name: '' }); // null item, handler defaults
    expect(result[1]).toEqual({ name: 'a' });
  });

  it('should parse a primitive JSON value (number)', () => {
    const field: ResourceFieldMinimal = { name: 'val', label: 'Val', type: 'number' };
    expect(expandFieldFromJson('42', field)).toBe(42);
  });

  it('should parse a string JSON value', () => {
    const field: ResourceFieldMinimal = { name: 'val', label: 'Val', type: 'string' };
    expect(expandFieldFromJson('"hello"', field)).toBe('hello');
  });

  it('should parse boolean JSON value', () => {
    const field: ResourceFieldMinimal = { name: 'val', label: 'Val', type: 'boolean' };
    expect(expandFieldFromJson('true', field)).toBe(true);
  });

  it('should parse null JSON value', () => {
    const field: ResourceFieldMinimal = { name: 'val', label: 'Val' };
    expect(expandFieldFromJson('null', field)).toBeNull();
  });
});

// ============================================================================
// safeGetArrayItems
// ============================================================================

describe('safeGetArrayItems', () => {
  it('should return the array when input is an array', () => {
    const arr = [{ id: 1 }, { id: 2 }];
    expect(safeGetArrayItems(arr)).toBe(arr); // same reference
  });

  it('should return empty array for null', () => {
    expect(safeGetArrayItems(null)).toEqual([]);
  });

  it('should return empty array for undefined', () => {
    expect(safeGetArrayItems(undefined)).toEqual([]);
  });

  it('should return empty array for a string (JSON string during transition)', () => {
    expect(safeGetArrayItems('[{"id":1}]')).toEqual([]);
  });

  it('should return empty array for a number', () => {
    expect(safeGetArrayItems(42)).toEqual([]);
  });

  it('should return empty array for an object', () => {
    expect(safeGetArrayItems({ key: 'val' })).toEqual([]);
  });

  it('should return empty array for boolean false', () => {
    expect(safeGetArrayItems(false)).toEqual([]);
  });

  it('should return the empty array when input is empty array', () => {
    const arr: any[] = [];
    expect(safeGetArrayItems(arr)).toBe(arr);
  });
});

// ============================================================================
// safeGetJsonString
// ============================================================================

describe('safeGetJsonString', () => {
  it('should return string value as-is', () => {
    expect(safeGetJsonString('{"key":"val"}')).toBe('{"key":"val"}');
  });

  it('should return empty string as-is', () => {
    expect(safeGetJsonString('')).toBe('');
  });

  it('should stringify an array', () => {
    expect(safeGetJsonString([1, 2, 3])).toBe(JSON.stringify([1, 2, 3], null, 2));
  });

  it('should stringify an object', () => {
    expect(safeGetJsonString({ a: 1 })).toBe(JSON.stringify({ a: 1 }, null, 2));
  });

  it('should return "[]" for null (default fallback)', () => {
    expect(safeGetJsonString(null)).toBe('[]');
  });

  it('should return "[]" for undefined (default fallback)', () => {
    expect(safeGetJsonString(undefined)).toBe('[]');
  });

  it('should stringify number 0', () => {
    expect(safeGetJsonString(0)).toBe('0');
  });

  it('should stringify false', () => {
    expect(safeGetJsonString(false)).toBe('false');
  });

  it('should handle nested objects', () => {
    const obj = { a: { b: [1, 2] } };
    expect(safeGetJsonString(obj)).toBe(JSON.stringify(obj, null, 2));
  });

  it('should handle empty array', () => {
    expect(safeGetJsonString([])).toBe('[]');
  });

  it('should handle empty object', () => {
    expect(safeGetJsonString({})).toBe('{}');
  });
});

// ============================================================================
// restoreCollapsedChildren (double-encoding prevention)
// ============================================================================
describe('restoreCollapsedChildren', () => {
  it('should parse string children back to objects under parent path', () => {
    const parentValue = {
      event_type: 'level_up',
      event_x2: '{\n  "type": "EventBodyX",\n  "good": "foo",\n  "great": 42\n}',
      description: 'test',
    };
    const prevCollapsedPaths = new Set(['payload.event_x2']);

    const restored = restoreCollapsedChildren(parentValue, 'payload', prevCollapsedPaths);

    expect(restored.event_x2).toEqual({ type: 'EventBodyX', good: 'foo', great: 42 });
    expect(restored.event_type).toBe('level_up');
    expect(restored.description).toBe('test');
  });

  it('should not mutate the original object', () => {
    const original = {
      child: '{"key":"val"}',
    };
    const prevPaths = new Set(['parent.child']);

    const restored = restoreCollapsedChildren(original, 'parent', prevPaths);

    expect(restored.child).toEqual({ key: 'val' });
    expect(original.child).toBe('{"key":"val"}'); // original unchanged
  });

  it('should handle multiple collapsed children', () => {
    const parentValue = {
      event_x: '{"good":"a","great":1}',
      event_x2: '{"good":"b","great":2}',
      name: 'test',
    };
    const prevPaths = new Set(['payload.event_x', 'payload.event_x2']);

    const restored = restoreCollapsedChildren(parentValue, 'payload', prevPaths);

    expect(restored.event_x).toEqual({ good: 'a', great: 1 });
    expect(restored.event_x2).toEqual({ good: 'b', great: 2 });
    expect(restored.name).toBe('test');
  });

  it('should ignore prevPaths not under parent', () => {
    const parentValue = {
      name: 'test',
    };
    const prevPaths = new Set(['other.child']);

    const restored = restoreCollapsedChildren(parentValue, 'payload', prevPaths);

    expect(restored).toEqual({ name: 'test' });
  });

  it('should skip non-string children (already objects)', () => {
    const parentValue = {
      event_x: { good: 'a', great: 1 },
    };
    const prevPaths = new Set(['payload.event_x']);

    const restored = restoreCollapsedChildren(parentValue, 'payload', prevPaths);

    expect(restored.event_x).toEqual({ good: 'a', great: 1 });
  });

  it('should handle invalid JSON strings gracefully', () => {
    const parentValue = {
      event_x: 'not valid json',
    };
    const prevPaths = new Set(['payload.event_x']);

    const restored = restoreCollapsedChildren(parentValue, 'payload', prevPaths);

    expect(restored.event_x).toBe('not valid json'); // unchanged
  });

  it('should return null/undefined as-is', () => {
    expect(restoreCollapsedChildren(null, 'p', new Set(['p.child']))).toBeNull();
    expect(restoreCollapsedChildren(undefined, 'p', new Set(['p.child']))).toBeUndefined();
  });
});

// ============================================================================
// computeDepthTransitionUpdates
// ============================================================================
describe('computeDepthTransitionUpdates', () => {
  it('should expand parent before collapsing children (depth 1→2)', () => {
    // Simulates: depth=1 had collapsedGroups=[{path:'payload'}]
    //            depth=2 has collapsedGroups=[{path:'payload.event_x2'},{path:'payload.event_x'}]
    const payloadJson = JSON.stringify({
      event_type: 'quest',
      character_name: 'Alice',
      event_x2: { type: 'EventBodyX', good: 'a', great: 'b' },
      event_x: { type: 'EventBodyX', good: 'c', great: 'd' },
      description: 'desc',
    });
    const formValues = { payload: payloadJson };
    const prevPaths = new Set(['payload']);
    const currCollapsedGroups = [
      { path: 'payload.event_x2', label: 'Event X2' },
      { path: 'payload.event_x', label: 'Event X' },
    ];
    const fields: ResourceFieldMinimal[] = []; // 'payload' is virtual ancestor, NOT in fields

    const updates = computeDepthTransitionUpdates(
      formValues,
      prevPaths,
      currCollapsedGroups,
      fields,
    );

    // Should expand payload first
    expect(updates.expands).toHaveLength(1);
    expect(updates.expands[0].path).toBe('payload');
    expect(updates.expands[0].value).toEqual({
      event_type: 'quest',
      character_name: 'Alice',
      event_x2: { type: 'EventBodyX', good: 'a', great: 'b' },
      event_x: { type: 'EventBodyX', good: 'c', great: 'd' },
      description: 'desc',
    });

    // Should collapse event_x2 and event_x
    expect(updates.collapses).toHaveLength(2);
    expect(updates.collapses[0].path).toBe('payload.event_x2');
    expect(JSON.parse(updates.collapses[0].value)).toEqual({
      type: 'EventBodyX',
      good: 'a',
      great: 'b',
    });
    expect(updates.collapses[1].path).toBe('payload.event_x');
    expect(JSON.parse(updates.collapses[1].value)).toEqual({
      type: 'EventBodyX',
      good: 'c',
      great: 'd',
    });
  });

  it('should collapse parent with restoreCollapsedChildren (depth 2→1)', () => {
    // depth=2 had collapsedGroups=[{path:'payload.event_x2'},{path:'payload.event_x'}]
    // depth=1 has collapsedGroups=[{path:'payload'}]
    const formValues = {
      payload: {
        event_type: 'quest',
        character_name: 'Alice',
        event_x2: '{"type":"EventBodyX","good":"a","great":"b"}', // already-collapsed string
        event_x: '{"type":"EventBodyX","good":"c","great":"d"}', // already-collapsed string
        description: 'desc',
      },
    };
    const prevPaths = new Set(['payload.event_x2', 'payload.event_x']);
    const currCollapsedGroups = [{ path: 'payload', label: 'Payload' }];
    const fields: ResourceFieldMinimal[] = [];

    const updates = computeDepthTransitionUpdates(
      formValues,
      prevPaths,
      currCollapsedGroups,
      fields,
    );

    // event_x2 and event_x were previously collapsed (strings) but no longer in currCollapsedGroups,
    // so they get expanded back to objects first
    expect(updates.expands).toHaveLength(2);
    expect(updates.expands.map((e) => e.path).sort()).toEqual([
      'payload.event_x',
      'payload.event_x2',
    ]);

    // Should collapse payload, with children already restored to objects by expansion
    expect(updates.collapses).toHaveLength(1);
    expect(updates.collapses[0].path).toBe('payload');
    const collapsed = JSON.parse(updates.collapses[0].value);
    expect(collapsed.event_type).toBe('quest');
    expect(collapsed.event_x2).toEqual({ type: 'EventBodyX', good: 'a', great: 'b' });
    expect(collapsed.event_x).toEqual({ type: 'EventBodyX', good: 'c', great: 'd' });
  });

  it('should return empty updates when nothing changed', () => {
    const formValues = { payload: '{"x":1}' };
    const prevPaths = new Set(['payload']);
    const currCollapsedGroups = [{ path: 'payload', label: 'Payload' }];
    const fields: ResourceFieldMinimal[] = [];

    const updates = computeDepthTransitionUpdates(
      formValues,
      prevPaths,
      currCollapsedGroups,
      fields,
    );

    expect(updates.expands).toHaveLength(0);
    expect(updates.collapses).toHaveLength(0);
  });

  it('should expand with field definition if available (with itemFields)', () => {
    const items = [{ id: 1, name: 'a', created: '2024-01-01' }];
    const formValues = { items: JSON.stringify(items) };
    const prevPaths = new Set(['items']);
    const currCollapsedGroups: { path: string; label: string }[] = [];
    const fields: ResourceFieldMinimal[] = [
      {
        name: 'items',
        label: 'Items',
        itemFields: [
          { name: 'id', label: 'ID', type: 'number' },
          { name: 'name', label: 'Name', type: 'string' },
          { name: 'created', label: 'Created', type: 'string' },
        ],
      },
    ];

    const updates = computeDepthTransitionUpdates(
      formValues,
      prevPaths,
      currCollapsedGroups,
      fields,
    );

    expect(updates.expands).toHaveLength(1);
    expect(updates.expands[0].path).toBe('items');
    // With itemFields, expandFieldFromJson processes sub-fields through handlers
    expect(updates.expands[0].value).toEqual([{ id: 1, name: 'a', created: '2024-01-01' }]);
  });

  it('should handle depth 3→2→1 multi-step without double encoding', () => {
    // At depth=2, payload.event_x2 is collapsed, payload isn't
    // Now going to depth=1: collapse payload, restore event_x2 from string
    const formValues = {
      payload: {
        name: 'test',
        event_x2: '{"good":"val"}', // already a string from depth=3→2
      },
    };
    const prevPaths = new Set(['payload.event_x2']);
    const currCollapsedGroups = [{ path: 'payload', label: 'Payload' }];
    const fields: ResourceFieldMinimal[] = [];

    const updates = computeDepthTransitionUpdates(
      formValues,
      prevPaths,
      currCollapsedGroups,
      fields,
    );

    expect(updates.collapses).toHaveLength(1);
    const collapsed = JSON.parse(updates.collapses[0].value);
    // event_x2 should be an object, not a double-encoded string
    expect(collapsed.event_x2).toEqual({ good: 'val' });
    expect(collapsed.name).toBe('test');
  });

  it('should skip expand when value is not a string', () => {
    // prevPath was collapsed but value is already an object (e.g., user manually mutated)
    const formValues = { payload: { name: 'test' } };
    const prevPaths = new Set(['payload']);
    const currCollapsedGroups: { path: string; label: string }[] = [];
    const fields: ResourceFieldMinimal[] = [];

    const updates = computeDepthTransitionUpdates(
      formValues,
      prevPaths,
      currCollapsedGroups,
      fields,
    );

    // No expand needed — already an object
    expect(updates.expands).toHaveLength(0);
  });

  it('should skip collapse when value is already a string', () => {
    // Currently-collapsed group is already a string (e.g., from stable state)
    const formValues = { payload: '{"name":"test"}' };
    const prevPaths = new Set(['payload']);
    const currCollapsedGroups = [{ path: 'payload', label: 'Payload' }];
    const fields: ResourceFieldMinimal[] = [];

    const updates = computeDepthTransitionUpdates(
      formValues,
      prevPaths,
      currCollapsedGroups,
      fields,
    );

    expect(updates.expands).toHaveLength(0);
    expect(updates.collapses).toHaveLength(0);
  });
});
