/**
 * ResourceTable - Generic resource list table with server-side pagination and sorting
 */

import { useCallback, useMemo, useState } from 'react';
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
} from '@mantine/core';
import { IconPlus, IconRefresh, IconSearch, IconX, IconAlertCircle } from '@tabler/icons-react';
import {
  MantineReactTable,
  useMantineReactTable,
  type MRT_PaginationState,
  type MRT_SortingState,
  type MRT_RowData,
} from 'mantine-react-table';
import { useResourceList } from '../../hooks/useResourceList';
import { AdvancedSearchPanel } from './AdvancedSearchPanel';
import { buildTableColumns } from './buildColumns';
import type { ActiveSearchState } from './searchUtils';
import type { ResourceTableProps } from './types';
import { sortByToSorts } from './utils';

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
}: ResourceTableProps<T>) {
  const navigate = useNavigate();
  const [pagination, setPagination] = useState<MRT_PaginationState>({ pageIndex: 0, pageSize: 20 });
  const [sorting, setSorting] = useState<MRT_SortingState>([]);

  // 即時篩選（client-side）- 只篩當前頁面已載入的資料
  const [globalFilter, setGlobalFilter] = useState('');

  // 已提交的搜尋狀態（由 AdvancedSearchPanel 管理，透過 callback 回傳）
  const [activeSearch, setActiveSearch] = useState<ActiveSearchState>({
    mode: 'condition',
    condition: { meta: {}, data: [] },
    qb: '',
    resultLimit: undefined,
    sortBy: undefined,
  });

  // AdvancedSearchPanel 搜尋狀態變更 — 重置分頁
  const handleSearchChange = useCallback((search: ActiveSearchState) => {
    setActiveSearch(search);
    setPagination((prev) => ({ ...prev, pageIndex: 0 }));
  }, []);

  const params = useMemo(() => {
    const baseParams: Record<string, unknown> = {
      limit: pagination.pageSize,
      offset: pagination.pageIndex * pagination.pageSize,
    };

    // 根據 activeSearch 的模式設定參數
    if (activeSearch.mode === 'qb' && activeSearch.qb) {
      // QB 模式：只傳 qb 字串（limit 和 sorts 已包含在 QB 中）
      baseParams.qb = activeSearch.qb;
    } else {
      // Condition 模式：傳遞各別參數
      const { meta, data } = activeSearch.condition;

      // 後端結果數量限制（優先於 pagination.pageSize）
      if (activeSearch.resultLimit) {
        baseParams.limit = activeSearch.resultLimit;
      }

      // 後端排序（優先於前端 table sorting）
      if (activeSearch.sortBy && activeSearch.sortBy.length > 0) {
        const sortsStr = sortByToSorts(activeSearch.sortBy);
        if (sortsStr) {
          baseParams.sorts = sortsStr;
        }
      }

      // 後端篩選參數（data_conditions）
      if (data.length > 0) {
        const dataConditions = data.map((condition) => ({
          field_path: condition.field,
          operator: condition.operator,
          value: condition.value,
        }));
        baseParams.data_conditions = JSON.stringify(dataConditions);
      }

      // Meta 篩選參數
      if (meta.created_time_start) baseParams.created_time_start = meta.created_time_start;
      if (meta.created_time_end) baseParams.created_time_end = meta.created_time_end;
      if (meta.updated_time_start) baseParams.updated_time_start = meta.updated_time_start;
      if (meta.updated_time_end) baseParams.updated_time_end = meta.updated_time_end;
      if (meta.created_by) baseParams.created_bys = [meta.created_by];
      if (meta.updated_by) baseParams.updated_bys = [meta.updated_by];
    }

    return baseParams;
  }, [pagination.pageSize, pagination.pageIndex, activeSearch]);

  const { data, total, loading, error, refresh } = useResourceList(config, params);

  const tableColumns = useMemo(
    () =>
      buildTableColumns(config, {
        order: columns?.order,
        overrides: columns?.overrides,
      }),
    [config.fields, columns],
  );

  const table = useMantineReactTable({
    columns: tableColumns,
    data,
    manualPagination: true,
    rowCount: total,
    enableGlobalFilter: true,
    state: { isLoading: loading, pagination, sorting, globalFilter },
    onGlobalFilterChange: setGlobalFilter,
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    mantineTableBodyRowProps: ({ row }) => ({
      onClick: () =>
        navigate({
          to: `${basePath}/$resourceId`,
          params: { resourceId: row.original?.meta?.resource_id ?? '' },
        }),
      style: { cursor: 'pointer' },
    }),
    initialState: { density: 'xs' },
  });

  return (
    <Container size="xl" py="xl">
      <Stack gap="md">
        <Group justify="space-between">
          <div>
            <Title order={2}>{config.label}</Title>
            <Text c="dimmed" size="sm">
              {total} total resources
            </Text>
          </div>
          <Group>
            <Button variant="light" leftSection={<IconRefresh size={16} />} onClick={refresh}>
              Refresh
            </Button>
            <Button
              leftSection={<IconPlus size={16} />}
              onClick={() => navigate({ to: `${basePath}/create` })}
            >
              Create
            </Button>
          </Group>
        </Group>

        {/* 即時篩選 - 只篩當前頁面的資料 */}
        <TextInput
          placeholder="在此頁中篩選..."
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

        {/* 進階搜尋面板（後端查詢） */}
        <AdvancedSearchPanel
          config={config}
          searchableFields={searchableFields}
          disableQB={disableQB}
          onSearchChange={handleSearchChange}
        />

        {/* 錯誤訊息 */}
        {error && (
          <Alert icon={<IconAlertCircle size={16} />} title="搜尋錯誤" color="red" withCloseButton>
            {error.message}
          </Alert>
        )}

        <MantineReactTable table={table} />
      </Stack>
    </Container>
  );
}
