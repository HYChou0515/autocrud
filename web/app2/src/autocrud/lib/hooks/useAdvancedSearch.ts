/**
 * useAdvancedSearch — Hook that encapsulates all advanced-search state,
 * URL synchronisation, editing callbacks, and submit/clear actions.
 *
 * The companion component `AdvancedSearchPanel` becomes a thin JSX shell
 * that simply destructures the return value of this hook.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useLocation } from '@tanstack/react-router';
import type { MRT_ColumnFiltersState, MRT_SortingState } from 'mantine-react-table';
import type { ResourceConfig } from '../resources';
import type {
  SearchCondition,
  MetaFilters,
  NormalizedSearchableField,
  SearchableField,
} from '../components/table/types';
import { conditionToQB, SERVER_META_FILTER_COLUMNS } from '../components/table/utils';
import { fieldsToSearchableFields } from '../components/table/searchFieldUtils';
import {
  type ActiveSearchState,
  type EditingState,
  EMPTY_ACTIVE_SEARCH,
  EMPTY_EDITING,
  parseSearchFromURL,
  serializeSearchToURL,
  countActiveConditions,
} from '../components/table/searchUtils';

// ---------------------------------------------------------------------------
// Pure state-transition helpers (exported for testing)
// ---------------------------------------------------------------------------

/** Parse a NumberInput value into an optional number. */
export function parseResultLimit(value: number | string): number | undefined {
  if (typeof value === 'number') return value;
  if (value === '') return undefined;
  return parseInt(value, 10);
}

/** Build the ActiveSearchState for a condition-mode submit. */
export function buildConditionSearch(editing: EditingState): ActiveSearchState {
  return {
    mode: 'condition',
    condition: editing.condition,
    qb: '',
    resultLimit: editing.resultLimit,
    sortBy: editing.sortBy,
  };
}

/** Build the ActiveSearchState for a QB-mode submit. */
export function buildQBSearch(editing: EditingState): ActiveSearchState {
  return {
    mode: 'qb',
    condition: { meta: {}, data: [] },
    qb: editing.qb,
    resultLimit: editing.resultLimit,
    sortBy: editing.sortBy,
  };
}

/** Compute sort-field options from searchable fields or config fields + meta. */
export function buildSortFieldOptions(
  normalizedFields: readonly { name: string; label: string }[],
  configFields: readonly { name: string; label: string }[],
): { value: string; label: string }[] {
  const dataFields = normalizedFields.length > 0 ? normalizedFields : configFields;
  const existing = new Set(dataFields.map((f) => f.name));

  const metaOptions = [
    { value: 'created_time', label: '建立時間' },
    { value: 'updated_time', label: '更新時間' },
    { value: 'created_by', label: '建立者' },
    { value: 'updated_by', label: '更新者' },
  ];

  return [
    ...dataFields.map((f) => ({ value: f.name, label: f.label })),
    ...metaOptions.filter((m) => !existing.has(m.value)),
  ];
}

/** Normalise searchable fields — default label to name. */
export function normalizeSearchableFields(fields?: SearchableField[]): NormalizedSearchableField[] {
  return fields?.map((f) => ({ ...f, label: f.label || f.name })) ?? [];
}

// ---------------------------------------------------------------------------
// Options / Return interfaces
// ---------------------------------------------------------------------------

export interface UseAdvancedSearchOptions {
  config: ResourceConfig;
  searchableFields?: SearchableField[];
  disableQB?: boolean;
  /** Called whenever the active (submitted) search state changes. */
  onSearchChange: (search: ActiveSearchState) => void;
  /** MRT column filters — synced into advanced search conditions. */
  mrtColumnFilters?: MRT_ColumnFiltersState;
  /** MRT sorting — synced bidirectionally with advanced search sorts. */
  mrtSorting?: MRT_SortingState;
  /** Callback to sync advanced search sort back to MRT sorting. */
  onMrtSortingChange?: (sorting: MRT_SortingState) => void;
}

export interface UseAdvancedSearchReturn {
  // UI state
  searchMode: 'condition' | 'qb';
  advancedOpen: boolean;
  setAdvancedOpen: React.Dispatch<React.SetStateAction<boolean>>;

  // Search state
  activeSearch: ActiveSearchState;
  editingState: EditingState;

  // Editing callbacks
  handleMetaConditionChange: (filters: MetaFilters, isDirty: boolean) => void;
  handleDataConditionChange: (conditions: SearchCondition[], isDirty: boolean) => void;
  handleQBTextChange: (text: string) => void;
  handleResultLimitChange: (value: number | string) => void;
  handleSortByChange: (sortBy: { field: string; order: 'asc' | 'desc' }[] | undefined) => void;

  // Submit / clear
  handleConditionSearch: () => void;
  handleConditionClear: () => void;
  handleQBSubmit: () => void;
  handleQBClear: () => void;
  handleSwitchToQB: () => void;
  handleModeSwitch: (value: string) => void;

  // Computed
  normalizedSearchableFields: NormalizedSearchableField[];
  sortFieldOptions: { value: string; label: string }[];
  activeBackendCount: number;

  // Filter depth control
  filterDepth: number;
  setFilterDepth: (depth: number) => void;
  maxFilterDepth: number;

  // MRT-derived conditions (read-only display in SearchForm)
  mrtDerivedConditions: SearchCondition[];
  mrtDerivedMetaFilters: MetaFilters;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// MRT ↔ Advanced Search sync helpers (exported for testing)
// ---------------------------------------------------------------------------

/** Convert MRT column filters to SearchCondition[] + MetaFilters. */
export function mrtFiltersToConditions(columnFilters: MRT_ColumnFiltersState): {
  dataConditions: SearchCondition[];
  metaFilters: MetaFilters;
} {
  const dataConditions: SearchCondition[] = [];
  const metaFilters: MetaFilters = {};

  for (const filter of columnFilters) {
    if (filter.value == null || filter.value === '') continue;

    // Meta filter columns → metaFilters
    if (filter.id in SERVER_META_FILTER_COLUMNS) {
      if (filter.id === 'created_by') {
        metaFilters.created_by = String(filter.value);
      } else if (filter.id === 'updated_by') {
        metaFilters.updated_by = String(filter.value);
      }
      // is_deleted is handled separately; skip for now
      continue;
    }

    // Data field → SearchCondition
    const operator = typeof filter.value === 'string' ? 'contains' : 'eq';
    dataConditions.push({
      field: filter.id,
      operator,
      value: filter.value as string | number | boolean,
    });
  }

  return { dataConditions, metaFilters };
}

/** Convert MRT sorting to advanced search sortBy. */
export function mrtSortingToSortBy(
  sorting: MRT_SortingState,
): { field: string; order: 'asc' | 'desc' }[] {
  return sorting.map((s) => ({ field: s.id, order: s.desc ? 'desc' : 'asc' }));
}

/** Convert advanced search sortBy to MRT sorting. */
export function sortByToMrtSorting(
  sortBy: { field: string; order: 'asc' | 'desc' }[] | undefined,
): MRT_SortingState {
  if (!sortBy) return [];
  return sortBy.filter((s) => s.field).map((s) => ({ id: s.field, desc: s.order === 'desc' }));
}

export function useAdvancedSearch({
  config,
  searchableFields,
  onSearchChange,
  mrtColumnFilters,
  mrtSorting,
  onMrtSortingChange,
}: UseAdvancedSearchOptions): UseAdvancedSearchReturn {
  const navigate = useNavigate();
  const location = useLocation();

  const [searchMode, setSearchMode] = useState<'condition' | 'qb'>('condition');
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [activeSearch, setActiveSearch] = useState<ActiveSearchState>(EMPTY_ACTIVE_SEARCH);
  const [editingState, setEditingState] = useState<EditingState>({ ...EMPTY_EDITING });
  const [filterDepth, setFilterDepth] = useState(1);

  const lastPathnameRef = useRef<string>(location.pathname);
  const isInternalUpdate = useRef(false);

  // ---- Notify parent whenever activeSearch changes ----
  useEffect(() => {
    onSearchChange(activeSearch);
  }, [activeSearch, onSearchChange]);

  // ---- URL → state sync ----
  useEffect(() => {
    // Page navigation — reset everything
    if (location.pathname !== lastPathnameRef.current) {
      lastPathnameRef.current = location.pathname;
      setSearchMode('condition');
      setAdvancedOpen(false);
      setActiveSearch(EMPTY_ACTIVE_SEARCH);
      setEditingState({ ...EMPTY_EDITING });
      return;
    }

    // Skip if this change was triggered by our own state → URL sync
    if (isInternalUpdate.current) {
      isInternalUpdate.current = false;
      return;
    }

    const queryString = location.href.split('?')[1] || '';
    const { search, editing, hasParams, isQBMode } = parseSearchFromURL(queryString);

    setActiveSearch(search);
    setEditingState(editing);
    if (isQBMode) setSearchMode('qb');
    setAdvancedOpen(hasParams);
  }, [location.href]);

  // ---- state → URL sync ----
  useEffect(() => {
    const searchParams = serializeSearchToURL(activeSearch);
    isInternalUpdate.current = true;
    navigate({ to: location.pathname, search: searchParams, replace: true });
  }, [activeSearch, navigate, location.pathname]);

  // ---- Auto-generate searchable fields when not manually provided ----
  const autoSearchableFields = useMemo(() => {
    if (searchableFields && searchableFields.length > 0) return undefined;
    return fieldsToSearchableFields(config.fields, config.indexedFields, filterDepth);
  }, [searchableFields, config.fields, config.indexedFields, filterDepth]);

  const effectiveSearchableFields = searchableFields ?? autoSearchableFields;

  const normalizedSearchableFields = useMemo(
    () => normalizeSearchableFields(effectiveSearchableFields),
    [effectiveSearchableFields],
  );

  const maxFilterDepth = useMemo(() => config.maxFormDepth ?? 1, [config.maxFormDepth]);

  const sortFieldOptions = useMemo(
    () => buildSortFieldOptions(normalizedSearchableFields, config.fields),
    [normalizedSearchableFields, config.fields],
  );

  // ---- MRT column filters → derived conditions (read-only display) ----
  const { mrtDerivedConditions, mrtDerivedMetaFilters } = useMemo(() => {
    if (!mrtColumnFilters || mrtColumnFilters.length === 0) {
      return {
        mrtDerivedConditions: [] as SearchCondition[],
        mrtDerivedMetaFilters: {} as MetaFilters,
      };
    }
    const { dataConditions, metaFilters } = mrtFiltersToConditions(mrtColumnFilters);
    return { mrtDerivedConditions: dataConditions, mrtDerivedMetaFilters: metaFilters };
  }, [mrtColumnFilters]);

  // ---- MRT sorting → editing sortBy sync (MRT → advanced search) ----
  const isMrtSortSync = useRef(false);
  const isAdvancedSortSync = useRef(false);

  useEffect(() => {
    if (!mrtSorting || isAdvancedSortSync.current) {
      isAdvancedSortSync.current = false;
      return;
    }
    isMrtSortSync.current = true;
    const newSortBy = mrtSortingToSortBy(mrtSorting);
    setEditingState((prev) => ({
      ...prev,
      sortBy: newSortBy.length > 0 ? newSortBy : undefined,
    }));
  }, [mrtSorting]);

  // ---- Advanced search sortBy → MRT sorting sync (advanced search → MRT) ----
  // Bug 3 fix: Only sync to MRT when activeSearch.sortBy changes (i.e. after
  // the user presses the "搜尋" button), not on every editing change.
  useEffect(() => {
    if (isMrtSortSync.current) {
      isMrtSortSync.current = false;
      return;
    }
    if (!onMrtSortingChange) return;
    isAdvancedSortSync.current = true;
    const newMrtSorting = sortByToMrtSorting(activeSearch.sortBy);
    onMrtSortingChange(newMrtSorting);
  }, [activeSearch.sortBy, onMrtSortingChange]);

  // ---- Editing callbacks ----
  const handleMetaConditionChange = useCallback((filters: MetaFilters, _isDirty: boolean) => {
    setEditingState((prev) => ({
      ...prev,
      condition: { ...prev.condition, meta: filters },
    }));
  }, []);

  const handleDataConditionChange = useCallback(
    (conditions: SearchCondition[], _isDirty: boolean) => {
      setEditingState((prev) => ({
        ...prev,
        condition: { ...prev.condition, data: conditions },
      }));
    },
    [],
  );

  const handleQBTextChange = useCallback((text: string) => {
    setEditingState((prev) => ({ ...prev, qb: text }));
  }, []);

  const handleResultLimitChange = useCallback((value: number | string) => {
    const limit = parseResultLimit(value);
    setEditingState((prev) => ({ ...prev, resultLimit: limit }));
  }, []);

  const handleSortByChange = useCallback(
    (sortBy: { field: string; order: 'asc' | 'desc' }[] | undefined) => {
      setEditingState((prev) => ({ ...prev, sortBy }));
    },
    [],
  );

  // ---- Submit / Clear ----
  const handleConditionSearch = useCallback(() => {
    setActiveSearch(buildConditionSearch(editingState));
  }, [editingState]);

  const handleConditionClear = useCallback(() => {
    setEditingState({ ...EMPTY_EDITING });
    setActiveSearch({ ...EMPTY_ACTIVE_SEARCH });
  }, []);

  const handleQBSubmit = useCallback(() => {
    setActiveSearch(buildQBSearch(editingState));
  }, [editingState]);

  const handleQBClear = useCallback(() => {
    setEditingState({ ...EMPTY_EDITING });
    setActiveSearch({ mode: 'qb', condition: { meta: {}, data: [] }, qb: '' });
  }, []);

  const handleSwitchToQB = useCallback(() => {
    const qb = conditionToQB(
      editingState.condition.meta,
      editingState.condition.data,
      editingState.resultLimit,
      editingState.sortBy,
    );
    setEditingState((prev) => ({ ...prev, qb }));
    setSearchMode('qb');
  }, [editingState.condition, editingState.resultLimit, editingState.sortBy]);

  const handleModeSwitch = useCallback((value: string) => {
    setSearchMode(value as 'condition' | 'qb');
  }, []);

  const activeBackendCount = useMemo(() => countActiveConditions(activeSearch), [activeSearch]);

  return {
    searchMode,
    advancedOpen,
    setAdvancedOpen,
    activeSearch,
    editingState,
    handleMetaConditionChange,
    handleDataConditionChange,
    handleQBTextChange,
    handleResultLimitChange,
    handleSortByChange,
    handleConditionSearch,
    handleConditionClear,
    handleQBSubmit,
    handleQBClear,
    handleSwitchToQB,
    handleModeSwitch,
    normalizedSearchableFields,
    sortFieldOptions,
    activeBackendCount,
    filterDepth,
    setFilterDepth,
    maxFilterDepth,
    mrtDerivedConditions,
    mrtDerivedMetaFilters,
  };
}
