import { describe, expect, it } from 'vitest';
import { validateJsonFields, parseAndValidateJson, preprocessArrayFields } from './validators';

describe('validateJsonFields', () => {
  it('should return empty errors for valid JSON object', () => {
    const fields = [{ name: 'metadata', type: 'object' }];
    const values = { metadata: '{"key": "value"}' };

    const errors = validateJsonFields(values, fields, []);

    expect(errors).toEqual({});
  });

  it('should error on JSON array (not object)', () => {
    const fields = [{ name: 'metadata', type: 'object' }];
    const values = { metadata: '[1, 2, 3]' };

    const errors = validateJsonFields(values, fields, []);

    expect(errors).toEqual({
      metadata: 'Must be a JSON object (not array or primitive)',
    });
  });

  it('should error on JSON primitive', () => {
    const fields = [{ name: 'metadata', type: 'object' }];
    const values = { metadata: '"string"' };

    const errors = validateJsonFields(values, fields, []);

    expect(errors).toEqual({
      metadata: 'Must be a JSON object (not array or primitive)',
    });
  });

  it('should error on null JSON value', () => {
    const fields = [{ name: 'metadata', type: 'object' }];
    const values = { metadata: 'null' };

    const errors = validateJsonFields(values, fields, []);

    expect(errors).toEqual({
      metadata: 'Must be a JSON object (not array or primitive)',
    });
  });

  it('should error on invalid JSON syntax', () => {
    const fields = [{ name: 'metadata', type: 'object' }];
    const values = { metadata: '{invalid json}' };

    const errors = validateJsonFields(values, fields, []);

    expect(errors).toEqual({
      metadata: 'Invalid JSON format',
    });
  });

  it('should skip validation for empty string', () => {
    const fields = [{ name: 'metadata', type: 'object' }];
    const values = { metadata: '' };

    const errors = validateJsonFields(values, fields, []);

    expect(errors).toEqual({});
  });

  it('should skip validation for non-object type fields', () => {
    const fields = [{ name: 'name', type: 'string' }];
    const values = { name: 'invalid json {' };

    const errors = validateJsonFields(values, fields, []);

    expect(errors).toEqual({});
  });

  it('should skip validation for fields with itemFields', () => {
    const fields = [{ name: 'items', type: 'object', itemFields: [{ name: 'id' }] }];
    const values = { items: '[1, 2, 3]' }; // Would be error if validated

    const errors = validateJsonFields(values, fields, []);

    expect(errors).toEqual({});
  });

  it('should validate collapsed groups', () => {
    const fields = [{ name: 'user.name' }];
    const collapsedGroups = [{ path: 'user', label: 'User' }];
    const values = { user: '{invalid}' };

    const errors = validateJsonFields(values, fields, collapsedGroups);

    expect(errors).toEqual({
      user: 'Invalid JSON format',
    });
  });

  it('should validate multiple fields', () => {
    const fields = [
      { name: 'data1', type: 'object' },
      { name: 'data2', type: 'object' },
    ];
    const values = { data1: '[1,2]', data2: '{invalid}' };

    const errors = validateJsonFields(values, fields, []);

    expect(errors).toEqual({
      data1: 'Must be a JSON object (not array or primitive)',
      data2: 'Invalid JSON format',
    });
  });
});

describe('parseAndValidateJson', () => {
  it('should parse valid JSON object', () => {
    const result = parseAndValidateJson('{"name": "Alice", "age": 30}');

    expect(result).toEqual({
      success: true,
      data: { name: 'Alice', age: 30 },
    });
  });

  it('should reject JSON array', () => {
    const result = parseAndValidateJson('[1, 2, 3]');

    expect(result).toEqual({
      success: false,
      error: 'Must be a JSON object',
    });
  });

  it('should reject JSON primitive', () => {
    const result = parseAndValidateJson('"string"');

    expect(result).toEqual({
      success: false,
      error: 'Must be a JSON object',
    });
  });

  it('should reject JSON number', () => {
    const result = parseAndValidateJson('42');

    expect(result).toEqual({
      success: false,
      error: 'Must be a JSON object',
    });
  });

  it('should reject JSON null', () => {
    const result = parseAndValidateJson('null');

    expect(result).toEqual({
      success: false,
      error: 'Must be a JSON object',
    });
  });

  it('should reject invalid JSON syntax', () => {
    const result = parseAndValidateJson('{invalid json}');

    expect(result).toEqual({
      success: false,
      error: 'Invalid JSON format',
    });
  });

  it('should handle empty object', () => {
    const result = parseAndValidateJson('{}');

    expect(result).toEqual({
      success: true,
      data: {},
    });
  });

  it('should handle nested objects', () => {
    const result = parseAndValidateJson('{"user": {"name": "Bob"}}');

    expect(result).toEqual({
      success: true,
      data: { user: { name: 'Bob' } },
    });
  });
});

describe('preprocessArrayFields', () => {
  it('should convert comma-separated string to array for isArray fields', () => {
    const fields = [{ name: 'tags', isArray: true }];
    const values = { tags: 'a, b, c' };

    const result = preprocessArrayFields(values, fields);

    expect(result.tags).toEqual(['a', 'b', 'c']);
  });

  it('should filter empty strings from comma-separated', () => {
    const fields = [{ name: 'tags', isArray: true }];
    const values = { tags: 'a, , b, , c' };

    const result = preprocessArrayFields(values, fields);

    expect(result.tags).toEqual(['a', 'b', 'c']);
  });

  it('should trim whitespace from array elements', () => {
    const fields = [{ name: 'tags', isArray: true }];
    const values = { tags: '  a  ,  b  ,  c  ' };

    const result = preprocessArrayFields(values, fields);

    expect(result.tags).toEqual(['a', 'b', 'c']);
  });

  it('should handle empty comma-separated string', () => {
    const fields = [{ name: 'tags', isArray: true }];
    const values = { tags: '' };

    const result = preprocessArrayFields(values, fields);

    expect(result.tags).toEqual([]);
  });

  it('should skip array ref fields', () => {
    const fields = [{ name: 'tags', isArray: true, ref: { type: 'resource_id', resource: 'tag' } }];
    const values = { tags: ['a', 'b', 'c'] }; // Already array

    const result = preprocessArrayFields(values, fields);

    expect(result.tags).toEqual(['a', 'b', 'c']); // Not converted
  });

  it('should skip fields with itemFields', () => {
    const fields = [{ name: 'items', isArray: true, itemFields: [{ name: 'id' }] }];
    const values = { items: [{ id: 1 }, { id: 2 }] }; // Already array of objects

    const result = preprocessArrayFields(values, fields);

    expect(result.items).toEqual([{ id: 1 }, { id: 2 }]); // Not converted
  });

  it('should process nested array strings in itemFields', () => {
    const fields = [
      {
        name: 'items',
        itemFields: [{ name: 'id' }, { name: 'tags', isArray: true }],
      },
    ];
    const values = {
      items: [
        { id: 1, tags: 'a, b' },
        { id: 2, tags: 'c, d, e' },
      ],
    };

    const result = preprocessArrayFields(values, fields);

    expect(result.items).toEqual([
      { id: 1, tags: ['a', 'b'] },
      { id: 2, tags: ['c', 'd', 'e'] },
    ]);
  });

  it('should handle non-array values for isArray fields', () => {
    const fields = [{ name: 'tags', isArray: true }];
    const values = { tags: null };

    const result = preprocessArrayFields(values, fields);

    expect(result.tags).toBeNull(); // Keep as-is if not string
  });

  it('should handle multiple fields', () => {
    const fields = [
      { name: 'tags', isArray: true },
      { name: 'categories', isArray: true },
      { name: 'name', type: 'string' },
    ];
    const values = {
      tags: 'a, b',
      categories: 'x, y, z',
      name: 'Test',
    };

    const result = preprocessArrayFields(values, fields);

    expect(result).toEqual({
      tags: ['a', 'b'],
      categories: ['x', 'y', 'z'],
      name: 'Test',
    });
  });
});
