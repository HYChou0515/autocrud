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

/**
 * Result of parent-based field grouping for Fieldset rendering
 */
export interface FieldParentGroup<T extends ResourceFieldMinimal = ResourceFieldMinimal> {
  /** Parent path (dot-notation prefix excluding leaf), or null for top-level fields */
  parentPath: string | null;
  /** Human-readable label for the parent, or null for top-level fields */
  parentLabel: string | null;
  /** Fields belonging to this group */
  fields: T[];
  /** Nested child groups (sub-structs whose parentPath is a child of this group's parentPath) */
  children: FieldParentGroup<T>[];
}

/**
 * Group visible fields by their immediate parent path for Fieldset rendering.
 *
 * Fields are grouped by stripping the last segment from their dot-notation name.
 * Consecutive fields sharing the same parent are merged into one group.
 * Fields without dots (top-level) get parentPath=null.
 *
 * @param fields - Visible fields (already filtered by depth)
 * @returns Array of groups, each with parentPath, parentLabel, and fields
 *
 * @example
 * groupFieldsByParent([
 *   { name: 'id', label: 'ID' },
 *   { name: 'user.email', label: 'Email' },
 *   { name: 'user.name', label: 'Name' },
 * ])
 * // Returns:
 * // [
 * //   { parentPath: null, parentLabel: null, fields: [{ name: 'id' }] },
 * //   { parentPath: 'user', parentLabel: 'User', fields: [{ name: 'user.email' }, { name: 'user.name' }] },
 * // ]
 */
export function groupFieldsByParent<T extends ResourceFieldMinimal>(
  fields: T[],
): FieldParentGroup<T>[] {
  if (fields.length === 0) return [];

  // Use a Map to accumulate fields by parent, preserving first-appearance order.
  // This merges non-consecutive fields sharing the same parent into one group,
  // preventing duplicate React keys (e.g. payload.* split by payload.event_body.*).
  const groupMap = new Map<string | null, FieldParentGroup<T>>();
  const insertionOrder: (string | null)[] = [];

  for (const field of fields) {
    const dotIdx = field.name.lastIndexOf('.');
    const parent: string | null = dotIdx > 0 ? field.name.substring(0, dotIdx) : null;

    const existing = groupMap.get(parent);
    if (existing) {
      existing.fields.push(field);
    } else {
      const parentLabel = parent != null ? toLabel(parent.split('.').pop()!) : null;
      const group: FieldParentGroup<T> = {
        parentPath: parent,
        parentLabel,
        fields: [field],
        children: [],
      };
      groupMap.set(parent, group);
      insertionOrder.push(parent);
    }
  }

  // Build tree: nest child groups under their parent group if it exists.
  // Process from deepest to shallowest so multi-level nesting works correctly.
  const nonNullKeys = insertionOrder
    .filter((k): k is string => k != null)
    .sort((a, b) => b.split('.').length - a.split('.').length);

  const nestedKeys = new Set<string | null>();

  for (const key of nonNullKeys) {
    const lastDot = key.lastIndexOf('.');
    if (lastDot > 0) {
      const ancestorKey = key.substring(0, lastDot);
      const ancestorGroup = groupMap.get(ancestorKey);
      if (ancestorGroup) {
        ancestorGroup.children.push(groupMap.get(key)!);
        nestedKeys.add(key);
      }
    }
  }

  // Return only root-level groups (not nested) in first-appearance order.
  return insertionOrder.filter((key) => !nestedKeys.has(key)).map((key) => groupMap.get(key)!);
}
