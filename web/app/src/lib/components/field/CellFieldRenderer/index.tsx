/**
 * CellFieldRenderer — Table cell display using a registry pattern.
 *
 * Mirrors the DetailFieldRenderer / FormFieldRenderer architecture:
 * 1. `resolveFieldKind()` determines the kind (shared across all three renderers).
 * 2. `CELL_RENDERERS` map dispatches to the appropriate compact cell display.
 *
 * Adding a new cell display:
 *   1. Add a FieldKind entry in `resolveFieldKind.ts` (if not already).
 *   2. Add a renderer entry in `CELL_RENDERERS` below.
 *   3. TypeScript will enforce that ALL THREE renderers (Form, Detail, Cell)
 *      have an entry for every FieldKind.
 *
 * Cell renderers are optimised for compact table display (single-line,
 * truncated, with tooltips for overflow) — unlike DetailFieldRenderer which
 * renders full-width read-only views.
 */

import { Text } from '@mantine/core';
import type { ResourceField } from '../../../resources';
import { resolveFieldKind, type FieldKind } from '../resolveFieldKind';
import { RefLink, RefLinkList, RefRevisionLink, RefRevisionLinkList } from '../../common/RefLink';
import { formatTime } from '../../common/TimeDisplay';
import { renderBinaryCell, renderObjectPreview } from './helpers';

// ---------------------------------------------------------------------------
// Context passed to every cell renderer function
// ---------------------------------------------------------------------------

export interface CellRenderContext {
  /** Field metadata from the resource schema. */
  field: ResourceField;
  /** The raw cell value extracted from the row. */
  value: unknown;
}

// ---------------------------------------------------------------------------
// Shared renderer helpers
// ---------------------------------------------------------------------------

type CellRenderer = (ctx: CellRenderContext) => React.ReactNode;

const renderBool: CellRenderer = ({ value }) => (value ? '✅' : '❌');

const renderToString: CellRenderer = ({ value }) => String(value ?? '');

const renderArrayJoin: CellRenderer = ({ value }) => {
  if (Array.isArray(value)) {
    if (value.length === 0)
      return (
        <Text c="dimmed" size="sm">
          []
        </Text>
      );
    if (typeof value[0] === 'object' && value[0] !== null) {
      return renderObjectPreview({ [`${value.length} items`]: value } as Record<string, unknown>);
    }
    return value.join(', ');
  }
  return String(value ?? '');
};

const renderJson: CellRenderer = ({ value }) => {
  if (typeof value === 'object' && value !== null) {
    return renderObjectPreview(value as Record<string, unknown>);
  }
  return String(value);
};

const NA = (
  <Text c="dimmed" size="sm">
    —
  </Text>
);

// ---------------------------------------------------------------------------
// CELL_RENDERERS — one entry per FieldKind (Record enforces completeness)
// ---------------------------------------------------------------------------

export const CELL_RENDERERS: Record<FieldKind, CellRenderer> = {
  /* ---- Complex / structured ---- */

  itemFields: ({ value }) => {
    if (!Array.isArray(value) || value.length === 0) return NA;
    return renderObjectPreview({ [`${value.length} items`]: value } as Record<string, unknown>);
  },

  union: renderJson,

  binary: ({ value }) => {
    if (value && typeof value === 'object' && 'file_id' in (value as Record<string, unknown>)) {
      return renderBinaryCell(value as Record<string, unknown>);
    }
    return NA;
  },

  /* ---- Text-like ---- */

  json: renderJson,
  markdown: renderToString,
  arrayString: renderArrayJoin,
  tags: renderArrayJoin,
  select: renderToString,
  textarea: renderToString,

  /* ---- Boolean ---- */

  checkbox: renderBool,
  switch: renderBool,

  /* ---- Date ---- */

  date: ({ value }) => formatTime(String(value), 'relative'),

  /* ---- Number ---- */

  numberSlider: renderToString,
  number: renderToString,

  /* ---- Ref ---- */

  refResourceId: ({ field, value }) => (
    <RefLink value={value as string | null} fieldRef={field.ref!} />
  ),

  refResourceIdMulti: ({ field, value }) => (
    <RefLinkList values={value as string[] | null} fieldRef={field.ref!} maxVisible={3} />
  ),

  refRevisionId: ({ field, value }) => (
    <RefRevisionLink value={value as string | null} fieldRef={field.ref!} />
  ),

  refRevisionIdMulti: ({ field, value }) => (
    <RefRevisionLinkList values={value as string[] | null} fieldRef={field.ref!} maxVisible={3} />
  ),

  /* ---- Default ---- */

  text: ({ value }) => {
    if (typeof value === 'boolean') return value ? '✅' : '❌';
    if (Array.isArray(value)) {
      if (value.length === 0)
        return (
          <Text c="dimmed" size="sm">
            []
          </Text>
        );
      if (typeof value[0] === 'object' && value[0] !== null) {
        return renderObjectPreview({ [`${value.length} items`]: value } as Record<string, unknown>);
      }
      return value.join(', ');
    }
    if (typeof value === 'object' && value !== null) {
      const obj = value as Record<string, unknown>;
      if ('file_id' in obj && 'size' in obj) {
        return renderBinaryCell(obj);
      }
      return renderObjectPreview(obj);
    }
    if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/.test(value)) {
      return formatTime(value, 'relative');
    }
    return String(value);
  },
};

// ---------------------------------------------------------------------------
// Public function — renders a cell value using the CELL_RENDERERS registry
// ---------------------------------------------------------------------------

/**
 * Render a cell value for a data field using the registry.
 * Returns null-safe output (null/undefined → "—").
 */
export function renderCellValue(ctx: CellRenderContext): React.ReactNode {
  if (ctx.value == null) return '';
  const kind = resolveFieldKind(ctx.field);
  return CELL_RENDERERS[kind](ctx);
}

// ---------------------------------------------------------------------------
// Public component — drop-in React component wrapper
// ---------------------------------------------------------------------------

/** Renders a single field's table cell using the CellFieldRenderer registry. */
export function CellFieldRenderer({ field, value }: CellRenderContext) {
  return <>{renderCellValue({ field, value })}</>;
}
