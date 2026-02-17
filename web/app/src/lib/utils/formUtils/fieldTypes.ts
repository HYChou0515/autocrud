/**
 * Field type inference and helper functions
 *
 * Delegates to the Field Type Registry for all type-specific logic.
 */

import {
  getDefaultVariant,
  getEmptyValue,
  type FieldVariant,
  type ResourceFieldMinimal,
} from './fieldTypeRegistry';

// Re-export for backwards compatibility
export type { FieldVariant, ResourceFieldMinimal };

/**
 * Infer default UI variant from field metadata
 * Used when no explicit variant is specified in field configuration
 *
 * Delegates to the Field Type Registry. Enum fields always get 'select'.
 *
 * @param field - Resource field definition
 * @returns Default field variant based on field type and metadata
 *
 * @example
 * inferDefaultVariant({ type: 'boolean' }) // { type: 'switch' }
 * inferDefaultVariant({ type: 'number' }) // { type: 'number' }
 * inferDefaultVariant({ enumValues: ['a', 'b'] }) // { type: 'select', options: [...] }
 */
export function inferDefaultVariant(field: ResourceFieldMinimal): FieldVariant {
  return getDefaultVariant(field);
}

/**
 * Infer TypeScript type from a runtime value
 * Used for simple union fields to determine which type variant is active
 *
 * @param value - Value to inspect
 * @returns Inferred type string ('string', 'number', or 'boolean')
 *
 * @example
 * inferSimpleUnionType(42) // 'number'
 * inferSimpleUnionType(true) // 'boolean'
 * inferSimpleUnionType('hello') // 'string'
 * inferSimpleUnionType(null) // 'string' (default)
 */
export function inferSimpleUnionType(value: any): 'string' | 'number' | 'boolean' {
  if (value === null || value === undefined || value === '') {
    return 'string'; // Default
  }
  if (typeof value === 'number') return 'number';
  if (typeof value === 'boolean') return 'boolean';
  return 'string';
}

/**
 * Create empty/default object for array item based on itemFields
 * Used when adding a new item to an array of typed objects
 *
 * Delegates to the Field Type Registry for per-field empty values.
 *
 * @param itemFields - Field definitions for array item properties
 * @returns Object with default values for all item fields
 *
 * @example
 * createEmptyItemForFields([
 *   { name: 'name', type: 'string' },
 *   { name: 'age', type: 'number' },
 *   { name: 'active', type: 'boolean' }
 * ])
 * // Returns: { name: '', age: '', active: false }
 */
export function createEmptyItemForFields(itemFields: ResourceFieldMinimal[]): Record<string, any> {
  const item: Record<string, any> = {};
  for (const sf of itemFields) {
    item[sf.name] = getEmptyValue(sf);
  }
  return item;
}
