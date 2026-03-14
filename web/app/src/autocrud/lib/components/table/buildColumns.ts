/**
 * buildTableColumns — Shared column definition builder for MRT tables.
 *
 * Extracted from ResourceTable so that both ResourceTable and RefTableSelectModal
 * can share the same column construction logic (data fields + meta fields,
 * ordering, overrides, CellFieldRenderer dispatch).
 */

import type { MRT_ColumnDef, MRT_RowData } from 'mantine-react-table';
import type { FullResourceRow } from '../../../types/api';
import type { ResourceConfig, ResourceField } from '../../resources';
import { formatTime } from '../common/TimeDisplay';
import { renderCellValue } from '../field/CellFieldRenderer';
import { ResourceIdCell } from '../common/ResourceIdCell';
import type { ColumnVariant, ColumnOverride } from './types';

// ---------------------------------------------------------------------------
// Internal column definition (before MRT conversion)
// ---------------------------------------------------------------------------

export interface InternalColumnDef<T> {
  id: string;
  header: string;
  accessorFn: (row: FullResourceRow<T>) => unknown;
  size?: number;
  /** Meta-column display variant (used only when field is absent). */
  variant?: ColumnVariant;
  /** ResourceField metadata — present for data columns, absent for meta columns. */
  field?: ResourceField;
  defaultHidden?: boolean;
  /** Override render — highest priority. */
  customRender?: (value: unknown) => React.ReactNode;
}

// ---------------------------------------------------------------------------
// Meta cell rendering helper
// ---------------------------------------------------------------------------

export function renderMetaCell(variant: ColumnVariant, value: unknown): React.ReactNode {
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
}

// ---------------------------------------------------------------------------
// Build raw (internal) column definitions from a ResourceConfig
// ---------------------------------------------------------------------------

export function buildRawColumns<T>(config: ResourceConfig<T>): InternalColumnDef<T>[] {
  const allColumns: InternalColumnDef<T>[] = [
    {
      id: 'resource_id',
      header: 'Resource ID',
      accessorFn: (row) => row?.meta?.resource_id,
      size: 180,
      variant: 'string',
      customRender: (value) => ResourceIdCell({ rid: String(value) }),
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
  ];

  // Data fields — cell rendering is delegated to CellFieldRenderer registry
  for (const field of config.fields) {
    if (field.variant?.type === 'json') continue;

    // ── Union resource: expand the "data" wrapper into discriminator + variant sub-fields ──
    if (config.isUnion && field.type === 'union' && field.unionMeta) {
      const { discriminatorField, variants } = field.unionMeta;

      // Discriminator column (e.g., "Type")
      allColumns.push({
        id: '__union_tag',
        header: discriminatorField.charAt(0).toUpperCase() + discriminatorField.slice(1),
        accessorFn: (row) => (row?.data as any)?.[discriminatorField],
        size: 100,
        customRender: (value) => (value != null ? String(value) : ''),
      });

      // Collect all unique sub-fields from all variants (skip discriminator)
      const seen = new Map<string, ResourceField>();
      for (const variant of variants) {
        for (const sf of variant.fields ?? []) {
          if (sf.name === discriminatorField) continue;
          if (!seen.has(sf.name)) seen.set(sf.name, sf);
        }
      }

      for (const [name, subField] of seen) {
        allColumns.push({
          id: name,
          header: subField.label,
          field: subField,
          accessorFn: (row) => (row?.data as any)?.[name],
          size: subField.type === 'binary' ? 120 : undefined,
        });
      }
      continue; // Don't create the default "data" column
    }

    // ── Normal field ──
    allColumns.push({
      id: field.name,
      header: field.label,
      field,
      accessorFn: (row) => {
        const parts = field.name.split('.');
        let val: any = row?.data;
        for (const p of parts) val = val?.[p];
        return val;
      },
      size: field.type === 'binary' ? 120 : undefined,
    });
  }

  // Meta columns (all available, some hidden by default)
  allColumns.push(
    {
      id: 'current_revision_id',
      header: 'Revision ID',
      accessorFn: (row) => row?.meta?.current_revision_id,
      variant: 'string',
      defaultHidden: true,
      customRender: (value) => ResourceIdCell({ rid: String(value) }),
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
  );

  return allColumns;
}

// ---------------------------------------------------------------------------
// Apply overrides, ordering, and convert to MRT column definitions
// ---------------------------------------------------------------------------

export interface BuildTableColumnsOptions {
  /** Column ordering */
  order?: string[];
  /** Per-column overrides */
  overrides?: Record<string, ColumnOverride>;
}

/**
 * Build final MRT-compatible column definitions from a ResourceConfig.
 *
 * This is the main entry point shared by ResourceTable and RefTableSelectModal.
 */
export function buildTableColumns<T extends MRT_RowData>(
  config: ResourceConfig<T>,
  options?: BuildTableColumnsOptions,
): MRT_ColumnDef<FullResourceRow<T>, unknown>[] {
  const allColumns = buildRawColumns(config);
  const overrides = options?.overrides ?? {};

  // Apply overrides
  const processedColumns = allColumns.map((col) => {
    const override = overrides[col.id];
    const hidden = override?.hidden !== undefined ? override.hidden : (col.defaultHidden ?? false);

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
  if (options?.order) {
    const orderMap = new Map(options.order.map((id, idx) => [id, idx]));
    orderedColumns = [...processedColumns].sort((a, b) => {
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
      Cell: ({ cell }: { cell: { getValue: () => unknown } }) => {
        const value = cell.getValue();
        // 1. Highest priority: custom render (ColumnOverride.render or meta hard-coded)
        if (col.customRender) {
          return col.customRender(value);
        }
        // 2. Data field: use CellFieldRenderer registry
        if (col.field) {
          return renderCellValue({ field: col.field, value });
        }
        // 3. Meta field fallback: use ColumnVariant
        return renderMetaCell(col.variant ?? 'auto', value);
      },
    }));
}
