/**
 * Field type inference and helper functions
 */

import type { BinaryFormValue } from './types';

// Import minimal types to avoid circular dependencies
interface ResourceFieldMinimal {
  name: string;
  label?: string;
  type?: 'string' | 'number' | 'boolean' | 'date' | 'array' | 'object' | 'binary' | 'union';
  isArray?: boolean;
  isRequired?: boolean;
  isNullable?: boolean;
  enumValues?: string[];
  variant?: any; // FieldVariant
  itemFields?: ResourceFieldMinimal[];
}

export type FieldVariant =
  | { type: 'text' }
  | { type: 'textarea'; rows?: number }
  | { type: 'number'; min?: number; max?: number; step?: number }
  | { type: 'slider'; sliderMin?: number; sliderMax?: number; step?: number }
  | { type: 'select'; options?: { value: string; label: string }[] }
  | { type: 'checkbox' }
  | { type: 'switch' }
  | { type: 'date' }
  | { type: 'file'; accept?: string; multiple?: boolean }
  | { type: 'json'; height?: number }
  | { type: 'markdown'; height?: number }
  | { type: 'tags'; maxTags?: number; splitChars?: string[] }
  | { type: 'array'; itemType?: 'text' | 'number'; minItems?: number; maxItems?: number };

/**
 * Infer default UI variant from field metadata
 * Used when no explicit variant is specified in field configuration
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
  const { type, isArray, enumValues } = field;

  // If field has enumValues, use select
  if (enumValues && enumValues.length > 0) {
    const options = enumValues.map((v) => ({ value: v, label: v }));
    return { type: 'select', options };
  }

  if (type === 'number') return { type: 'number' };
  if (type === 'boolean') return { type: 'switch' };
  if (type === 'date') return { type: 'date' };
  if (type === 'binary') return { type: 'file' };
  if (type === 'object') return { type: 'json' };
  if (isArray) return { type: 'array', itemType: 'text' };

  // Default to text
  return { type: 'text' };
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
    if (sf.type === 'binary') {
      item[sf.name] = { _mode: 'empty' } as BinaryFormValue;
    } else if (sf.enumValues && sf.enumValues.length > 0) {
      item[sf.name] = sf.isNullable ? null : (sf.enumValues[0] ?? '');
    } else if (sf.type === 'number') {
      item[sf.name] = '';
    } else if (sf.type === 'boolean') {
      item[sf.name] = false;
    } else if (sf.type === 'object') {
      item[sf.name] = '';
    } else {
      item[sf.name] = '';
    }
  }
  return item;
}
