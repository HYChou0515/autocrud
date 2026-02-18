/**
 * Tests for Field Type Registry
 *
 * Covers:
 * - All 8 built-in handlers (string, number, boolean, date, object, binary, union, array)
 * - Each handler method (defaultVariant, emptyValue, toFormValue, toApiValue, fromJsonValue, submitValue, validate)
 * - Registry functions (getHandler, registerFieldType, getDefaultVariant, getEmptyValue)
 * - Custom type registration
 */

import { describe, it, expect, afterEach } from 'vitest';
import {
  getHandler,
  registerFieldType,
  getDefaultVariant,
  getEmptyValue,
  inferSimpleUnionType,
  stringHandler,
  numberHandler,
  booleanHandler,
  dateHandler,
  objectHandler,
  binaryHandler,
  unionHandler,
  arrayHandler,
  type FieldTypeHandler,
  type ResourceFieldMinimal,
} from './fieldTypeRegistry';

// ============================================================================
// Helper: create a minimal field
// ============================================================================
function field(overrides: Partial<ResourceFieldMinimal> = {}): ResourceFieldMinimal {
  return { name: 'test', ...overrides };
}

// ============================================================================
// Registry Functions
// ============================================================================
describe('Registry Functions', () => {
  describe('getHandler', () => {
    it('returns stringHandler for undefined type', () => {
      expect(getHandler(undefined)).toBe(stringHandler);
    });

    it('returns stringHandler for "string" type', () => {
      expect(getHandler('string')).toBe(stringHandler);
    });

    it('returns numberHandler for "number" type', () => {
      expect(getHandler('number')).toBe(numberHandler);
    });

    it('returns booleanHandler for "boolean" type', () => {
      expect(getHandler('boolean')).toBe(booleanHandler);
    });

    it('returns dateHandler for "date" type', () => {
      expect(getHandler('date')).toBe(dateHandler);
    });

    it('returns objectHandler for "object" type', () => {
      expect(getHandler('object')).toBe(objectHandler);
    });

    it('returns binaryHandler for "binary" type', () => {
      expect(getHandler('binary')).toBe(binaryHandler);
    });

    it('returns unionHandler for "union" type', () => {
      expect(getHandler('union')).toBe(unionHandler);
    });

    it('returns arrayHandler for "array" type', () => {
      expect(getHandler('array')).toBe(arrayHandler);
    });

    it('falls back to stringHandler for unknown type', () => {
      expect(getHandler('unknown_xyz')).toBe(stringHandler);
    });
  });

  describe('registerFieldType', () => {
    const customHandler: FieldTypeHandler = {
      defaultVariant: () => ({ type: 'text' }),
      emptyValue: () => 'custom_default',
      toFormValue: (val) => val ?? 'custom_default',
      toApiValue: (val) => val,
      fromJsonValue: (val) => val ?? 'custom_default',
    };

    afterEach(() => {
      // Clean up: re-register to avoid test pollution
      // (The registry is a module singleton, so we need to be careful)
    });

    it('registers a new custom type', () => {
      registerFieldType('email', customHandler);
      expect(getHandler('email')).toBe(customHandler);
      // Clean up
      registerFieldType('email', stringHandler);
    });

    it('custom handler methods work correctly', () => {
      registerFieldType('custom_test', customHandler);
      const handler = getHandler('custom_test');
      expect(handler.emptyValue(field())).toBe('custom_default');
      expect(handler.toFormValue(null, field())).toBe('custom_default');
      expect(handler.fromJsonValue(undefined, field())).toBe('custom_default');
      // Clean up
      registerFieldType('custom_test', stringHandler);
    });

    it('can override a built-in type', () => {
      const originalNumber = getHandler('number');
      registerFieldType('number', customHandler);
      expect(getHandler('number')).toBe(customHandler);
      // Restore
      registerFieldType('number', originalNumber);
    });
  });

  describe('getDefaultVariant', () => {
    it('returns select for fields with enumValues', () => {
      const result = getDefaultVariant(field({ enumValues: ['a', 'b', 'c'] }));
      expect(result).toEqual({
        type: 'select',
        options: [
          { value: 'a', label: 'a' },
          { value: 'b', label: 'b' },
          { value: 'c', label: 'c' },
        ],
      });
    });

    it('delegates to handler for non-enum fields', () => {
      expect(getDefaultVariant(field({ type: 'number' }))).toEqual({ type: 'number' });
      expect(getDefaultVariant(field({ type: 'boolean' }))).toEqual({ type: 'switch' });
    });
  });

  describe('getEmptyValue', () => {
    it('returns null for nullable enum fields', () => {
      expect(getEmptyValue(field({ enumValues: ['a'], isNullable: true }))).toBe(null);
    });

    it('returns first enum value for required enum fields', () => {
      expect(getEmptyValue(field({ enumValues: ['a', 'b'] }))).toBe('a');
    });

    it('returns empty string for empty enumValues with required', () => {
      expect(getEmptyValue(field({ enumValues: [] }))).toBe('');
    });

    it('delegates to handler for non-enum fields', () => {
      expect(getEmptyValue(field({ type: 'boolean' }))).toBe(false);
      expect(getEmptyValue(field({ type: 'number' }))).toBe('');
    });
  });
});

// ============================================================================
// String Handler
// ============================================================================
describe('stringHandler', () => {
  describe('defaultVariant', () => {
    it('returns text for regular string', () => {
      expect(stringHandler.defaultVariant(field())).toEqual({ type: 'text' });
    });

    it('returns array for isArray string', () => {
      expect(stringHandler.defaultVariant(field({ isArray: true }))).toEqual({
        type: 'array',
        itemType: 'text',
      });
    });
  });

  describe('emptyValue', () => {
    it('returns empty string', () => {
      expect(stringHandler.emptyValue(field())).toBe('');
    });
  });

  describe('toFormValue', () => {
    it('returns empty string for null', () => {
      expect(stringHandler.toFormValue(null, field())).toBe('');
    });

    it('returns empty string for undefined', () => {
      expect(stringHandler.toFormValue(undefined, field())).toBe('');
    });

    it('returns null for null with enum values', () => {
      expect(stringHandler.toFormValue(null, field({ enumValues: ['a'] }))).toBe(null);
    });

    it('returns the value as-is for non-null', () => {
      expect(stringHandler.toFormValue('hello', field())).toBe('hello');
    });

    it('joins array to comma-separated string for isArray', () => {
      expect(stringHandler.toFormValue(['a', 'b', 'c'], field({ isArray: true }))).toBe('a, b, c');
    });

    it('handles empty array for isArray', () => {
      expect(stringHandler.toFormValue([], field({ isArray: true }))).toBe('');
    });
  });

  describe('toApiValue', () => {
    it('returns value as-is for regular string', () => {
      expect(stringHandler.toApiValue('hello', field())).toBe('hello');
    });

    it('returns null for empty string with nullable', () => {
      expect(stringHandler.toApiValue('', field({ isNullable: true }))).toBe(null);
    });

    it('returns empty string for empty string without nullable', () => {
      expect(stringHandler.toApiValue('', field())).toBe('');
    });

    it('splits comma-separated string for isArray', () => {
      expect(stringHandler.toApiValue('a, b, c', field({ isArray: true }))).toEqual([
        'a',
        'b',
        'c',
      ]);
    });

    it('returns empty array for empty string isArray', () => {
      expect(stringHandler.toApiValue('', field({ isArray: true }))).toEqual([]);
    });

    it('returns array as-is for isArray when value is already array', () => {
      expect(stringHandler.toApiValue(['a', 'b'], field({ isArray: true }))).toEqual(['a', 'b']);
    });

    it('returns empty array for non-string non-array isArray', () => {
      expect(stringHandler.toApiValue(42, field({ isArray: true }))).toEqual([]);
    });

    it('returns null for empty enum value with nullable', () => {
      expect(stringHandler.toApiValue('', field({ enumValues: ['a'], isNullable: true }))).toBe(
        null,
      );
    });

    it('returns undefined for empty enum value without nullable', () => {
      expect(stringHandler.toApiValue('', field({ enumValues: ['a'] }))).toBe(undefined);
    });

    it('returns null for null enum value with nullable', () => {
      expect(stringHandler.toApiValue(null, field({ enumValues: ['a'], isNullable: true }))).toBe(
        null,
      );
    });
  });

  describe('fromJsonValue', () => {
    it('returns value for non-null', () => {
      expect(stringHandler.fromJsonValue('hello', field())).toBe('hello');
    });

    it('returns empty string for null', () => {
      expect(stringHandler.fromJsonValue(null, field())).toBe('');
    });

    it('returns empty string for undefined', () => {
      expect(stringHandler.fromJsonValue(undefined, field())).toBe('');
    });

    it('joins array to comma-separated for isArray', () => {
      expect(stringHandler.fromJsonValue(['x', 'y'], field({ isArray: true }))).toBe('x, y');
    });

    it('returns value for non-array isArray', () => {
      expect(stringHandler.fromJsonValue('not_array', field({ isArray: true }))).toBe('not_array');
    });
  });
});

// ============================================================================
// Number Handler
// ============================================================================
describe('numberHandler', () => {
  describe('defaultVariant', () => {
    it('returns number variant', () => {
      expect(numberHandler.defaultVariant(field())).toEqual({ type: 'number' });
    });
  });

  describe('emptyValue', () => {
    it('returns empty string', () => {
      expect(numberHandler.emptyValue(field())).toBe('');
    });
  });

  describe('toFormValue', () => {
    it('returns empty string for null', () => {
      expect(numberHandler.toFormValue(null, field())).toBe('');
    });

    it('returns null for null with enum values', () => {
      expect(numberHandler.toFormValue(null, field({ enumValues: ['1'] }))).toBe(null);
    });

    it('returns value for non-null', () => {
      expect(numberHandler.toFormValue(42, field())).toBe(42);
    });
  });

  describe('toApiValue', () => {
    it('returns null for empty string with nullable', () => {
      expect(numberHandler.toApiValue('', field({ isNullable: true }))).toBe(null);
    });

    it('returns undefined for empty string without nullable', () => {
      expect(numberHandler.toApiValue('', field())).toBe(undefined);
    });

    it('returns null for undefined with nullable', () => {
      expect(numberHandler.toApiValue(undefined, field({ isNullable: true }))).toBe(null);
    });

    it('returns value as-is for numbers', () => {
      expect(numberHandler.toApiValue(42, field())).toBe(42);
    });

    it('handles enum empty value with nullable', () => {
      expect(numberHandler.toApiValue('', field({ enumValues: ['1'], isNullable: true }))).toBe(
        null,
      );
    });

    it('handles enum empty value without nullable', () => {
      expect(numberHandler.toApiValue('', field({ enumValues: ['1'] }))).toBe(undefined);
    });
  });

  describe('fromJsonValue', () => {
    it('returns value for non-null', () => {
      expect(numberHandler.fromJsonValue(42, field())).toBe(42);
    });

    it('returns empty string for null', () => {
      expect(numberHandler.fromJsonValue(null, field())).toBe('');
    });
  });
});

// ============================================================================
// Boolean Handler
// ============================================================================
describe('booleanHandler', () => {
  describe('defaultVariant', () => {
    it('returns switch variant', () => {
      expect(booleanHandler.defaultVariant(field())).toEqual({ type: 'switch' });
    });
  });

  describe('emptyValue', () => {
    it('returns false', () => {
      expect(booleanHandler.emptyValue(field())).toBe(false);
    });
  });

  describe('toFormValue', () => {
    it('returns false for null', () => {
      expect(booleanHandler.toFormValue(null, field())).toBe(false);
    });

    it('returns false for undefined', () => {
      expect(booleanHandler.toFormValue(undefined, field())).toBe(false);
    });

    it('returns true for true', () => {
      expect(booleanHandler.toFormValue(true, field())).toBe(true);
    });

    it('returns false for false', () => {
      expect(booleanHandler.toFormValue(false, field())).toBe(false);
    });
  });

  describe('toApiValue', () => {
    it('passes through boolean values', () => {
      expect(booleanHandler.toApiValue(true, field())).toBe(true);
      expect(booleanHandler.toApiValue(false, field())).toBe(false);
    });
  });

  describe('fromJsonValue', () => {
    it('returns false for null', () => {
      expect(booleanHandler.fromJsonValue(null, field())).toBe(false);
    });

    it('returns the value for non-null', () => {
      expect(booleanHandler.fromJsonValue(true, field())).toBe(true);
    });
  });
});

// ============================================================================
// Date Handler
// ============================================================================
describe('dateHandler', () => {
  describe('defaultVariant', () => {
    it('returns date variant', () => {
      expect(dateHandler.defaultVariant(field())).toEqual({ type: 'date' });
    });
  });

  describe('emptyValue', () => {
    it('returns null', () => {
      expect(dateHandler.emptyValue(field())).toBe(null);
    });
  });

  describe('toFormValue', () => {
    it('converts ISO string to Date', () => {
      const result = dateHandler.toFormValue('2024-01-15T10:30:00.000Z', field());
      expect(result).toBeInstanceOf(Date);
      expect((result as Date).toISOString()).toBe('2024-01-15T10:30:00.000Z');
    });

    it('returns null for null', () => {
      expect(dateHandler.toFormValue(null, field())).toBe(null);
    });

    it('returns null for undefined', () => {
      expect(dateHandler.toFormValue(undefined, field())).toBe(null);
    });

    it('returns empty string as-is (falsy non-null)', () => {
      expect(dateHandler.toFormValue('', field())).toBe('');
    });

    it('returns Date as-is if already Date', () => {
      const d = new Date('2024-01-15');
      expect(dateHandler.toFormValue(d, field())).toBe(d);
    });
  });

  describe('toApiValue', () => {
    it('converts Date to ISO string', () => {
      const d = new Date('2024-01-15T10:30:00.000Z');
      expect(dateHandler.toApiValue(d, field())).toBe('2024-01-15T10:30:00.000Z');
    });

    it('converts valid date string to ISO', () => {
      const result = dateHandler.toApiValue('2024-01-15T10:30:00.000Z', field());
      expect(result).toBe('2024-01-15T10:30:00.000Z');
    });

    it('returns invalid date string as-is', () => {
      expect(dateHandler.toApiValue('not-a-date', field())).toBe('not-a-date');
    });

    it('returns null for null', () => {
      expect(dateHandler.toApiValue(null, field())).toBe(null);
    });

    it('returns null for empty string', () => {
      expect(dateHandler.toApiValue('', field())).toBe(null);
    });
  });

  describe('fromJsonValue', () => {
    it('converts valid ISO string to Date', () => {
      const result = dateHandler.fromJsonValue('2024-01-15T10:30:00.000Z', field());
      expect(result).toBeInstanceOf(Date);
    });

    it('returns null for invalid date string', () => {
      expect(dateHandler.fromJsonValue('not-a-date', field())).toBe(null);
    });

    it('returns null for null', () => {
      expect(dateHandler.fromJsonValue(null, field())).toBe(null);
    });

    it('returns null for empty string', () => {
      expect(dateHandler.fromJsonValue('', field())).toBe(null);
    });
  });

  describe('submitValue', () => {
    it('converts Date to ISO string', () => {
      const d = new Date('2024-01-15T10:30:00.000Z');
      expect(dateHandler.submitValue!(d, field())).toBe('2024-01-15T10:30:00.000Z');
    });

    it('converts valid date string to ISO', () => {
      const result = dateHandler.submitValue!('2024-01-15T10:30:00.000Z', field());
      expect(result).toBe('2024-01-15T10:30:00.000Z');
    });

    it('returns value as-is for invalid date string', () => {
      expect(dateHandler.submitValue!('not-a-date', field())).toBe('not-a-date');
    });

    it('returns value as-is for null (no Date, no string)', () => {
      expect(dateHandler.submitValue!(null, field())).toBe(null);
    });

    it('returns value as-is for empty string', () => {
      expect(dateHandler.submitValue!('', field())).toBe('');
    });
  });
});

// ============================================================================
// Object Handler
// ============================================================================
describe('objectHandler', () => {
  describe('defaultVariant', () => {
    it('returns json variant', () => {
      expect(objectHandler.defaultVariant(field())).toEqual({ type: 'json' });
    });
  });

  describe('emptyValue', () => {
    it('returns empty string', () => {
      expect(objectHandler.emptyValue(field())).toBe('');
    });
  });

  describe('toFormValue', () => {
    it('returns empty string for null', () => {
      expect(objectHandler.toFormValue(null, field())).toBe('');
    });

    it('serializes object to JSON string', () => {
      const result = objectHandler.toFormValue({ a: 1, b: 2 }, field());
      expect(JSON.parse(result)).toEqual({ a: 1, b: 2 });
    });

    it('returns non-object value as-is', () => {
      expect(objectHandler.toFormValue('already-string', field())).toBe('already-string');
    });
  });

  describe('toApiValue', () => {
    it('parses valid JSON string', () => {
      expect(objectHandler.toApiValue('{"a": 1}', field())).toEqual({ a: 1 });
    });

    it('returns original string for invalid JSON', () => {
      expect(objectHandler.toApiValue('{invalid}', field())).toBe('{invalid}');
    });

    it('returns null for empty string', () => {
      expect(objectHandler.toApiValue('', field())).toBe(null);
    });

    it('returns null for whitespace-only string', () => {
      expect(objectHandler.toApiValue('   ', field())).toBe(null);
    });

    it('returns null for null', () => {
      expect(objectHandler.toApiValue(null, field())).toBe(null);
    });

    it('returns null for non-string non-null', () => {
      expect(objectHandler.toApiValue(42, field())).toBe(null);
    });
  });

  describe('fromJsonValue', () => {
    it('serializes object to JSON string', () => {
      const result = objectHandler.fromJsonValue({ x: 1 }, field());
      expect(JSON.parse(result)).toEqual({ x: 1 });
    });

    it('returns empty string for null', () => {
      expect(objectHandler.fromJsonValue(null, field())).toBe('');
    });

    it('returns empty string for undefined', () => {
      expect(objectHandler.fromJsonValue(undefined, field())).toBe('');
    });

    it('returns empty string for non-object value', () => {
      expect(objectHandler.fromJsonValue('string', field())).toBe('');
    });
  });

  describe('submitValue', () => {
    it('parses valid JSON string', () => {
      expect(objectHandler.submitValue!('{"key": "val"}', field())).toEqual({ key: 'val' });
    });

    it('returns string as-is for invalid JSON', () => {
      expect(objectHandler.submitValue!('{bad}', field())).toBe('{bad}');
    });

    it('returns null for empty string', () => {
      expect(objectHandler.submitValue!('', field())).toBe(null);
    });

    it('returns null for whitespace string', () => {
      expect(objectHandler.submitValue!('  ', field())).toBe(null);
    });

    it('returns non-string value as-is', () => {
      expect(objectHandler.submitValue!(42, field())).toBe(42);
    });

    it('returns null as-is', () => {
      expect(objectHandler.submitValue!(null, field())).toBe(null);
    });
  });

  describe('validate', () => {
    it('returns null for valid JSON object', () => {
      expect(objectHandler.validate!('{"a": 1}', field())).toBe(null);
    });

    it('returns error for JSON array', () => {
      expect(objectHandler.validate!('[1, 2]', field())).toBe(
        'Must be a JSON object (not array or primitive)',
      );
    });

    it('returns error for JSON primitive', () => {
      expect(objectHandler.validate!('"string"', field())).toBe(
        'Must be a JSON object (not array or primitive)',
      );
    });

    it('returns error for JSON null', () => {
      expect(objectHandler.validate!('null', field())).toBe(
        'Must be a JSON object (not array or primitive)',
      );
    });

    it('returns error for invalid JSON', () => {
      expect(objectHandler.validate!('{bad}', field())).toBe('Invalid JSON format');
    });

    it('returns null for empty string', () => {
      expect(objectHandler.validate!('', field())).toBe(null);
    });

    it('returns null for whitespace string', () => {
      expect(objectHandler.validate!('   ', field())).toBe(null);
    });

    it('returns null for non-string value', () => {
      expect(objectHandler.validate!(42, field())).toBe(null);
    });
  });
});

// ============================================================================
// Binary Handler
// ============================================================================
describe('binaryHandler', () => {
  describe('defaultVariant', () => {
    it('returns file variant', () => {
      expect(binaryHandler.defaultVariant(field())).toEqual({ type: 'file' });
    });
  });

  describe('emptyValue', () => {
    it('returns BinaryFormValue with _mode empty', () => {
      expect(binaryHandler.emptyValue(field())).toEqual({ _mode: 'empty' });
    });

    it('returns a new object each time', () => {
      const a = binaryHandler.emptyValue(field());
      const b = binaryHandler.emptyValue(field());
      expect(a).not.toBe(b);
      expect(a).toEqual(b);
    });
  });

  describe('toFormValue', () => {
    it('converts existing binary data to BinaryFormValue', () => {
      const apiVal = { file_id: 'abc123', content_type: 'image/png', size: 1024 };
      expect(binaryHandler.toFormValue(apiVal, field())).toEqual({
        _mode: 'existing',
        file_id: 'abc123',
        content_type: 'image/png',
        size: 1024,
      });
    });

    it('returns empty BinaryFormValue for null', () => {
      expect(binaryHandler.toFormValue(null, field())).toEqual({ _mode: 'empty' });
    });

    it('returns empty BinaryFormValue for undefined', () => {
      expect(binaryHandler.toFormValue(undefined, field())).toEqual({ _mode: 'empty' });
    });

    it('returns empty BinaryFormValue for object without file_id', () => {
      expect(binaryHandler.toFormValue({ no_file_id: true }, field())).toEqual({ _mode: 'empty' });
    });
  });

  describe('toApiValue', () => {
    it('converts existing BinaryFormValue', () => {
      const bv = {
        _mode: 'existing' as const,
        file_id: 'abc',
        content_type: 'text/plain',
        size: 100,
      };
      expect(binaryHandler.toApiValue(bv, field())).toEqual({
        file_id: 'abc',
        content_type: 'text/plain',
        size: 100,
      });
    });

    it('converts file BinaryFormValue', () => {
      const mockFile = { name: 'test.txt', type: 'text/plain' } as File;
      const bv = { _mode: 'file' as const, file: mockFile };
      expect(binaryHandler.toApiValue(bv, field())).toEqual({
        _pending_file: 'test.txt',
        content_type: 'text/plain',
      });
    });

    it('converts url BinaryFormValue', () => {
      const bv = { _mode: 'url' as const, url: 'https://example.com/img.png' };
      expect(binaryHandler.toApiValue(bv, field())).toEqual({
        _pending_url: 'https://example.com/img.png',
      });
    });

    it('returns null for empty BinaryFormValue', () => {
      expect(binaryHandler.toApiValue({ _mode: 'empty' }, field())).toBe(null);
    });

    it('returns null for null', () => {
      expect(binaryHandler.toApiValue(null, field())).toBe(null);
    });
  });

  describe('fromJsonValue', () => {
    it('converts existing binary data', () => {
      const val = { file_id: 'xyz', content_type: 'image/jpeg', size: 2048 };
      expect(binaryHandler.fromJsonValue(val, field())).toEqual({
        _mode: 'existing',
        file_id: 'xyz',
        content_type: 'image/jpeg',
        size: 2048,
      });
    });

    it('returns empty for null', () => {
      expect(binaryHandler.fromJsonValue(null, field())).toEqual({ _mode: 'empty' });
    });

    it('returns empty for object without file_id', () => {
      expect(binaryHandler.fromJsonValue({ other: 'data' }, field())).toEqual({ _mode: 'empty' });
    });
  });
});

// ============================================================================
// Union Handler
// ============================================================================
describe('unionHandler', () => {
  describe('defaultVariant', () => {
    it('returns union variant', () => {
      expect(unionHandler.defaultVariant(field())).toEqual({ type: 'union' });
    });
  });

  describe('emptyValue', () => {
    it('returns null', () => {
      expect(unionHandler.emptyValue(field())).toBe(null);
    });
  });

  describe('toFormValue', () => {
    it('passes through value', () => {
      const complexVal = { type: 'fire', damage: 10 };
      expect(unionHandler.toFormValue(complexVal, field())).toBe(complexVal);
    });

    it('passes through null', () => {
      expect(unionHandler.toFormValue(null, field())).toBe(null);
    });
  });

  describe('toApiValue', () => {
    it('passes through value', () => {
      const val = { type: 'ice', power: 5 };
      expect(unionHandler.toApiValue(val, field())).toBe(val);
    });
  });

  describe('fromJsonValue', () => {
    it('returns value for non-null', () => {
      const val = { type: 'thunder' };
      expect(unionHandler.fromJsonValue(val, field())).toBe(val);
    });

    it('returns null for null', () => {
      expect(unionHandler.fromJsonValue(null, field())).toBe(null);
    });

    it('returns null for undefined', () => {
      expect(unionHandler.fromJsonValue(undefined, field())).toBe(null);
    });
  });
});

// ============================================================================
// Array Handler
// ============================================================================
describe('arrayHandler', () => {
  describe('defaultVariant', () => {
    it('returns array variant', () => {
      expect(arrayHandler.defaultVariant(field())).toEqual({ type: 'array', itemType: 'text' });
    });
  });

  describe('emptyValue', () => {
    it('returns empty array', () => {
      expect(arrayHandler.emptyValue(field())).toEqual([]);
    });

    it('returns a new array each time', () => {
      const a = arrayHandler.emptyValue(field());
      const b = arrayHandler.emptyValue(field());
      expect(a).not.toBe(b);
    });
  });

  describe('toFormValue', () => {
    it('returns array as-is', () => {
      expect(arrayHandler.toFormValue([1, 2, 3], field())).toEqual([1, 2, 3]);
    });

    it('returns empty array for non-array', () => {
      expect(arrayHandler.toFormValue('not-array', field())).toEqual([]);
    });

    it('returns empty array for null', () => {
      expect(arrayHandler.toFormValue(null, field())).toEqual([]);
    });
  });

  describe('toApiValue', () => {
    it('passes through value', () => {
      const val = [1, 2, 3];
      expect(arrayHandler.toApiValue(val, field())).toBe(val);
    });
  });

  describe('fromJsonValue', () => {
    it('returns array as-is', () => {
      expect(arrayHandler.fromJsonValue([1, 2], field())).toEqual([1, 2]);
    });

    it('returns empty array for non-array', () => {
      expect(arrayHandler.fromJsonValue(null, field())).toEqual([]);
    });
  });
});

// ============================================================================
// inferSimpleUnionType
// ============================================================================
describe('inferSimpleUnionType', () => {
  it('should infer number type', () => {
    expect(inferSimpleUnionType(42)).toBe('number');
    expect(inferSimpleUnionType(0)).toBe('number');
    expect(inferSimpleUnionType(-10)).toBe('number');
    expect(inferSimpleUnionType(3.14)).toBe('number');
  });

  it('should infer boolean type', () => {
    expect(inferSimpleUnionType(true)).toBe('boolean');
    expect(inferSimpleUnionType(false)).toBe('boolean');
  });

  it('should infer string type for string values', () => {
    expect(inferSimpleUnionType('hello')).toBe('string');
    expect(inferSimpleUnionType('123')).toBe('string');
    expect(inferSimpleUnionType('true')).toBe('string');
  });

  it('should default to string for null', () => {
    expect(inferSimpleUnionType(null)).toBe('string');
  });

  it('should default to string for undefined', () => {
    expect(inferSimpleUnionType(undefined)).toBe('string');
  });

  it('should default to string for empty string', () => {
    expect(inferSimpleUnionType('')).toBe('string');
  });

  it('should infer string for objects', () => {
    expect(inferSimpleUnionType({})).toBe('string');
    expect(inferSimpleUnionType({ key: 'value' })).toBe('string');
  });

  it('should infer string for arrays', () => {
    expect(inferSimpleUnionType([])).toBe('string');
    expect(inferSimpleUnionType([1, 2, 3])).toBe('string');
  });
});

// ============================================================================
// Integration: Handler dispatch via getHandler
// ============================================================================
describe('Handler dispatch integration', () => {
  it('processes a form field lifecycle through handler', () => {
    // Simulate: API value → form value → API value (round-trip)
    const f = field({ type: 'object', name: 'metadata' });
    const handler = getHandler(f.type);

    // API → form
    const apiData = { key: 'value', nested: { x: 1 } };
    const formVal = handler.toFormValue(apiData, f);
    expect(typeof formVal).toBe('string');
    expect(JSON.parse(formVal)).toEqual(apiData);

    // form → API
    const apiVal = handler.toApiValue(formVal, f);
    expect(apiVal).toEqual(apiData);
  });

  it('handles date round-trip', () => {
    const f = field({ type: 'date', name: 'created' });
    const handler = getHandler(f.type);

    const isoStr = '2024-06-15T10:30:00.000Z';
    const formVal = handler.toFormValue(isoStr, f);
    expect(formVal).toBeInstanceOf(Date);

    const apiVal = handler.toApiValue(formVal, f);
    expect(apiVal).toBe(isoStr);
  });

  it('handles binary round-trip', () => {
    const f = field({ type: 'binary', name: 'avatar' });
    const handler = getHandler(f.type);

    const apiData = { file_id: 'hash123', content_type: 'image/png', size: 4096 };
    const formVal = handler.toFormValue(apiData, f);
    expect(formVal).toEqual({ _mode: 'existing', ...apiData });

    const apiVal = handler.toApiValue(formVal, f);
    expect(apiVal).toEqual(apiData);
  });

  it('handles nullable string correctly', () => {
    const f = field({ type: 'string', name: 'nickname', isNullable: true });
    const handler = getHandler(f.type);

    // null → '' (form)
    expect(handler.toFormValue(null, f)).toBe('');
    // '' → null (API, nullable)
    expect(handler.toApiValue('', f)).toBe(null);
    // non-empty → as-is
    expect(handler.toApiValue('alice', f)).toBe('alice');
  });
});
