import { describe, it, expect, vi } from 'vitest';
import {
  collapseFieldToJson,
  expandFieldFromJson,
  safeGetArrayItems,
  safeGetJsonString,
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
