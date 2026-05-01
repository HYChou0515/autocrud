/**
 * ResourceTable - Generic resource list table with lazy upgrade between
 * server-side and client-side modes.
 *
 * Default: **server mode** — pagination, sorting, and filtering are delegated
 * to the backend API.  When the user triggers an operation the backend cannot
 * handle (global free-text search, non-indexed column sort/filter) the table
 * automatically upgrades to **client mode** — fetches up to CLIENT_FETCH_LIMIT
 * items and lets MRT handle everything locally.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from '@tanstack/react-router';
import {
  Container,
  Title,
  Group,
  Button,
  Stack,
  Text,
  ActionIcon,
  TextInput,
  Alert,
  Badge,
} from '@mantine/core';
import { useDebouncedValue } from '@mantine/hooks';
import { IconPlus, IconRefresh, IconSearch, IconX, IconAlertCircle } from '@tabler/icons-react';
import {
  MantineReactTable,
  useMantineReactTable,
  type MRT_SortingState,
  type MRT_ColumnFiltersState,
  type MRT_PaginationState,
  type MRT_RowData,
  type MRT_RowSelectionState,
} from 'mantine-react-table';
import { useResourceList } from '../../hooks/useResourceList';
import type { FullResourceRow } from '../../../types/api';
import { formatTime } from '../common/TimeDisplay';
import { AdvancedSearchPanel } from './AdvancedSearchPanel';
import { buildTableColumns } from './buildColumns';
import type { InternalColumnDef } from './buildColumns';
import type { ActiveSearchState } from './searchUtils';
import type { ResourceTableProps } from './types';
import {
  computeTableMode,
  buildRequestParams,
  DEFAULT_SORTING,
  splitConditionsByIndex,
  applyClientConditions,
  applyClientSort,
  type TableMode,
} from './utils';

/** Debounce delay (ms) for globalFilter before triggering client mode */
const GLOBAL_FILTER_DEBOUNCE_MS = 1000;

/**
 * Generic resource list table with server-side pagination and sorting
 *
 * @example
 * // 預設：顯示所有欄位
 * <ResourceTable config={config} basePath="/guilds" />
 *
 * @example
 * // 控制欄位順序
 * <ResourceTable config={config} basePath="/guilds" columns={{
 *   order: ['name', 'created_at', 'resource_id']
 * }} />
 *
 * @example
 * // 覆蓋特定欄位的顯示方式
 * <ResourceTable config={config} basePath="/guilds" columns={{
 *   overrides: {
 *     created_at: { variant: 'full-time', label: '建立時間' },
 *     resource_id: { hidden: true }
 *   }
 * }} />
 *
 * @example
 * // 顯示預設隱藏的 meta 欄位
 * <ResourceTable config={config} basePath="/guilds" columns={{
 *   overrides: {
 *     created_by: { hidden: false },           // 顯示建立者
 *     updated_by: { hidden: false },           // 顯示更新者
 *     current_revision_id: { hidden: false },  // 顯示版本 ID
 *     schema_version: { hidden: false },       // 顯示 Schema 版本
 *     is_deleted: { hidden: false }            // 顯示刪除狀態
 *   }
 * }} />
 *
 * @example
 * // 啟用後端篩選表單（label 預設為 name）
 * <ResourceTable
 *   config={config}
 *   basePath="/characters"
 *   searchableFields={[
 *     { name: 'level', type: 'number' },
 *     { name: 'class', label: '職業', type: 'select', options: [
 *       { label: '戰士', value: 'warrior' },
 *       { label: '法師', value: 'mage' }
 *     ]},
 *     { name: 'is_active', type: 'boolean' },
 *   ]}
 * />
 *
 * @example
 * // 停用 QB 語法搜尋
 * <ResourceTable config={config} basePath="/guilds" disableQB />
 */
export function ResourceTable<T extends MRT_RowData>({
  config,
  basePath,
  columns,
  moreColumns,
  searchableFields,
  disableQB = true,
  // ── New customization props (override config.tableConfig) ──
  canCreate: canCreateProp,
  alwaysSearchCondition: alwaysSearchConditionProp,
  width: widthProp,
  initPageSize: initPageSizeProp,
  rowPerPageOptions: rowPerPageOptionsProp,
  wrappedInContainer: wrappedInContainerProp,
  onRowClick: onRowClickProp,
  disableGlobalSearch: disableGlobalSearchProp,
  disableAdvancedSearch: disableAdvancedSearchProp,
  defaultSort: defaultSortProp,
  title: titleProp,
  density: densityProp,
  mrtOptions: mrtOptionsProp,
  // ── Row selection props ──
  selectionMode,
  selectedIds,
  onSelectionChange,
  getRowId: getRowIdProp,
}: ResourceTableProps<T>) {
  const navigate = useNavigate();

  // ── Merge config.tableConfig with props (props win) ──
  const tc = config.tableConfig ?? {};
  const canCreate = canCreateProp ?? tc.canCreate ?? true;
  const alwaysSearchCondition = alwaysSearchConditionProp ?? tc.alwaysSearchCondition;
  const containerSize = widthProp ?? tc.width ?? 'xl';
  const initPageSize = initPageSizeProp ?? tc.initPageSize ?? 20;
  const rowPerPageOptions = rowPerPageOptionsProp ?? tc.rowPerPageOptions;
  const wrappedInContainer = wrappedInContainerProp ?? tc.wrappedInContainer ?? false;
  const onRowClick = onRowClickProp ?? tc.onRowClick;
  const disableGlobalSearch = disableGlobalSearchProp ?? tc.disableGlobalSearch ?? false;
  const disableAdvancedSearch = disableAdvancedSearchProp ?? tc.disableAdvancedSearch ?? false;
  const defaultSortOverride = defaultSortProp ?? tc.defaultSort;
  const tableTitle = titleProp ?? tc.title ?? config.label;
  const density = densityProp ?? tc.density ?? 'xs';
  const mrtOptions = mrtOptionsProp ?? tc.mrtOptions ?? {};

  // ── Row selection ──
  const selectionEnabled = selectionMode != null;
  const getRowId = useMemo(() => {
    if (getRowIdProp) return getRowIdProp;
    return (row: FullResourceRow<T>) => row?.meta?.resource_id ?? '';
  }, [getRowIdProp]);

  const [rowSelection, setRowSelection] = useState<MRT_RowSelectionState>(() => {
    if (!selectedIds) return {};
    const init: MRT_RowSelectionState = {};
    for (const id of selectedIds) init[id] = true;
    return init;
  });

  // Sync controlled selectedIds → internal rowSelection
  const prevSelectedIdsRef = useRef(selectedIds);
  useEffect(() => {
    if (selectedIds && selectedIds !== prevSelectedIdsRef.current) {
      prevSelectedIdsRef.current = selectedIds;
      const next: MRT_RowSelectionState = {};
      for (const id of selectedIds) next[id] = true;
      setRowSelection(next);
    }
  }, [selectedIds]);

  // Fire onSelectionChange when rowSelection changes
  const handleRowSelectionChange = useCallback(
    (
      updaterOrValue:
        | MRT_RowSelectionState
        | ((prev: MRT_RowSelectionState) => MRT_RowSelectionState),
    ) => {
      setRowSelection((prev) => {
        const next = typeof updaterOrValue === 'function' ? updaterOrValue(prev) : updaterOrValue;
        return next;
      });
    },
    [],
  );

  // Notify parent when rowSelection stabilises (via effect to access latest data)
  const dataRef = useRef([] as FullResourceRow<T>[]);

  // ── MRT state ──
  const [sorting, setSorting] = useState<MRT_SortingState>(defaultSortOverride ?? DEFAULT_SORTING);
  const [columnFilters, setColumnFilters] = useState<MRT_ColumnFiltersState>([]);
  const [pagination, setPagination] = useState<MRT_PaginationState>({
    pageIndex: 0,
    pageSize: initPageSize,
  });

  // ── Global filter with debounce (triggers client mode after delay) ──
  const [globalFilter, setGlobalFilter] = useState('');
  const [debouncedGlobalFilter] = useDebouncedValue(globalFilter, GLOBAL_FILTER_DEBOUNCE_MS);

  // ── AdvancedSearchPanel state ──
  const [activeSearch, setActiveSearch] = useState<ActiveSearchState>({
    mode: 'condition',
    condition: { meta: {}, data: [] },
    qb: '',
    resultLimit: undefined,
    sortBy: undefined,
  });

  const handleSearchChange = useCallback((search: ActiveSearchState) => {
    setActiveSearch(search);
  }, []);

  // ── Compute table mode (server vs client) ──
  const mode: TableMode = useMemo(
    () =>
      computeTableMode({
        debouncedGlobalFilter,
        sorting,
        columnFilters,
        indexedFields: config.indexedFields,
        activeSearchData: activeSearch.condition?.data,
        activeSearchSortBy: activeSearch.sortBy,
      }),
    [
      debouncedGlobalFilter,
      sorting,
      columnFilters,
      config.indexedFields,
      activeSearch.condition?.data,
      activeSearch.sortBy,
    ],
  );

  // Reset page index when mode changes
  const prevModeRef = useRef(mode);
  useEffect(() => {
    if (prevModeRef.current !== mode) {
      prevModeRef.current = mode;
      setPagination((prev) => ({ ...prev, pageIndex: 0 }));
    }
  }, [mode]);

  // ── Build request params ──
  const params = useMemo(
    () =>
      buildRequestParams({
        mode,
        pagination,
        activeSearch,
        sorting,
        columnFilters,
        indexedFields: config.indexedFields,
        alwaysSearchCondition,
      }),
    [
      mode,
      pagination,
      activeSearch,
      sorting,
      columnFilters,
      config.indexedFields,
      alwaysSearchCondition,
    ],
  );

  const { data: rawData, total, loading, error, refresh } = useResourceList(config, params);

  // ── Client-side post-processing: apply non-indexed conditions & sort ──
  const data = useMemo(() => {
    let result = rawData;

    // Apply non-indexed data conditions client-side
    const advancedDataConditions = activeSearch.condition?.data ?? [];
    if (advancedDataConditions.length > 0) {
      const { clientConditions: nonIndexed } = splitConditionsByIndex(
        advancedDataConditions,
        config.indexedFields ?? [],
      );
      if (nonIndexed.length > 0) {
        result = applyClientConditions(result, nonIndexed);
      }
    }

    // Apply non-indexed sorts client-side
    const advancedSortBy = activeSearch.sortBy;
    if (advancedSortBy && advancedSortBy.length > 0) {
      // Only apply client-side sort for non-indexed sort fields
      const clientSorts = advancedSortBy.filter((s) => !config.indexedFields?.includes(s.field));
      if (clientSorts.length > 0) {
        result = applyClientSort(result, clientSorts);
      }
    }

    return result;
  }, [rawData, activeSearch.condition?.data, activeSearch.sortBy, config.indexedFields]);

  // Keep dataRef in sync so the selection-change effect can look up rows.
  dataRef.current = data as FullResourceRow<T>[];

  // Fire onSelectionChange when rowSelection changes
  useEffect(() => {
    if (!selectionEnabled || !onSelectionChange) return;
    const selectedKeys = Object.keys(rowSelection).filter((k) => rowSelection[k]);
    // Build a lookup map from current data for O(1) access
    const idMap = new Map<string, FullResourceRow<T>>();
    for (const row of dataRef.current) {
      const id = getRowId(row);
      if (id) idMap.set(id, row);
    }
    const selectedRows = selectedKeys
      .map((k) => idMap.get(k))
      .filter((r): r is FullResourceRow<T> => r != null);
    onSelectionChange(selectedRows);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rowSelection, selectionEnabled]);

  // ── Client mode overflow info (cutoff timestamp) ──
  const clientOverflowInfo = useMemo(() => {
    if (mode !== 'client' || total <= data.length || data.length === 0) return null;

    // Find the oldest updated_time in the loaded data set
    let oldestTime: string | null = null;
    for (const item of data) {
      const ut = item?.meta?.updated_time;
      if (ut && (!oldestTime || ut < oldestTime)) {
        oldestTime = ut;
      }
    }

    if (!oldestTime) return null;
    return {
      cutoffTime: oldestTime,
      unfetchedCount: total - data.length,
    };
  }, [mode, total, data]);

  // ── Count label ──
  const countLabel = useMemo(() => {
    if (mode === 'server') return `${total} total resources`;
    if (clientOverflowInfo) return `${data.length} / ${total} total resources`;
    return `${total} total resources`;
  }, [mode, total, data.length, clientOverflowInfo]);

  // ── Columns ──
  const tableColumns = useMemo(
    () =>
      buildTableColumns(config, {
        order: columns?.order,
        overrides: columns?.overrides,
        moreColumns: moreColumns as InternalColumnDef<T>[] | undefined,
      }),
    [config.fields, columns, moreColumns],
  );

  // ── MRT instance ──
  const isServer = mode === 'server';

  const table = useMantineReactTable({
    // ── User pass-through options (lowest priority) ──
    ...(mrtOptions as Record<string, unknown>),

    // ── Internal settings (override mrtOptions) ──
    columns: tableColumns,
    data: data as FullResourceRow<T>[],

    // Row selection
    ...(selectionEnabled
      ? {
          enableRowSelection: true,
          enableMultiRowSelection: selectionMode === 'multi',
          getRowId: (row: FullResourceRow<T>) => getRowId(row),
          onRowSelectionChange: handleRowSelectionChange,
        }
      : {}),

    // Global filter
    enableGlobalFilter: !disableGlobalSearch,
    onGlobalFilterChange: disableGlobalSearch ? undefined : setGlobalFilter,

    // Column filters
    enableColumnFilters: true,
    onColumnFiltersChange: setColumnFilters,

    // Sorting
    onSortingChange: setSorting,

    // Pagination
    onPaginationChange: setPagination,
    ...(rowPerPageOptions
      ? { mantinePaginationProps: { rowsPerPageOptions: rowPerPageOptions.map(String) } }
      : {}),

    // Server / client mode toggle
    manualPagination: isServer,
    manualSorting: isServer,
    manualFiltering: isServer,
    rowCount: isServer ? total : undefined,

    state: {
      isLoading: loading,
      sorting,
      globalFilter: disableGlobalSearch ? undefined : globalFilter,
      columnFilters,
      pagination,
      ...(selectionEnabled ? { rowSelection } : {}),
    },

    mantineTableBodyRowProps: selectionEnabled
      ? ({ row }) => ({
          onClick: () => {
            if (selectionMode === 'single') {
              setRowSelection({ [row.id]: true });
            } else {
              setRowSelection((prev) => ({
                ...prev,
                [row.id]: !prev[row.id],
              }));
            }
          },
          style: { cursor: 'pointer' },
        })
      : onRowClick === false
        ? undefined
        : ({ row }) => ({
            onClick: () => {
              if (typeof onRowClick === 'function') {
                onRowClick(row.original);
              } else {
                const rid = row.original?.meta?.resource_id ?? '';
                navigate({
                  to: `${basePath}/$resourceId`,
                  params: { resourceId: rid },
                });
              }
            },
            style: { cursor: 'pointer' },
          }),
    initialState: { density },
  });

  const tableContent = (
    <Stack gap="md">
      <Group justify="space-between">
        <div>
          <Title order={2}>{tableTitle}</Title>
          <Group gap="xs">
            <Text c="dimmed" size="sm">
              {countLabel}
            </Text>
            <Badge size="xs" variant="light" color={isServer ? 'blue' : 'orange'}>
              {isServer ? 'Server' : 'Client'}
            </Badge>
            {clientOverflowInfo && (
              <Text c="orange" size="xs">
                僅載入 {formatTime(clientOverflowInfo.cutoffTime, 'full')} 之後更新的資料，尚有{' '}
                {clientOverflowInfo.unfetchedCount} 筆未載入
              </Text>
            )}
          </Group>
        </div>
        <Group>
          <Button variant="light" leftSection={<IconRefresh size={16} />} onClick={refresh}>
            Refresh
          </Button>
          {canCreate && (
            <Button
              leftSection={<IconPlus size={16} />}
              onClick={() => navigate({ to: `${basePath}/create` })}
            >
              Create
            </Button>
          )}
        </Group>
      </Group>

      {/* 即時篩選 - client-side free text search (triggers client mode after debounce) */}
      {!disableGlobalSearch && (
        <TextInput
          placeholder="Search all loaded resources..."
          value={globalFilter ?? ''}
          onChange={(e) => setGlobalFilter(e.currentTarget.value)}
          leftSection={<IconSearch size={16} />}
          rightSection={
            globalFilter ? (
              <ActionIcon variant="subtle" onClick={() => setGlobalFilter('')}>
                <IconX size={16} />
              </ActionIcon>
            ) : null
          }
          size="sm"
        />
      )}

      {/* 進階搜尋面板（後端查詢） */}
      {!disableAdvancedSearch && (
        <AdvancedSearchPanel
          config={config}
          searchableFields={searchableFields}
          disableQB={disableQB}
          onSearchChange={handleSearchChange}
          mrtColumnFilters={columnFilters}
          mrtSorting={sorting}
          onMrtSortingChange={setSorting}
        />
      )}

      {/* 錯誤訊息 */}
      {error && (
        <Alert icon={<IconAlertCircle size={16} />} title="搜尋錯誤" color="red" withCloseButton>
          {error.message}
        </Alert>
      )}

      <MantineReactTable table={table} />
    </Stack>
  );

  if (!wrappedInContainer) return tableContent;

  return (
    <Container size={containerSize as any} py="xl">
      {tableContent}
    </Container>
  );
}
