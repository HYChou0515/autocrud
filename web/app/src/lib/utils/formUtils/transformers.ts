/**
 * Core data transformation functions for form-to-API and API-to-form conversions
 * These are the most complex functions in the form utilities
 */

import { getByPath, setByPath } from './paths';
import type { BinaryFormValue } from './types';

// Minimal ResourceField interface
interface ResourceFieldMinimal {
  name: string;
  label?: string;
  type?: 'string' | 'number' | 'boolean' | 'date' | 'array' | 'object' | 'binary' | 'union';
  isArray?: boolean;
  isRequired?: boolean;
  isNullable?: boolean;
  enumValues?: string[];
  itemFields?: ResourceFieldMinimal[];
  ref?: { resource: string; type: 'resource_id' | 'revision_id'; onDelete?: string };
  [key: string]: any;
}

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
        // Process each item's sub-fields for proper form defaults
        const processedItems = val.map((item: any) => {
          const processedItem = { ...item };
          for (const sf of field.itemFields!) {
            if (sf.type === 'binary') {
              // Convert existing binary data to BinaryFormValue
              const sv = processedItem[sf.name];
              if (sv && typeof sv === 'object' && sv.file_id) {
                processedItem[sf.name] = {
                  _mode: 'existing',
                  file_id: sv.file_id,
                  content_type: sv.content_type,
                  size: sv.size,
                } as BinaryFormValue;
              } else {
                processedItem[sf.name] = { _mode: 'empty' } as BinaryFormValue;
              }
            } else if (sf.isArray && sf.type === 'string' && Array.isArray(processedItem[sf.name])) {
              // Convert array to comma-separated string for form display
              processedItem[sf.name] = processedItem[sf.name].join(', ');
            } else if (processedItem[sf.name] === null || processedItem[sf.name] === undefined) {
              if (sf.enumValues && sf.enumValues.length > 0) processedItem[sf.name] = null;
              else if (sf.type === 'string' || sf.type === undefined) processedItem[sf.name] = '';
              else if (sf.type === 'number') processedItem[sf.name] = '';
              else if (sf.type === 'boolean') processedItem[sf.name] = false;
              else if (sf.type === 'object') processedItem[sf.name] = '';
            } else if (sf.type === 'object' && typeof processedItem[sf.name] === 'object') {
              processedItem[sf.name] = JSON.stringify(processedItem[sf.name], null, 2);
            }
          }
          return processedItem;
        });
        setByPath(processed, field.name, processedItems);
      } else {
        setByPath(processed, field.name, []);
      }
      continue;
    }

    if (dateFieldNames.includes(field.name)) {
      if (typeof val === 'string' && val) {
        setByPath(processed, field.name, new Date(val));
      } else if (val == null) {
        setByPath(processed, field.name, null);
      }
    } else if (field.isArray && field.ref && field.ref.type === 'resource_id') {
      // Array ref field — keep as array for MultiSelect, default to []
      setByPath(processed, field.name, Array.isArray(val) ? val : []);
    } else if (field.type === 'binary') {
      // Convert existing binary data to BinaryFormValue for editing
      if (val && typeof val === 'object' && val.file_id) {
        setByPath(processed, field.name, {
          _mode: 'existing',
          file_id: val.file_id,
          content_type: val.content_type,
          size: val.size,
        } as BinaryFormValue);
      } else {
        setByPath(processed, field.name, { _mode: 'empty' } as BinaryFormValue);
      }
    } else if (val == null) {
      // Convert null/undefined to proper defaults to avoid React warnings and Zod errors
      if (field.enumValues && field.enumValues.length > 0) {
        // Nullable enum: keep null so Zod z.enum().nullable() is satisfied
        setByPath(processed, field.name, null);
      } else if (field.type === 'string' || field.type === undefined) {
        setByPath(processed, field.name, '');
      } else if (field.type === 'number') {
        setByPath(processed, field.name, '');
      } else if (field.type === 'boolean') {
        setByPath(processed, field.name, false);
      } else if (field.type === 'object') {
        setByPath(processed, field.name, '');
      }
    } else if (field.type === 'object' && typeof val === 'object') {
      // Serialize object values to JSON string for textarea display
      setByPath(processed, field.name, JSON.stringify(val, null, 2));
    }
  }

  // For collapsed groups (fields beyond formDepth), reconstruct the parent object as JSON string
  for (const group of collapsedGroups) {
    const parentVal = getByPath(processed, group.path);
    if (parentVal && typeof parentVal === 'object' && !(parentVal instanceof Date)) {
      setByPath(processed, group.path, JSON.stringify(parentVal, null, 2));
    } else if (parentVal == null || parentVal === undefined) {
      setByPath(processed, group.path, '{}');
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

    // Array of typed objects — process each item's sub-fields
    if (field.itemFields && field.itemFields.length > 0) {
      const items = Array.isArray(val) ? val : [];
      const processedItems = items.map((item: any) => {
        const res: Record<string, any> = {};
        for (const sf of field.itemFields!) {
          let v = item?.[sf.name];
          if (sf.type === 'binary') {
            // Binary in array items — show info only (sync can't convert)
            const bv = v as BinaryFormValue | null;
            if (bv && bv._mode === 'existing' && bv.file_id) {
              v = { file_id: bv.file_id, content_type: bv.content_type, size: bv.size };
            } else if (bv && bv._mode === 'file' && bv.file) {
              v = { _pending_file: bv.file.name, content_type: bv.file.type };
            } else if (bv && bv._mode === 'url' && bv.url) {
              v = { _pending_url: bv.url };
            } else {
              v = null;
            }
          } else if (sf.isArray && sf.type === 'string') {
            // Convert comma-separated string to array
            v =
              typeof v === 'string'
                ? v
                    .split(',')
                    .map((s: string) => s.trim())
                    .filter(Boolean)
                : Array.isArray(v)
                  ? v
                  : [];
          } else if (
            sf.enumValues &&
            sf.enumValues.length > 0 &&
            (v === '' || v === null || v === undefined)
          ) {
            // Nullable enum: empty/null → null; required enum: keep as-is
            v = sf.isNullable ? null : undefined;
          } else if (sf.type === 'number' && (v === '' || v === undefined)) {
            v = sf.isNullable ? null : undefined;
          } else if (sf.type === 'string' && v === '' && sf.isNullable) {
            v = null;
          } else if (sf.type === 'object') {
            if (typeof v === 'string' && v.trim()) {
              try {
                v = JSON.parse(v);
              } catch {
                /* keep */
              }
            } else {
              v = null;
            }
          }
          res[sf.name] = v;
        }
        return res;
      });
      setByPath(result, field.name, processedItems);
      continue;
    }

    let cleanVal: any = val;
    if (dateFieldNames.includes(field.name)) {
      if (val instanceof Date) {
        cleanVal = val.toISOString();
      } else if (typeof val === 'string' && val) {
        const d = new Date(val);
        cleanVal = !isNaN(d.getTime()) ? d.toISOString() : val;
      } else {
        cleanVal = null;
      }
    } else if (field.type === 'binary') {
      // For JSON mode display, show existing binary info or null
      const bv = val as BinaryFormValue | null;
      if (bv && bv._mode === 'existing' && bv.file_id) {
        cleanVal = { file_id: bv.file_id, content_type: bv.content_type, size: bv.size };
      } else if (bv && bv._mode === 'file' && bv.file) {
        cleanVal = { _pending_file: bv.file.name, content_type: bv.file.type };
      } else if (bv && bv._mode === 'url' && bv.url) {
        cleanVal = { _pending_url: bv.url };
      } else {
        cleanVal = null;
      }
    } else if (field.type === 'object') {
      if (typeof val === 'string' && val.trim()) {
        try {
          cleanVal = JSON.parse(val);
        } catch {
          cleanVal = val;
        }
      } else {
        cleanVal = null;
      }
    } else if (field.type === 'number') {
      if (val === '' || val === undefined) {
        cleanVal = field.isNullable ? null : undefined;
      }
    } else if (field.type === 'string') {
      if (val === '' && field.isNullable) {
        cleanVal = null;
      }
    }

    setByPath(result, field.name, cleanVal);
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

    // Array of typed objects — process items for form
    if (field.itemFields && field.itemFields.length > 0) {
      if (Array.isArray(val)) {
        newValues[field.name] = val.map((item: any) => {
          const processed: Record<string, any> = {};
          for (const sf of field.itemFields!) {
            const v = item?.[sf.name];
            if (sf.type === 'binary') {
              if (v && typeof v === 'object' && v.file_id) {
                processed[sf.name] = {
                  _mode: 'existing',
                  file_id: v.file_id,
                  content_type: v.content_type,
                  size: v.size,
                };
              } else {
                processed[sf.name] = { _mode: 'empty' };
              }
            } else if (sf.isArray && sf.type === 'string') {
              // Convert array back to comma-separated string for form display
              processed[sf.name] = Array.isArray(v) ? v.join(', ') : (v ?? '');
            } else if (sf.type === 'object' && v != null && typeof v === 'object') {
              processed[sf.name] = JSON.stringify(v, null, 2);
            } else if (sf.type === 'number') {
              processed[sf.name] = v ?? '';
            } else if (sf.type === 'boolean') {
              processed[sf.name] = v ?? false;
            } else {
              processed[sf.name] = v ?? '';
            }
          }
          return processed;
        });
      } else {
        newValues[field.name] = [];
      }
      continue;
    }

    if (dateFieldNames.includes(field.name)) {
      if (typeof val === 'string' && val) {
        const d = new Date(val);
        newValues[field.name] = !isNaN(d.getTime()) ? d : null;
      } else {
        newValues[field.name] = null;
      }
    } else if (field.type === 'binary') {
      // Convert JSON binary data back to BinaryFormValue
      if (val && typeof val === 'object' && val.file_id) {
        newValues[field.name] = {
          _mode: 'existing',
          file_id: val.file_id,
          content_type: val.content_type,
          size: val.size,
        };
      } else {
        newValues[field.name] = { _mode: 'empty' };
      }
    } else if (field.type === 'object') {
      if (val != null && typeof val === 'object') {
        newValues[field.name] = JSON.stringify(val, null, 2);
      } else {
        newValues[field.name] = '';
      }
    } else if (field.type === 'number') {
      newValues[field.name] = val ?? '';
    } else if (field.type === 'boolean') {
      newValues[field.name] = val ?? false;
    } else {
      newValues[field.name] = val ?? '';
    }
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
