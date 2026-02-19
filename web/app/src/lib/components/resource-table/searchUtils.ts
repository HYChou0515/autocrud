/**
 * searchUtils — Pure functions for URL ↔ ActiveSearchState conversion
 * and other search-related helpers.
 *
 * These are side-effect-free and easily unit-testable.
 */

import type { SearchCondition, MetaFilters } from './types';

// ---------------------------------------------------------------------------
// Types  (re-exported by AdvancedSearchPanel for convenience)
// ---------------------------------------------------------------------------

/** The active search state emitted to the parent. */
export interface ActiveSearchState {
  mode: 'condition' | 'qb';
  condition: { meta: MetaFilters; data: SearchCondition[] };
  qb: string;
  resultLimit?: number;
  sortBy?: { field: string; order: 'asc' | 'desc' }[];
}

/** Shape of the editing-in-progress state (not yet submitted). */
export interface EditingState {
  condition: { meta: MetaFilters; data: SearchCondition[] };
  qb: string;
  resultLimit?: number;
  sortBy?: { field: string; order: 'asc' | 'desc' }[];
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

export const EMPTY_ACTIVE_SEARCH: ActiveSearchState = {
  mode: 'condition',
  condition: { meta: {}, data: [] },
  qb: '',
  resultLimit: undefined,
  sortBy: undefined,
};

export const EMPTY_EDITING: EditingState = {
  condition: { meta: {}, data: [] },
  qb: '',
  resultLimit: undefined,
  sortBy: undefined,
};

// ---------------------------------------------------------------------------
// URL → ActiveSearchState
// ---------------------------------------------------------------------------

export interface ParseSearchResult {
  search: ActiveSearchState;
  editing: EditingState;
  hasParams: boolean;
  isQBMode: boolean;
}

/**
 * Parse URL search-string (the part after `?`) into an `ActiveSearchState`.
 *
 * @param searchString — raw query string, e.g. `"qb=QB.all()&result_limit=10"`.
 *   Leading `?` is tolerated.
 */
export function parseSearchFromURL(searchString: string): ParseSearchResult {
  const urlParams = new URLSearchParams(
    searchString.startsWith('?') ? searchString.slice(1) : searchString,
  );

  // QB
  const qbFromUrl = urlParams.get('qb');

  // Meta filters
  const meta: MetaFilters = {};
  const cts = urlParams.get('created_time_start');
  const cte = urlParams.get('created_time_end');
  const uts = urlParams.get('updated_time_start');
  const ute = urlParams.get('updated_time_end');
  const cb = urlParams.get('created_by');
  const ub = urlParams.get('updated_by');
  if (cts) meta.created_time_start = cts;
  if (cte) meta.created_time_end = cte;
  if (uts) meta.updated_time_start = uts;
  if (ute) meta.updated_time_end = ute;
  if (cb) meta.created_by = cb;
  if (ub) meta.updated_by = ub;

  // Data conditions
  let parsedConditions: SearchCondition[] = [];
  const dcStr = urlParams.get('data_conditions');
  if (dcStr) {
    try {
      const parsed = JSON.parse(dcStr) as {
        field_path: string;
        operator: string;
        value: unknown;
      }[];
      parsedConditions = parsed.map((c) => ({
        field: c.field_path,
        operator: c.operator,
        value: c.value ?? '',
      })) as SearchCondition[];
    } catch {
      /* ignore parse error */
    }
  }

  // Result limit
  const resultLimitStr = urlParams.get('result_limit');
  const resultLimit = resultLimitStr ? parseInt(resultLimitStr, 10) : undefined;

  // Sort
  let sortBy: { field: string; order: 'asc' | 'desc' }[] | undefined;
  const sortByStr = urlParams.get('sort_by');
  if (sortByStr) {
    try {
      sortBy = JSON.parse(sortByStr) as { field: string; order: 'asc' | 'desc' }[];
    } catch {
      /* ignore parse error */
    }
  }

  const search: ActiveSearchState = {
    mode: qbFromUrl ? 'qb' : 'condition',
    condition: { meta, data: parsedConditions },
    qb: qbFromUrl ?? '',
    resultLimit,
    sortBy,
  };

  const editing: EditingState = {
    condition: { meta, data: parsedConditions },
    qb: qbFromUrl ?? '',
    resultLimit,
    sortBy,
  };

  const hasParams = !!qbFromUrl || Object.keys(meta).length > 0 || parsedConditions.length > 0;

  return { search, editing, hasParams, isQBMode: !!qbFromUrl };
}

// ---------------------------------------------------------------------------
// ActiveSearchState → URL search params
// ---------------------------------------------------------------------------

/**
 * Serialize an `ActiveSearchState` into a flat `Record<string, string>`
 * suitable for `navigate({ search: ... })`.
 */
export function serializeSearchToURL(search: ActiveSearchState): Record<string, string> {
  const params: Record<string, string> = {};

  if (search.mode === 'qb' && search.qb) {
    params.qb = search.qb;
  } else {
    const { meta, data } = search.condition;
    if (data.length > 0) {
      params.data_conditions = JSON.stringify(
        data.map((c) => ({ field_path: c.field, operator: c.operator, value: c.value })),
      );
    }
    if (meta.created_time_start) params.created_time_start = meta.created_time_start;
    if (meta.created_time_end) params.created_time_end = meta.created_time_end;
    if (meta.updated_time_start) params.updated_time_start = meta.updated_time_start;
    if (meta.updated_time_end) params.updated_time_end = meta.updated_time_end;
    if (meta.created_by) params.created_by = meta.created_by;
    if (meta.updated_by) params.updated_by = meta.updated_by;
  }

  if (search.resultLimit) params.result_limit = String(search.resultLimit);
  if (search.sortBy && search.sortBy.length > 0) {
    params.sort_by = JSON.stringify(search.sortBy);
  }

  return params;
}

// ---------------------------------------------------------------------------
// Misc helpers
// ---------------------------------------------------------------------------

/** Count the number of active backend search conditions. */
export function countActiveConditions(search: ActiveSearchState): number {
  if (search.mode === 'qb') return search.qb ? 1 : 0;
  return search.condition.data.length + Object.keys(search.condition.meta).length;
}
