/**
 * Resource Table 工具函數
 */

import type { MetaFilters, SearchCondition } from './types';

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
