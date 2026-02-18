/**
 * Field grouping and depth-based visibility logic
 */

import { toLabel } from './converters';

// Minimal ResourceField interface to avoid circular dependencies
interface ResourceFieldMinimal {
  name: string;
  label?: string;
  type?: string;
  itemFields?: ResourceFieldMinimal[];
  [key: string]: any;
}

/**
 * Result of field grouping computation
 */
export interface FieldGroupingResult<T extends ResourceFieldMinimal = ResourceFieldMinimal> {
  /** Fields that should be rendered as individual form inputs */
  visibleFields: T[];
  /** Parent paths that have collapsed children (rendered as JSON editors) */
  collapsedGroups: Array<{ path: string; label: string }>;
  /** Mapping from parent path to its child fields (for reconstruction) */
  collapsedGroupFields: Map<string, T[]>;
}

/**
 * Compute visible fields and collapsed groups based on form depth
 *
 * This function splits fields into two categories:
 * 1. Fields at or above the depth threshold → rendered as individual form inputs
 * 2. Fields beyond the depth threshold → grouped by ancestor path, rendered as JSON editors
 *
 * @param fields - All resource fields
 * @param formDepth - Maximum depth for field expansion (1 = flat, higher = more nesting)
 * @returns Object with visibleFields, collapsedGroups, and collapsedGroupFields
 *
 * @example
 * // With formDepth=1, all nested fields collapse into JSON editors
 * computeVisibleFieldsAndGroups([
 *   { name: 'name' },
 *   { name: 'user.email' },
 *   { name: 'user.profile.bio' }
 * ], 1)
 * // Returns:
 * // visibleFields: [{ name: 'name' }]
 * // collapsedGroups: [{ path: 'user', label: 'User' }]
 * // collapsedGroupFields: Map { 'user' => [{ name: 'user.email' }, { name: 'user.profile.bio' }] }
 *
 * @example
 * // With formDepth=2, second-level fields are visible
 * computeVisibleFieldsAndGroups([
 *   { name: 'name' },
 *   { name: 'user.email' },
 *   { name: 'user.profile.bio' }
 * ], 2)
 * // Returns:
 * // visibleFields: [{ name: 'name' }, { name: 'user.email' }]
 * // collapsedGroups: [{ path: 'user.profile', label: 'Profile' }]
 * // collapsedGroupFields: Map { 'user.profile' => [{ name: 'user.profile.bio' }] }
 */
export function computeVisibleFieldsAndGroups<T extends ResourceFieldMinimal>(
  fields: T[],
  formDepth: number,
): FieldGroupingResult<T> {
  const visible: T[] = [];
  const groupedChildren = new Map<string, T[]>();

  for (const field of fields) {
    const depth = field.name.split('.').length;

    if (depth <= formDepth) {
      // Field is at or above the depth threshold
      // If field has itemFields but depth isn't enough to expand them,
      // treat it as a collapsed JSON editor (like a nested object group).
      if (field.itemFields && field.itemFields.length > 0 && depth + 1 > formDepth) {
        if (!groupedChildren.has(field.name)) {
          groupedChildren.set(field.name, []);
        }
      } else {
        visible.push(field);
      }
    } else {
      // Field is beyond the depth threshold
      // Find the ancestor path at the formDepth boundary
      const parts = field.name.split('.');
      const ancestorPath = parts.slice(0, formDepth).join('.');
      if (!groupedChildren.has(ancestorPath)) {
        groupedChildren.set(ancestorPath, []);
      }
      groupedChildren.get(ancestorPath)!.push(field);
    }
  }

  // Build collapsed group info: parent paths that have collapsed children
  const groups: { path: string; label: string }[] = [];
  for (const parentPath of groupedChildren.keys()) {
    // Don't add a collapsed group if this path already exists as a visible field
    // (e.g. field.type === 'object' already renders as JSON)
    const alreadyVisible = visible.some((f) => f.name === parentPath);
    if (!alreadyVisible) {
      const labelParts = parentPath.split('.');
      const label = toLabel(labelParts[labelParts.length - 1]);
      groups.push({ path: parentPath, label });
    }
  }

  return {
    visibleFields: visible,
    collapsedGroups: groups,
    collapsedGroupFields: groupedChildren,
  };
}

/**
 * Compute maximum available depth from all fields
 * Fields with itemFields add an extra depth level
 *
 * @param fields - All resource fields
 * @returns Maximum depth value (minimum is 1)
 *
 * @example
 * computeMaxAvailableDepth([
 *   { name: 'name' },                    // depth 1
 *   { name: 'user.email' },              // depth 2
 *   { name: 'user.profile.bio' }         // depth 3
 * ])
 * // Returns: 3
 *
 * @example
 * computeMaxAvailableDepth([
 *   { name: 'items', itemFields: [...] } // depth 1 + 1 = 2
 * ])
 * // Returns: 2
 */
export function computeMaxAvailableDepth(fields: ResourceFieldMinimal[]): number {
  let max = 1;
  for (const f of fields) {
    const d = f.name.split('.').length;
    if (d > max) max = d;
    // Fields with itemFields (array of typed objects) represent an extra depth level
    if (f.itemFields && f.itemFields.length > 0 && d + 1 > max) max = d + 1;
  }
  return max;
}
