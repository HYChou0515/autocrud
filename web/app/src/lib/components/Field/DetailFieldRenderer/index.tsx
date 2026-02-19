/**
 * DetailFieldRenderer — Read-only field display using a registry pattern.
 *
 * Mirrors the FieldRenderer (form editing) architecture:
 * 1. `resolveFieldKind()` determines the kind (shared with FieldRenderer).
 * 2. `DETAIL_RENDERERS` map dispatches to the appropriate display function.
 *
 * Adding a new display:
 *   1. Add a FieldKind entry in `resolveFieldKind.ts` (if not already).
 *   2. Add a renderer entry in `DETAIL_RENDERERS` below.
 *   3. TypeScript will enforce that BOTH FieldRenderer and DetailFieldRenderer
 *      have an entry for every FieldKind.
 */

import { Code, Text } from '@mantine/core';
import type { ResourceField } from '../../../resources';
import { resolveFieldKind, type FieldKind } from '../resolveFieldKind';
import { RefLink, RefLinkList, RefRevisionLink, RefRevisionLinkList } from '../../RefLink';
import { TimeDisplay } from '../../TimeDisplay';
import { isBlobObject, renderSimpleValue, NA } from '../../../utils/displayHelpers';
import { BinaryFieldDisplay } from './BinaryFieldDisplay';
import { ArrayFieldDisplay } from './ArrayFieldDisplay';
import { UnionFieldDisplay } from './UnionFieldDisplay';

// ---------------------------------------------------------------------------
// Context passed to every detail renderer function
// ---------------------------------------------------------------------------

export interface DetailRenderContext {
  field: ResourceField;
  value: unknown;
  data: Record<string, any>;
}

/** Render a value using the DETAIL_RENDERERS registry (recursive entry point) */
function renderDetailValue(ctx: DetailRenderContext): React.ReactNode {
  if (ctx.value == null) return NA;
  const kind = resolveFieldKind(ctx.field);
  return DETAIL_RENDERERS[kind](ctx);
}

// ---------------------------------------------------------------------------
// Shared renderer helpers (reused by multiple FieldKinds)
// ---------------------------------------------------------------------------

type Renderer = (ctx: DetailRenderContext) => React.ReactNode;

const renderBool: Renderer = ({ value }) => (value ? '✅ Yes' : '❌ No');

const renderToString: Renderer = ({ value }) => String(value ?? '');

const renderLongText: Renderer = ({ value }) => {
  if (typeof value === 'string' && value.length > 100) {
    return <Code block>{value}</Code>;
  }
  return String(value ?? '');
};

const renderArrayJoin: Renderer = ({ value }) => {
  if (Array.isArray(value)) {
    return value.length === 0 ? (
      <Text c="dimmed" size="sm">
        []
      </Text>
    ) : (
      value.join(', ')
    );
  }
  return String(value ?? '');
};

// ---------------------------------------------------------------------------
// Renderer map — one entry per FieldKind
// ---------------------------------------------------------------------------

const DETAIL_RENDERERS: Record<FieldKind, (ctx: DetailRenderContext) => React.ReactNode> = {
  /* ---- Complex / structured ---- */

  itemFields: ({ field, value }) => {
    if (!Array.isArray(value)) return NA;
    return (
      <ArrayFieldDisplay
        value={value}
        itemFields={field.itemFields!}
        renderValue={renderDetailValue}
      />
    );
  },

  union: ({ field, value }) => {
    if (
      field.unionMeta &&
      field.unionMeta.discriminatorField !== '__type' &&
      typeof value === 'object' &&
      value !== null
    ) {
      return (
        <UnionFieldDisplay
          value={value as Record<string, any>}
          unionMeta={field.unionMeta}
          renderValue={renderDetailValue}
        />
      );
    }
    // Simple union or fallback: show as JSON
    return <Code block>{JSON.stringify(value, null, 2)}</Code>;
  },

  binary: ({ value }) => {
    if (
      typeof value === 'object' &&
      value !== null &&
      isBlobObject(value as Record<string, unknown>)
    ) {
      return <BinaryFieldDisplay value={value as Record<string, unknown>} />;
    }
    return <Code block>{JSON.stringify(value, null, 2)}</Code>;
  },

  /* ---- Text-like ---- */

  json: ({ value }) => {
    if (typeof value === 'object' && value !== null) {
      return <Code block>{JSON.stringify(value, null, 2)}</Code>;
    }
    return String(value);
  },

  markdown: renderLongText,

  arrayString: renderArrayJoin,
  tags: renderArrayJoin,

  select: renderToString,
  textarea: renderLongText,

  /* ---- Boolean ---- */

  checkbox: renderBool,
  switch: renderBool,

  /* ---- Date ---- */

  date: ({ value }) => <TimeDisplay time={String(value)} format="full" />,

  /* ---- Number ---- */

  numberSlider: renderToString,
  number: renderToString,

  /* ---- Ref ---- */

  refResourceId: ({ field, value }) => (
    <RefLink value={value as string | null} fieldRef={field.ref!} />
  ),

  refResourceIdMulti: ({ field, value }) => (
    <RefLinkList values={value as string[] | null} fieldRef={field.ref!} />
  ),

  refRevisionId: ({ field, value }) => (
    <RefRevisionLink value={value as string | null} fieldRef={field.ref!} />
  ),

  refRevisionIdMulti: ({ field, value }) => (
    <RefRevisionLinkList values={value as string[] | null} fieldRef={field.ref!} />
  ),

  /* ---- Default ---- */

  text: ({ field, value }) => {
    // Schema-aware overrides first
    if (field.type === 'date') return <TimeDisplay time={String(value)} format="full" />;
    if (
      typeof value === 'object' &&
      value !== null &&
      isBlobObject(value as Record<string, unknown>)
    ) {
      return <BinaryFieldDisplay value={value as Record<string, unknown>} />;
    }
    // Fall back to shared simple renderer
    return renderSimpleValue(value);
  },
};

// ---------------------------------------------------------------------------
// Public component
// ---------------------------------------------------------------------------

/** Renders a single field value in read-only mode using the registry pattern. */
export function DetailFieldRenderer({ field, value, data }: DetailRenderContext) {
  return <>{renderDetailValue({ field, value, data })}</>;
}
