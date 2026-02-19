/**
 * resolveFieldKind — Pure function that resolves a ResourceField into
 * a concrete FieldKind enum value for renderer dispatch.
 *
 * The resolution priority follows the same precedence as the original
 * if-else chain to ensure identical behaviour.
 */

import type { ResourceField, FieldVariant } from '../../resources';
import { getDefaultVariant } from '@/lib/utils/formUtils';

/**
 * Exhaustive list of field kinds recognised by the renderer map.
 */
export type FieldKind =
  | 'itemFields'
  | 'union'
  | 'binary'
  | 'json'
  | 'markdown'
  | 'arrayString'
  | 'tags'
  | 'select'
  | 'checkbox'
  | 'switch'
  | 'date'
  | 'numberSlider'
  | 'number'
  | 'textarea'
  | 'refResourceId'
  | 'refResourceIdMulti'
  | 'refRevisionId'
  | 'refRevisionIdMulti'
  | 'text';

/**
 * Resolve a field + effective variant into a `FieldKind`.
 *
 * The order of checks mirrors the original `FieldRenderer` if-else chain
 * so behaviour is preserved exactly.
 */
export function resolveFieldKind(field: ResourceField): FieldKind {
  // 1. Array of typed objects (itemFields)
  if (field.itemFields && field.itemFields.length > 0) {
    return 'itemFields';
  }

  const effectiveVariant: FieldVariant = field.variant || getDefaultVariant(field);

  // 2. Union
  if (field.type === 'union' && field.unionMeta) {
    return 'union';
  }

  // 3. Binary
  if (field.type === 'binary') {
    return 'binary';
  }

  // 4. JSON / Object
  if (effectiveVariant.type === 'json' || field.type === 'object') {
    return 'json';
  }

  // 5. Markdown
  if (effectiveVariant.type === 'markdown') {
    return 'markdown';
  }

  // 6. Array of strings (comma-separated) — but not ref arrays
  if (field.isArray && field.type === 'string' && !field.ref) {
    return 'arrayString';
  }

  // 7. Tags
  if (effectiveVariant.type === 'tags') {
    return 'tags';
  }

  // 8. Select (enum or variant-based)
  if (effectiveVariant.type === 'select') {
    return 'select';
  }

  // 9. Boolean — checkbox
  if (field.type === 'boolean' && effectiveVariant.type === 'checkbox') {
    return 'checkbox';
  }

  // 10. Boolean — switch (default boolean)
  if (field.type === 'boolean') {
    return 'switch';
  }

  // 11. Date
  if (field.type === 'date' || effectiveVariant.type === 'date') {
    return 'date';
  }

  // 12. Number — slider
  if (field.type === 'number' && effectiveVariant.type === 'slider') {
    return 'numberSlider';
  }

  // 13. Number
  if (field.type === 'number') {
    return 'number';
  }

  // 14. Textarea
  if (effectiveVariant.type === 'textarea') {
    return 'textarea';
  }

  // 15. Ref resource_id (array)
  if (field.ref?.type === 'resource_id' && field.isArray) {
    return 'refResourceIdMulti';
  }

  // 16. Ref resource_id (single)
  if (field.ref?.type === 'resource_id') {
    return 'refResourceId';
  }

  // 17. Ref revision_id (array)
  if (field.ref?.type === 'revision_id' && field.isArray) {
    return 'refRevisionIdMulti';
  }

  // 18. Ref revision_id (single)
  if (field.ref?.type === 'revision_id') {
    return 'refRevisionId';
  }

  // 19. Default: text
  return 'text';
}
