/**
 * buildColumns — Tests for the shared column-building utility.
 *
 * Covers:
 *  - buildRawColumns: generates correct raw column defs from ResourceConfig
 *  - buildTableColumns: applies overrides, ordering, hidden filtering
 *  - renderMetaCell: meta-column variant rendering
 */

import { describe, it, expect } from 'vitest';
import { buildRawColumns, buildTableColumns, renderMetaCell } from './buildColumns';
import type { ResourceConfig, ResourceField } from '../../resources';

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

function makeField(overrides: Partial<ResourceField> & { name: string }): ResourceField {
  return {
    label: overrides.label ?? overrides.name,
    type: 'string',
    isArray: false,
    isRequired: false,
    isNullable: false,
    ...overrides,
  };
}

function makeConfig(fields: ResourceField[]): ResourceConfig {
  return {
    name: 'test',
    label: 'Test',
    pluralLabel: 'Tests',
    schema: 'Test',
    fields,
    apiClient: {} as any,
  };
}

// ---------------------------------------------------------------------------
// renderMetaCell
// ---------------------------------------------------------------------------

describe('renderMetaCell', () => {
  it('returns empty string for null/undefined', () => {
    expect(renderMetaCell('string', null)).toBe('');
    expect(renderMetaCell('string', undefined)).toBe('');
  });

  it('renders string variant', () => {
    expect(renderMetaCell('string', 'hello')).toBe('hello');
  });

  it('renders boolean variant', () => {
    expect(renderMetaCell('boolean', true)).toBe('✅');
    expect(renderMetaCell('boolean', false)).toBe('❌');
  });

  it('renders array variant', () => {
    expect(renderMetaCell('array', ['a', 'b'])).toBe('a, b');
    expect(renderMetaCell('array', 'not-array')).toBe('not-array');
  });

  it('renders json variant', () => {
    expect(renderMetaCell('json', { a: 1 })).toBe('{"a":1}');
    expect(renderMetaCell('json', 'scalar')).toBe('scalar');
  });

  it('renders auto as string', () => {
    expect(renderMetaCell('auto', 42)).toBe('42');
  });
});

// ---------------------------------------------------------------------------
// buildRawColumns
// ---------------------------------------------------------------------------

describe('buildRawColumns', () => {
  it('always includes resource_id as first column', () => {
    const config = makeConfig([]);
    const cols = buildRawColumns(config);
    expect(cols[0].id).toBe('resource_id');
    expect(cols[0].header).toBe('Resource ID');
  });

  it('generates data columns from config.fields', () => {
    const config = makeConfig([
      makeField({ name: 'name', label: 'Name' }),
      makeField({ name: 'age', label: 'Age', type: 'number' }),
    ]);
    const cols = buildRawColumns(config);
    const dataColIds = cols.filter((c) => c.field).map((c) => c.id);
    expect(dataColIds).toEqual(['name', 'age']);
  });

  it('skips fields with json variant', () => {
    const config = makeConfig([
      makeField({ name: 'meta_data', label: 'Meta', variant: { type: 'json' } }),
      makeField({ name: 'title', label: 'Title' }),
    ]);
    const cols = buildRawColumns(config);
    const dataColIds = cols.filter((c) => c.field).map((c) => c.id);
    expect(dataColIds).toEqual(['title']);
    expect(dataColIds).not.toContain('meta_data');
  });

  it('generates standard meta columns', () => {
    const config = makeConfig([]);
    const cols = buildRawColumns(config);
    const metaIds = cols.filter((c) => !c.field).map((c) => c.id);
    expect(metaIds).toContain('resource_id');
    expect(metaIds).toContain('current_revision_id');
    expect(metaIds).toContain('created_time');
    expect(metaIds).toContain('updated_time');
    expect(metaIds).toContain('schema_version');
    expect(metaIds).toContain('is_deleted');
    expect(metaIds).toContain('created_by');
    expect(metaIds).toContain('updated_by');
  });

  it('marks meta columns as defaultHidden correctly', () => {
    const config = makeConfig([]);
    const cols = buildRawColumns(config);
    const findCol = (id: string) => cols.find((c) => c.id === id);

    // These should be visible by default
    expect(findCol('resource_id')?.defaultHidden).toBeUndefined();
    expect(findCol('created_time')?.defaultHidden).toBe(false);
    expect(findCol('updated_time')?.defaultHidden).toBe(false);

    // These should be hidden by default
    expect(findCol('current_revision_id')?.defaultHidden).toBe(true);
    expect(findCol('schema_version')?.defaultHidden).toBe(true);
    expect(findCol('is_deleted')?.defaultHidden).toBe(true);
    expect(findCol('created_by')?.defaultHidden).toBe(true);
    expect(findCol('updated_by')?.defaultHidden).toBe(true);
  });

  it('sets size 120 for binary fields', () => {
    const config = makeConfig([makeField({ name: 'avatar', label: 'Avatar', type: 'binary' })]);
    const cols = buildRawColumns(config);
    const avatarCol = cols.find((c) => c.id === 'avatar');
    expect(avatarCol?.size).toBe(120);
  });

  it('accessorFn traverses nested dot-notation paths', () => {
    const config = makeConfig([makeField({ name: 'address.city', label: 'City' })]);
    const cols = buildRawColumns(config);
    const cityCol = cols.find((c) => c.id === 'address.city')!;
    const row = { data: { address: { city: 'Taipei' } }, meta: {} } as any;
    expect(cityCol.accessorFn(row)).toBe('Taipei');
  });
});

// ---------------------------------------------------------------------------
// buildTableColumns
// ---------------------------------------------------------------------------

describe('buildTableColumns', () => {
  it('filters out defaultHidden columns', () => {
    const config = makeConfig([makeField({ name: 'name', label: 'Name' })]);
    const mrtCols = buildTableColumns(config);
    const ids = mrtCols.map((c) => c.id);
    // resource_id, name, created_time, updated_time should be visible
    expect(ids).toContain('resource_id');
    expect(ids).toContain('name');
    expect(ids).toContain('created_time');
    expect(ids).toContain('updated_time');
    // defaultHidden columns should be filtered out
    expect(ids).not.toContain('schema_version');
    expect(ids).not.toContain('is_deleted');
    expect(ids).not.toContain('created_by');
    expect(ids).not.toContain('updated_by');
    expect(ids).not.toContain('current_revision_id');
  });

  it('applies overrides to show hidden columns', () => {
    const config = makeConfig([makeField({ name: 'name', label: 'Name' })]);
    const mrtCols = buildTableColumns(config, {
      overrides: { created_by: { hidden: false } },
    });
    const ids = mrtCols.map((c) => c.id);
    expect(ids).toContain('created_by');
  });

  it('applies overrides to hide visible columns', () => {
    const config = makeConfig([makeField({ name: 'name', label: 'Name' })]);
    const mrtCols = buildTableColumns(config, {
      overrides: { name: { hidden: true } },
    });
    const ids = mrtCols.map((c) => c.id);
    expect(ids).not.toContain('name');
  });

  it('applies label override', () => {
    const config = makeConfig([makeField({ name: 'name', label: 'Name' })]);
    const mrtCols = buildTableColumns(config, {
      overrides: { name: { label: 'Custom Name' } },
    });
    const nameCol = mrtCols.find((c) => c.id === 'name');
    expect(nameCol?.header).toBe('Custom Name');
  });

  it('applies column ordering', () => {
    const config = makeConfig([
      makeField({ name: 'aaa', label: 'AAA' }),
      makeField({ name: 'bbb', label: 'BBB' }),
      makeField({ name: 'ccc', label: 'CCC' }),
    ]);
    const mrtCols = buildTableColumns(config, {
      order: ['ccc', 'aaa', 'bbb'],
    });
    const dataIds = mrtCols.filter((c) => ['aaa', 'bbb', 'ccc'].includes(c.id!)).map((c) => c.id);
    expect(dataIds).toEqual(['ccc', 'aaa', 'bbb']);
  });

  it('unordered columns go after ordered ones', () => {
    const config = makeConfig([
      makeField({ name: 'x', label: 'X' }),
      makeField({ name: 'y', label: 'Y' }),
    ]);
    // Only order 'y' — 'x' should follow after
    const mrtCols = buildTableColumns(config, { order: ['y'] });
    const dataIds = mrtCols.filter((c) => ['x', 'y'].includes(c.id!)).map((c) => c.id);
    expect(dataIds[0]).toBe('y');
  });

  it('returns MRT-compatible column defs with Cell renderer', () => {
    const config = makeConfig([makeField({ name: 'foo', label: 'Foo' })]);
    const mrtCols = buildTableColumns(config);
    const fooCol = mrtCols.find((c) => c.id === 'foo');
    expect(fooCol).toBeDefined();
    expect(fooCol!.accessorFn).toBeDefined();
    expect(typeof fooCol!.Cell).toBe('function');
  });

  it('applies size override', () => {
    const config = makeConfig([makeField({ name: 'name', label: 'Name' })]);
    const mrtCols = buildTableColumns(config, {
      overrides: { name: { size: 300 } },
    });
    const nameCol = mrtCols.find((c) => c.id === 'name');
    expect(nameCol?.size).toBe(300);
  });

  it('works with empty options', () => {
    const config = makeConfig([makeField({ name: 'a', label: 'A' })]);
    const mrtCols = buildTableColumns(config, {});
    expect(mrtCols.length).toBeGreaterThan(0);
  });

  it('works without options', () => {
    const config = makeConfig([makeField({ name: 'a', label: 'A' })]);
    const mrtCols = buildTableColumns(config);
    expect(mrtCols.length).toBeGreaterThan(0);
  });
});
