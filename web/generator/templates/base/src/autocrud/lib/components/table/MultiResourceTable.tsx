/**
 * MultiResourceTable — Display rows from multiple ResourceConfigs in a
 * single MRT table.
 *
 * Fully generic — does **not** assume the resources are jobs or any
 * particular type.  A "Source" badge column is prepended so the user
 * can tell which resource each row belongs to.
 *
 * Uses client-side MRT (no server pagination) since aggregated datasets
 * are typically small.
 */

import { useMemo } from 'react';
import { useNavigate } from '@tanstack/react-router';
import { Badge, Group, Stack, Text, Button, Alert, Loader, Center } from '@mantine/core';
import { IconRefresh, IconAlertCircle } from '@tabler/icons-react';
import {
  MantineReactTable,
  useMantineReactTable,
  type MRT_ColumnDef,
  type MRT_RowData,
} from 'mantine-react-table';
import type { ResourceConfig, ResourceField } from '../../resources';
import { getResource } from '../../resources';
import type { UseResourceListParams } from '../../hooks/useResourceList';
import { useMultiResourceList, type MultiResourceRow } from '../../hooks/useMultiResourceList';
import { renderCellValue } from '../field/CellFieldRenderer';
import { ResourceIdCell } from '../common/ResourceIdCell';
import { formatTime } from '../common/TimeDisplay';
import type { ColumnOverride } from './types';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface MultiResourceTableProps {
  /** ResourceConfigs to aggregate rows from. */
  configs: ResourceConfig[];
  /** Query params applied to every resource. */
  params?: UseResourceListParams;
  /** Column overrides keyed by column id. */
  columns?: {
    order?: string[];
    overrides?: Record<string, ColumnOverride>;
  };
  /** Custom row click handler.  `false` disables click.
   *  Defaults to navigating to `/autocrud-admin/{source}/{resourceId}`. */
  onRowClick?: false | ((row: MultiResourceRow) => void);
  /** Table title. */
  title?: string;
  /** Message shown when no rows are returned. `null` hides the component entirely. */
  emptyMessage?: string | null;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Build a label→color map so each source gets a consistent badge colour. */
const SOURCE_COLORS = ['blue', 'teal', 'violet', 'orange', 'pink', 'cyan', 'grape', 'lime'];

function sourceColor(index: number): string {
  return SOURCE_COLORS[index % SOURCE_COLORS.length];
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function MultiResourceTable({
  configs,
  params,
  columns: columnOptions,
  onRowClick,
  title,
  emptyMessage,
}: MultiResourceTableProps) {
  const navigate = useNavigate();

  // ── Build entries for the hook ──
  const entries = useMemo(
    () => configs.filter((c) => !!c).map((config) => ({ config })),
    [configs],
  );

  const { items, totalCount, loading, error, refresh } = useMultiResourceList(entries, params);

  // ── Source badge colour map ──
  const sourceColorMap = useMemo(() => {
    const map: Record<string, string> = {};
    configs.forEach((c, i) => {
      if (c) map[c.name] = sourceColor(i);
    });
    return map;
  }, [configs]);

  // ── Build union of all data fields across configs ──
  const unionFields = useMemo(() => {
    const seen = new Map<string, ResourceField>();
    for (const config of configs) {
      if (!config) continue;
      for (const field of config.fields) {
        if (!seen.has(field.name)) {
          seen.set(field.name, field);
        }
      }
    }
    return Array.from(seen.values());
  }, [configs]);

  // ── Build MRT columns ──
  const tableColumns = useMemo(() => {
    const overrides = columnOptions?.overrides ?? {};

    const cols: MRT_ColumnDef<MultiResourceRow & MRT_RowData>[] = [
      // Source column
      {
        id: '_source',
        header: 'Source',
        size: 160,
        accessorFn: (row) => row._source,
        Cell: ({ cell }) => {
          const name = cell.getValue<string>();
          const config = getResource(name);
          return (
            <Badge color={sourceColorMap[name] ?? 'gray'} variant="light" size="sm">
              {config?.label ?? name}
            </Badge>
          );
        },
      },
      // Resource ID
      {
        id: 'resource_id',
        header: 'Resource ID',
        size: 180,
        accessorFn: (row) => row?.meta?.resource_id,
        Cell: ({ cell }) => ResourceIdCell({ rid: String(cell.getValue() ?? '') }),
      },
    ];

    // Data fields (union of all configs)
    for (const field of unionFields) {
      const override = overrides[field.name];
      if (override?.hidden) continue;

      cols.push({
        id: field.name,
        header: override?.label ?? field.label,
        size: override?.size ?? (field.type === 'binary' ? 120 : undefined),
        accessorFn: (row) => {
          const parts = field.name.split('.');
          let val: any = row?.data;
          for (const p of parts) val = val?.[p];
          return val;
        },
        Cell: ({ cell }) => {
          const value = cell.getValue();
          if (override?.render) return override.render(value);
          return renderCellValue({ field, value });
        },
      });
    }

    // Meta columns
    cols.push(
      {
        id: 'created_time',
        header: overrides['created_time']?.label ?? 'Created',
        accessorFn: (row) => row?.meta?.created_time,
        Cell: ({ cell }) => {
          const v = cell.getValue<string>();
          return v ? formatTime(v, 'relative') : '';
        },
      },
      {
        id: 'updated_time',
        header: overrides['updated_time']?.label ?? 'Updated',
        accessorFn: (row) => row?.meta?.updated_time,
        Cell: ({ cell }) => {
          const v = cell.getValue<string>();
          return v ? formatTime(v, 'relative') : '';
        },
      },
    );

    // Apply column ordering
    if (columnOptions?.order) {
      const orderMap = new Map(columnOptions.order.map((id, idx) => [id, idx]));
      cols.sort((a, b) => {
        const aOrder = orderMap.get(a.id!) ?? Infinity;
        const bOrder = orderMap.get(b.id!) ?? Infinity;
        return aOrder - bOrder;
      });
    }

    return cols;
  }, [unionFields, columnOptions, sourceColorMap]);

  // ── MRT instance ──
  const table = useMantineReactTable({
    columns: tableColumns,
    data: items as (MultiResourceRow & MRT_RowData)[],

    enableGlobalFilter: true,
    enableColumnFilters: false,

    manualPagination: false,
    manualSorting: false,
    manualFiltering: false,

    state: { isLoading: loading },

    mantineTableBodyRowProps:
      onRowClick === false
        ? undefined
        : ({ row }) => ({
            onClick: () => {
              const rid = row.original?.meta?.resource_id ?? '';
              const source = row.original?._source ?? '';
              if (typeof onRowClick === 'function') {
                onRowClick(row.original);
              } else {
                navigate({
                  to: `/autocrud-admin/${source}/$resourceId`,
                  params: { resourceId: rid },
                });
              }
            },
            style: { cursor: 'pointer' },
          }),

    initialState: { density: 'xs' },
  });

  // ── Empty state ──
  if (!loading && items.length === 0) {
    if (emptyMessage === null) return null;
    return emptyMessage ? (
      <Text c="dimmed" size="sm" ta="center" py="md">
        {emptyMessage}
      </Text>
    ) : null;
  }

  return (
    <Stack gap="xs">
      {(title || error) && (
        <Group justify="space-between">
          {title && (
            <Group gap="xs">
              <Text fw={500}>{title}</Text>
              <Badge size="xs" variant="light">
                {totalCount}
              </Badge>
            </Group>
          )}
          <Button
            variant="subtle"
            size="compact-xs"
            leftSection={<IconRefresh size={14} />}
            onClick={refresh}
          >
            Refresh
          </Button>
        </Group>
      )}

      {error && (
        <Alert icon={<IconAlertCircle size={16} />} title="Fetch error" color="red" withCloseButton>
          {error.message}
        </Alert>
      )}

      {loading && items.length === 0 ? (
        <Center py="md">
          <Loader size="sm" />
        </Center>
      ) : (
        <MantineReactTable table={table} />
      )}
    </Stack>
  );
}
