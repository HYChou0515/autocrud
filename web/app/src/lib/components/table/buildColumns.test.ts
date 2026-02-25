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
import type { ResourceConfig, ResourceField, UnionMeta } from '../../resources';

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

function makeConfig(fields: ResourceField[], overrides?: Partial<ResourceConfig>): ResourceConfig {
  return {
    name: 'test',
    label: 'Test',
    pluralLabel: 'Tests',
    schema: 'Test',
    fields,
    apiClient: {} as any,
    ...overrides,
  };
}

/** Helper to build a union resource config (like Pet = Dog | Mount) */
function makeUnionConfig(): ResourceConfig {
  const unionMeta: UnionMeta = {
    discriminatorField: 'type',
    variants: [
      {
        tag: 'Dog',
        label: 'Dog',
        schemaName: 'Dog',
        fields: [
          makeField({ name: 'name', label: 'Name' }),
          makeField({ name: 'breed', label: 'Breed' }),
          makeField({ name: 'level', label: 'Level', type: 'number' }),
        ],
      },
      {
        tag: 'Mount',
        label: 'Mount',
        schemaName: 'Mount',
        fields: [
          makeField({ name: 'name', label: 'Name' }),
          makeField({ name: 'species', label: 'Species' }),
          makeField({ name: 'speed', label: 'Speed', type: 'number' }),
        ],
      },
    ],
  };

  return makeConfig(
    [
      {
        name: 'data',
        label: 'Pet',
        type: 'union',
        isArray: false,
        isRequired: true,
        isNullable: false,
        unionMeta,
      },
    ],
    { isUnion: true },
  );
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

// ---------------------------------------------------------------------------
// Union resource column expansion
// ---------------------------------------------------------------------------

describe('buildRawColumns (union resource)', () => {
  it('expands union field into discriminator + variant sub-fields', () => {
    const config = makeUnionConfig();
    const cols = buildRawColumns(config);
    const colIds = cols.map((c) => c.id);

    // Should NOT have the original "data" wrapper column
    expect(colIds).not.toContain('data');

    // Should have discriminator column
    expect(colIds).toContain('__union_tag');

    // Should have all unique sub-fields from both variants
    expect(colIds).toContain('name');
    expect(colIds).toContain('breed'); // Dog-only
    expect(colIds).toContain('level'); // Dog-only
    expect(colIds).toContain('species'); // Mount-only
    expect(colIds).toContain('speed'); // Mount-only
  });

  it('discriminator column has size 100 and customRender', () => {
    const config = makeUnionConfig();
    const cols = buildRawColumns(config);
    const tagCol = cols.find((c) => c.id === '__union_tag')!;

    expect(tagCol.size).toBe(100);
    expect(tagCol.header).toBe('Type');
    expect(tagCol.customRender).toBeDefined();
    expect(tagCol.customRender!('Dog')).toBe('Dog');
    expect(tagCol.customRender!(null)).toBe('');
  });

  it('discriminator accessorFn reads from row.data directly', () => {
    const config = makeUnionConfig();
    const cols = buildRawColumns(config);
    const tagCol = cols.find((c) => c.id === '__union_tag')!;

    const dogRow = { data: { type: 'Dog', name: 'Buddy', breed: 'Lab' }, meta: {} } as any;
    expect(tagCol.accessorFn(dogRow)).toBe('Dog');

    const mountRow = { data: { type: 'Mount', name: 'Storm', species: 'Horse' }, meta: {} } as any;
    expect(tagCol.accessorFn(mountRow)).toBe('Mount');
  });

  it('variant sub-field accessorFn reads from row.data directly', () => {
    const config = makeUnionConfig();
    const cols = buildRawColumns(config);

    const nameCol = cols.find((c) => c.id === 'name')!;
    const breedCol = cols.find((c) => c.id === 'breed')!;
    const speciesCol = cols.find((c) => c.id === 'species')!;

    const dogRow = { data: { type: 'Dog', name: 'Buddy', breed: 'Lab' }, meta: {} } as any;
    expect(nameCol.accessorFn(dogRow)).toBe('Buddy');
    expect(breedCol.accessorFn(dogRow)).toBe('Lab');
    expect(speciesCol.accessorFn(dogRow)).toBeUndefined(); // Not a Mount

    const mountRow = {
      data: { type: 'Mount', name: 'Storm', species: 'Horse', speed: 20 },
      meta: {},
    } as any;
    expect(nameCol.accessorFn(mountRow)).toBe('Storm');
    expect(speciesCol.accessorFn(mountRow)).toBe('Horse');
    expect(breedCol.accessorFn(mountRow)).toBeUndefined(); // Not a Dog
  });

  it('deduplicates sub-fields shared across variants', () => {
    const config = makeUnionConfig();
    const cols = buildRawColumns(config);
    // "name" appears in both Dog and Mount but should only appear once
    const nameCols = cols.filter((c) => c.id === 'name');
    expect(nameCols).toHaveLength(1);
  });

  it('preserves field metadata on expanded sub-field columns', () => {
    const config = makeUnionConfig();
    const cols = buildRawColumns(config);
    const levelCol = cols.find((c) => c.id === 'level')!;
    expect(levelCol.field).toBeDefined();
    expect(levelCol.field!.type).toBe('number');
    expect(levelCol.field!.label).toBe('Level');
  });

  it('still includes resource_id and meta columns', () => {
    const config = makeUnionConfig();
    const cols = buildRawColumns(config);
    const colIds = cols.map((c) => c.id);
    expect(colIds[0]).toBe('resource_id');
    expect(colIds).toContain('created_time');
    expect(colIds).toContain('updated_time');
  });

  it('non-union config is not affected by union expansion', () => {
    const normalConfig = makeConfig([
      makeField({ name: 'title', label: 'Title' }),
      makeField({ name: 'count', label: 'Count', type: 'number' }),
    ]);
    const cols = buildRawColumns(normalConfig);
    const dataColIds = cols.filter((c) => c.field).map((c) => c.id);
    expect(dataColIds).toEqual(['title', 'count']);
    expect(cols.find((c) => c.id === '__union_tag')).toBeUndefined();
  });
});

describe('buildTableColumns (union resource)', () => {
  it('includes discriminator and variant columns in MRT output', () => {
    const config = makeUnionConfig();
    const mrtCols = buildTableColumns(config);
    const ids = mrtCols.map((c) => c.id);

    expect(ids).toContain('__union_tag');
    expect(ids).toContain('name');
    expect(ids).toContain('breed');
    expect(ids).toContain('species');
    expect(ids).not.toContain('data');
  });

  it('discriminator column uses customRender in Cell', () => {
    const config = makeUnionConfig();
    const mrtCols = buildTableColumns(config);
    const tagCol = mrtCols.find((c) => c.id === '__union_tag')!;
    expect(tagCol.Cell).toBeDefined();

    // The Cell function wraps customRender
    const rendered = tagCol.Cell!({ cell: { getValue: () => 'Dog' } } as any);
    expect(rendered).toBe('Dog');
  });
});
