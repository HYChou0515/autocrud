/**
 * ResourceTable 相關類型定義
 */

import type { ResourceConfig } from '../../resources';

/**
 * 搜尋條件介面
 */
export interface SearchCondition {
  field: string;
  operator: string;
  value: string | number | boolean;
}

/**
 * Meta 篩選介面
 */
export interface MetaFilters {
  created_time_start?: string;
  created_time_end?: string;
  updated_time_start?: string;
  updated_time_end?: string;
  created_by?: string;
  updated_by?: string;
}

/**
 * 欄位顯示變體
 */
export type ColumnVariant =
  | 'auto' // 自動判斷（預設）
  | 'string' // 強制顯示為字串
  | 'relative-time' // 相對時間（2小時前）
  | 'full-time' // 完整時間（ISO格式）
  | 'short-time' // 短格式時間（MM/DD HH:mm）
  | 'date' // 只顯示日期（YYYY-MM-DD）
  | 'boolean' // ✅/❌
  | 'array' // 陣列 join(', ')
  | 'json'; // JSON.stringify

/**
 * 欄位覆蓋設定
 */
export interface ColumnOverride {
  label?: string; // 自訂欄位標題
  variant?: ColumnVariant; // 顯示方式
  size?: number; // 欄位寬度
  hidden?: boolean; // 是否隱藏
  render?: (value: unknown) => React.ReactNode; // 自訂渲染函數（優先於 variant）
}

/**
 * 可搜尋欄位的定義
 */
export interface SearchableField {
  name: string; // 欄位名稱（對應 data 中的 key）
  label?: string; // 顯示標籤（預設為 name）
  type: 'string' | 'number' | 'boolean' | 'date' | 'select'; // 搜尋類型
  operators?: (
    | 'eq'
    | 'ne'
    | 'gt'
    | 'gte'
    | 'lt'
    | 'lte'
    | 'in'
    | 'not_in'
    | 'contains'
    | 'starts_with'
    | 'ends_with'
  )[];
  options?: { label: string; value: string | number | boolean }[]; // select/boolean 的選項
}

/**
 * 正規化後的可搜尋欄位（label 必填）
 */
export interface NormalizedSearchableField extends Omit<SearchableField, 'label'> {
  label: string;
}

/**
 * ResourceTable 元件 Props
 */
export interface ResourceTableProps<T> {
  config: ResourceConfig<T>;
  basePath: string;
  columns?: {
    order?: string[]; // 欄位順序（不在此列表的按預設順序放後面）
    overrides?: Record<string, ColumnOverride>; // 覆蓋特定欄位的設定
  };
  searchableFields?: SearchableField[]; // 可搜尋的欄位（用於後端 filter 表單）
  disableQB?: boolean; // 是否啟用 QB 語法搜尋（預設 false）
}

/**
 * 操作符顯示名稱
 */
export const operatorLabels: Record<string, string> = {
  eq: '=',
  ne: '≠',
  gt: '>',
  gte: '≥',
  lt: '<',
  lte: '≤',
  in: 'IN',
  not_in: 'NOT IN',
  contains: '包含',
  starts_with: '開頭',
  ends_with: '結尾',
};

/**
 * 取得欄位類型的預設操作符列表
 */
export const getDefaultOperators = (type: SearchableField['type']) => {
  switch (type) {
    case 'string':
      return ['eq', 'ne', 'contains', 'starts_with', 'ends_with'];
    case 'number':
    case 'date':
      return ['eq', 'ne', 'gt', 'gte', 'lt', 'lte'];
    case 'boolean':
      return ['eq', 'ne'];
    case 'select':
      return ['eq', 'ne', 'in'];
    default:
      return ['eq', 'ne'];
  }
};
