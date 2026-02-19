/**
 * ResourceTable 模組統一導出
 */

// 主元件
export { ResourceTable } from './ResourceTable';

// 子元件
export { ResourceIdCell } from '../common/ResourceIdCell';
export { RevisionIdCell } from '../common/RevisionIdCell';
export { SearchForm } from './SearchForm';
export { MetaSearchForm } from './MetaSearchForm';
export { AdvancedSearchPanel } from './AdvancedSearchPanel';
export type { ActiveSearchState, AdvancedSearchPanelProps } from './AdvancedSearchPanel';

// Search utilities (pure functions)
export {
  parseSearchFromURL,
  serializeSearchToURL,
  countActiveConditions,
  EMPTY_ACTIVE_SEARCH,
  EMPTY_EDITING,
} from './searchUtils';
export type { EditingState, ParseSearchResult } from './searchUtils';

// Hook
export { useAdvancedSearch } from '../../hooks/useAdvancedSearch';
export type {
  UseAdvancedSearchOptions,
  UseAdvancedSearchReturn,
} from '../../hooks/useAdvancedSearch';

// CellFieldRenderer registry
export { CellFieldRenderer, renderCellValue, CELL_RENDERERS } from '../field/CellFieldRenderer';
export type { CellRenderContext } from '../field/CellFieldRenderer';

// Cell helpers (for custom cell renderers)
export {
  renderBinaryCell,
  renderObjectPreview,
  getContentTypeIcon,
  formatBinarySize,
  getBlobUrl,
  isImageContentType,
} from '../field/CellFieldRenderer/helpers';

// 工具函數
export { conditionToQB, sortByToSorts, isoToPythonDatetime } from './utils';

// 類型
export type {
  SearchCondition,
  MetaFilters,
  ColumnVariant,
  ColumnOverride,
  SearchableField,
  NormalizedSearchableField,
  ResourceTableProps,
} from './types';

// 常數與工具函數
export { operatorLabels, getDefaultOperators } from './types';
