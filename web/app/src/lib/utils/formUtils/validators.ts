/**
 * Validation utility functions for form data
 *
 * Delegates type-specific validation to the Field Type Registry.
 */

import { getByPath } from './paths';
import { getHandler } from './fieldTypeRegistry';

// Minimal field interface
interface ResourceFieldMinimal {
  name: string;
  type?: string;
  itemFields?: ResourceFieldMinimal[];
  [key: string]: any;
}

interface CollapsedGroup {
  path: string;
  label: string;
}

/**
 * Validate JSON object fields
 * Delegates to registry handler.validate() for each field type.
 *
 * @param values - Form values to validate
 * @param fields - Field definitions
 * @param collapsedGroups - Collapsed groups (also validated as JSON objects)
 * @returns Object with field names as keys and error messages as values
 *
 * @example
 * validateJsonFields(
 *   { metadata: '{"key": "value"}' },
 *   [{ name: 'metadata', type: 'object' }],
 *   []
 * )
 * // Returns: {} (no errors)
 *
 * @example
 * validateJsonFields(
 *   { metadata: '[1, 2, 3]' },  // Array, not object
 *   [{ name: 'metadata', type: 'object' }],
 *   []
 * )
 * // Returns: { metadata: 'Must be a JSON object (not array or primitive)' }
 */
export function validateJsonFields(
  values: Record<string, any>,
  fields: ResourceFieldMinimal[],
  collapsedGroups: CollapsedGroup[],
): Record<string, string> {
  const errors: Record<string, string> = {};

  // Validate fields using registry handler.validate()
  for (const field of fields) {
    // Skip array fields with itemFields — they use actual arrays
    if (field.itemFields && field.itemFields.length > 0) continue;

    const handler = getHandler(field.type);
    if (handler.validate) {
      const val = getByPath(values, field.name);
      const error = handler.validate(val, field);
      if (error) {
        errors[field.name] = error;
      }
    }
  }

  // Also validate collapsed group JSON fields (structural concern, not type-based)
  for (const group of collapsedGroups) {
    const val = getByPath(values, group.path);
    if (typeof val === 'string' && val.trim()) {
      try {
        const parsed = JSON.parse(val);
        if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
          errors[group.path] = 'Must be a JSON object (not array or primitive)';
        }
      } catch {
        errors[group.path] = 'Invalid JSON format';
      }
    }
  }

  return errors;
}

/**
 * Parse and validate JSON text
 * Used for JSON mode validation
 *
 * @param jsonText - JSON string to validate
 * @returns Object with success flag, error message, or parsed data
 *
 * @example
 * parseAndValidateJson('{"name": "Alice"}')
 * // Returns: { success: true, data: { name: 'Alice' } }
 *
 * @example
 * parseAndValidateJson('[1, 2, 3]')  // Array, not object
 * // Returns: { success: false, error: 'Must be a JSON object' }
 *
 * @example
 * parseAndValidateJson('invalid json')
 * // Returns: { success: false, error: 'Invalid JSON format' }
 */
export function parseAndValidateJson(jsonText: string): {
  success: boolean;
  data?: any;
  error?: string;
} {
  let parsed: any;
  try {
    parsed = JSON.parse(jsonText);
  } catch {
    return { success: false, error: 'Invalid JSON format' };
  }

  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
    return { success: false, error: 'Must be a JSON object' };
  }

  return { success: true, data: parsed };
}

/**
 * Pre-process array field values for validation
 * Converts comma-separated strings to arrays for isArray fields
 * (excluding array ref fields and itemFields arrays which are already arrays)
 *
 * @param values - Form values
 * @param fields - Field definitions
 * @returns Processed values with arrays converted
 *
 * @example
 * preprocessArrayFields(
 *   { tags: 'a, b, c', items: [{ id: 1 }] },
 *   [
 *     { name: 'tags', isArray: true },
 *     { name: 'items', itemFields: [{ name: 'id' }] }
 *   ]
 * )
 * // Returns: { tags: ['a', 'b', 'c'], items: [{ id: 1 }] }
 */
export function preprocessArrayFields(
  values: Record<string, any>,
  fields: ResourceFieldMinimal[],
): Record<string, any> {
  const processed = { ...(values as Record<string, any>) };

  for (const field of fields) {
    // Simple array fields (comma-separated string) need conversion
    if (
      field.isArray &&
      !(field.itemFields && field.itemFields.length > 0) &&
      !(field.ref && field.ref.type === 'resource_id')
    ) {
      const val = processed[field.name];
      if (typeof val === 'string') {
        processed[field.name] = val
          ? val
              .split(',')
              .map((s: string) => s.trim())
              .filter(Boolean)
          : [];
      }
    }

    // Also pre-process nested simple-array sub-fields inside array-with-itemFields
    if (field.itemFields && field.itemFields.length > 0 && Array.isArray(processed[field.name])) {
      processed[field.name] = processed[field.name].map((item: any) => {
        if (!item || typeof item !== 'object') return item;
        const processedItem = { ...item };
        for (const sf of field.itemFields!) {
          if (sf.isArray && typeof processedItem[sf.name] === 'string') {
            processedItem[sf.name] = processedItem[sf.name]
              ? processedItem[sf.name]
                  .split(',')
                  .map((s: string) => s.trim())
                  .filter(Boolean)
              : [];
          }
        }
        return processedItem;
      });
    }
  }

  return processed;
}
