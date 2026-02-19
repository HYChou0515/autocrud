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
  type MRT_ColumnDef,
  type MRT_PaginationState,
  type MRT_SortingState,
  type MRT_RowData,
} from 'mantine-react-table';
import type { FullResource } from '../../../types/api';
import type { ResourceField } from '../../resources';
import { useResourceList } from '../../hooks/useResourceList';
import { formatTime } from '../common/TimeDisplay';
import { renderCellValue } from '../field/CellFieldRenderer';
import { ResourceIdCell } from '../common/ResourceIdCell';
import { AdvancedSearchPanel } from './AdvancedSearchPanel';
import type { ActiveSearchState } from './searchUtils';
import type { ResourceTableProps, ColumnVariant } from './types';
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

  const tableColumns = useMemo<MRT_ColumnDef<FullResource<T>, unknown>[]>(() => {
    // Render meta columns using ColumnVariant (fixed set, no ResourceField)
    const renderMetaCell = (variant: ColumnVariant, value: unknown): React.ReactNode => {
      if (value == null) return '';
      switch (variant) {
        case 'string':
          return String(value);
        case 'relative-time':
          return formatTime(String(value), 'relative');
        case 'full-time':
          return formatTime(String(value), 'full');
        case 'short-time':
          return formatTime(String(value), 'short');
        case 'date':
          return formatTime(String(value), 'date');
        case 'boolean':
          return value ? '✅' : '❌';
        case 'array':
          return Array.isArray(value) ? value.join(', ') : String(value);
        case 'json':
          return typeof value === 'object' ? JSON.stringify(value) : String(value);
        case 'auto':
        default:
          return String(value);
      }
    };

    // Build column definitions with default settings
    interface ColumnDef {
      id: string;
      header: string;
      accessorFn: (row: FullResource<T>) => unknown;
      size?: number;
      /** Meta-column display variant (used only when field is absent). */
      variant?: ColumnVariant;
      /** ResourceField metadata — present for data columns, absent for meta columns. */
      field?: ResourceField;
      defaultHidden?: boolean;
      /** Override render — highest priority, set by ColumnOverride.render or meta-specific renderers. */
      customRender?: (value: unknown) => React.ReactNode;
    }

    const allColumns: ColumnDef[] = [
      {
        id: 'resource_id',
        header: 'Resource ID',
        accessorFn: (row) => row?.meta?.resource_id,
        size: 180,
        variant: 'string',
        customRender: (value) => <ResourceIdCell rid={String(value)} />,
      },
    ];

    // Add data fields — cell rendering is delegated to CellFieldRenderer registry
    for (const field of config.fields) {
      if (field.variant?.type === 'json') continue;

      allColumns.push({
        id: field.name,
        header: field.label,
        field, // <-- attach ResourceField for registry-based rendering
        accessorFn: (row) => {
          const parts = field.name.split('.');
          let val: any = row?.data;
          for (const p of parts) val = val?.[p];
          return val;
        },
        size: field.type === 'binary' ? 120 : undefined,
      });
    }

    // Add metadata columns (all available, some hidden by default)
    allColumns.push(
      {
        id: 'current_revision_id',
        header: 'Revision ID',
        accessorFn: (row) => row?.meta?.current_revision_id,
        variant: 'string',
        defaultHidden: true,
        customRender: (value) => <ResourceIdCell rid={String(value)} />,
      },
      {
        id: 'schema_version',
        header: 'Schema Version',
        accessorFn: (row) => row?.meta?.schema_version,
        variant: 'string',
        defaultHidden: true,
      },
      {
        id: 'is_deleted',
        header: 'Deleted',
        accessorFn: (row) => row?.meta?.is_deleted,
        variant: 'boolean',
        defaultHidden: true,
      },
      {
        id: 'created_time',
        header: 'Created',
        accessorFn: (row) => row?.meta?.created_time,
        variant: 'relative-time',
        defaultHidden: false,
      },
      {
        id: 'created_by',
        header: 'Created By',
        accessorFn: (row) => row?.meta?.created_by,
        variant: 'string',
        defaultHidden: true,
      },
      {
        id: 'updated_time',
        header: 'Updated',
        accessorFn: (row) => row?.meta?.updated_time,
        variant: 'relative-time',
        defaultHidden: false,
      },
      {
        id: 'updated_by',
        header: 'Updated By',
        accessorFn: (row) => row?.meta?.updated_by,
        variant: 'string',
        defaultHidden: true,
      },
    );

    // Apply overrides
    const overrides = columns?.overrides ?? {};
    const processedColumns = allColumns.map((col) => {
      const override = overrides[col.id];

      // 決定是否隱藏：override.hidden > defaultHidden > false
      const hidden =
        override?.hidden !== undefined ? override.hidden : (col.defaultHidden ?? false);

      return {
        ...col,
        header: override?.label ?? col.header,
        size: override?.size ?? col.size,
        variant: override?.variant ?? col.variant,
        hidden,
        customRender: override?.render ?? col.customRender,
      };
    });

    // Apply ordering
    let orderedColumns = processedColumns;
    if (columns?.order) {
      const orderMap = new Map(columns.order.map((id, idx) => [id, idx]));
      orderedColumns = processedColumns.sort((a, b) => {
        const aOrder = orderMap.get(a.id) ?? Infinity;
        const bOrder = orderMap.get(b.id) ?? Infinity;
        return aOrder - bOrder;
      });
    }

    // Filter hidden columns and convert to MRT format
    return orderedColumns
      .filter((col) => !col.hidden)
      .map((col) => ({
        id: col.id,
        header: col.header,
        accessorFn: col.accessorFn,
        size: col.size,
        Cell: ({ cell }) => {
          const value = cell.getValue();
          // 1. 最高優先：使用者自訂 render（ColumnOverride.render 或 meta 硬編碼）
          if (col.customRender) {
            return col.customRender(value);
          }
          // 2. Data field：使用 CellFieldRenderer registry
          if (col.field) {
            return renderCellValue({ field: col.field, value });
          }
          // 3. Meta field fallback：使用 ColumnVariant
          return renderMetaCell(col.variant ?? 'auto', value);
        },
      }));
  }, [config.fields, columns]);

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
