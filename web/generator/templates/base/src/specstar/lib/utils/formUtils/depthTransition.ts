/**
 * Depth transition utilities for form field collapse/expand operations.
 *
 * When the form depth slider changes, fields transition between:
 * - visible (rendered as individual form inputs) → collapsed (JSON string textarea)
 * - collapsed (JSON string textarea) → visible (individual form inputs)
 *
 * These pure functions handle the value conversion for those transitions,
 * plus guards for the transitional frame before useEffect fires.
 */

import { getHandler } from './fieldTypeRegistry';
import type { ResourceFieldMinimal } from './fieldTypeRegistry';
import { getByPath, setByPath } from './paths';

/**
 * Convert a form value (array/object) to a JSON string for collapsed display.
 *
 * Used when a field transitions from visible → collapsed (depth decreased).
 * If the value is already a string, returns it as-is.
 *
 * @param value - Current form value (array, object, or already a string)
 * @param field - Field definition (used to determine default: '[]' for itemFields, '{}' for objects)
 * @returns JSON string representation of the value
 *
 * @example
 * collapseFieldToJson([{ name: 'a' }], { name: 'items', itemFields: [...] })
 * // Returns: '[\n  {\n    "name": "a"\n  }\n]'
 *
 * @example
 * collapseFieldToJson(null, { name: 'items', itemFields: [{ name: 'id' }] })
 * // Returns: '[]'
 *
 * @example
 * collapseFieldToJson(null, { name: 'meta', type: 'object' })
 * // Returns: '{}'
 */
export function collapseFieldToJson(value: any, field: ResourceFieldMinimal): string {
  // Already a string — no conversion needed
  if (typeof value === 'string') {
    return value;
  }

  if (value != null) {
    return JSON.stringify(value, null, 2);
  }

  // null/undefined — use type-appropriate empty default
  return field.itemFields?.length ? '[]' : '{}';
}

/**
 * Parse a JSON string back to proper form values when a field transitions
 * from collapsed → visible (depth increased).
 *
 * For fields with itemFields, each sub-field is processed through the
 * registry handler's toFormValue to ensure proper type conversion
 * (e.g. date strings → Date objects).
 *
 * @param jsonStr - JSON string from the collapsed textarea
 * @param field - Field definition with optional itemFields
 * @returns Parsed form value, or undefined if parsing fails (caller should keep as-is)
 *
 * @example
 * expandFieldFromJson('[{"name":"a","created":"2024-01-01"}]', fieldWithItemFields)
 * // Returns: [{ name: 'a', created: Date('2024-01-01') }]  (dates converted)
 *
 * @example
 * expandFieldFromJson('{"key":"val"}', { name: 'meta', type: 'object' })
 * // Returns: { key: 'val' }
 *
 * @example
 * expandFieldFromJson('invalid json', field)
 * // Returns: undefined (parse failure)
 */
export function expandFieldFromJson(jsonStr: string, field: ResourceFieldMinimal): any | undefined {
  const defaultStr = field.itemFields?.length ? '[]' : '{}';
  const toParse = jsonStr || defaultStr;

  let parsed: any;
  try {
    parsed = JSON.parse(toParse);
  } catch {
    return undefined; // Parse failure — caller keeps value as-is
  }

  // For array-with-itemFields: process each item's sub-fields through handlers
  if (field.itemFields && field.itemFields.length > 0) {
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed.map((item: any) => {
      const processedItem: Record<string, any> = {};
      for (const sf of field.itemFields!) {
        const sv = item?.[sf.name];
        const handler = getHandler(sf.type);
        processedItem[sf.name] = handler.toFormValue(sv, sf);
      }
      return processedItem;
    });
  }

  // Plain object or other types — return parsed directly
  return parsed;
}

/**
 * Guard: safely coerce a raw form value to an array.
 *
 * During depth transitions, the form value for an itemFields field may still
 * be a JSON string (before useEffect fires). This guard ensures rendering
 * code always gets an array.
 *
 * @param rawItems - Raw value from form state (may be array, string, null, etc.)
 * @returns The value if it's already an array, otherwise an empty array
 *
 * @example
 * safeGetArrayItems([{ id: 1 }])  // Returns: [{ id: 1 }]
 * safeGetArrayItems('[{"id":1}]') // Returns: [] (string, not array)
 * safeGetArrayItems(null)         // Returns: []
 * safeGetArrayItems(undefined)    // Returns: []
 */
export function safeGetArrayItems(rawItems: any): any[] {
  return Array.isArray(rawItems) ? rawItems : [];
}

/**
 * Guard: safely coerce a raw form value to a JSON string.
 *
 * During depth transitions, the form value for a collapsed group may still
 * be an array or object (before useEffect fires). This guard ensures the
 * collapsed textarea always gets a string.
 *
 * @param rawVal - Raw value from form state (may be string, array, object, null, etc.)
 * @returns The value if it's already a string, otherwise JSON.stringify with formatting
 *
 * @example
 * safeGetJsonString('{"key":"val"}')  // Returns: '{"key":"val"}'
 * safeGetJsonString([1, 2, 3])        // Returns: '[\n  1,\n  2,\n  3\n]'
 * safeGetJsonString(null)             // Returns: '[]'
 * safeGetJsonString(undefined)        // Returns: '[]'
 */
export function safeGetJsonString(rawVal: any): string {
  if (typeof rawVal === 'string') {
    return rawVal;
  }
  return JSON.stringify(rawVal ?? [], null, 2);
}

/**
 * Restore previously-collapsed children within a parent object before collapsing the parent.
 *
 * When decreasing form depth, a parent group (e.g. `payload`) gets collapsed into JSON.
 * If child paths (e.g. `payload.event_x2`) were already collapsed to JSON strings from
 * a previous depth change, the parent object contains stringified children.
 * Collapsing the parent would then produce double-encoded JSON.
 *
 * This function parses those string children back to objects so the parent can be
 * cleanly serialized.
 *
 * @param parentValue - The parent object value from form state
 * @param parentPath - The dot-notation path of the parent being collapsed
 * @param prevCollapsedPaths - Set of paths that were previously collapsed (may contain children)
 * @returns A shallow clone of parentValue with string children parsed back to objects
 *
 * @example
 * restoreCollapsedChildren(
 *   { event_x2: '{"type":"EventBodyX","good":"foo"}', name: 'test' },
 *   'payload',
 *   new Set(['payload.event_x2'])
 * )
 * // Returns: { event_x2: { type: 'EventBodyX', good: 'foo' }, name: 'test' }
 */
export function restoreCollapsedChildren(
  parentValue: any,
  parentPath: string,
  prevCollapsedPaths: Set<string>,
): any {
  if (parentValue == null || typeof parentValue !== 'object') return parentValue;

  const restored = { ...parentValue };
  const prefix = parentPath + '.';

  for (const childPath of prevCollapsedPaths) {
    if (!childPath.startsWith(prefix)) continue;
    const relativePath = childPath.slice(prefix.length);
    // Only handle direct children (single segment) — deeper paths are nested within them
    if (relativePath.includes('.')) continue;
    const childVal = restored[relativePath];
    if (typeof childVal === 'string') {
      try {
        restored[relativePath] = JSON.parse(childVal);
      } catch {
        // Invalid JSON — leave as-is
      }
    }
  }

  return restored;
}

/**
 * Result of depth transition computation.
 * Contains ordered lists of updates to apply to form state.
 */
export interface DepthTransitionUpdates {
  /** Paths to expand (JSON string → object). Applied first. */
  expands: Array<{ path: string; value: any }>;
  /** Paths to collapse (object → JSON string). Applied after expands. */
  collapses: Array<{ path: string; value: string }>;
}

/**
 * Compute form value updates needed when form depth changes.
 *
 * CRITICAL ordering: expands run BEFORE collapses. When going from depth=1→2,
 * the parent (e.g. `payload`) must be expanded from a JSON string to an object
 * before child paths (e.g. `payload.event_x2`) can be collapsed. If collapsed
 * first, accessing a child path on a string crashes with "can't assign to property".
 *
 * Handles virtual ancestor paths that don't exist in `fields` (e.g. `payload`
 * when only `payload.event_type`, `payload.event_x2.good`, etc. exist).
 *
 * @param formValues - Current form values (flat object; nested paths accessed via getByPath)
 * @param prevCollapsedPaths - Set of paths that were collapsed before the depth change
 * @param currCollapsedGroups - Collapsed groups after the depth change
 * @param fields - Field definitions (used for itemFields expansion; may be empty for virtual ancestors)
 * @returns Ordered updates: expands first, then collapses
 */
export function computeDepthTransitionUpdates(
  formValues: Record<string, any>,
  prevCollapsedPaths: Set<string>,
  currCollapsedGroups: Array<{ path: string; label: string }>,
  fields: ResourceFieldMinimal[],
): DepthTransitionUpdates {
  const currPaths = new Set(currCollapsedGroups.map((g) => g.path));
  const expands: Array<{ path: string; value: any }> = [];
  const collapses: Array<{ path: string; value: string }> = [];

  // ── Phase 1: Expand paths that are no longer collapsed ──
  // Build a mutable copy of values so collapses see expanded data
  const workingValues = { ...formValues };

  for (const prevPath of prevCollapsedPaths) {
    if (currPaths.has(prevPath)) continue; // Still collapsed — no change
    const val = getByPath(workingValues, prevPath);
    if (typeof val !== 'string') continue; // Already an object — no expand needed

    // Use field definition if available, fallback to synthetic for virtual ancestors
    const field = fields.find((f) => f.name === prevPath);
    const fieldOrFallback = field ?? { name: prevPath, label: prevPath };
    const expanded = expandFieldFromJson(val, fieldOrFallback);
    if (expanded !== undefined) {
      expands.push({ path: prevPath, value: expanded });
      // Update working values so collapses see the expanded object
      setByPath(workingValues, prevPath, expanded);
    }
  }

  // ── Phase 2: Collapse paths that are newly collapsed ──
  for (const group of currCollapsedGroups) {
    if (prevCollapsedPaths.has(group.path)) continue; // Was already collapsed — no change
    const val = getByPath(workingValues, group.path);
    if (typeof val === 'string') continue; // Already a string — skip

    // Restore any previously-collapsed children to prevent double encoding
    const cleanVal = restoreCollapsedChildren(val, group.path, prevCollapsedPaths);
    const field = fields.find((f) => f.name === group.path);
    const jsonStr = collapseFieldToJson(
      cleanVal,
      field ?? { name: group.path, label: group.label },
    );
    collapses.push({ path: group.path, value: jsonStr });
  }

  return { expands, collapses };
}
