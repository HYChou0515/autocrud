/**
 * ResourceTable 元件 - 從 table 模組 re-export
 *
 * 此檔案保持向後相容性，實際實作已移至 ./table/ 資料夾
 */

export {
  ResourceTable,
  ResourceIdCell,
  SearchForm,
  MetaSearchForm,
  operatorLabels,
  getDefaultOperators,
} from './table';

export type {
  SearchCondition,
  MetaFilters,
  ColumnVariant,
  ColumnOverride,
  SearchableField,
  NormalizedSearchableField,
  ResourceTableProps,
} from './table';
