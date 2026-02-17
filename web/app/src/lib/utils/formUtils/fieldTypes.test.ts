import { describe, expect, it } from 'vitest';
import { inferDefaultVariant, inferSimpleUnionType, createEmptyItemForFields } from './fieldTypes';

describe('inferDefaultVariant', () => {
  it('should return select variant for fields with enumValues', () => {
    const field = { name: 'status', enumValues: ['active', 'inactive', 'pending'] };
    const variant = inferDefaultVariant(field);

    expect(variant.type).toBe('select');
    expect(variant).toHaveProperty('options');
    if (variant.type === 'select') {
      expect(variant.options).toHaveLength(3);
      expect(variant.options?.[0]).toEqual({ value: 'active', label: 'active' });
    }
  });

  it('should return number variant for number type', () => {
    const field = { name: 'age', type: 'number' as const };
    const variant = inferDefaultVariant(field);

    expect(variant).toEqual({ type: 'number' });
  });

  it('should return switch variant for boolean type', () => {
    const field = { name: 'active', type: 'boolean' as const };
    const variant = inferDefaultVariant(field);

    expect(variant).toEqual({ type: 'switch' });
  });

  it('should return date variant for date type', () => {
    const field = { name: 'created_at', type: 'date' as const };
    const variant = inferDefaultVariant(field);

    expect(variant).toEqual({ type: 'date' });
  });

  it('should return file variant for binary type', () => {
    const field = { name: 'avatar', type: 'binary' as const };
    const variant = inferDefaultVariant(field);

    expect(variant).toEqual({ type: 'file' });
  });

  it('should return json variant for object type', () => {
    const field = { name: 'metadata', type: 'object' as const };
    const variant = inferDefaultVariant(field);

    expect(variant).toEqual({ type: 'json' });
  });

  it('should return array variant for array fields', () => {
    const field = { name: 'tags', isArray: true };
    const variant = inferDefaultVariant(field);

    expect(variant.type).toBe('array');
    if (variant.type === 'array') {
      expect(variant.itemType).toBe('text');
    }
  });

  it('should return text variant as default', () => {
    const field = { name: 'name' };
    const variant = inferDefaultVariant(field);

    expect(variant).toEqual({ type: 'text' });
  });

  it('should prioritize enumValues over type', () => {
    const field = { name: 'status', type: 'string' as const, enumValues: ['a', 'b'] };
    const variant = inferDefaultVariant(field);

    expect(variant.type).toBe('select');
  });

  it('should handle empty enumValues array', () => {
    const field = { name: 'status', enumValues: [] };
    const variant = inferDefaultVariant(field);

    // With empty array, should fall back to default text
    expect(variant).toEqual({ type: 'text' });
  });

  it('should handle string type explicitly', () => {
    const field = { name: 'description', type: 'string' as const };
    const variant = inferDefaultVariant(field);

    expect(variant).toEqual({ type: 'text' });
  });
});

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

describe('createEmptyItemForFields', () => {
  it('should create empty item with default values for all field types', () => {
    const itemFields = [
      { name: 'name', type: 'string' as const },
      { name: 'age', type: 'number' as const },
      { name: 'active', type: 'boolean' as const },
      { name: 'metadata', type: 'object' as const },
    ];

    const item = createEmptyItemForFields(itemFields);

    expect(item).toEqual({
      name: '',
      age: '',
      active: false,
      metadata: '',
    });
  });

  it('should create BinaryFormValue for binary fields', () => {
    const itemFields = [{ name: 'avatar', type: 'binary' as const }];

    const item = createEmptyItemForFields(itemFields);

    expect(item.avatar).toEqual({ _mode: 'empty' });
  });

  it('should use first enum value for non-nullable enum fields', () => {
    const itemFields = [{ name: 'status', enumValues: ['active', 'inactive'], isNullable: false }];

    const item = createEmptyItemForFields(itemFields);

    expect(item.status).toBe('active');
  });

  it('should use null for nullable enum fields', () => {
    const itemFields = [{ name: 'status', enumValues: ['active', 'inactive'], isNullable: true }];

    const item = createEmptyItemForFields(itemFields);

    expect(item.status).toBeNull();
  });

  it('should handle fields without explicit type', () => {
    const itemFields = [{ name: 'field1' }, { name: 'field2' }];

    const item = createEmptyItemForFields(itemFields);

    expect(item).toEqual({
      field1: '',
      field2: '',
    });
  });

  it('should handle empty itemFields array', () => {
    const item = createEmptyItemForFields([]);

    expect(item).toEqual({});
  });

  it('should handle mixed field types', () => {
    const itemFields = [
      { name: 'id', type: 'number' as const },
      { name: 'name', type: 'string' as const },
      { name: 'enabled', type: 'boolean' as const },
      { name: 'category', enumValues: ['A', 'B', 'C'], isNullable: false },
      { name: 'image', type: 'binary' as const },
      { name: 'config', type: 'object' as const },
    ];

    const item = createEmptyItemForFields(itemFields);

    expect(item).toEqual({
      id: '',
      name: '',
      enabled: false,
      category: 'A',
      image: { _mode: 'empty' },
      config: '',
    });
  });

  it('should handle enum with empty array', () => {
    const itemFields = [{ name: 'status', enumValues: [], isNullable: false }];

    const item = createEmptyItemForFields(itemFields);

    // Empty enum array should fall back to empty string
    expect(item.status).toBe('');
  });
});
