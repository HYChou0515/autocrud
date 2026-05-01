/**
 * searchFieldUtils — Automatically derive SearchableField[] from
 * ResourceField[] + indexedFields, with depth-controlled expansion.
 *
 * Index fields are always included regardless of depth.
 * Non-index fields are included up to the specified depth (default 1).
 * Complex types (array, object, binary, union) are skipped unless indexed.
 */

import type { ResourceField } from '../../resources';
import type { SearchableField } from './types';

/** Primitive field types that can be used as search filters */
const PRIMITIVE_FIELD_TYPES = new Set<string>(['string', 'number', 'boolean', 'date']);

/**
 * Meta fields that can be searched via the SearchForm.
 * These do NOT overlap with MetaSearchForm (time ranges + created_by/updated_by
 * are already handled there). We add:
 * - resource_id, schema_version, current_revision_id (string)
 * - is_deleted (boolean)
 */
export const META_SEARCHABLE_FIELDS: SearchableField[] = [
  { name: 'resource_id', label: '[meta] Resource ID', type: 'string' },
  { name: 'schema_version', label: '[meta] Schema Version', type: 'string' },
  { name: 'is_deleted', label: '[meta] Is Deleted', type: 'boolean' },
  { name: 'current_revision_id', label: '[meta] Current Revision ID', type: 'string' },
  { name: 'created_by', label: '[meta] Created By', type: 'string' },
  { name: 'updated_by', label: '[meta] Updated By', type: 'string' },
];

/**
 * Map a ResourceField type to a SearchableField type.
 * Fields with enumValues become 'select'.
 */
function toSearchType(
  field: ResourceField,
): 'string' | 'number' | 'boolean' | 'date' | 'select' | null {
  if (field.enumValues && field.enumValues.length > 0) return 'select';
  if (PRIMITIVE_FIELD_TYPES.has(field.type))
    return field.type as 'string' | 'number' | 'boolean' | 'date';
  return null;
}

/**
 * Build select options from enumValues.
 */
function buildSelectOptions(enumValues: string[]): { label: string; value: string }[] {
  return enumValues.map((v) => ({ label: v, value: v }));
}

/**
 * Derive SearchableField[] from ResourceField[] + indexedFields.
 *
 * @param fields      Resource field definitions from config.fields
 * @param indexedFields  List of indexed field names (dot-paths)
 * @param depth       Max depth for non-indexed fields (default 1 = first level only)
 * @returns SearchableField[] suitable for SearchForm
 */
export function fieldsToSearchableFields(
  fields: ResourceField[],
  indexedFields?: string[],
  depth: number = 1,
): SearchableField[] {
  const result: SearchableField[] = [];
  const indexed = new Set(indexedFields ?? []);

  collectFields(fields, '', indexed, depth, 1, result);

  // Also add indexed fields that weren't discovered by traversal
  // (e.g. deeply nested indexed dot-paths beyond `fields`)
  if (indexedFields) {
    const existingNames = new Set(result.map((f) => f.name));
    for (const idxField of indexedFields) {
      if (!existingNames.has(idxField)) {
        // Add as a string type by default for indexed fields not in the schema
        result.push({ name: idxField, label: idxField, type: 'string' });
      }
    }
  }

  // Append meta searchable fields (Bug 2)
  const existingAfterAll = new Set(result.map((f) => f.name));
  for (const mf of META_SEARCHABLE_FIELDS) {
    if (!existingAfterAll.has(mf.name)) {
      result.push(mf);
    }
  }

  return result;
}

/**
 * Recursively collect searchable fields.
 */
function collectFields(
  fields: ResourceField[],
  prefix: string,
  indexed: Set<string>,
  maxDepth: number,
  currentDepth: number,
  result: SearchableField[],
): void {
  for (const field of fields) {
    // Skip const/discriminator fields
    if (field.constValue !== undefined) continue;

    const fullPath = prefix ? `${prefix}.${field.name}` : field.name;
    const isIndexed = indexed.has(fullPath);

    // Determine if this field should be included
    const searchType = toSearchType(field);

    if (searchType) {
      // Include if: indexed OR within depth limit
      if (isIndexed || currentDepth <= maxDepth) {
        const sf: SearchableField = {
          name: fullPath,
          label: field.label,
          type: searchType,
        };
        if (searchType === 'select' && field.enumValues) {
          sf.options = buildSelectOptions(field.enumValues);
        }
        result.push(sf);
      }
    }

    // Recurse into object sub-fields (itemFields on non-array objects)
    if (field.type === 'object' && field.itemFields && !field.isArray) {
      // Check if any indexed field starts with this prefix
      const hasIndexedChild = Array.from(indexed).some((f) => f.startsWith(fullPath + '.'));
      // Recurse if indexed children exist or within depth limit
      if (hasIndexedChild || currentDepth < maxDepth) {
        collectFields(field.itemFields, fullPath, indexed, maxDepth, currentDepth + 1, result);
      }
    }
  }
}
