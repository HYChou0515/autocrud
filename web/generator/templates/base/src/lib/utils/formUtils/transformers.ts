/**
 * Core data transformation functions for form-to-API and API-to-form conversions
 *
 * Delegates type-specific logic to the Field Type Registry.
 */

import { getByPath, setByPath } from './paths';
import { getHandler, getEmptyValue } from './fieldTypeRegistry';
import type { ResourceFieldMinimal } from './fieldTypeRegistry';

interface CollapsedGroup {
  path: string;
  label: string;
}

/**
 * Check if a field name is a child of any collapsed group
 * @param fieldName - Field name to check (e.g., "user.profile.name")
 * @param collapsedGroups - Array of collapsed group definitions
 * @returns true if the field is under a collapsed group
 *
 * @example
 * isCollapsedChild('user.profile.name', [{ path: 'user', label: 'User' }])
 * // Returns: true (because 'user.profile.name' starts with 'user.')
 */
export function isCollapsedChild(fieldName: string, collapsedGroups: CollapsedGroup[]): boolean {
  return collapsedGroups.some((g) => fieldName.startsWith(g.path + '.'));
}

/**
 * Process initial values from API to form-compatible format
 *
 * Transforms raw API data into form state:
 * - ISO date strings → Date objects
 * - Binary data → BinaryFormValue objects
 * - Array refs → proper arrays
 * - null/undefined → type-appropriate defaults (empty string, false, etc.)
 * - Objects → JSON strings for textarea display
 * - Collapsed groups → JSON strings
 * - itemFields (array of typed objects) → processed array items
 *
 * **Warning**: This function mutates the input object (deep clone recommended before calling)
 *
 * @param initialValues - Raw initial values from API
 * @param fields - Field definitions
 * @param collapsedGroups - Groups that should render as JSON editors
 * @param dateFieldNames - Names of date fields for conversion
 * @returns Processed values ready for form initialization
 */
export function processInitialValues(
  initialValues: Record<string, any>,
  fields: ResourceFieldMinimal[],
  collapsedGroups: CollapsedGroup[],
  dateFieldNames: string[],
): Record<string, any> {
  const processed = { ...initialValues } as Record<string, any>;

  // Deep clone nested objects so mutations don't affect original data
  for (const key of Object.keys(processed)) {
    if (
      processed[key] &&
      typeof processed[key] === 'object' &&
      !Array.isArray(processed[key]) &&
      !(processed[key] instanceof Date)
    ) {
      processed[key] = JSON.parse(JSON.stringify(processed[key]));
    }
  }

  for (const field of fields) {
    const val = getByPath(processed, field.name);

    // Array of typed objects (has itemFields) — keep as actual array for list form
    if (field.itemFields && field.itemFields.length > 0) {
      if (Array.isArray(val)) {
        // Process each item's sub-fields using registry handlers
        const processedItems = val.map((item: any) => {
          const processedItem = { ...item };
          for (const sf of field.itemFields!) {
            const sv = processedItem[sf.name];
            const handler = getHandler(sf.type);
            processedItem[sf.name] = handler.toFormValue(sv, sf);
          }
          return processedItem;
        });
        setByPath(processed, field.name, processedItems);
      } else {
        setByPath(processed, field.name, []);
      }
      continue;
    }

    // Determine effective type: use 'date' handler for date-variant fields
    const effectiveType = dateFieldNames.includes(field.name) ? 'date' : field.type;

    // Array ref field — keep as array for MultiSelect, default to []
    if (field.isArray && field.ref && field.ref.type === 'resource_id') {
      setByPath(processed, field.name, Array.isArray(val) ? val : []);
    } else {
      // Delegate to handler for all type-specific conversion
      const handler = getHandler(effectiveType);
      setByPath(processed, field.name, handler.toFormValue(val, field));
    }
  }

  // For collapsed groups (fields beyond formDepth), reconstruct the parent object as JSON string
  for (const group of collapsedGroups) {
    const parentVal = getByPath(processed, group.path);
    if (parentVal && typeof parentVal === 'object' && !(parentVal instanceof Date)) {
      setByPath(processed, group.path, JSON.stringify(parentVal, null, 2));
    } else if (parentVal == null || parentVal === undefined) {
      // Use '[]' for array fields (itemFields), '{}' for plain objects
      const field = fields.find((f) => f.name === group.path);
      setByPath(processed, group.path, field?.itemFields ? '[]' : '{}');
    }
    // If it's already a string (e.g. from a visible 'object' field), keep it
  }

  return processed;
}

/**
 * Convert form values to API-ready object (synchronous version)
 * Does NOT convert binary files (use processSubmitValues for that)
 *
 * Transforms form state to API format:
 * - Date objects → ISO strings
 * - Binary → display format (existing file_id or pending markers)
 * - JSON strings → parsed objects
 * - Empty strings → null for nullable fields
 * - itemFields → processed array items
 * - Collapsed groups → parsed objects
 *
 * @param formValues - Current form state
 * @param fields - Field definitions
 * @param collapsedGroups - Groups rendered as JSON editors
 * @param dateFieldNames - Names of date fields
 * @returns API-ready object (binary fields show as info only)
 */
export function formValuesToApiObject(
  formValues: Record<string, any>,
  fields: ResourceFieldMinimal[],
  collapsedGroups: CollapsedGroup[],
  dateFieldNames: string[],
): Record<string, any> {
  const result: Record<string, any> = {};

  for (const field of fields) {
    // Skip fields whose data is managed by a collapsed group JSON editor
    if (isCollapsedChild(field.name, collapsedGroups)) continue;

    const val = getByPath(formValues, field.name);

    // Array of typed objects — process each item's sub-fields using registry
    if (field.itemFields && field.itemFields.length > 0) {
      const items = Array.isArray(val) ? val : [];
      const processedItems = items.map((item: any) => {
        const res: Record<string, any> = {};
        for (const sf of field.itemFields!) {
          const v = item?.[sf.name];
          const handler = getHandler(sf.type);
          res[sf.name] = handler.toApiValue(v, sf);
        }
        return res;
      });
      setByPath(result, field.name, processedItems);
      continue;
    }

    // Determine effective type: use 'date' handler for date-variant fields
    const effectiveType = dateFieldNames.includes(field.name) ? 'date' : field.type;
    const handler = getHandler(effectiveType);
    setByPath(result, field.name, handler.toApiValue(val, field));
  }

  // Parse collapsed group JSON strings back to objects
  for (const group of collapsedGroups) {
    const val = getByPath(formValues, group.path);
    if (typeof val === 'string' && val.trim()) {
      try {
        setByPath(result, group.path, JSON.parse(val));
      } catch {
        /* keep as-is */
      }
    } else {
      setByPath(result, group.path, null);
    }
  }

  return result;
}

/**
 * Apply a parsed JSON object back into form values
 * Inverse operation of formValuesToApiObject
 *
 * Transforms API JSON to form state:
 * - ISO date strings → Date objects
 * - Binary objects → BinaryFormValue objects
 * - Objects → JSON strings for textarea display
 * - null/undefined → type-appropriate form defaults
 * - itemFields → processed array items
 * - Collapsed groups → JSON strings
 *
 * @param jsonObject - Parsed JSON object from API
 * @param fields - Field definitions
 * @param collapsedGroups - Groups that render as JSON editors
 * @param dateFieldNames - Names of date fields
 * @returns Form-compatible values object
 */
export function applyJsonToForm(
  jsonObject: Record<string, any>,
  fields: ResourceFieldMinimal[],
  collapsedGroups: CollapsedGroup[],
  dateFieldNames: string[],
): Record<string, any> {
  const newValues: Record<string, any> = {};

  for (const field of fields) {
    // Skip fields managed by collapsed groups
    if (isCollapsedChild(field.name, collapsedGroups)) continue;

    const val = getByPath(jsonObject, field.name);

    // Array of typed objects — process items for form using registry
    if (field.itemFields && field.itemFields.length > 0) {
      if (Array.isArray(val)) {
        newValues[field.name] = val.map((item: any) => {
          const processed: Record<string, any> = {};
          for (const sf of field.itemFields!) {
            const v = item?.[sf.name];
            const handler = getHandler(sf.type);
            processed[sf.name] = handler.fromJsonValue(v, sf);
          }
          return processed;
        });
      } else {
        newValues[field.name] = [];
      }
      continue;
    }

    // Array ref field — keep as array for RefMultiSelect, default to []
    if (field.isArray && field.ref && field.ref.type === 'resource_id') {
      newValues[field.name] = Array.isArray(val) ? val : [];
      continue;
    }

    // Determine effective type: use 'date' handler for date-variant fields
    const effectiveType = dateFieldNames.includes(field.name) ? 'date' : field.type;
    const handler = getHandler(effectiveType);
    newValues[field.name] = handler.fromJsonValue(val, field);
  }

  // Apply collapsed group values as JSON strings
  for (const group of collapsedGroups) {
    const val = getByPath(jsonObject, group.path);
    if (val != null && typeof val === 'object') {
      newValues[group.path] = JSON.stringify(val, null, 2);
    } else {
      newValues[group.path] = '{}';
    }
  }

  return newValues;
}

/**
 * Create an empty item for an array-with-itemFields field.
 *
 * Builds a default object with each sub-field set to its type-appropriate
 * empty value via the Field Type Registry.
 *
 * @param itemFields - Sub-field definitions for the array items
 * @returns A new empty item object with defaults for each sub-field
 *
 * @example
 * createEmptyItem([
 *   { name: 'name', label: 'Name', type: 'string' },
 *   { name: 'count', label: 'Count', type: 'number' },
 *   { name: 'active', label: 'Active', type: 'boolean' },
 * ])
 * // Returns: { name: '', count: '', active: false }
 */
export function createEmptyItem(itemFields: ResourceFieldMinimal[]): Record<string, any> {
  const item: Record<string, any> = {};
  for (const sf of itemFields) {
    item[sf.name] = getEmptyValue(sf);
  }
  return item;
}

/**
 * Process form values for submission (synchronous field processing).
 *
 * Handles all non-binary field transformations:
 * - itemFields: each sub-field processed via handler.submitValue ?? handler.toApiValue
 * - Date fields: converted via date handler
 * - Binary field sub-items in itemFields: marked as skipped (returned in binarySubFieldKeys)
 * - All other fields: delegated to registry handler
 * - Collapsed groups: JSON strings parsed back to objects
 *
 * Binary top-level fields are SKIPPED (returned in skippedBinaryFields) because
 * they require async File→base64 conversion that must happen in the component.
 *
 * @param values - Deep-cloned form values (will be mutated)
 * @param fields - Field definitions
 * @param collapsedGroups - Groups rendered as JSON editors
 * @param dateFieldNames - Names of date-type fields
 * @returns Object with processed values and lists of binary fields to handle async
 */
export function processSubmitValues(
  values: Record<string, any>,
  fields: ResourceFieldMinimal[],
  collapsedGroups: CollapsedGroup[],
  dateFieldNames: string[],
): {
  processed: Record<string, any>;
  skippedBinaryFields: string[];
  binarySubFieldKeys: string[];
} {
  const processed = values;
  const skippedBinaryFields: string[] = [];
  const binarySubFieldKeys: string[] = [];

  for (const field of fields) {
    // Skip collapsed children — their data is in the parent JSON string
    if (isCollapsedChild(field.name, collapsedGroups)) continue;

    const val = getByPath(processed, field.name);

    // Array of typed objects — process each item's sub-fields
    if (field.itemFields && field.itemFields.length > 0) {
      if (Array.isArray(val)) {
        const cleanItems = val.map((item: any, idx: number) => {
          const res: Record<string, any> = {};
          for (const sf of field.itemFields!) {
            let v = item?.[sf.name];
            if (sf.type === 'binary') {
              // Mark for async processing by component
              binarySubFieldKeys.push(`${field.name}.${idx}.${sf.name}`);
              res[sf.name] = v; // placeholder, component replaces with async result
            } else {
              const handler = getHandler(sf.type);
              v = (handler.submitValue ?? handler.toApiValue)(v, sf);
              res[sf.name] = v;
            }
          }
          return res;
        });
        setByPath(processed, field.name, cleanItems);
      }
      continue;
    }

    if (dateFieldNames.includes(field.name)) {
      const handler = getHandler('date');
      const submitFn = handler.submitValue ?? handler.toApiValue;
      setByPath(processed, field.name, submitFn(val, field));
    } else if (field.type === 'binary') {
      skippedBinaryFields.push(field.name);
      continue;
    } else {
      const handler = getHandler(field.type);
      const submitFn = handler.submitValue ?? handler.toApiValue;
      setByPath(processed, field.name, submitFn(val, field));
    }
  }

  // Parse collapsed group JSON strings back to objects
  for (const group of collapsedGroups) {
    const val = getByPath(processed, group.path);
    if (typeof val === 'string' && val.trim()) {
      try {
        setByPath(processed, group.path, JSON.parse(val));
      } catch {
        /* keep */
      }
    } else if (typeof val === 'string' && !val.trim()) {
      setByPath(processed, group.path, null);
    }
  }

  return { processed, skippedBinaryFields, binarySubFieldKeys };
}
