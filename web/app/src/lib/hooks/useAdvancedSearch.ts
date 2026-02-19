/**
 * useAdvancedSearch — Hook that encapsulates all advanced-search state,
 * URL synchronisation, editing callbacks, and submit/clear actions.
 *
 * The companion component `AdvancedSearchPanel` becomes a thin JSX shell
 * that simply destructures the return value of this hook.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useLocation } from '@tanstack/react-router';
import type { ResourceConfig } from '../resources';
import type {
  SearchCondition,
  MetaFilters,
  NormalizedSearchableField,
  SearchableField,
} from '../components/resource-table/types';
import { conditionToQB } from '../components/resource-table/utils';
import {
  type ActiveSearchState,
  type EditingState,
  EMPTY_ACTIVE_SEARCH,
  EMPTY_EDITING,
  parseSearchFromURL,
  serializeSearchToURL,
  countActiveConditions,
} from '../components/resource-table/searchUtils';

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
  return [
    ...dataFields.map((f) => ({ value: f.name, label: f.label })),
    { value: 'created_time', label: '建立時間' },
    { value: 'updated_time', label: '更新時間' },
    { value: 'created_by', label: '建立者' },
    { value: 'updated_by', label: '更新者' },
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
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useAdvancedSearch({
  config,
  searchableFields,
  onSearchChange,
}: UseAdvancedSearchOptions): UseAdvancedSearchReturn {
  const navigate = useNavigate();
  const location = useLocation();

  const [searchMode, setSearchMode] = useState<'condition' | 'qb'>('condition');
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [activeSearch, setActiveSearch] = useState<ActiveSearchState>(EMPTY_ACTIVE_SEARCH);
  const [editingState, setEditingState] = useState<EditingState>({ ...EMPTY_EDITING });

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

  // ---- Normalised searchable fields ----
  const normalizedSearchableFields = useMemo(
    () => normalizeSearchableFields(searchableFields),
    [searchableFields],
  );

  const sortFieldOptions = useMemo(
    () => buildSortFieldOptions(normalizedSearchableFields, config.fields),
    [normalizedSearchableFields, config.fields],
  );

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
  };
}
