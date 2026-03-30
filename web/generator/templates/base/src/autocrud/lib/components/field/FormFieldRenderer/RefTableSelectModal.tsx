/**
 * RefTableSelectModal — A modal with a full-featured ResourceTable for selecting
 * referenced resources (or revisions).
 *
 * Features:
 * - Server-side pagination (via ResourceTable)
 * - Global text search + advanced search (via ResourceTable)
 * - Column sorting & filtering
 * - Row checkbox selection (single or multi) via ResourceTable's selectionMode
 * - Pre-selects already-chosen values
 * - Fullscreen modal with flex layout for proper table fitting
 *
 * Delegates all table logic to ResourceTable — no duplicate MRT setup.
 *
 * Used by RefSelect / RefMultiSelect / RefRevisionSelect / RefRevisionMultiSelect
 * as a "table mode" alternative to the dropdown picker.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { ActionIcon, Button, Group, Modal, Stack, Text, Tooltip } from '@mantine/core';
import { IconArrowsMaximize, IconArrowsMinimize } from '@tabler/icons-react';
import {
  MRT_ShowHideColumnsButton,
  MRT_ToggleDensePaddingButton,
  MRT_ToggleFiltersButton,
  MRT_ToggleGlobalFilterButton,
} from 'mantine-react-table';
import { getResource } from '../../../resources';
import type { FullResourceRow } from '../../../../types/api';
import type { SearchCondition } from '../../table/types';
import { ResourceTable } from '../../table/ResourceTable';

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
// is_deleted=false condition (reused across renders)
// ---------------------------------------------------------------------------
const IS_NOT_DELETED_CONDITION: SearchCondition = {
  field: 'is_deleted',
  operator: 'eq',
  value: false,
};

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

  const [isFullScreen, setIsFullScreen] = useState(false);

  // Track selected rows from ResourceTable
  const [selectedRows, setSelectedRows] = useState<FullResourceRow<unknown>[]>([]);

  // Key to force remount ResourceTable when modal re-opens (resets internal state)
  const [tableKey, setTableKey] = useState(0);

  // Reset state when modal opens
  useEffect(() => {
    if (opened && config) {
      setIsFullScreen(false);
      setSelectedRows([]);
      setTableKey((k) => k + 1);
    }
  }, [opened, config]);

  // Merge alwaysSearchCondition with is_deleted=false
  const mergedAlwaysCondition = useMemo(() => {
    const base = alwaysSearchCondition ?? [];
    return [...base, IS_NOT_DELETED_CONDITION];
  }, [alwaysSearchCondition]);

  // Custom getRowId based on valueField
  const getRowId = useCallback(
    (row: FullResourceRow<unknown>) => row?.meta?.[valueField] ?? '',
    [valueField],
  );

  const handleSelectionChange = useCallback((rows: FullResourceRow<unknown>[]) => {
    setSelectedRows(rows);
  }, []);

  const selectedCount = selectedRows.length;

  const handleConfirm = () => {
    const selected = selectedRows.map((r) => getRowId(r)).filter(Boolean);
    onConfirm(selected);
    onClose();
  };

  // MRT options: custom toolbar with fullscreen toggle, disable MRT's built-in fullscreen
  const mrtOptions = useMemo(
    () => ({
      enableFullScreenToggle: false,
      renderToolbarInternalActions: ({ table: t }: { table: any }) => (
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
    }),
    [isFullScreen],
  );

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
        {/* 表格（使用 ResourceTable 含 selection） */}
        <div style={isFullScreen ? { flex: 1, minHeight: 0, overflow: 'auto' } : undefined}>
          <ResourceTable
            key={tableKey}
            config={config}
            basePath=""
            selectionMode={mode}
            selectedIds={selectedValues}
            onSelectionChange={handleSelectionChange}
            getRowId={getRowId}
            alwaysSearchCondition={mergedAlwaysCondition}
            wrappedInContainer={false}
            initPageSize={10}
            canCreate={false}
            title={undefined}
            defaultSort={[]}
            columns={{
              overrides: {
                schema_version: { hidden: true },
                is_deleted: { hidden: true },
                created_by: { hidden: true },
                updated_by: { hidden: true },
              },
            }}
            mrtOptions={mrtOptions}
          />
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
