/**
 * Unit tests for ResourceTable utility functions:
 * - isServerSortable
 * - isServerFilterable
 * - computeTableMode
 * - mrtSortingToSorts
 * - mrtFiltersToParams
 */

import { describe, it, expect } from 'vitest';
import {
  isServerSortable,
  isServerFilterable,
  computeTableMode,
  mrtSortingToSorts,
  mrtFiltersToParams,
  DEFAULT_SORTING,
  buildRequestParams,
  applyAlwaysSearchConditions,
  splitConditionsByIndex,
  applyClientConditions,
  applyClientSort,
  getNestedValue,
  isMetaField,
  META_SORT_FIELDS,
  conditionToQB,
  isoToPythonDatetime,
} from './utils';
import type { ActiveSearchState } from './searchUtils';

// ---------------------------------------------------------------------------
// isServerSortable
// ---------------------------------------------------------------------------

describe('isServerSortable', () => {
  it('returns true for meta sort keys', () => {
    expect(isServerSortable('resource_id')).toBe(true);
    expect(isServerSortable('created_time')).toBe(true);
    expect(isServerSortable('updated_time')).toBe(true);
  });

  it('returns false for non-sortable meta columns', () => {
    expect(isServerSortable('created_by')).toBe(false);
    expect(isServerSortable('updated_by')).toBe(false);
    expect(isServerSortable('schema_version')).toBe(false);
    expect(isServerSortable('is_deleted')).toBe(false);
    expect(isServerSortable('current_revision_id')).toBe(false);
  });

  it('returns true for indexed data fields', () => {
    expect(isServerSortable('level', ['level', 'name'])).toBe(true);
    expect(isServerSortable('name', ['level', 'name'])).toBe(true);
  });

  it('returns false for non-indexed data fields', () => {
    expect(isServerSortable('description', ['level', 'name'])).toBe(false);
  });

  it('returns false for data fields when indexedFields is undefined', () => {
    expect(isServerSortable('level')).toBe(false);
    expect(isServerSortable('level', undefined)).toBe(false);
  });

  it('returns false for data fields when indexedFields is empty', () => {
    expect(isServerSortable('level', [])).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// isServerFilterable
// ---------------------------------------------------------------------------

describe('isServerFilterable', () => {
  it('returns true for dedicated meta filter columns', () => {
    expect(isServerFilterable('created_by')).toBe(true);
    expect(isServerFilterable('updated_by')).toBe(true);
    expect(isServerFilterable('is_deleted')).toBe(true);
  });

  it('returns false for meta columns without dedicated filter support', () => {
    expect(isServerFilterable('created_time')).toBe(false);
    expect(isServerFilterable('updated_time')).toBe(false);
    expect(isServerFilterable('resource_id')).toBe(false);
    expect(isServerFilterable('current_revision_id')).toBe(false);
    expect(isServerFilterable('schema_version')).toBe(false);
  });

  it('returns true for indexed data fields', () => {
    expect(isServerFilterable('level', ['level', 'name'])).toBe(true);
  });

  it('returns false for non-indexed data fields', () => {
    expect(isServerFilterable('description', ['level', 'name'])).toBe(false);
    expect(isServerFilterable('description')).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// computeTableMode
// ---------------------------------------------------------------------------

describe('computeTableMode', () => {
  const base = {
    debouncedGlobalFilter: '',
    sorting: [] as any[],
    columnFilters: [] as any[],
    indexedFields: ['level', 'name'],
  };

  it('returns "server" with no triggers', () => {
    expect(computeTableMode(base)).toBe('server');
  });

  it('returns "client" when globalFilter is non-empty', () => {
    expect(computeTableMode({ ...base, debouncedGlobalFilter: 'hello' })).toBe('client');
  });

  it('returns "server" when sorting on server-sortable meta column', () => {
    expect(computeTableMode({ ...base, sorting: [{ id: 'created_time', desc: false }] })).toBe(
      'server',
    );
  });

  it('returns "server" when sorting on indexed data field', () => {
    expect(computeTableMode({ ...base, sorting: [{ id: 'level', desc: true }] })).toBe('server');
  });

  it('returns "client" when sorting on non-server-sortable column', () => {
    expect(computeTableMode({ ...base, sorting: [{ id: 'created_by', desc: false }] })).toBe(
      'client',
    );
  });

  it('returns "client" when sorting on non-indexed data field', () => {
    expect(computeTableMode({ ...base, sorting: [{ id: 'description', desc: false }] })).toBe(
      'client',
    );
  });

  it('returns "client" when mixed sorts include a non-sortable column', () => {
    expect(
      computeTableMode({
        ...base,
        sorting: [
          { id: 'created_time', desc: false },
          { id: 'description', desc: true },
        ],
      }),
    ).toBe('client');
  });

  it('returns "server" when column filter targets server-filterable column', () => {
    expect(
      computeTableMode({ ...base, columnFilters: [{ id: 'created_by', value: 'admin' }] }),
    ).toBe('server');
  });

  it('returns "server" when column filter targets indexed data field', () => {
    expect(computeTableMode({ ...base, columnFilters: [{ id: 'level', value: '5' }] })).toBe(
      'server',
    );
  });

  it('returns "client" when column filter targets non-filterable column', () => {
    expect(
      computeTableMode({ ...base, columnFilters: [{ id: 'created_time', value: '2024' }] }),
    ).toBe('client');
  });

  it('returns "client" when column filter targets non-indexed data field', () => {
    expect(
      computeTableMode({ ...base, columnFilters: [{ id: 'description', value: 'test' }] }),
    ).toBe('client');
  });

  it('ignores empty/null filter values', () => {
    expect(
      computeTableMode({
        ...base,
        columnFilters: [
          { id: 'description', value: '' },
          { id: 'description', value: null },
        ],
      }),
    ).toBe('server');
  });

  it('returns "client" on combined triggers', () => {
    expect(
      computeTableMode({
        ...base,
        debouncedGlobalFilter: 'search',
        sorting: [{ id: 'description', desc: false }],
        columnFilters: [{ id: 'resource_id', value: 'abc' }],
      }),
    ).toBe('client');
  });

  it('returns "client" for any data sort when indexedFields is undefined', () => {
    expect(
      computeTableMode({
        debouncedGlobalFilter: '',
        sorting: [{ id: 'level', desc: false }],
        columnFilters: [],
        indexedFields: undefined,
      }),
    ).toBe('client');
  });
});

// ---------------------------------------------------------------------------
// mrtSortingToSorts
// ---------------------------------------------------------------------------

describe('mrtSortingToSorts', () => {
  it('returns empty string for empty sorting', () => {
    expect(mrtSortingToSorts([])).toBe('');
  });

  it('converts meta sort key ascending', () => {
    const result = JSON.parse(mrtSortingToSorts([{ id: 'created_time', desc: false }]));
    expect(result).toEqual([{ type: 'meta', key: 'created_time', direction: '+' }]);
  });

  it('converts meta sort key descending', () => {
    const result = JSON.parse(mrtSortingToSorts([{ id: 'resource_id', desc: true }]));
    expect(result).toEqual([{ type: 'meta', key: 'resource_id', direction: '-' }]);
  });

  it('converts indexed data field sort', () => {
    const result = JSON.parse(mrtSortingToSorts([{ id: 'level', desc: false }], ['level']));
    expect(result).toEqual([{ type: 'data', field_path: 'level', direction: '+' }]);
  });

  it('omits non-server-sortable columns', () => {
    expect(mrtSortingToSorts([{ id: 'description', desc: false }], ['level'])).toBe('');
  });

  it('handles mixed sortable and non-sortable columns', () => {
    const result = JSON.parse(
      mrtSortingToSorts(
        [
          { id: 'created_time', desc: false },
          { id: 'description', desc: true },
          { id: 'level', desc: true },
        ],
        ['level'],
      ),
    );
    expect(result).toEqual([
      { type: 'meta', key: 'created_time', direction: '+' },
      { type: 'data', field_path: 'level', direction: '-' },
    ]);
  });

  it('returns empty string when all columns are non-sortable', () => {
    expect(
      mrtSortingToSorts(
        [
          { id: 'created_by', desc: false },
          { id: 'description', desc: true },
        ],
        [],
      ),
    ).toBe('');
  });
});

// ---------------------------------------------------------------------------
// mrtFiltersToParams
// ---------------------------------------------------------------------------

describe('mrtFiltersToParams', () => {
  it('returns empty results for empty filters', () => {
    const { serverParams, dataConditions } = mrtFiltersToParams([]);
    expect(serverParams).toEqual({});
    expect(dataConditions).toEqual([]);
  });

  it('converts created_by filter to created_bys param', () => {
    const { serverParams, dataConditions } = mrtFiltersToParams([
      { id: 'created_by', value: 'admin' },
    ]);
    expect(serverParams).toEqual({ created_bys: ['admin'] });
    expect(dataConditions).toEqual([]);
  });

  it('converts updated_by filter to updated_bys param', () => {
    const { serverParams } = mrtFiltersToParams([{ id: 'updated_by', value: 'user1' }]);
    expect(serverParams).toEqual({ updated_bys: ['user1'] });
  });

  it('converts is_deleted filter to boolean param', () => {
    const { serverParams } = mrtFiltersToParams([{ id: 'is_deleted', value: 'true' }]);
    expect(serverParams).toEqual({ is_deleted: true });
  });

  it('converts is_deleted "false" string correctly', () => {
    const { serverParams } = mrtFiltersToParams([{ id: 'is_deleted', value: 'false' }]);
    expect(serverParams).toEqual({ is_deleted: false });
  });

  it('converts indexed data field string to contains condition', () => {
    const { dataConditions } = mrtFiltersToParams(
      [{ id: 'name', value: 'alice' }],
      ['name', 'level'],
    );
    expect(dataConditions).toEqual([{ field_path: 'name', operator: 'contains', value: 'alice' }]);
  });

  it('converts indexed data field number to eq condition', () => {
    const { dataConditions } = mrtFiltersToParams([{ id: 'level', value: 5 }], ['level']);
    expect(dataConditions).toEqual([{ field_path: 'level', operator: 'eq', value: 5 }]);
  });

  it('ignores non-filterable columns', () => {
    const { serverParams, dataConditions } = mrtFiltersToParams([
      { id: 'created_time', value: '2024-01-01' },
      { id: 'description', value: 'test' },
    ]);
    expect(serverParams).toEqual({});
    expect(dataConditions).toEqual([]);
  });

  it('ignores empty and null values', () => {
    const { serverParams, dataConditions } = mrtFiltersToParams([
      { id: 'created_by', value: '' },
      { id: 'created_by', value: null },
    ]);
    expect(serverParams).toEqual({});
    expect(dataConditions).toEqual([]);
  });

  it('handles mixed meta and indexed data filters', () => {
    const { serverParams, dataConditions } = mrtFiltersToParams(
      [
        { id: 'created_by', value: 'admin' },
        { id: 'name', value: 'bob' },
        { id: 'description', value: 'ignored' },
      ],
      ['name'],
    );
    expect(serverParams).toEqual({ created_bys: ['admin'] });
    expect(dataConditions).toEqual([{ field_path: 'name', operator: 'contains', value: 'bob' }]);
  });
});

// ---------------------------------------------------------------------------
// DEFAULT_SORTING
// ---------------------------------------------------------------------------

describe('DEFAULT_SORTING', () => {
  it('sorts by updated_time descending', () => {
    expect(DEFAULT_SORTING).toEqual([{ id: 'updated_time', desc: true }]);
  });

  it('is a valid server-sortable state (stays in server mode)', () => {
    const mode = computeTableMode({
      debouncedGlobalFilter: '',
      sorting: DEFAULT_SORTING,
      columnFilters: [],
      indexedFields: [],
    });
    expect(mode).toBe('server');
  });

  it('produces valid backend sorts string via mrtSortingToSorts', () => {
    const sortsStr = mrtSortingToSorts(DEFAULT_SORTING);
    const parsed = JSON.parse(sortsStr);
    expect(parsed).toEqual([{ type: 'meta', key: 'updated_time', direction: '-' }]);
  });
});

// ---------------------------------------------------------------------------
// buildRequestParams
// ---------------------------------------------------------------------------

describe('buildRequestParams', () => {
  const baseActiveSearch: ActiveSearchState = {
    mode: 'condition',
    condition: { meta: {}, data: [] },
    qb: '',
    resultLimit: undefined,
    sortBy: undefined,
  };

  const defaultArgs = {
    mode: 'server' as const,
    pagination: { pageIndex: 0, pageSize: 20 },
    activeSearch: baseActiveSearch,
    sorting: DEFAULT_SORTING,
    columnFilters: [] as any[],
    indexedFields: [] as string[],
    alwaysSearchCondition: undefined,
  };

  it('includes sorts in server mode with condition search', () => {
    const params = buildRequestParams(defaultArgs);
    expect(params.sorts).toBeDefined();
    expect(params.qb).toBeUndefined();
  });

  it('includes sorts in client mode with condition search', () => {
    const params = buildRequestParams({
      ...defaultArgs,
      mode: 'client',
    });
    expect(params.sorts).toBeDefined();
    expect(params.qb).toBeUndefined();
  });

  it('does NOT include sorts when QB mode is active (server mode)', () => {
    const params = buildRequestParams({
      ...defaultArgs,
      mode: 'server',
      activeSearch: {
        ...baseActiveSearch,
        mode: 'qb',
        qb: 'QB.all().order_by("-updated_time")',
      },
    });
    expect(params.qb).toBe('QB.all().order_by("-updated_time")');
    expect(params.sorts).toBeUndefined();
  });

  it('does NOT include sorts when QB mode is active (client mode)', () => {
    const params = buildRequestParams({
      ...defaultArgs,
      mode: 'client',
      activeSearch: {
        ...baseActiveSearch,
        mode: 'qb',
        qb: 'QB["level"] > 5',
      },
    });
    expect(params.qb).toBe('QB["level"] > 5');
    expect(params.sorts).toBeUndefined();
  });

  it('does NOT include data_conditions or meta filters in QB mode', () => {
    const params = buildRequestParams({
      ...defaultArgs,
      mode: 'server',
      activeSearch: {
        ...baseActiveSearch,
        mode: 'qb',
        qb: 'QB.all()',
      },
    });
    expect(params.qb).toBe('QB.all()');
    expect(params.sorts).toBeUndefined();
    expect(params.data_conditions).toBeUndefined();
    expect(params.created_time_start).toBeUndefined();
  });

  it('uses pagination in server mode', () => {
    const params = buildRequestParams({
      ...defaultArgs,
      mode: 'server',
      pagination: { pageIndex: 2, pageSize: 10 },
    });
    expect(params.limit).toBe(10);
    expect(params.offset).toBe(20);
  });

  it('uses CLIENT_FETCH_LIMIT in client mode', () => {
    const params = buildRequestParams({
      ...defaultArgs,
      mode: 'client',
    });
    expect(params.limit).toBe(1000);
    expect(params.offset).toBeUndefined();
  });

  it('includes advanced panel sorts in condition mode (server)', () => {
    const params = buildRequestParams({
      ...defaultArgs,
      mode: 'server',
      activeSearch: {
        ...baseActiveSearch,
        sortBy: [{ field: 'updated_time', order: 'desc' }],
      },
    });
    expect(params.sorts).toBeDefined();
    const parsed = JSON.parse(params.sorts as string);
    expect(parsed).toEqual([{ type: 'meta', key: 'updated_time', direction: '-' }]);
  });

  it('includes MRT sorting in server mode when no advanced sorts', () => {
    const params = buildRequestParams({
      ...defaultArgs,
      mode: 'server',
      sorting: [{ id: 'created_time', desc: false }],
    });
    expect(params.sorts).toBeDefined();
    const parsed = JSON.parse(params.sorts as string);
    expect(parsed).toEqual([{ type: 'meta', key: 'created_time', direction: '+' }]);
  });

  it('merges alwaysSearchCondition with existing data_conditions', () => {
    const params = buildRequestParams({
      ...defaultArgs,
      indexedFields: ['name'],
      activeSearch: {
        ...baseActiveSearch,
        condition: {
          meta: {},
          data: [{ field: 'name', operator: 'eq', value: 'hero' }],
        },
      },
      alwaysSearchCondition: [{ field: 'active', operator: 'eq', value: true }],
    });
    const parsed = JSON.parse(params.data_conditions as string);
    expect(parsed).toHaveLength(2);
    expect(parsed[0]).toEqual({ field_path: 'name', operator: 'eq', value: 'hero' });
    expect(parsed[1]).toEqual({ field_path: 'active', operator: 'eq', value: true });
  });

  it('handles QB mode with empty string (falls back to condition mode)', () => {
    const params = buildRequestParams({
      ...defaultArgs,
      activeSearch: {
        ...baseActiveSearch,
        mode: 'qb',
        qb: '', // empty QB → should behave like condition mode
      },
    });
    expect(params.qb).toBeUndefined();
    // Should still include sorts since it's effectively condition mode
    expect(params.sorts).toBeDefined();
  });

  it('converts server-filterable meta conditions to query params', () => {
    const params = buildRequestParams({
      ...defaultArgs,
      activeSearch: {
        ...baseActiveSearch,
        condition: {
          meta: {},
          data: [{ field: 'is_deleted', operator: 'eq', value: true }],
        },
      },
    });
    expect(params.is_deleted).toBe(true);
    // Should NOT be in data_conditions
    expect(params.data_conditions).toBeUndefined();
  });

  it('converts created_by meta condition to created_bys param', () => {
    const params = buildRequestParams({
      ...defaultArgs,
      activeSearch: {
        ...baseActiveSearch,
        condition: {
          meta: {},
          data: [{ field: 'created_by', operator: 'eq', value: 'admin' }],
        },
      },
    });
    expect(params.created_bys).toEqual(['admin']);
  });
});

// ---------------------------------------------------------------------------
// META_SORT_FIELDS
// ---------------------------------------------------------------------------

describe('META_SORT_FIELDS', () => {
  it('contains 8 standard meta fields', () => {
    expect(META_SORT_FIELDS).toHaveLength(8);
  });

  it('includes resource_id, created_time, updated_time', () => {
    expect(META_SORT_FIELDS).toContain('resource_id');
    expect(META_SORT_FIELDS).toContain('created_time');
    expect(META_SORT_FIELDS).toContain('updated_time');
  });

  it('includes created_by, updated_by, schema_version, is_deleted, current_revision_id', () => {
    expect(META_SORT_FIELDS).toContain('created_by');
    expect(META_SORT_FIELDS).toContain('updated_by');
    expect(META_SORT_FIELDS).toContain('schema_version');
    expect(META_SORT_FIELDS).toContain('is_deleted');
    expect(META_SORT_FIELDS).toContain('current_revision_id');
  });
});

// ---------------------------------------------------------------------------
// isMetaField
// ---------------------------------------------------------------------------

describe('isMetaField', () => {
  it('returns true for meta searchable fields', () => {
    expect(isMetaField('resource_id')).toBe(true);
    expect(isMetaField('schema_version')).toBe(true);
    expect(isMetaField('is_deleted')).toBe(true);
    expect(isMetaField('current_revision_id')).toBe(true);
    expect(isMetaField('created_by')).toBe(true);
    expect(isMetaField('updated_by')).toBe(true);
  });

  it('returns false for data fields', () => {
    expect(isMetaField('name')).toBe(false);
    expect(isMetaField('level')).toBe(false);
    expect(isMetaField('stats.hp')).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// getNestedValue
// ---------------------------------------------------------------------------

describe('getNestedValue', () => {
  it('returns top-level value for simple key', () => {
    expect(getNestedValue({ a: 1 }, 'a')).toBe(1);
  });

  it('returns nested value for dot-path', () => {
    expect(getNestedValue({ a: { b: { c: 42 } } }, 'a.b.c')).toBe(42);
  });

  it('returns undefined for missing path', () => {
    expect(getNestedValue({ a: 1 }, 'b')).toBeUndefined();
    expect(getNestedValue({ a: { b: 1 } }, 'a.c')).toBeUndefined();
  });

  it('returns undefined for null object', () => {
    expect(getNestedValue(null, 'a')).toBeUndefined();
    expect(getNestedValue(undefined, 'a.b')).toBeUndefined();
  });

  it('returns undefined when intermediate is null', () => {
    expect(getNestedValue({ a: null }, 'a.b')).toBeUndefined();
  });

  it('handles arrays in path', () => {
    expect(getNestedValue({ a: [10, 20] }, 'a.1')).toBe(20);
  });
});

// ---------------------------------------------------------------------------
// splitConditionsByIndex
// ---------------------------------------------------------------------------

describe('splitConditionsByIndex', () => {
  it('separates indexed vs non-indexed data fields', () => {
    const conditions = [
      { field: 'name', operator: 'eq', value: 'hero' },
      { field: 'level', operator: 'gte', value: 10 },
      { field: 'desc', operator: 'contains', value: 'test' },
    ];
    const { serverConditions, clientConditions, serverMetaConditions } = splitConditionsByIndex(
      conditions,
      ['name', 'level'],
    );
    expect(serverConditions).toHaveLength(2);
    expect(clientConditions).toHaveLength(1);
    expect(clientConditions[0].field).toBe('desc');
    expect(serverMetaConditions).toHaveLength(0);
  });

  it('classifies server-filterable meta fields as serverMetaConditions', () => {
    const conditions = [
      { field: 'created_by', operator: 'eq', value: 'admin' },
      { field: 'updated_by', operator: 'eq', value: 'bob' },
      { field: 'is_deleted', operator: 'eq', value: true },
    ];
    const { serverConditions, clientConditions, serverMetaConditions } = splitConditionsByIndex(
      conditions,
      [],
    );
    expect(serverMetaConditions).toHaveLength(3);
    expect(serverConditions).toHaveLength(0);
    expect(clientConditions).toHaveLength(0);
  });

  it('classifies non-server-filterable meta fields as clientConditions', () => {
    const conditions = [
      { field: 'resource_id', operator: 'eq', value: 'abc' },
      { field: 'schema_version', operator: 'eq', value: 'v1' },
      { field: 'current_revision_id', operator: 'eq', value: 'rev-1' },
    ];
    const { serverConditions, clientConditions, serverMetaConditions } = splitConditionsByIndex(
      conditions,
      [],
    );
    expect(clientConditions).toHaveLength(3);
    expect(serverConditions).toHaveLength(0);
    expect(serverMetaConditions).toHaveLength(0);
  });

  it('handles mixed data + meta conditions', () => {
    const conditions = [
      { field: 'name', operator: 'eq', value: 'hero' },
      { field: 'created_by', operator: 'eq', value: 'admin' },
      { field: 'resource_id', operator: 'eq', value: 'x' },
      { field: 'desc', operator: 'contains', value: 'test' },
    ];
    const { serverConditions, clientConditions, serverMetaConditions } = splitConditionsByIndex(
      conditions,
      ['name'],
    );
    expect(serverConditions).toHaveLength(1);
    expect(serverConditions[0].field).toBe('name');
    expect(serverMetaConditions).toHaveLength(1);
    expect(serverMetaConditions[0].field).toBe('created_by');
    expect(clientConditions).toHaveLength(2);
    expect(clientConditions.map((c) => c.field).sort()).toEqual(['desc', 'resource_id']);
  });

  it('returns empty arrays for empty conditions', () => {
    const { serverConditions, clientConditions, serverMetaConditions } = splitConditionsByIndex(
      [],
      ['level'],
    );
    expect(serverConditions).toHaveLength(0);
    expect(clientConditions).toHaveLength(0);
    expect(serverMetaConditions).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// applyClientConditions
// ---------------------------------------------------------------------------

describe('applyClientConditions', () => {
  const rows = [
    {
      data: { name: 'Alice', level: 10, desc: 'warrior' },
      meta: { resource_id: 'r1', is_deleted: false, schema_version: 'v1' },
    },
    {
      data: { name: 'Bob', level: 20, desc: 'mage' },
      meta: { resource_id: 'r2', is_deleted: true, schema_version: 'v2' },
    },
    {
      data: { name: 'Charlie', level: 5, desc: 'thief' },
      meta: { resource_id: 'r3', is_deleted: false, schema_version: 'v1' },
    },
  ];

  it('returns all rows when no conditions', () => {
    expect(applyClientConditions(rows, [])).toEqual(rows);
  });

  it('filters by data field (eq)', () => {
    const result = applyClientConditions(rows, [{ field: 'name', operator: 'eq', value: 'Alice' }]);
    expect(result).toHaveLength(1);
    expect(result[0].data.name).toBe('Alice');
  });

  it('filters by data field (contains)', () => {
    const result = applyClientConditions(rows, [
      { field: 'desc', operator: 'contains', value: 'a' },
    ]);
    expect(result).toHaveLength(2); // warrior, mage
  });

  it('filters by data field (gte) with number coercion', () => {
    const result = applyClientConditions(rows, [{ field: 'level', operator: 'gte', value: 10 }]);
    expect(result).toHaveLength(2);
  });

  it('filters by meta field (resource_id)', () => {
    const result = applyClientConditions(rows, [
      { field: 'resource_id', operator: 'eq', value: 'r2' },
    ]);
    expect(result).toHaveLength(1);
    expect(result[0].meta.resource_id).toBe('r2');
  });

  it('filters by meta field (is_deleted)', () => {
    const result = applyClientConditions(rows, [
      { field: 'is_deleted', operator: 'eq', value: false },
    ]);
    expect(result).toHaveLength(2);
  });

  it('handles AND logic with mixed data + meta conditions', () => {
    const result = applyClientConditions(rows, [
      { field: 'schema_version', operator: 'eq', value: 'v1' },
      { field: 'level', operator: 'gte', value: 10 },
    ]);
    expect(result).toHaveLength(1);
    expect(result[0].data.name).toBe('Alice');
  });

  it('supports dot-path data fields', () => {
    const nestedRows = [
      { data: { stats: { hp: 100, mp: 50 } }, meta: {} },
      { data: { stats: { hp: 200, mp: 30 } }, meta: {} },
    ];
    const result = applyClientConditions(nestedRows, [
      { field: 'stats.hp', operator: 'gte', value: 150 },
    ]);
    expect(result).toHaveLength(1);
    expect(result[0].data.stats.hp).toBe(200);
  });

  it('supports deep dot-path (a.b.c)', () => {
    const deepRows = [
      { data: { a: { b: { c: 'x' } } }, meta: {} },
      { data: { a: { b: { c: 'y' } } }, meta: {} },
    ];
    const result = applyClientConditions(deepRows, [
      { field: 'a.b.c', operator: 'eq', value: 'x' },
    ]);
    expect(result).toHaveLength(1);
  });

  it('supports ne operator', () => {
    const result = applyClientConditions(rows, [{ field: 'name', operator: 'ne', value: 'Alice' }]);
    expect(result).toHaveLength(2);
  });

  it('supports starts_with operator', () => {
    const result = applyClientConditions(rows, [
      { field: 'name', operator: 'starts_with', value: 'Ch' },
    ]);
    expect(result).toHaveLength(1);
    expect(result[0].data.name).toBe('Charlie');
  });

  it('supports ends_with operator', () => {
    const result = applyClientConditions(rows, [
      { field: 'name', operator: 'ends_with', value: 'ob' },
    ]);
    expect(result).toHaveLength(1);
    expect(result[0].data.name).toBe('Bob');
  });
});

// ---------------------------------------------------------------------------
// applyClientSort
// ---------------------------------------------------------------------------

describe('applyClientSort', () => {
  const rows = [
    {
      data: { name: 'Charlie', level: 5 },
      meta: { created_time: '2024-03-01', resource_id: 'r3' },
    },
    { data: { name: 'Alice', level: 10 }, meta: { created_time: '2024-01-01', resource_id: 'r1' } },
    { data: { name: 'Bob', level: 20 }, meta: { created_time: '2024-02-01', resource_id: 'r2' } },
  ];

  it('returns copy when no sort criteria', () => {
    const result = applyClientSort(rows, []);
    expect(result).toEqual(rows);
    expect(result).not.toBe(rows); // does not mutate
  });

  it('sorts by data field ascending', () => {
    const result = applyClientSort(rows, [{ field: 'name', order: 'asc' }]);
    expect(result.map((r) => r.data.name)).toEqual(['Alice', 'Bob', 'Charlie']);
  });

  it('sorts by data field descending', () => {
    const result = applyClientSort(rows, [{ field: 'level', order: 'desc' }]);
    expect(result.map((r) => r.data.level)).toEqual([20, 10, 5]);
  });

  it('sorts by meta field', () => {
    const result = applyClientSort(rows, [{ field: 'created_time', order: 'asc' }]);
    expect(result.map((r) => r.meta.resource_id)).toEqual(['r1', 'r2', 'r3']);
  });

  it('multi-level sort', () => {
    const rowsWithTie = [
      { data: { group: 'A', level: 10 }, meta: {} },
      { data: { group: 'A', level: 5 }, meta: {} },
      { data: { group: 'B', level: 20 }, meta: {} },
    ];
    const result = applyClientSort(rowsWithTie, [
      { field: 'group', order: 'asc' },
      { field: 'level', order: 'desc' },
    ]);
    expect(result.map((r) => r.data.level)).toEqual([10, 5, 20]);
  });

  it('does not mutate original array', () => {
    const original = [...rows];
    applyClientSort(rows, [{ field: 'name', order: 'asc' }]);
    expect(rows).toEqual(original);
  });
});

// ---------------------------------------------------------------------------
// isoToPythonDatetime
// ---------------------------------------------------------------------------

describe('isoToPythonDatetime', () => {
  it('converts a valid ISO string to Python dt.datetime(...)', () => {
    // Use a fixed UTC string to avoid timezone issues
    const result = isoToPythonDatetime('2024-03-15T10:30:00');
    expect(result).toMatch(/^dt\.datetime\(\d{4}, \d+, \d+, \d+, \d+, \d+\)$/);
  });

  it('returns quoted fallback for invalid date', () => {
    expect(isoToPythonDatetime('not-a-date')).toBe('"not-a-date"');
  });
});

// ---------------------------------------------------------------------------
// conditionToQB
// ---------------------------------------------------------------------------

describe('conditionToQB', () => {
  it('returns QB.all() when no conditions', () => {
    expect(conditionToQB({}, [])).toBe('QB.all()');
  });

  // --- Data conditions ---

  it('generates eq condition', () => {
    const result = conditionToQB({}, [{ field: 'name', operator: 'eq', value: 'Alice' }]);
    expect(result).toBe('(QB["name"] == "Alice")');
  });

  it('generates ne condition', () => {
    const result = conditionToQB({}, [{ field: 'status', operator: 'ne', value: 'deleted' }]);
    expect(result).toBe('(QB["status"] != "deleted")');
  });

  it('generates numeric comparison with gte', () => {
    const result = conditionToQB({}, [{ field: 'level', operator: 'gte', value: 6 }]);
    expect(result).toBe('(QB["level"] >= 6)');
  });

  it('generates gt condition', () => {
    const result = conditionToQB({}, [{ field: 'score', operator: 'gt', value: 100 }]);
    expect(result).toBe('(QB["score"] > 100)');
  });

  it('generates lt condition', () => {
    const result = conditionToQB({}, [{ field: 'age', operator: 'lt', value: 18 }]);
    expect(result).toBe('(QB["age"] < 18)');
  });

  it('generates lte condition', () => {
    const result = conditionToQB({}, [{ field: 'priority', operator: 'lte', value: 3 }]);
    expect(result).toBe('(QB["priority"] <= 3)');
  });

  // --- String methods (no parens needed) ---

  it('generates contains condition', () => {
    const result = conditionToQB({}, [{ field: 'name', operator: 'contains', value: 'foo' }]);
    expect(result).toBe('QB["name"].contains("foo")');
  });

  it('generates starts_with condition', () => {
    const result = conditionToQB({}, [{ field: 'name', operator: 'starts_with', value: 'A' }]);
    expect(result).toBe('QB["name"].starts_with("A")');
  });

  it('generates ends_with condition', () => {
    const result = conditionToQB({}, [{ field: 'name', operator: 'ends_with', value: 'z' }]);
    expect(result).toBe('QB["name"].ends_with("z")');
  });

  // --- Multiple conditions joined with & ---

  it('joins multiple conditions with &', () => {
    const result = conditionToQB({}, [
      { field: 'level', operator: 'gte', value: 5 },
      { field: 'name', operator: 'eq', value: 'Bob' },
    ]);
    expect(result).toBe('(QB["level"] >= 5) & (QB["name"] == "Bob")');
  });

  it('joins comparison + method conditions with &', () => {
    const result = conditionToQB({}, [
      { field: 'level', operator: 'gte', value: 5 },
      { field: 'name', operator: 'contains', value: 'Bob' },
    ]);
    expect(result).toBe('(QB["level"] >= 5) & QB["name"].contains("Bob")');
  });

  // --- order_by chaining ---

  it('appends .order_by() to QB.all()', () => {
    const result = conditionToQB({}, [], undefined, [{ field: 'updated_time', order: 'desc' }]);
    expect(result).toBe('QB.all().order_by("-updated_time")');
  });

  it('wraps comparison in parens before .order_by()', () => {
    const result = conditionToQB({}, [{ field: 'level', operator: 'gte', value: 6 }], undefined, [
      { field: 'updated_time', order: 'desc' },
    ]);
    expect(result).toBe('(QB["level"] >= 6).order_by("-updated_time")');
  });

  it('wraps multiple conditions in parens before .order_by()', () => {
    const result = conditionToQB(
      {},
      [
        { field: 'level', operator: 'gte', value: 5 },
        { field: 'name', operator: 'eq', value: 'Bob' },
      ],
      undefined,
      [{ field: 'created_time', order: 'asc' }],
    );
    expect(result).toBe('((QB["level"] >= 5) & (QB["name"] == "Bob")).order_by("created_time")');
  });

  it('handles multi-sort order_by', () => {
    const result = conditionToQB({}, [], undefined, [
      { field: 'level', order: 'desc' },
      { field: 'name', order: 'asc' },
    ]);
    expect(result).toBe('QB.all().order_by("-level", "name")');
  });

  // --- limit chaining ---

  it('appends .limit() correctly', () => {
    const result = conditionToQB({}, [], 50);
    expect(result).toBe('QB.all().limit(50)');
  });

  it('wraps comparison in parens before .limit()', () => {
    const result = conditionToQB({}, [{ field: 'level', operator: 'gte', value: 6 }], 10);
    expect(result).toBe('(QB["level"] >= 6).limit(10)');
  });

  // --- order_by + limit combined ---

  it('chains order_by and limit together', () => {
    const result = conditionToQB({}, [{ field: 'level', operator: 'gte', value: 6 }], 10, [
      { field: 'updated_time', order: 'desc' },
    ]);
    expect(result).toBe('(QB["level"] >= 6).order_by("-updated_time").limit(10)');
  });

  // --- Meta conditions ---

  it('generates meta created_by condition', () => {
    const result = conditionToQB({ created_by: 'admin' }, []);
    expect(result).toBe('QB.created_by().eq("admin")');
  });

  it('generates meta time range conditions', () => {
    const result = conditionToQB(
      { created_time_start: '2024-01-01T00:00:00', created_time_end: '2024-12-31T23:59:59' },
      [],
    );
    expect(result).toContain('QB.created_time().gte(dt.datetime(');
    expect(result).toContain('QB.created_time().lte(dt.datetime(');
    expect(result).toContain(' & ');
  });

  // --- Meta + data + order_by + limit combined ---

  it('combines meta, data, order_by and limit', () => {
    const result = conditionToQB(
      { created_by: 'admin' },
      [{ field: 'level', operator: 'gte', value: 6 }],
      20,
      [{ field: 'updated_time', order: 'desc' }],
    );
    expect(result).toBe(
      '(QB.created_by().eq("admin") & (QB["level"] >= 6)).order_by("-updated_time").limit(20)',
    );
  });

  // --- Skips empty sort entries ---

  it('skips sort entries with empty field', () => {
    const result = conditionToQB({}, [], undefined, [{ field: '', order: 'asc' }]);
    expect(result).toBe('QB.all()');
  });

  // --- String method conditions do not need extra parens for chaining ---

  it('method-style condition with order_by does not need wrapping', () => {
    const result = conditionToQB(
      {},
      [{ field: 'name', operator: 'contains', value: 'test' }],
      undefined,
      [{ field: 'name', order: 'asc' }],
    );
    expect(result).toBe('QB["name"].contains("test").order_by("name")');
  });
});

// ---------------------------------------------------------------------------
// applyAlwaysSearchConditions
// ---------------------------------------------------------------------------

describe('applyAlwaysSearchConditions', () => {
  it('does nothing when conditions is undefined', () => {
    const params: Record<string, unknown> = { limit: 20 };
    applyAlwaysSearchConditions(params, undefined);
    expect(params.data_conditions).toBeUndefined();
  });

  it('does nothing when conditions is empty array', () => {
    const params: Record<string, unknown> = { limit: 20 };
    applyAlwaysSearchConditions(params, []);
    expect(params.data_conditions).toBeUndefined();
  });

  it('creates data_conditions when none exist', () => {
    const params: Record<string, unknown> = { limit: 20 };
    applyAlwaysSearchConditions(params, [{ field: 'type', operator: 'eq', value: 'weapon' }]);
    const parsed = JSON.parse(params.data_conditions as string);
    expect(parsed).toEqual([{ field_path: 'type', operator: 'eq', value: 'weapon' }]);
  });

  it('merges with existing data_conditions', () => {
    const params: Record<string, unknown> = {
      data_conditions: JSON.stringify([{ field_path: 'name', operator: 'eq', value: 'hero' }]),
    };
    applyAlwaysSearchConditions(params, [{ field: 'active', operator: 'eq', value: true }]);
    const parsed = JSON.parse(params.data_conditions as string);
    expect(parsed).toHaveLength(2);
    expect(parsed[0]).toEqual({ field_path: 'name', operator: 'eq', value: 'hero' });
    expect(parsed[1]).toEqual({ field_path: 'active', operator: 'eq', value: true });
  });

  it('handles multiple always conditions', () => {
    const params: Record<string, unknown> = {};
    applyAlwaysSearchConditions(params, [
      { field: 'type', operator: 'eq', value: 'sword' },
      { field: 'rarity', operator: 'gte', value: 3 },
    ]);
    const parsed = JSON.parse(params.data_conditions as string);
    expect(parsed).toHaveLength(2);
    expect(parsed[0]).toEqual({ field_path: 'type', operator: 'eq', value: 'sword' });
    expect(parsed[1]).toEqual({ field_path: 'rarity', operator: 'gte', value: 3 });
  });

  it('converts is_deleted meta condition to direct query param instead of data_conditions', () => {
    const params: Record<string, unknown> = {};
    applyAlwaysSearchConditions(params, [{ field: 'is_deleted', operator: 'eq', value: false }]);
    expect(params.is_deleted).toBe(false);
    expect(params.data_conditions).toBeUndefined();
  });

  it('converts created_by meta condition to direct query param', () => {
    const params: Record<string, unknown> = {};
    applyAlwaysSearchConditions(params, [{ field: 'created_by', operator: 'eq', value: 'admin' }]);
    expect(params.created_bys).toEqual(['admin']);
    expect(params.data_conditions).toBeUndefined();
  });

  it('splits meta and data conditions correctly', () => {
    const params: Record<string, unknown> = {};
    applyAlwaysSearchConditions(params, [
      { field: 'is_deleted', operator: 'eq', value: false },
      { field: 'type', operator: 'eq', value: 'sword' },
    ]);
    expect(params.is_deleted).toBe(false);
    const parsed = JSON.parse(params.data_conditions as string);
    expect(parsed).toEqual([{ field_path: 'type', operator: 'eq', value: 'sword' }]);
  });
});
