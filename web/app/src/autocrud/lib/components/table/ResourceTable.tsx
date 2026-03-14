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
} from 'mantine-react-table';
import { useResourceList } from '../../hooks/useResourceList';
import type { FullResourceRow } from '../../../types/api';
import { formatTime } from '../common/TimeDisplay';
import { AdvancedSearchPanel } from './AdvancedSearchPanel';
import { buildTableColumns } from './buildColumns';
import type { ActiveSearchState } from './searchUtils';
import type { ResourceTableProps } from './types';
import {
  sortByToSorts,
  computeTableMode,
  mrtSortingToSorts,
  mrtFiltersToParams,
  DEFAULT_SORTING,
  type TableMode,
} from './utils';

/** Maximum number of items fetched from the backend for client-side operations */
const CLIENT_FETCH_LIMIT = 1000;

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
}: ResourceTableProps<T>) {
  const navigate = useNavigate();

  // ── Merge config.tableConfig with props (props win) ──
  const tc = config.tableConfig ?? {};
  const canCreate = canCreateProp ?? tc.canCreate ?? true;
  const alwaysSearchCondition = alwaysSearchConditionProp ?? tc.alwaysSearchCondition;
  const containerSize = widthProp ?? tc.width ?? 'xl';
  const initPageSize = initPageSizeProp ?? tc.initPageSize ?? 20;
  const rowPerPageOptions = rowPerPageOptionsProp ?? tc.rowPerPageOptions;
  const wrappedInContainer = wrappedInContainerProp ?? tc.wrappedInContainer ?? true;
  const onRowClick = onRowClickProp ?? tc.onRowClick;
  const disableGlobalSearch = disableGlobalSearchProp ?? tc.disableGlobalSearch ?? false;
  const disableAdvancedSearch = disableAdvancedSearchProp ?? tc.disableAdvancedSearch ?? false;
  const defaultSortOverride = defaultSortProp ?? tc.defaultSort;
  const tableTitle = titleProp ?? tc.title ?? config.label;
  const density = densityProp ?? tc.density ?? 'xs';

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
      }),
    [debouncedGlobalFilter, sorting, columnFilters, config.indexedFields],
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
  const params = useMemo(() => {
    const baseParams: Record<string, unknown> = {};

    // --- Pagination ---
    if (mode === 'server') {
      baseParams.limit = pagination.pageSize;
      baseParams.offset = pagination.pageIndex * pagination.pageSize;
    } else {
      baseParams.limit = CLIENT_FETCH_LIMIT;
      // Sort by updated_time desc to fetch the most recently updated items
      baseParams.sorts = JSON.stringify([{ type: 'meta', key: 'updated_time', direction: '-' }]);
    }

    // --- AdvancedSearchPanel conditions ---
    if (activeSearch.mode === 'qb' && activeSearch.qb) {
      // QB mode: just send the QB string
      baseParams.qb = activeSearch.qb;
    } else {
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
      if (mode === 'server' && activeSearch.sortBy && activeSearch.sortBy.length > 0) {
        const sortsStr = sortByToSorts(activeSearch.sortBy);
        if (sortsStr) baseParams.sorts = sortsStr;
      }

      // Advanced panel data_conditions
      const advancedConditions = advancedData.map((condition) => ({
        field_path: condition.field,
        operator: condition.operator,
        value: condition.value,
      }));

      // Advanced panel meta filters
      if (meta.created_time_start) baseParams.created_time_start = meta.created_time_start;
      if (meta.created_time_end) baseParams.created_time_end = meta.created_time_end;
      if (meta.updated_time_start) baseParams.updated_time_start = meta.updated_time_start;
      if (meta.updated_time_end) baseParams.updated_time_end = meta.updated_time_end;
      if (meta.created_by) baseParams.created_bys = [meta.created_by];
      if (meta.updated_by) baseParams.updated_bys = [meta.updated_by];

      // --- MRT column filters (server-filterable ones sent to backend in both modes) ---
      const { serverParams, dataConditions: mrtDataConditions } = mrtFiltersToParams(
        columnFilters,
        config.indexedFields,
      );
      Object.assign(baseParams, serverParams);

      // Merge advanced + MRT data_conditions
      const allDataConditions = [...advancedConditions, ...mrtDataConditions];
      if (allDataConditions.length > 0) {
        baseParams.data_conditions = JSON.stringify(allDataConditions);
      }
    }

    // --- MRT column sorting (server mode only — send sortable columns to backend) ---
    if (mode === 'server' && sorting.length > 0 && !baseParams.sorts) {
      const sortsStr = mrtSortingToSorts(sorting, config.indexedFields);
      if (sortsStr) baseParams.sorts = sortsStr;
    }

    // --- Always-on search conditions (e.g. filter for a specific tag) ---
    if (alwaysSearchCondition && alwaysSearchCondition.length > 0) {
      const alwaysConditions = alwaysSearchCondition.map((c) => ({
        field_path: c.field,
        operator: c.operator,
        value: c.value,
      }));
      const existing = baseParams.data_conditions
        ? (JSON.parse(baseParams.data_conditions as string) as unknown[])
        : [];
      baseParams.data_conditions = JSON.stringify([...existing, ...alwaysConditions]);
    }

    return baseParams;
  }, [
    mode,
    pagination,
    activeSearch,
    sorting,
    columnFilters,
    config.indexedFields,
    alwaysSearchCondition,
  ]);

  const { data, total, loading, error, refresh } = useResourceList(config, params);

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
      }),
    [config.fields, columns],
  );

  // ── MRT instance ──
  const isServer = mode === 'server';

  const table = useMantineReactTable({
    columns: tableColumns,
    data: data as FullResourceRow<T>[],

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
    },

    mantineTableBodyRowProps:
      onRowClick === false
        ? undefined
        : ({ row }) => ({
            onClick: () => {
              const rid = row.original?.meta?.resource_id ?? '';
              if (typeof onRowClick === 'function') {
                onRowClick(rid);
              } else {
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
