/**
 * searchUtils — Unit tests for pure URL ↔ ActiveSearchState helpers.
 */

import { describe, it, expect } from 'vitest';
import {
  parseSearchFromURL,
  serializeSearchToURL,
  countActiveConditions,
  EMPTY_ACTIVE_SEARCH,
  EMPTY_EDITING,
  type ActiveSearchState,
} from './searchUtils';

// ---------------------------------------------------------------------------
// parseSearchFromURL
// ---------------------------------------------------------------------------

describe('parseSearchFromURL', () => {
  it('returns empty state for empty string', () => {
    const result = parseSearchFromURL('');
    expect(result.search).toEqual(EMPTY_ACTIVE_SEARCH);
    expect(result.editing).toEqual(EMPTY_EDITING);
    expect(result.hasParams).toBe(false);
    expect(result.isQBMode).toBe(false);
  });

  it('tolerates leading ? and parses meta', () => {
    const result = parseSearchFromURL('?created_by=alice');
    expect(result.search.condition.meta.created_by).toBe('alice');
    expect(result.hasParams).toBe(true); // meta has keys → hasParams true
  });

  it('parses qb parameter', () => {
    const result = parseSearchFromURL('qb=QB.all().limit(10)');
    expect(result.search.mode).toBe('qb');
    expect(result.search.qb).toBe('QB.all().limit(10)');
    expect(result.isQBMode).toBe(true);
    expect(result.hasParams).toBe(true);
  });

  it('parses all meta filters', () => {
    const qs =
      'created_time_start=2024-01-01&created_time_end=2024-12-31' +
      '&updated_time_start=2024-06-01&updated_time_end=2024-06-30' +
      '&created_by=alice&updated_by=bob';
    const result = parseSearchFromURL(qs);
    const { meta } = result.search.condition;
    expect(meta.created_time_start).toBe('2024-01-01');
    expect(meta.created_time_end).toBe('2024-12-31');
    expect(meta.updated_time_start).toBe('2024-06-01');
    expect(meta.updated_time_end).toBe('2024-06-30');
    expect(meta.created_by).toBe('alice');
    expect(meta.updated_by).toBe('bob');
    expect(result.search.mode).toBe('condition');
    expect(result.hasParams).toBe(true);
  });

  it('parses data_conditions JSON', () => {
    const conditions = [
      { field_path: 'level', operator: 'gte', value: 10 },
      { field_path: 'name', operator: 'contains', value: 'hero' },
    ];
    const qs = `data_conditions=${encodeURIComponent(JSON.stringify(conditions))}`;
    const result = parseSearchFromURL(qs);
    expect(result.search.condition.data).toEqual([
      { field: 'level', operator: 'gte', value: 10 },
      { field: 'name', operator: 'contains', value: 'hero' },
    ]);
    expect(result.hasParams).toBe(true);
  });

  it('handles malformed data_conditions gracefully', () => {
    const result = parseSearchFromURL('data_conditions=not-json');
    expect(result.search.condition.data).toEqual([]);
    expect(result.hasParams).toBe(false);
  });

  it('defaults null value in data_conditions to empty string', () => {
    const conditions = [{ field_path: 'x', operator: 'eq', value: null }];
    const qs = `data_conditions=${encodeURIComponent(JSON.stringify(conditions))}`;
    const result = parseSearchFromURL(qs);
    expect(result.search.condition.data[0].value).toBe('');
  });

  it('parses result_limit', () => {
    const result = parseSearchFromURL('result_limit=50');
    expect(result.search.resultLimit).toBe(50);
  });

  it('returns undefined resultLimit when absent', () => {
    const result = parseSearchFromURL('created_by=alice');
    expect(result.search.resultLimit).toBeUndefined();
  });

  it('parses sort_by JSON', () => {
    const sortBy = [
      { field: 'name', order: 'asc' },
      { field: 'level', order: 'desc' },
    ];
    const qs = `sort_by=${encodeURIComponent(JSON.stringify(sortBy))}`;
    const result = parseSearchFromURL(qs);
    expect(result.search.sortBy).toEqual(sortBy);
  });

  it('handles malformed sort_by gracefully', () => {
    const result = parseSearchFromURL('sort_by=bad-json');
    expect(result.search.sortBy).toBeUndefined();
  });

  it('mirrors search into editing state', () => {
    const qs = 'qb=QB.all()&result_limit=100';
    const result = parseSearchFromURL(qs);
    expect(result.editing.qb).toBe('QB.all()');
    expect(result.editing.resultLimit).toBe(100);
  });

  it('combines qb with result_limit and sort_by', () => {
    const sortBy = [{ field: 'level', order: 'desc' as const }];
    const qs = `qb=QB.all()&result_limit=20&sort_by=${encodeURIComponent(JSON.stringify(sortBy))}`;
    const result = parseSearchFromURL(qs);
    expect(result.search.mode).toBe('qb');
    expect(result.search.qb).toBe('QB.all()');
    expect(result.search.resultLimit).toBe(20);
    expect(result.search.sortBy).toEqual(sortBy);
    expect(result.isQBMode).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// serializeSearchToURL
// ---------------------------------------------------------------------------

describe('serializeSearchToURL', () => {
  it('returns empty object for empty search', () => {
    const params = serializeSearchToURL(EMPTY_ACTIVE_SEARCH);
    expect(params).toEqual({});
  });

  it('serializes qb mode', () => {
    const search: ActiveSearchState = {
      ...EMPTY_ACTIVE_SEARCH,
      mode: 'qb',
      qb: 'QB.all().limit(5)',
    };
    const params = serializeSearchToURL(search);
    expect(params).toEqual({ qb: 'QB.all().limit(5)' });
  });

  it('does not serialize empty qb string in qb mode', () => {
    const search: ActiveSearchState = {
      ...EMPTY_ACTIVE_SEARCH,
      mode: 'qb',
      qb: '',
    };
    const params = serializeSearchToURL(search);
    expect(params).toEqual({});
  });

  it('serializes meta filters in condition mode', () => {
    const search: ActiveSearchState = {
      ...EMPTY_ACTIVE_SEARCH,
      mode: 'condition',
      condition: {
        meta: { created_by: 'alice', updated_time_start: '2024-01-01' },
        data: [],
      },
    };
    const params = serializeSearchToURL(search);
    expect(params.created_by).toBe('alice');
    expect(params.updated_time_start).toBe('2024-01-01');
    expect(params.qb).toBeUndefined();
  });

  it('serializes all six meta filters', () => {
    const search: ActiveSearchState = {
      ...EMPTY_ACTIVE_SEARCH,
      mode: 'condition',
      condition: {
        meta: {
          created_time_start: 'a',
          created_time_end: 'b',
          updated_time_start: 'c',
          updated_time_end: 'd',
          created_by: 'e',
          updated_by: 'f',
        },
        data: [],
      },
    };
    const params = serializeSearchToURL(search);
    expect(params.created_time_start).toBe('a');
    expect(params.created_time_end).toBe('b');
    expect(params.updated_time_start).toBe('c');
    expect(params.updated_time_end).toBe('d');
    expect(params.created_by).toBe('e');
    expect(params.updated_by).toBe('f');
  });

  it('serializes data conditions as JSON', () => {
    const search: ActiveSearchState = {
      ...EMPTY_ACTIVE_SEARCH,
      mode: 'condition',
      condition: {
        meta: {},
        data: [{ field: 'level', operator: 'gte', value: 10 }],
      },
    };
    const params = serializeSearchToURL(search);
    const parsed = JSON.parse(params.data_conditions);
    expect(parsed).toEqual([{ field_path: 'level', operator: 'gte', value: 10 }]);
  });

  it('serializes resultLimit', () => {
    const search: ActiveSearchState = {
      ...EMPTY_ACTIVE_SEARCH,
      resultLimit: 200,
    };
    const params = serializeSearchToURL(search);
    expect(params.result_limit).toBe('200');
  });

  it('does not include result_limit when undefined', () => {
    const params = serializeSearchToURL(EMPTY_ACTIVE_SEARCH);
    expect(params.result_limit).toBeUndefined();
  });

  it('serializes sortBy as JSON', () => {
    const search: ActiveSearchState = {
      ...EMPTY_ACTIVE_SEARCH,
      sortBy: [{ field: 'name', order: 'asc' }],
    };
    const params = serializeSearchToURL(search);
    expect(JSON.parse(params.sort_by)).toEqual([{ field: 'name', order: 'asc' }]);
  });

  it('does not include sort_by when empty array', () => {
    const search: ActiveSearchState = {
      ...EMPTY_ACTIVE_SEARCH,
      sortBy: [],
    };
    const params = serializeSearchToURL(search);
    expect(params.sort_by).toBeUndefined();
  });

  it('round-trips with parseSearchFromURL (condition mode)', () => {
    const original: ActiveSearchState = {
      mode: 'condition',
      condition: {
        meta: { created_by: 'bob', updated_time_end: '2025-12-31' },
        data: [{ field: 'hp', operator: 'gt', value: 100 }],
      },
      qb: '',
      resultLimit: 50,
      sortBy: [{ field: 'hp', order: 'desc' }],
    };
    const serialized = serializeSearchToURL(original);
    const qs = new URLSearchParams(serialized).toString();
    const { search } = parseSearchFromURL(qs);

    expect(search.mode).toBe('condition');
    expect(search.condition.meta.created_by).toBe('bob');
    expect(search.condition.data).toEqual([{ field: 'hp', operator: 'gt', value: 100 }]);
    expect(search.resultLimit).toBe(50);
    expect(search.sortBy).toEqual([{ field: 'hp', order: 'desc' }]);
  });

  it('round-trips with parseSearchFromURL (qb mode)', () => {
    const original: ActiveSearchState = {
      mode: 'qb',
      condition: { meta: {}, data: [] },
      qb: 'QB["level"] > 50',
      resultLimit: 10,
      sortBy: undefined,
    };
    const serialized = serializeSearchToURL(original);
    const qs = new URLSearchParams(serialized).toString();
    const { search } = parseSearchFromURL(qs);

    expect(search.mode).toBe('qb');
    expect(search.qb).toBe('QB["level"] > 50');
    expect(search.resultLimit).toBe(10);
  });
});

// ---------------------------------------------------------------------------
// countActiveConditions
// ---------------------------------------------------------------------------

describe('countActiveConditions', () => {
  it('returns 0 for empty condition mode', () => {
    expect(countActiveConditions(EMPTY_ACTIVE_SEARCH)).toBe(0);
  });

  it('returns 1 for qb mode with non-empty qb', () => {
    const search: ActiveSearchState = {
      ...EMPTY_ACTIVE_SEARCH,
      mode: 'qb',
      qb: 'QB.all()',
    };
    expect(countActiveConditions(search)).toBe(1);
  });

  it('returns 0 for qb mode with empty qb', () => {
    const search: ActiveSearchState = {
      ...EMPTY_ACTIVE_SEARCH,
      mode: 'qb',
      qb: '',
    };
    expect(countActiveConditions(search)).toBe(0);
  });

  it('counts data conditions + meta keys', () => {
    const search: ActiveSearchState = {
      ...EMPTY_ACTIVE_SEARCH,
      mode: 'condition',
      condition: {
        meta: { created_by: 'alice', updated_by: 'bob' },
        data: [
          { field: 'level', operator: 'gte', value: 10 },
          { field: 'name', operator: 'eq', value: 'hero' },
        ],
      },
    };
    expect(countActiveConditions(search)).toBe(4); // 2 meta + 2 data
  });

  it('counts only meta when no data conditions', () => {
    const search: ActiveSearchState = {
      ...EMPTY_ACTIVE_SEARCH,
      mode: 'condition',
      condition: {
        meta: { created_time_start: '2024-01-01' },
        data: [],
      },
    };
    expect(countActiveConditions(search)).toBe(1);
  });

  it('counts only data when no meta filters', () => {
    const search: ActiveSearchState = {
      ...EMPTY_ACTIVE_SEARCH,
      mode: 'condition',
      condition: {
        meta: {},
        data: [{ field: 'x', operator: 'eq', value: 1 }],
      },
    };
    expect(countActiveConditions(search)).toBe(1);
  });
});

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

describe('constants', () => {
  it('EMPTY_ACTIVE_SEARCH is condition mode with empty data', () => {
    expect(EMPTY_ACTIVE_SEARCH.mode).toBe('condition');
    expect(EMPTY_ACTIVE_SEARCH.condition.data).toEqual([]);
    expect(EMPTY_ACTIVE_SEARCH.condition.meta).toEqual({});
    expect(EMPTY_ACTIVE_SEARCH.qb).toBe('');
    expect(EMPTY_ACTIVE_SEARCH.resultLimit).toBeUndefined();
    expect(EMPTY_ACTIVE_SEARCH.sortBy).toBeUndefined();
  });

  it('EMPTY_EDITING matches EMPTY_ACTIVE_SEARCH shape', () => {
    expect(EMPTY_EDITING.condition.data).toEqual([]);
    expect(EMPTY_EDITING.condition.meta).toEqual({});
    expect(EMPTY_EDITING.qb).toBe('');
    expect(EMPTY_EDITING.resultLimit).toBeUndefined();
    expect(EMPTY_EDITING.sortBy).toBeUndefined();
  });
});
