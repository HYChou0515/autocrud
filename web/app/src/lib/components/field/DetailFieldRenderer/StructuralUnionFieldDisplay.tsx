/**
 * StructuralUnionFieldDisplay — Read-only display for structural union fields.
 *
 * Structural unions use `discriminatorField: '__variant'` in their metadata,
 * but the **actual API data does NOT contain a `__variant` key**. The display
 * must *infer* which variant the value belongs to by examining the runtime
 * data shape (array, dict, or object-with-specific-keys).
 *
 * Variant kinds handled:
 *  - **Array variant** (`isArray: true`): value is `Array`
 *    - with `itemUnionMeta`: each element is a discriminated union → delegate to UnionFieldDisplay
 *    - with `fields` only: each element has a fixed schema → delegate to ArrayFieldDisplay
 *  - **Dict variant** (`isDict: true`): value is a plain object whose values share a schema
 *    - Renders a key→value table using `dictValueFields`
 *  - **Object variant** (has `fields`): value is a single typed object
 *    - Renders fields in a nested table (like UnionFieldDisplay)
 *  - **Fallback**: CollapsibleJson
 */

import { Paper, Stack, Table, Text } from '@mantine/core';
import type { UnionMeta, UnionVariant, ResourceField } from '../../../resources';
import type { DetailRenderContext } from './index';
import { UnionFieldDisplay } from './UnionFieldDisplay';
import { ArrayFieldDisplay } from './ArrayFieldDisplay';
import { CollapsibleJson } from './CollapsibleJson';

export interface StructuralUnionFieldDisplayProps {
  value: unknown;
  unionMeta: UnionMeta;
  /** Render function for individual sub-field values (recursive entry) */
  renderValue: (ctx: DetailRenderContext) => React.ReactNode;
}

// ---------------------------------------------------------------------------
// Variant inference — pure function, easy to unit test
// ---------------------------------------------------------------------------

/**
 * Infer which structural-union variant matches the given runtime value.
 *
 * Strategy (ordered):
 *  1. `Array.isArray(value)` → pick an `isArray` variant
 *     - prefer the one with `itemUnionMeta` (more specialised) over plain `fields`
 *  2. Plain object where ALL values are objects → try `isDict` variant
 *  3. Plain object → try object variants (those with `fields`) ranked by key-overlap
 *  4. Null / unmatched → return null (caller should show JSON fallback)
 */
export function inferVariant(value: unknown, variants: UnionVariant[]): UnionVariant | null {
  if (value == null) return null;

  // 1. Array
  if (Array.isArray(value)) {
    const arrayVariants = variants.filter((v) => v.isArray);
    if (arrayVariants.length === 0) return null;
    // prefer itemUnionMeta (nested discriminated union array)
    return arrayVariants.find((v) => v.itemUnionMeta) ?? arrayVariants[0];
  }

  if (typeof value !== 'object') return null;

  const obj = value as Record<string, unknown>;
  const keys = Object.keys(obj);

  // 2. Dict — all values are objects (or empty dict)
  const dictVariant = variants.find((v) => v.isDict);
  if (dictVariant && keys.length > 0) {
    const allValuesAreObjects = keys.every(
      (k) => typeof obj[k] === 'object' && obj[k] !== null && !Array.isArray(obj[k]),
    );
    if (allValuesAreObjects) return dictVariant;
  }

  // 3. Object variants — pick by highest key overlap score
  const objectVariants = variants.filter(
    (v) => !v.isArray && !v.isDict && v.fields && v.fields.length > 0,
  );
  if (objectVariants.length > 0 && keys.length > 0) {
    let best: UnionVariant | null = null;
    let bestScore = -1;
    for (const variant of objectVariants) {
      const variantKeys = new Set(variant.fields!.map((f) => f.name));
      let score = 0;
      for (const k of keys) {
        if (variantKeys.has(k)) score++;
      }
      if (score > bestScore) {
        bestScore = score;
        best = variant;
      }
    }
    if (best && bestScore > 0) return best;
  }

  // 4. If there's only one non-array, non-dict variant without fields (primitive/null)
  // or we truly can't match, fallback
  return null;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function StructuralUnionFieldDisplay({
  value,
  unionMeta,
  renderValue,
}: StructuralUnionFieldDisplayProps) {
  const matched = inferVariant(value, unionMeta.variants);

  // Fallback: show as collapsible JSON
  if (!matched) {
    return <CollapsibleJson value={value} />;
  }

  return <VariantRenderer variant={matched} value={value} renderValue={renderValue} />;
}

// ---------------------------------------------------------------------------
// Internal: render a matched variant's value
// ---------------------------------------------------------------------------

function VariantRenderer({
  variant,
  value,
  renderValue,
}: {
  variant: UnionVariant;
  value: unknown;
  renderValue: (ctx: DetailRenderContext) => React.ReactNode;
}) {
  // ---- Array variant ----
  if (variant.isArray && Array.isArray(value)) {
    if (value.length === 0) {
      return (
        <Text c="dimmed" size="sm">
          No items
        </Text>
      );
    }

    // Array of discriminated unions (each item has its own tag)
    if (variant.itemUnionMeta) {
      return (
        <Stack gap="xs">
          {value.map((item, idx) => (
            <Paper key={idx} withBorder p="xs" radius="sm">
              <Text size="xs" c="dimmed" mb={4}>
                #{idx + 1}
              </Text>
              <UnionFieldDisplay
                value={item as Record<string, any>}
                unionMeta={variant.itemUnionMeta!}
                renderValue={renderValue}
              />
            </Paper>
          ))}
        </Stack>
      );
    }

    // Array of fixed-schema items
    if (variant.fields && variant.fields.length > 0) {
      return (
        <ArrayFieldDisplay value={value} itemFields={variant.fields} renderValue={renderValue} />
      );
    }

    // Array but no field info — JSON fallback
    return <CollapsibleJson value={value} />;
  }

  // ---- Dict variant ----
  if (variant.isDict) {
    const obj = value as Record<string, unknown>;
    const entries = Object.entries(obj);
    if (entries.length === 0) {
      return (
        <Text c="dimmed" size="sm">
          No items
        </Text>
      );
    }

    const dictFields = variant.dictValueFields;

    return (
      <Stack gap="xs">
        {entries.map(([key, val]) => (
          <Paper key={key} withBorder p="xs" radius="sm">
            <Text size="xs" fw={600} mb={4}>
              {key}
            </Text>
            {dictFields && dictFields.length > 0 && typeof val === 'object' && val !== null ? (
              <Table fz="sm">
                <Table.Tbody>
                  {dictFields.map((sf: ResourceField) => (
                    <Table.Tr key={sf.name}>
                      <Table.Td style={{ fontWeight: 500, width: '35%' }}>{sf.label}</Table.Td>
                      <Table.Td>
                        {renderValue({
                          field: sf,
                          value: (val as Record<string, any>)[sf.name],
                          data: val as Record<string, any>,
                        })}
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            ) : (
              <CollapsibleJson value={val} />
            )}
          </Paper>
        ))}
      </Stack>
    );
  }

  // ---- Object variant (with fields) ----
  if (variant.fields && variant.fields.length > 0 && typeof value === 'object' && value !== null) {
    const obj = value as Record<string, any>;
    return (
      <Table fz="sm">
        <Table.Tbody>
          {variant.fields.map((sf: ResourceField) => (
            <Table.Tr key={sf.name}>
              <Table.Td style={{ fontWeight: 500, width: '35%' }}>{sf.label}</Table.Td>
              <Table.Td>
                {renderValue({
                  field: sf,
                  value: obj[sf.name],
                  data: obj,
                })}
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    );
  }

  // Fallback
  return <CollapsibleJson value={value} />;
}
