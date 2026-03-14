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
} from './utils';

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
