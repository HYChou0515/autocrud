/**
 * useFieldDepth — Shared hook for depth-based field visibility control.
 *
 * Used by both ResourceDetail (read-only display) and ResourceForm (editing)
 * to compute which fields are visible and which are collapsed at a given depth.
 *
 * ResourceDetail uses `stripItemFields: true` so array-of-typed-objects fields
 * whose children exceed the depth threshold still appear (rendered as plain JSON
 * instead of sub-table cards). ResourceForm uses `stripItemFields: false`
 * (the default) so they become collapsed JSON editors.
 */

import { useState, useMemo } from 'react';
import type { ResourceField } from '../resources';
import { computeMaxAvailableDepth, computeVisibleFieldsAndGroups } from '@/lib/utils/formUtils';

export interface UseFieldDepthOptions {
  fields: ResourceField[];
  /** Override initial depth (defaults to maxAvailableDepth) */
  maxFormDepth?: number;
  /**
   * When true, fields with itemFields that exceed depth are kept visible
   * but with itemFields stripped (so they render as plain values).
   * When false (default), they become collapsed groups (JSON editors).
   */
  stripItemFields?: boolean;
}

export interface UseFieldDepthReturn {
  maxAvailableDepth: number;
  depth: number;
  setDepth: (depth: number) => void;
  visibleFields: ResourceField[];
  collapsedGroups: { path: string; label: string }[];
}

export function useFieldDepth({
  fields,
  maxFormDepth,
  stripItemFields = false,
}: UseFieldDepthOptions): UseFieldDepthReturn {
  const maxAvailableDepth = useMemo(() => computeMaxAvailableDepth(fields), [fields]);

  const [depth, setDepth] = useState<number>(maxFormDepth ?? maxAvailableDepth);

  const { visibleFields, collapsedGroups } = useMemo(() => {
    if (!stripItemFields) {
      const result = computeVisibleFieldsAndGroups(fields, depth);
      return {
        visibleFields: result.visibleFields as ResourceField[],
        collapsedGroups: result.collapsedGroups,
      };
    }

    // Detail-specific behaviour: keep itemFields-bearing fields visible
    // but strip their itemFields when depth is insufficient.
    const result = computeVisibleFieldsAndGroups(fields, depth);
    const visible = result.visibleFields as ResourceField[];

    // Find fields that formUtils collapsed due to itemFields,
    // and re-add them with itemFields stripped.
    const visibleNames = new Set(visible.map((f) => f.name));
    const groupPaths = new Set(result.collapsedGroups.map((g) => g.path));

    for (const field of fields) {
      const fieldDepth = field.name.split('.').length;
      if (
        field.itemFields &&
        field.itemFields.length > 0 &&
        fieldDepth <= depth &&
        fieldDepth + 1 > depth &&
        !visibleNames.has(field.name) &&
        groupPaths.has(field.name)
      ) {
        // Insert this field (with itemFields stripped) in position
        visible.push({ ...field, itemFields: undefined });
        // Remove from collapsed groups since we're showing it
        groupPaths.delete(field.name);
      }
    }

    const filteredGroups = result.collapsedGroups.filter(
      (g) =>
        !fields.some(
          (f) =>
            f.name === g.path &&
            f.itemFields &&
            f.itemFields.length > 0 &&
            f.name.split('.').length <= depth &&
            f.name.split('.').length + 1 > depth,
        ),
    );

    // Re-sort visible fields to match original field order
    const fieldOrder = new Map(fields.map((f, i) => [f.name, i]));
    visible.sort((a, b) => (fieldOrder.get(a.name) ?? 0) - (fieldOrder.get(b.name) ?? 0));

    return { visibleFields: visible, collapsedGroups: filteredGroups };
  }, [fields, depth, stripItemFields]);

  return {
    maxAvailableDepth,
    depth,
    setDepth,
    visibleFields,
    collapsedGroups,
  };
}
