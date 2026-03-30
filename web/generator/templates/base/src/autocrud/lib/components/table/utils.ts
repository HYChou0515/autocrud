/**
 * Resource Table 工具函數
 */

import type { MRT_ColumnFiltersState, MRT_SortingState } from 'mantine-react-table';
import type { MetaFilters, SearchCondition } from './types';
import { META_SEARCHABLE_FIELDS } from './searchFieldUtils';

// ---------------------------------------------------------------------------
// Server-capability constants
// ---------------------------------------------------------------------------

/**
 * Meta columns that the backend can sort on.
 * Corresponds to ResourceMetaSortKey in autocrud/types.py.
 */
export const SERVER_META_SORT_KEYS = ['resource_id', 'created_time', 'updated_time'] as const;

/**
 * Default sorting state for ResourceTable.
 * Sorts by updated_time descending so the most recently modified items appear first.
 */
export const DEFAULT_SORTING: MRT_SortingState = [{ id: 'updated_time', desc: true }];

/**
 * Meta columns that the backend can filter on via dedicated query params.
 * Maps column id → the backend query parameter name(s) and conversion strategy.
 */
export const SERVER_META_FILTER_COLUMNS: Record<
  string,
  { paramName: string; convert: (value: unknown) => Record<string, unknown> }
> = {
  created_by: {
    paramName: 'created_bys',
    convert: (v) => ({ created_bys: [String(v)] }),
  },
  updated_by: {
    paramName: 'updated_bys',
    convert: (v) => ({ updated_bys: [String(v)] }),
  },
  is_deleted: {
    paramName: 'is_deleted',
    convert: (v) => {
      const str = String(v).toLowerCase();
      return { is_deleted: str === 'true' || str === '1' };
    },
  },
};

/**
 * All 8 standard meta fields.
 * Used for client-side sorting and advanced search sort field options.
 */
export const META_SORT_FIELDS = [
  'resource_id',
  'created_time',
  'updated_time',
  'created_by',
  'updated_by',
  'schema_version',
  'is_deleted',
  'current_revision_id',
] as const;

// ---------------------------------------------------------------------------
// Server-capability queries
// ---------------------------------------------------------------------------

/** Check whether a column can be sorted server-side. */
export function isServerSortable(columnId: string, indexedFields?: string[]): boolean {
  if ((SERVER_META_SORT_KEYS as readonly string[]).includes(columnId)) return true;
  if (indexedFields && indexedFields.includes(columnId)) return true;
  return false;
}

/** Check whether a column can be filtered server-side. */
export function isServerFilterable(columnId: string, indexedFields?: string[]): boolean {
  if (columnId in SERVER_META_FILTER_COLUMNS) return true;
  if (indexedFields && indexedFields.includes(columnId)) return true;
  return false;
}

// ---------------------------------------------------------------------------
// Table mode computation
// ---------------------------------------------------------------------------

export type TableMode = 'server' | 'client';

export interface ComputeTableModeArgs {
  debouncedGlobalFilter: string;
  sorting: MRT_SortingState;
  columnFilters: MRT_ColumnFiltersState;
  indexedFields?: string[];
  /** Advanced search data conditions — non-indexed fields trigger client mode. */
  activeSearchData?: SearchCondition[];
  /** Advanced search sort-by — non-indexed/non-meta fields trigger client mode. */
  activeSearchSortBy?: { field: string; order: 'asc' | 'desc' }[];
}

/**
 * Determine whether the table should operate in server or client mode.
 *
 * Returns 'client' when any operation requires client-side processing:
 *  - globalFilter is non-empty (free-text search across all fields)
 *  - any column sort targets a non-server-sortable column
 *  - any column filter targets a non-server-filterable column
 */
export function computeTableMode({
  debouncedGlobalFilter,
  sorting,
  columnFilters,
  indexedFields,
  activeSearchData,
  activeSearchSortBy,
}: ComputeTableModeArgs): TableMode {
  // Trigger 1: global free-text filter
  if (debouncedGlobalFilter) return 'client';

  // Trigger 2: non-server-sortable column in MRT sorting
  for (const sort of sorting) {
    if (!isServerSortable(sort.id, indexedFields)) return 'client';
  }

  // Trigger 3: non-server-filterable column in MRT column filters
  for (const filter of columnFilters) {
    if (filter.value == null || filter.value === '') continue;
    if (!isServerFilterable(filter.id, indexedFields)) return 'client';
  }

  // Trigger 4: advanced search data conditions on non-indexed fields
  if (activeSearchData) {
    for (const cond of activeSearchData) {
      if (!indexedFields || !indexedFields.includes(cond.field)) return 'client';
    }
  }

  // Trigger 5: advanced search sort on non-indexed/non-meta fields
  if (activeSearchSortBy) {
    for (const s of activeSearchSortBy) {
      if (!s.field) continue;
      const isMeta = (META_SORT_FIELDS as readonly string[]).includes(s.field);
      const isIndexed = indexedFields && indexedFields.includes(s.field);
      if (!isMeta && !isIndexed) return 'client';
    }
  }

  return 'server';
}

// ---------------------------------------------------------------------------
// MRT state → backend params conversion
// ---------------------------------------------------------------------------

/**
 * Convert MRT sorting state to backend `sorts` JSON string.
 * Only includes server-sortable columns; non-sortable ones are omitted
 * (they'll be handled client-side by MRT).
 */
export function mrtSortingToSorts(sorting: MRT_SortingState, indexedFields?: string[]): string {
  const serverSorts = sorting.filter((s) => isServerSortable(s.id, indexedFields));
  if (serverSorts.length === 0) return '';

  const sortsArray = serverSorts.map((s) => {
    const direction = s.desc ? '-' : '+';
    if ((SERVER_META_SORT_KEYS as readonly string[]).includes(s.id)) {
      return { type: 'meta', key: s.id, direction };
    }
    return { type: 'data', field_path: s.id, direction };
  });

  return JSON.stringify(sortsArray);
}

/**
 * Convert MRT column filters to backend query params.
 * Only includes server-filterable columns. Returns an object with
 * backend param keys ready to merge into the request params.
 *
 * - Meta filter columns → dedicated params (created_bys, updated_bys, is_deleted)
 * - Indexed data columns → data_conditions array (string uses "contains", others "eq")
 */
export function mrtFiltersToParams(
  columnFilters: MRT_ColumnFiltersState,
  indexedFields?: string[],
): {
  serverParams: Record<string, unknown>;
  dataConditions: Array<{ field_path: string; operator: string; value: unknown }>;
} {
  const serverParams: Record<string, unknown> = {};
  const dataConditions: Array<{ field_path: string; operator: string; value: unknown }> = [];

  for (const filter of columnFilters) {
    if (filter.value == null || filter.value === '') continue;

    // Meta filter columns
    const metaDef = SERVER_META_FILTER_COLUMNS[filter.id];
    if (metaDef) {
      Object.assign(serverParams, metaDef.convert(filter.value));
      continue;
    }

    // Indexed data columns
    if (indexedFields && indexedFields.includes(filter.id)) {
      const value = filter.value;
      // Use "contains" for strings, "eq" for everything else
      const operator = typeof value === 'string' ? 'contains' : 'eq';
      dataConditions.push({ field_path: filter.id, operator, value });
    }
  }

  return { serverParams, dataConditions };
}

/**
 * 將 ISO 時間字串轉換為 Python dt.datetime(...) 格式
 */
export function isoToPythonDatetime(isoStr: string): string {
  const d = new Date(isoStr);
  if (isNaN(d.getTime())) return `"${isoStr}"`; // fallback
  return `dt.datetime(${d.getFullYear()}, ${d.getMonth() + 1}, ${d.getDate()}, ${d.getHours()}, ${d.getMinutes()}, ${d.getSeconds()})`;
}

/**
 * 將條件轉換為 QB 語法（包含 Meta 和 Data 條件）
 * 注意：resultLimit 和 sortBy 應透過 .limit() 和 .order_by() 方法鏈加入
 */
export function conditionToQB(
  meta: MetaFilters,
  data: SearchCondition[],
  resultLimit?: number,
  sortBy?: { field: string; order: 'asc' | 'desc' }[],
): string {
  const parts: string[] = [];

  // 轉換 Meta 條件 - 使用 QB.created_time().gte(dt.datetime(...)) 語法
  if (meta.created_time_start) {
    parts.push(`QB.created_time().gte(${isoToPythonDatetime(meta.created_time_start)})`);
  }
  if (meta.created_time_end) {
    parts.push(`QB.created_time().lte(${isoToPythonDatetime(meta.created_time_end)})`);
  }
  if (meta.updated_time_start) {
    parts.push(`QB.updated_time().gte(${isoToPythonDatetime(meta.updated_time_start)})`);
  }
  if (meta.updated_time_end) {
    parts.push(`QB.updated_time().lte(${isoToPythonDatetime(meta.updated_time_end)})`);
  }
  if (meta.created_by) {
    parts.push(`QB.created_by().eq("${meta.created_by}")`);
  }
  if (meta.updated_by) {
    parts.push(`QB.updated_by().eq("${meta.updated_by}")`);
  }

  // 轉換 Data conditions
  for (const cond of data) {
    const op = cond.operator;
    const val = typeof cond.value === 'string' ? `"${cond.value}"` : cond.value;

    // 使用 QB["field"] 語法
    const field = `QB["${cond.field}"]`;

    switch (op) {
      // 比較運算符 - 需要加括號，避免 Python 運算符優先順序問題
      // 例: (QB["level"] >= 6).order_by(...) 而非 QB["level"] >= 6.order_by(...)
      case 'eq':
        parts.push(`(${field} == ${val})`);
        break;
      case 'ne':
        parts.push(`(${field} != ${val})`);
        break;
      case 'gt':
        parts.push(`(${field} > ${val})`);
        break;
      case 'gte':
        parts.push(`(${field} >= ${val})`);
        break;
      case 'lt':
        parts.push(`(${field} < ${val})`);
        break;
      case 'lte':
        parts.push(`(${field} <= ${val})`);
        break;
      // 字串方法 - 使用 .method() 語法，不需要括號
      case 'contains':
        parts.push(`${field}.contains(${val})`);
        break;
      case 'starts_with':
        parts.push(`${field}.starts_with(${val})`);
        break;
      case 'ends_with':
        parts.push(`${field}.ends_with(${val})`);
        break;
      default:
        parts.push(`(${field} == ${val})`);
    }
  }

  // 基礎查詢條件（使用 & 連接）
  // 如果沒有條件，使用 QB.all() 表示查詢全部
  let qb = parts.length > 0 ? parts.join(' & ') : 'QB.all()';

  // 判斷是否需要鏈式呼叫（.order_by / .limit）
  const needsChaining =
    (sortBy && sortBy.some((s) => s.field)) || (resultLimit != null && resultLimit > 0);

  // 如果有多個 parts 且需要鏈式呼叫，外層要加括號
  // 例: (condA & condB).order_by(...) 而非 condA & condB.order_by(...)
  if (needsChaining && parts.length > 1) {
    qb = `(${qb})`;
  }

  // 加入排序（多層排序）
  if (sortBy && sortBy.length > 0) {
    const validSorts = sortBy.filter((s) => s.field); // 過濾掉未選擇欄位的
    if (validSorts.length > 0) {
      const orderByArgs = validSorts
        .map((s) => `"${s.order === 'desc' ? '-' : ''}${s.field}"`)
        .join(', ');
      qb = `${qb}.order_by(${orderByArgs})`;
    }
  }

  // 加入結果數量限制
  if (resultLimit) {
    qb = `${qb}.limit(${resultLimit})`;
  }

  return qb;
}

// ---------------------------------------------------------------------------
// buildRequestParams — pure function extracted from ResourceTable useMemo
// ---------------------------------------------------------------------------

/** Maximum number of items fetched from the backend for client-side operations */
const CLIENT_FETCH_LIMIT = 1000;

import type { ActiveSearchState } from './searchUtils';

export interface BuildRequestParamsArgs {
  mode: TableMode;
  pagination: { pageIndex: number; pageSize: number };
  activeSearch: ActiveSearchState;
  sorting: MRT_SortingState;
  columnFilters: MRT_ColumnFiltersState;
  indexedFields?: string[];
  alwaysSearchCondition?: { field: string; operator: string; value: unknown }[];
}

/**
 * Build the request params for the resource list API call.
 *
 * **Key rule**: when `activeSearch.mode === 'qb'` and `activeSearch.qb` is
 * non-empty, the `sorts` parameter is **never** included. The backend rejects
 * `qb` + `sorts` together (HTTP 422). Ordering must be expressed inside the
 * QB expression itself (e.g. `.order_by("-updated_time")`).
 */
export function buildRequestParams({
  mode,
  pagination,
  activeSearch,
  sorting,
  columnFilters,
  indexedFields,
  alwaysSearchCondition,
}: BuildRequestParamsArgs): Record<string, unknown> {
  const baseParams: Record<string, unknown> = {};
  const isQBMode = activeSearch.mode === 'qb' && !!activeSearch.qb;

  // --- Pagination ---
  if (mode === 'server') {
    baseParams.limit = pagination.pageSize;
    baseParams.offset = pagination.pageIndex * pagination.pageSize;
  } else {
    baseParams.limit = CLIENT_FETCH_LIMIT;
  }

  // --- AdvancedSearchPanel conditions ---
  if (isQBMode) {
    // QB mode: just send the QB string — NO sorts, data_conditions, or meta filters
    baseParams.qb = activeSearch.qb;
  } else {
    // Client mode default sort (updated_time desc)
    if (mode === 'client') {
      baseParams.sorts = JSON.stringify([{ type: 'meta', key: 'updated_time', direction: '-' }]);
    }

    // Condition mode
    const { meta, data: advancedData } = activeSearch.condition;

    // Advanced panel result limit (cap at CLIENT_FETCH_LIMIT)
    if (activeSearch.resultLimit) {
      baseParams.limit = Math.min(
        activeSearch.resultLimit,
        mode === 'server' ? activeSearch.resultLimit : CLIENT_FETCH_LIMIT,
      );
    }

    // Advanced panel sorts (only in server mode — in client mode MRT handles sorting)
    // Filter to only indexed + meta sort fields; non-indexed sorts applied client-side.
    if (mode === 'server' && activeSearch.sortBy && activeSearch.sortBy.length > 0) {
      const serverSorts = activeSearch.sortBy.filter(
        (s) =>
          (indexedFields ?? []).includes(s.field) ||
          (META_SORT_FIELDS as readonly string[]).includes(s.field),
      );
      if (serverSorts.length > 0) {
        const sortsStr = sortByToSorts(serverSorts);
        if (sortsStr) baseParams.sorts = sortsStr;
      }
    }

    // Advanced panel data_conditions — only send indexed conditions to server;
    // non-indexed conditions are applied client-side in ResourceTable.
    // Meta conditions that are server-filterable get converted to query params.
    const { serverConditions: indexedAdvanced, serverMetaConditions: metaConditions } =
      splitConditionsByIndex(advancedData, indexedFields ?? []);
    const advancedConditions = indexedAdvanced.map((condition) => ({
      field_path: condition.field,
      operator: condition.operator,
      value: condition.value,
    }));

    // Advanced panel meta filters (from MetaSearchForm)
    if (meta.created_time_start) baseParams.created_time_start = meta.created_time_start;
    if (meta.created_time_end) baseParams.created_time_end = meta.created_time_end;
    if (meta.updated_time_start) baseParams.updated_time_start = meta.updated_time_start;
    if (meta.updated_time_end) baseParams.updated_time_end = meta.updated_time_end;
    if (meta.created_by) baseParams.created_bys = [meta.created_by];
    if (meta.updated_by) baseParams.updated_bys = [meta.updated_by];

    // Server-filterable meta conditions from SearchForm (Bug 2)
    for (const mc of metaConditions) {
      const metaDef = SERVER_META_FILTER_COLUMNS[mc.field];
      if (metaDef) {
        Object.assign(baseParams, metaDef.convert(mc.value));
      }
    }

    // --- MRT column filters (server-filterable ones sent to backend in both modes) ---
    const { serverParams, dataConditions: mrtDataConditions } = mrtFiltersToParams(
      columnFilters,
      indexedFields,
    );
    Object.assign(baseParams, serverParams);

    // Merge advanced + MRT data_conditions
    const allDataConditions = [...advancedConditions, ...mrtDataConditions];
    if (allDataConditions.length > 0) {
      baseParams.data_conditions = JSON.stringify(allDataConditions);
    }
  }

  // --- MRT column sorting (server mode only, condition mode only) ---
  if (mode === 'server' && sorting.length > 0 && !baseParams.sorts && !isQBMode) {
    const sortsStr = mrtSortingToSorts(sorting, indexedFields);
    if (sortsStr) baseParams.sorts = sortsStr;
  }

  // --- Always-on search conditions (e.g. filter for a specific tag) ---
  applyAlwaysSearchConditions(baseParams, alwaysSearchCondition);

  return baseParams;
}

// ---------------------------------------------------------------------------
// Always-on search conditions — shared by ResourceTable & RefTableSelectModal
// ---------------------------------------------------------------------------

/**
 * Merge always-on search conditions into the request params.
 *
 * - **Meta fields** (e.g. `is_deleted`, `created_by`) that are in
 *   `SERVER_META_FILTER_COLUMNS` are converted to direct query params
 *   via the column's `convert()` helper — just like MRT column filters.
 * - **Data fields** are appended to the existing `data_conditions` array
 *   so they are always sent to the backend on every request.
 *
 * This is a pure helper — it mutates `params` in-place for convenience.
 */
export function applyAlwaysSearchConditions(
  params: Record<string, unknown>,
  conditions?: { field: string; operator: string; value: unknown }[],
): void {
  if (!conditions || conditions.length === 0) return;

  const dataConditions: { field_path: string; operator: string; value: unknown }[] = [];

  for (const c of conditions) {
    const metaDef = SERVER_META_FILTER_COLUMNS[c.field];
    if (metaDef) {
      // Meta field → convert to direct query param (e.g. is_deleted=false)
      Object.assign(params, metaDef.convert(c.value));
    } else {
      // Data field → collect into data_conditions
      dataConditions.push({
        field_path: c.field,
        operator: c.operator,
        value: c.value,
      });
    }
  }

  if (dataConditions.length > 0) {
    const existing = params.data_conditions
      ? (JSON.parse(params.data_conditions as string) as unknown[])
      : [];
    params.data_conditions = JSON.stringify([...existing, ...dataConditions]);
  }
}

// ---------------------------------------------------------------------------
// Client-side filtering & sorting helpers
// ---------------------------------------------------------------------------

/** Set of meta field names from META_SEARCHABLE_FIELDS for fast lookup */
const META_FIELD_NAMES = new Set(META_SEARCHABLE_FIELDS.map((f) => f.name));

/**
 * Check whether a field name is a meta field (from META_SEARCHABLE_FIELDS).
 */
export function isMetaField(field: string): boolean {
  return META_FIELD_NAMES.has(field);
}

/**
 * Split advanced search data conditions into server (indexed) and client
 * (non-indexed) buckets.
 *
 * Meta fields that are server-filterable (in SERVER_META_FILTER_COLUMNS)
 * are classified as server conditions. Other meta fields and non-indexed
 * data fields go to client.
 */
export function splitConditionsByIndex(
  conditions: SearchCondition[],
  indexedFields: string[],
): {
  serverConditions: SearchCondition[];
  clientConditions: SearchCondition[];
  serverMetaConditions: SearchCondition[];
} {
  const serverConditions: SearchCondition[] = [];
  const clientConditions: SearchCondition[] = [];
  const serverMetaConditions: SearchCondition[] = [];
  for (const c of conditions) {
    if (isMetaField(c.field)) {
      // Meta field: check if server-filterable
      if (c.field in SERVER_META_FILTER_COLUMNS) {
        serverMetaConditions.push(c);
      } else {
        clientConditions.push(c);
      }
    } else if (indexedFields.includes(c.field)) {
      serverConditions.push(c);
    } else {
      clientConditions.push(c);
    }
  }
  return { serverConditions, clientConditions, serverMetaConditions };
}

/**
 * Resolve a potentially nested value from an object using a dot-path.
 * E.g. getNestedValue({ a: { b: { c: 1 } } }, 'a.b.c') → 1
 */
export function getNestedValue(obj: any, path: string): any {
  if (obj == null) return undefined;
  // Fast path: no dots
  if (!path.includes('.')) return obj[path];
  const parts = path.split('.');
  let current = obj;
  for (const part of parts) {
    if (current == null) return undefined;
    current = current[part];
  }
  return current;
}

/**
 * Apply search conditions to rows client-side (AND logic).
 * Supports operators: eq, ne, gt, gte, lt, lte, contains, starts_with, ends_with.
 * Handles numeric coercion for comparison operators.
 * Supports meta fields (looked up from row.meta) and dot-path data fields.
 */
export function applyClientConditions(rows: any[], conditions: SearchCondition[]): any[] {
  if (conditions.length === 0) return rows;

  const metaFields = META_SORT_FIELDS as readonly string[];

  return rows.filter((row) =>
    conditions.every((cond) => {
      // Determine where to look up the value: meta or data
      const isMeta = metaFields.includes(cond.field) || isMetaField(cond.field);
      const fieldValue = isMeta ? row?.meta?.[cond.field] : getNestedValue(row?.data, cond.field);
      const condValue = cond.value;

      // Coerce to numbers for comparison if possible
      const numField = Number(fieldValue);
      const numCond = Number(condValue);
      const canCompareNum = !isNaN(numField) && !isNaN(numCond);

      switch (cond.operator) {
        case 'eq':
          return fieldValue == condValue;
        case 'ne':
          return fieldValue != condValue;
        case 'gt':
          return canCompareNum ? numField > numCond : String(fieldValue) > String(condValue);
        case 'gte':
          return canCompareNum ? numField >= numCond : String(fieldValue) >= String(condValue);
        case 'lt':
          return canCompareNum ? numField < numCond : String(fieldValue) < String(condValue);
        case 'lte':
          return canCompareNum ? numField <= numCond : String(fieldValue) <= String(condValue);
        case 'contains':
          return String(fieldValue ?? '').includes(String(condValue));
        case 'starts_with':
          return String(fieldValue ?? '').startsWith(String(condValue));
        case 'ends_with':
          return String(fieldValue ?? '').endsWith(String(condValue));
        default:
          return fieldValue == condValue;
      }
    }),
  );
}

/**
 * Sort rows client-side by multiple sort criteria.
 * Supports data fields and meta fields. Does NOT mutate the original array.
 */
export function applyClientSort(
  rows: any[],
  sortBy: { field: string; order: 'asc' | 'desc' }[],
): any[] {
  if (sortBy.length === 0) return [...rows];

  const metaFields = META_SORT_FIELDS as readonly string[];

  return [...rows].sort((a, b) => {
    for (const s of sortBy) {
      if (!s.field) continue;
      const isMeta = metaFields.includes(s.field);
      const valA = isMeta ? a?.meta?.[s.field] : a?.data?.[s.field];
      const valB = isMeta ? b?.meta?.[s.field] : b?.data?.[s.field];

      let cmp: number;
      if (valA == null && valB == null) {
        cmp = 0;
      } else if (valA == null) {
        cmp = -1;
      } else if (valB == null) {
        cmp = 1;
      } else if (typeof valA === 'number' && typeof valB === 'number') {
        cmp = valA - valB;
      } else {
        cmp = String(valA).localeCompare(String(valB));
      }

      if (cmp !== 0) return s.order === 'desc' ? -cmp : cmp;
    }
    return 0;
  });
}

/**
 * 將 sortBy 轉換為 API 需要的 sorts 格式
 * Meta 欄位使用 key，Data 欄位使用 field_path
 */
export function sortByToSorts(sortBy: { field: string; order: 'asc' | 'desc' }[]): string {
  const validSorts = sortBy.filter((s) => s.field); // 過濾掉未選擇欄位的
  if (validSorts.length === 0) return '';

  const metaFields = [
    'created_time',
    'updated_time',
    'created_by',
    'updated_by',
    'resource_id',
    'current_revision_id',
    'schema_version',
    'is_deleted',
  ];

  const sortsArray = validSorts.map((s) => {
    const isMeta = metaFields.includes(s.field);
    const direction = s.order === 'desc' ? '-' : '+';

    if (isMeta) {
      // Meta 欄位使用 key
      return {
        type: 'meta',
        key: s.field,
        direction,
      };
    } else {
      // Data 欄位使用 field_path
      return {
        type: 'data',
        field_path: s.field,
        direction,
      };
    }
  });

  return JSON.stringify(sortsArray);
}
