/**
 * Resource Table 工具函數
 */

import type { MRT_ColumnFiltersState, MRT_SortingState } from 'mantine-react-table';
import type { MetaFilters, SearchCondition } from './types';

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
      // 比較運算符 - 直接用 Python 語法
      case 'eq':
        parts.push(`${field} == ${val}`);
        break;
      case 'ne':
        parts.push(`${field} != ${val}`);
        break;
      case 'gt':
        parts.push(`${field} > ${val}`);
        break;
      case 'gte':
        parts.push(`${field} >= ${val}`);
        break;
      case 'lt':
        parts.push(`${field} < ${val}`);
        break;
      case 'lte':
        parts.push(`${field} <= ${val}`);
        break;
      // 字串方法 - 使用 .method() 語法
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
        parts.push(`${field} == ${val}`);
    }
  }

  // 基礎查詢條件（使用 & 連接）
  // 如果沒有條件，使用 QB.all() 表示查詢全部
  let qb = parts.length > 0 ? parts.join(' & ') : 'QB.all()';

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
