/**
 * RefTableSelectModal — A modal with a full-featured MRT table for selecting
 * referenced resources (or revisions).
 *
 * Features:
 * - Server-side pagination
 * - Global text search (client-side, current page)
 * - Advanced search (server-side conditions + QB)
 * - Column sorting & filtering
 * - Row checkbox selection (single or multi)
 * - Pre-selects already-chosen values
 * - Fullscreen modal with flex layout for proper table fitting
 *
 * Used by RefSelect / RefMultiSelect / RefRevisionSelect / RefRevisionMultiSelect
 * as a "table mode" alternative to the dropdown picker.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { ActionIcon, Button, Group, Modal, Stack, Text, Tooltip } from '@mantine/core';
import { IconArrowsMaximize, IconArrowsMinimize } from '@tabler/icons-react';
import {
  MantineReactTable,
  MRT_ShowHideColumnsButton,
  MRT_ToggleDensePaddingButton,
  MRT_ToggleFiltersButton,
  MRT_ToggleGlobalFilterButton,
  useMantineReactTable,
  type MRT_PaginationState,
  type MRT_RowSelectionState,
  type MRT_SortingState,
} from 'mantine-react-table';
import { getResource } from '../../../resources';
import type { FullResourceRow } from '../../../../types/api';
import { useResourceList } from '../../../hooks/useResourceList';
import { buildTableColumns } from '../../table/buildColumns';
import { AdvancedSearchPanel } from '../../table/AdvancedSearchPanel';
import type { SearchCondition } from '../../table/types';
import { EMPTY_ACTIVE_SEARCH, type ActiveSearchState } from '../../table/searchUtils';
import { buildRequestParams } from '../../table/utils';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface RefTableSelectModalProps {
  /** Whether the modal is open */
  opened: boolean;
  /** Close the modal */
  onClose: () => void;
  /** Confirm callback with selected IDs */
  onConfirm: (selected: string[]) => void;
  /** Target resource name (e.g. 'character') */
  resourceName: string;
  /** Selection mode */
  mode: 'single' | 'multi';
  /** Currently selected values (for pre-selection) */
  selectedValues: string[];
  /** Which meta field to use as the row ID */
  valueField: 'resource_id' | 'current_revision_id';
  /** Search conditions that are always applied to every API request.
   *  Useful for narrowing the selectable items (e.g. only show items
   *  with a specific type). */
  alwaysSearchCondition?: SearchCondition[];
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function RefTableSelectModal({
  opened,
  onClose,
  onConfirm,
  resourceName,
  mode,
  selectedValues,
  valueField,
  alwaysSearchCondition,
}: RefTableSelectModalProps) {
  const config = getResource(resourceName);

  const [pagination, setPagination] = useState<MRT_PaginationState>({
    pageIndex: 0,
    pageSize: 10,
  });
  const [sorting, setSorting] = useState<MRT_SortingState>([]);
  const [globalFilter, setGlobalFilter] = useState('');
  const [rowSelection, setRowSelection] = useState<MRT_RowSelectionState>({});
  const [isFullScreen, setIsFullScreen] = useState(false);

  // Advanced search state (mirrors ResourceTable pattern)
  const [activeSearch, setActiveSearch] = useState<ActiveSearchState>(EMPTY_ACTIVE_SEARCH);

  const handleSearchChange = useCallback((search: ActiveSearchState) => {
    setActiveSearch(search);
    setPagination((prev) => ({ ...prev, pageIndex: 0 }));
  }, []);

  // Reset selection state when modal opens
  useEffect(() => {
    if (opened && config) {
      const initial: MRT_RowSelectionState = {};
      for (const v of selectedValues) {
        initial[v] = true;
      }
      setRowSelection(initial);
      setPagination({ pageIndex: 0, pageSize: 10 });
      setGlobalFilter('');
      setIsFullScreen(false);
      setActiveSearch(EMPTY_ACTIVE_SEARCH);
    }
  }, [opened, config, selectedValues]);

  // Build params using shared buildRequestParams (same logic as ResourceTable)
  const params = useMemo(() => {
    const p = buildRequestParams({
      mode: 'server',
      pagination,
      activeSearch,
      sorting,
      columnFilters: [],
      alwaysSearchCondition,
    });
    // RefTableSelectModal always filters out soft-deleted resources
    p.is_deleted = false;
    return p;
  }, [pagination, activeSearch, sorting, alwaysSearchCondition]);

  const { data, total, loading } = useResourceList(config!, params);

  // Build columns using the shared helper
  const tableColumns = useMemo(() => {
    if (!config) return [];
    return buildTableColumns(config, {
      overrides: {
        schema_version: { hidden: true },
        is_deleted: { hidden: true },
        created_by: { hidden: true },
        updated_by: { hidden: true },
      },
    });
  }, [config]);

  // Map data rows to use valueField as the row ID for MRT selection
  const getRowId = (row: FullResourceRow<unknown>) => {
    return row?.meta?.[valueField] ?? '';
  };

  const table = useMantineReactTable({
    columns: tableColumns,
    data: data as FullResourceRow<unknown>[],
    manualPagination: true,
    rowCount: total,
    getRowId,
    // Selection
    enableRowSelection: true,
    enableMultiRowSelection: mode === 'multi',
    // Search & filter
    enableGlobalFilter: true,
    enableColumnFilters: true,
    enableSorting: true,
    // State
    state: {
      isLoading: loading,
      pagination,
      sorting,
      globalFilter,
      rowSelection,
    },
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    onGlobalFilterChange: setGlobalFilter,
    onRowSelectionChange: setRowSelection,
    // Disable MRT's built-in fullscreen (its CSS conflicts with Modal)
    enableFullScreenToggle: false,
    // Custom toolbar: re-add standard MRT buttons + our own fullscreen toggle
    renderToolbarInternalActions: ({ table: t }) => (
      <>
        <MRT_ToggleGlobalFilterButton table={t} />
        <MRT_ToggleFiltersButton table={t} />
        <MRT_ShowHideColumnsButton table={t} />
        <MRT_ToggleDensePaddingButton table={t} />
        <Tooltip label={isFullScreen ? '離開全螢幕' : '全螢幕'}>
          <ActionIcon
            color="gray"
            size="lg"
            variant="subtle"
            onClick={() => setIsFullScreen((v) => !v)}
            aria-label="Toggle fullscreen"
          >
            {isFullScreen ? <IconArrowsMinimize size={18} /> : <IconArrowsMaximize size={18} />}
          </ActionIcon>
        </Tooltip>
      </>
    ),
    // Appearance
    initialState: { density: 'xs' },
    mantineTableBodyRowProps: ({ row }) => ({
      onClick: () => {
        if (mode === 'single') {
          setRowSelection({ [row.id]: true });
        }
      },
      style: { cursor: 'pointer' },
    }),
  });

  // Derive selected count
  const selectedCount = Object.keys(rowSelection).filter((k) => rowSelection[k]).length;

  const handleConfirm = () => {
    const selected = Object.keys(rowSelection).filter((k) => rowSelection[k]);
    onConfirm(selected);
    onClose();
  };

  if (!config) {
    return null;
  }

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title={
        <Text fw={600}>
          選擇{config.label}
          {mode === 'multi' ? '（多選）' : ''}
        </Text>
      }
      fullScreen={isFullScreen}
      size={isFullScreen ? undefined : '80%'}
      centered={!isFullScreen}
      styles={{
        content: isFullScreen
          ? { display: 'flex', flexDirection: 'column', height: '100vh' }
          : undefined,
        body: isFullScreen
          ? {
              display: 'flex',
              flexDirection: 'column',
              flex: 1,
              minHeight: 0,
              overflow: 'hidden',
            }
          : { minHeight: 400 },
      }}
    >
      <Stack
        gap="sm"
        style={
          isFullScreen
            ? {
                flex: 1,
                minHeight: 0,
                overflow: 'hidden',
                display: 'flex',
                flexDirection: 'column',
              }
            : undefined
        }
      >
        {/* 進階搜尋面板 */}
        <AdvancedSearchPanel config={config} onSearchChange={handleSearchChange} />

        {/* 表格 */}
        <div style={isFullScreen ? { flex: 1, minHeight: 0, overflow: 'auto' } : undefined}>
          <MantineReactTable table={table} />
        </div>

        {/* Footer — 選擇計數 + 確認/取消 */}
        <Group justify="space-between">
          <Text size="sm" c="dimmed">
            已選擇 {selectedCount} 筆
          </Text>
          <Group>
            <Button variant="default" onClick={onClose}>
              取消
            </Button>
            <Button onClick={handleConfirm} disabled={selectedCount === 0}>
              確認
            </Button>
          </Group>
        </Group>
      </Stack>
    </Modal>
  );
}
