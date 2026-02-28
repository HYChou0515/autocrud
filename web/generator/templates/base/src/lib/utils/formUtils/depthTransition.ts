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
