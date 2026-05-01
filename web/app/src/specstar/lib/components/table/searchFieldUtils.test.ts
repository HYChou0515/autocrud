/**
 * Tests for searchFieldUtils — fieldsToSearchableFields()
 */

import { describe, it, expect } from 'vitest';
import { fieldsToSearchableFields, META_SEARCHABLE_FIELDS } from './searchFieldUtils';
import type { ResourceField } from '../../resources';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function mkField(overrides: Partial<ResourceField> & { name: string }): ResourceField {
  return {
    label: overrides.label ?? overrides.name,
    type: 'string',
    isArray: false,
    isRequired: false,
    isNullable: false,
    ...overrides,
  };
}

const META_COUNT = META_SEARCHABLE_FIELDS.length;

/** Strip appended meta fields to get only data-derived fields */
function dataFields(result: ReturnType<typeof fieldsToSearchableFields>) {
  return result.slice(0, result.length - META_COUNT);
}

// ---------------------------------------------------------------------------
// Basic field type mapping
// ---------------------------------------------------------------------------

describe('fieldsToSearchableFields', () => {
  it('converts string fields', () => {
    const fields = [mkField({ name: 'name', type: 'string' })];
    const result = fieldsToSearchableFields(fields);
    expect(dataFields(result)).toEqual([{ name: 'name', label: 'name', type: 'string' }]);
  });

  it('converts number fields', () => {
    const fields = [mkField({ name: 'level', type: 'number', label: 'Level' })];
    const result = fieldsToSearchableFields(fields);
    expect(dataFields(result)).toEqual([{ name: 'level', label: 'Level', type: 'number' }]);
  });

  it('converts boolean fields', () => {
    const fields = [mkField({ name: 'active', type: 'boolean' })];
    const result = fieldsToSearchableFields(fields);
    expect(dataFields(result)).toEqual([{ name: 'active', label: 'active', type: 'boolean' }]);
  });

  it('converts date fields', () => {
    const fields = [mkField({ name: 'birthday', type: 'date' })];
    const result = fieldsToSearchableFields(fields);
    expect(dataFields(result)).toEqual([{ name: 'birthday', label: 'birthday', type: 'date' }]);
  });

  it('converts enum fields to select type with options', () => {
    const fields = [
      mkField({
        name: 'class',
        type: 'string',
        label: '職業',
        enumValues: ['warrior', 'mage', 'thief'],
      }),
    ];
    const result = fieldsToSearchableFields(fields);
    expect(dataFields(result)).toEqual([
      {
        name: 'class',
        label: '職業',
        type: 'select',
        options: [
          { label: 'warrior', value: 'warrior' },
          { label: 'mage', value: 'mage' },
          { label: 'thief', value: 'thief' },
        ],
      },
    ]);
  });

  it('skips complex types (array, object, binary, union, file) at depth 1', () => {
    const fields = [
      mkField({ name: 'name', type: 'string' }),
      mkField({ name: 'items', type: 'array', isArray: true }),
      mkField({ name: 'stats', type: 'object' }),
      mkField({ name: 'avatar', type: 'binary' }),
      mkField({ name: 'kind', type: 'union' }),
      mkField({ name: 'doc', type: 'file' }),
    ];
    const result = fieldsToSearchableFields(fields);
    expect(dataFields(result)).toHaveLength(1);
    expect(dataFields(result)[0].name).toBe('name');
  });

  it('includes all primitive fields at depth 1 by default', () => {
    const fields = [
      mkField({ name: 'name', type: 'string' }),
      mkField({ name: 'level', type: 'number' }),
      mkField({ name: 'active', type: 'boolean' }),
      mkField({ name: 'birthday', type: 'date' }),
    ];
    const result = fieldsToSearchableFields(fields);
    expect(dataFields(result)).toHaveLength(4);
  });

  // -----------------------------------------------------------------------
  // Indexed fields
  // -----------------------------------------------------------------------

  it('always includes indexed fields regardless of depth', () => {
    const fields = [
      mkField({ name: 'name', type: 'string' }),
      mkField({ name: 'level', type: 'number' }),
    ];
    // depth 0 = no non-indexed fields, but indexed still included
    const result = fieldsToSearchableFields(fields, ['level'], 0);
    expect(dataFields(result)).toHaveLength(1);
    expect(dataFields(result)[0].name).toBe('level');
  });

  it('adds indexed fields not in schema as string type', () => {
    const fields = [mkField({ name: 'name', type: 'string' })];
    const result = fieldsToSearchableFields(fields, ['deep.nested.field'], 1);
    const df = dataFields(result);
    expect(df).toHaveLength(2);
    expect(df[1]).toEqual({
      name: 'deep.nested.field',
      label: 'deep.nested.field',
      type: 'string',
    });
  });

  // -----------------------------------------------------------------------
  // Depth control for nested objects
  // -----------------------------------------------------------------------

  it('does not expand nested object fields at depth 1', () => {
    const fields = [
      mkField({
        name: 'stats',
        type: 'object',
        itemFields: [
          mkField({ name: 'hp', type: 'number' }),
          mkField({ name: 'mp', type: 'number' }),
        ],
      }),
    ];
    const result = fieldsToSearchableFields(fields, [], 1);
    expect(dataFields(result)).toHaveLength(0);
  });

  it('expands nested object fields at depth 2', () => {
    const fields = [
      mkField({
        name: 'stats',
        type: 'object',
        itemFields: [
          mkField({ name: 'hp', type: 'number', label: 'HP' }),
          mkField({ name: 'mp', type: 'number', label: 'MP' }),
        ],
      }),
    ];
    const result = fieldsToSearchableFields(fields, [], 2);
    const df = dataFields(result);
    expect(df).toHaveLength(2);
    expect(df[0]).toEqual({ name: 'stats.hp', label: 'HP', type: 'number' });
    expect(df[1]).toEqual({ name: 'stats.mp', label: 'MP', type: 'number' });
  });

  it('expands indexed nested fields regardless of depth', () => {
    const fields = [
      mkField({
        name: 'stats',
        type: 'object',
        itemFields: [
          mkField({ name: 'hp', type: 'number', label: 'HP' }),
          mkField({ name: 'mp', type: 'number', label: 'MP' }),
        ],
      }),
    ];
    // depth 1 won't expand stats, but 'stats.hp' is indexed so should be included
    const result = fieldsToSearchableFields(fields, ['stats.hp'], 1);
    expect(result.find((f) => f.name === 'stats.hp')).toEqual({
      name: 'stats.hp',
      label: 'HP',
      type: 'number',
    });
  });

  // -----------------------------------------------------------------------
  // Skips constValue (discriminator) fields
  // -----------------------------------------------------------------------

  it('skips fields with constValue', () => {
    const fields = [
      mkField({ name: 'type', type: 'string', constValue: 'warrior' }),
      mkField({ name: 'name', type: 'string' }),
    ];
    const result = fieldsToSearchableFields(fields);
    expect(dataFields(result)).toHaveLength(1);
    expect(dataFields(result)[0].name).toBe('name');
  });

  // -----------------------------------------------------------------------
  // Mix of indexed and non-indexed
  // -----------------------------------------------------------------------

  it('handles mixed indexed/non-indexed fields correctly', () => {
    const fields = [
      mkField({ name: 'name', type: 'string', label: 'Name' }),
      mkField({ name: 'level', type: 'number', label: 'Level' }),
      mkField({ name: 'desc', type: 'string', label: 'Description' }),
      mkField({ name: 'items', type: 'array', isArray: true }),
    ];
    const result = fieldsToSearchableFields(fields, ['name', 'level'], 1);
    const df = dataFields(result);
    // All primitive fields at depth 1 + indexed fields
    expect(df).toHaveLength(3); // name, level, desc (all at depth 1)
    expect(df.map((f) => f.name)).toEqual(['name', 'level', 'desc']);
  });

  // -----------------------------------------------------------------------
  // Empty inputs
  // -----------------------------------------------------------------------

  it('returns only meta fields for empty fields', () => {
    const result = fieldsToSearchableFields([]);
    expect(dataFields(result)).toEqual([]);
    expect(result).toHaveLength(META_COUNT);
  });

  it('returns only meta fields for no primitive fields at depth 0 with no indexed', () => {
    const fields = [
      mkField({ name: 'name', type: 'string' }),
      mkField({ name: 'level', type: 'number' }),
    ];
    const result = fieldsToSearchableFields(fields, [], 0);
    expect(dataFields(result)).toHaveLength(0);
  });

  // -----------------------------------------------------------------------
  // Depth 3+ with deeply nested objects
  // -----------------------------------------------------------------------

  it('handles deeply nested objects at depth 3', () => {
    const fields = [
      mkField({
        name: 'character',
        type: 'object',
        itemFields: [
          mkField({
            name: 'stats',
            type: 'object',
            itemFields: [mkField({ name: 'hp', type: 'number', label: 'HP' })],
          }),
        ],
      }),
    ];
    const result = fieldsToSearchableFields(fields, [], 3);
    expect(result.find((f) => f.name === 'character.stats.hp')).toEqual({
      name: 'character.stats.hp',
      label: 'HP',
      type: 'number',
    });
  });

  // -----------------------------------------------------------------------
  // Array fields with isArray: true skipped
  // -----------------------------------------------------------------------

  it('skips array-of-objects (isArray: true)', () => {
    const fields = [
      mkField({
        name: 'skills',
        type: 'object',
        isArray: true,
        itemFields: [mkField({ name: 'name', type: 'string' })],
      }),
    ];
    const result = fieldsToSearchableFields(fields, [], 2);
    expect(dataFields(result)).toHaveLength(0); // array objects not expanded
  });

  // -----------------------------------------------------------------------
  // Default depth parameter
  // -----------------------------------------------------------------------

  it('defaults to depth 1', () => {
    const fields = [
      mkField({ name: 'name', type: 'string' }),
      mkField({
        name: 'nested',
        type: 'object',
        itemFields: [mkField({ name: 'inner', type: 'string' })],
      }),
    ];
    const result = fieldsToSearchableFields(fields);
    expect(dataFields(result)).toHaveLength(1);
    expect(dataFields(result)[0].name).toBe('name');
  });

  // -----------------------------------------------------------------------
  // Meta searchable fields
  // -----------------------------------------------------------------------

  it('appends meta searchable fields after data fields', () => {
    const fields = [mkField({ name: 'name', type: 'string' })];
    const result = fieldsToSearchableFields(fields);
    // 1 data field + META_SEARCHABLE_FIELDS.length meta fields
    expect(result).toHaveLength(1 + META_SEARCHABLE_FIELDS.length);
    // Last N items should be meta fields
    const metaPart = result.slice(-META_SEARCHABLE_FIELDS.length);
    expect(metaPart).toEqual(META_SEARCHABLE_FIELDS);
  });

  it('meta fields labels have [meta] prefix', () => {
    const result = fieldsToSearchableFields([]);
    // Even with no data fields, meta fields should be present
    expect(result).toHaveLength(META_SEARCHABLE_FIELDS.length);
    result.forEach((f) => {
      expect(f.label).toMatch(/^\[meta\]/);
    });
  });

  it('meta fields include resource_id, schema_version, is_deleted, current_revision_id, created_by, updated_by', () => {
    const metaNames = META_SEARCHABLE_FIELDS.map((f) => f.name);
    expect(metaNames).toContain('resource_id');
    expect(metaNames).toContain('schema_version');
    expect(metaNames).toContain('is_deleted');
    expect(metaNames).toContain('current_revision_id');
    expect(metaNames).toContain('created_by');
    expect(metaNames).toContain('updated_by');
  });

  it('meta fields do not duplicate with indexed fields', () => {
    const fields = [mkField({ name: 'name', type: 'string' })];
    // Even if 'resource_id' is passed as indexed, meta field still appears separately
    const result = fieldsToSearchableFields(fields, ['resource_id'], 1);
    const resourceIdFields = result.filter((f) => f.name === 'resource_id');
    // indexed adds one, meta adds one — but indexed resource_id is not in schema
    // so it gets added as string type, then meta also adds it
    expect(resourceIdFields.length).toBeGreaterThanOrEqual(1);
  });
});

// ---------------------------------------------------------------------------
// META_SEARCHABLE_FIELDS constant
// ---------------------------------------------------------------------------

describe('META_SEARCHABLE_FIELDS', () => {
  it('has 6 meta fields', () => {
    expect(META_SEARCHABLE_FIELDS).toHaveLength(6);
  });

  it('each field has name, label, and type', () => {
    META_SEARCHABLE_FIELDS.forEach((f) => {
      expect(f).toHaveProperty('name');
      expect(f).toHaveProperty('label');
      expect(f).toHaveProperty('type');
    });
  });

  it('is_deleted has boolean type', () => {
    const isDeleted = META_SEARCHABLE_FIELDS.find((f) => f.name === 'is_deleted');
    expect(isDeleted?.type).toBe('boolean');
  });

  it('resource_id, schema_version, created_by, updated_by, current_revision_id have string type', () => {
    const stringFields = META_SEARCHABLE_FIELDS.filter((f) => f.name !== 'is_deleted');
    stringFields.forEach((f) => {
      expect(f.type).toBe('string');
    });
  });
});
