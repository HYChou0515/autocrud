/**
 * Field Type Registry — centralizes ALL field.type dispatch logic
 *
 * Before the registry, adding a new field type required changes in 30+ places
 * across 4 files. Now, you only need to:
 *
 * 1. Add a FieldTypeHandler with all behaviors
 * 2. Call registerFieldType('myType', myHandler)
 *
 * @example
 * // Register a custom field type
 * registerFieldType('email', {
 *   defaultVariant: () => ({ type: 'text' }),
 *   emptyValue: () => '',
 *   toFormValue: (val) => val ?? '',
 *   toApiValue: (val, field) => (val === '' && field.isNullable ? null : val),
 *   fromJsonValue: (val) => val ?? '',
 * });
 */

import type { FieldVariant } from '../../resources';
import type { BinaryFormValue } from './types';

// Re-export for convenience — consumers can import from the registry
export type { FieldVariant };

/**
 * Supported built-in field types
 */
export type FieldType =
  | 'string'
  | 'number'
  | 'boolean'
  | 'date'
  | 'array'
  | 'object'
  | 'binary'
  | 'union';

/**
 * Minimal field interface used by handlers.
 * Avoids importing the full ResourceField to prevent circular dependencies.
 */
export interface ResourceFieldMinimal {
  name: string;
  label?: string;
  type?: string;
  isArray?: boolean;
  isRequired?: boolean;
  isNullable?: boolean;
  enumValues?: string[];
  itemFields?: ResourceFieldMinimal[];
  ref?: { resource: string; type: 'resource_id' | 'revision_id'; onDelete?: string };
  [key: string]: any;
}

/**
 * Defines ALL behaviors for a single field type.
 *
 * Each method handles a specific stage of the form lifecycle:
 * - defaultVariant: Which UI component to render by default
 * - emptyValue: Default value for new/empty fields
 * - toFormValue: API data → form state (processInitialValues)
 * - toApiValue: form state → API data (formValuesToApiObject, preview/sync)
 * - fromJsonValue: JSON import → form state (applyJsonToForm)
 * - submitValue: form state → API data for final submission (handleSubmit)
 * - validate: Type-specific validation (validateJsonFields)
 */
export interface FieldTypeHandler {
  /** Default UI variant when no explicit variant is specified */
  defaultVariant(field: ResourceFieldMinimal): FieldVariant;

  /** Create an empty/default value for a new field of this type */
  emptyValue(field: ResourceFieldMinimal): any;

  /**
   * Convert API/raw value to form-compatible value.
   * Must handle both null and non-null inputs.
   *
   * Called during:
   * - processInitialValues (top-level fields and itemFields sub-fields)
   */
  toFormValue(value: any, field: ResourceFieldMinimal): any;

  /**
   * Convert form value to API-ready value (synchronous).
   *
   * Called during:
   * - formValuesToApiObject (preview, JSON mode display)
   */
  toApiValue(value: any, field: ResourceFieldMinimal): any;

  /**
   * Convert JSON-imported value to form-compatible value.
   *
   * Called during:
   * - applyJsonToForm (JSON mode → form mode switch)
   */
  fromJsonValue(value: any, field: ResourceFieldMinimal): any;

  /**
   * Convert form value for final submission.
   * If not provided, toApiValue is used as fallback.
   *
   * Called during:
   * - handleSubmit (actual form submission)
   *
   * @remarks
   * This exists because submit-time conversion can differ from preview conversion.
   * For example, date fields handle Date objects in submit but not in sync preview.
   */
  submitValue?(value: any, field: ResourceFieldMinimal): any;

  /**
   * Validate form value for this field type.
   * Returns error message string or null if valid.
   *
   * Called during:
   * - validateJsonFields (form validation pass)
   */
  validate?(value: any, field: ResourceFieldMinimal): string | null;
}

// ============================================================================
// Built-in Handlers
// ============================================================================

export const stringHandler: FieldTypeHandler = {
  defaultVariant(field) {
    if (field.isArray) return { type: 'array', itemType: 'text' };
    return { type: 'text' };
  },

  emptyValue() {
    return '';
  },

  toFormValue(val, field) {
    // Array of strings → comma-separated for form display
    if (field.isArray && Array.isArray(val)) return val.join(', ');
    if (val == null) {
      // Nullable enum: keep null so Zod z.enum().nullable() is satisfied
      if (field.enumValues && field.enumValues.length > 0) return null;
      return '';
    }
    return val;
  },

  toApiValue(val, field) {
    // Array of strings → split comma-separated string
    if (field.isArray) {
      return typeof val === 'string'
        ? val
            .split(',')
            .map((s: string) => s.trim())
            .filter(Boolean)
        : Array.isArray(val)
          ? val
          : [];
    }
    // Enum empty value → null/undefined based on nullable
    if (field.enumValues && field.enumValues.length > 0 && (val === '' || val == null)) {
      return field.isNullable ? null : undefined;
    }
    // Nullable empty string → null
    if (val === '' && field.isNullable) return null;
    return val;
  },

  fromJsonValue(val, field) {
    if (field.isArray && Array.isArray(val)) return val.join(', ');
    return val ?? '';
  },
};

export const numberHandler: FieldTypeHandler = {
  defaultVariant() {
    return { type: 'number' };
  },

  emptyValue() {
    return '';
  },

  toFormValue(val, field) {
    if (val == null) {
      if (field.enumValues && field.enumValues.length > 0) return null;
      return '';
    }
    return val;
  },

  toApiValue(val, field) {
    if (field.enumValues && field.enumValues.length > 0 && (val === '' || val == null)) {
      return field.isNullable ? null : undefined;
    }
    if (val === '' || val === undefined) return field.isNullable ? null : undefined;
    return val;
  },

  fromJsonValue(val) {
    return val ?? '';
  },
};

export const booleanHandler: FieldTypeHandler = {
  defaultVariant() {
    return { type: 'switch' };
  },

  emptyValue() {
    return false;
  },

  toFormValue(val) {
    return val ?? false;
  },

  toApiValue(val) {
    return val;
  },

  fromJsonValue(val) {
    return val ?? false;
  },
};

export const dateHandler: FieldTypeHandler = {
  defaultVariant() {
    return { type: 'date' };
  },

  emptyValue() {
    return null;
  },

  toFormValue(val) {
    if (typeof val === 'string' && val) return new Date(val);
    if (val == null) return null;
    return val;
  },

  toApiValue(val) {
    if (val instanceof Date) return val.toISOString();
    if (typeof val === 'string' && val) {
      const d = new Date(val);
      return !isNaN(d.getTime()) ? d.toISOString() : val;
    }
    return null;
  },

  fromJsonValue(val) {
    if (typeof val === 'string' && val) {
      const d = new Date(val);
      return !isNaN(d.getTime()) ? d : null;
    }
    return null;
  },

  submitValue(val) {
    if (val instanceof Date || (typeof val === 'string' && val)) {
      const d = val instanceof Date ? val : new Date(val);
      if (!isNaN(d.getTime())) return d.toISOString();
    }
    return val;
  },
};

export const objectHandler: FieldTypeHandler = {
  defaultVariant() {
    return { type: 'json' };
  },

  emptyValue() {
    return '';
  },

  toFormValue(val) {
    if (val == null) return '';
    if (typeof val === 'object') return JSON.stringify(val, null, 2);
    return val;
  },

  toApiValue(val) {
    if (typeof val === 'string' && val.trim()) {
      try {
        return JSON.parse(val);
      } catch {
        return val;
      }
    }
    return null;
  },

  fromJsonValue(val) {
    if (val != null && typeof val === 'object') return JSON.stringify(val, null, 2);
    return '';
  },

  submitValue(val) {
    if (typeof val === 'string' && val.trim()) {
      try {
        return JSON.parse(val);
      } catch {
        return val;
      }
    }
    if (typeof val === 'string' && !val.trim()) return null;
    return val;
  },

  validate(val) {
    if (typeof val === 'string' && val.trim()) {
      try {
        const parsed = JSON.parse(val);
        if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
          return 'Must be a JSON object (not array or primitive)';
        }
      } catch {
        return 'Invalid JSON format';
      }
    }
    return null;
  },
};

export const binaryHandler: FieldTypeHandler = {
  defaultVariant() {
    return { type: 'file' };
  },

  emptyValue() {
    return { _mode: 'empty' } as BinaryFormValue;
  },

  toFormValue(val) {
    if (val && typeof val === 'object' && val.file_id) {
      return {
        _mode: 'existing',
        file_id: val.file_id,
        content_type: val.content_type,
        size: val.size,
      } as BinaryFormValue;
    }
    return { _mode: 'empty' } as BinaryFormValue;
  },

  toApiValue(val) {
    const bv = val as BinaryFormValue | null;
    if (bv && bv._mode === 'existing' && bv.file_id) {
      return { file_id: bv.file_id, content_type: bv.content_type, size: bv.size };
    }
    if (bv && bv._mode === 'file' && bv.file) {
      return { _pending_file: bv.file.name, content_type: bv.file.type };
    }
    if (bv && bv._mode === 'url' && bv.url) {
      return { _pending_url: bv.url };
    }
    return null;
  },

  fromJsonValue(val) {
    if (val && typeof val === 'object' && val.file_id) {
      return {
        _mode: 'existing',
        file_id: val.file_id,
        content_type: val.content_type,
        size: val.size,
      };
    }
    return { _mode: 'empty' };
  },
};

export const unionHandler: FieldTypeHandler = {
  defaultVariant() {
    return { type: 'union' };
  },

  emptyValue() {
    return null;
  },

  toFormValue(val) {
    return val;
  },

  toApiValue(val) {
    return val;
  },

  fromJsonValue(val) {
    return val ?? null;
  },
};

export const arrayHandler: FieldTypeHandler = {
  defaultVariant() {
    return { type: 'array', itemType: 'text' };
  },

  emptyValue() {
    return [];
  },

  toFormValue(val) {
    return Array.isArray(val) ? val : [];
  },

  toApiValue(val) {
    return val;
  },

  fromJsonValue(val) {
    return Array.isArray(val) ? val : [];
  },
};

// ============================================================================
// Registry
// ============================================================================

const registry = new Map<string, FieldTypeHandler>();

// Register built-in types
registry.set('string', stringHandler);
registry.set('number', numberHandler);
registry.set('boolean', booleanHandler);
registry.set('date', dateHandler);
registry.set('object', objectHandler);
registry.set('binary', binaryHandler);
registry.set('union', unionHandler);
registry.set('array', arrayHandler);

/**
 * Get the handler for a given field type.
 * Falls back to stringHandler for unknown types (including undefined).
 */
export function getHandler(type?: string): FieldTypeHandler {
  return registry.get(type ?? 'string') ?? stringHandler;
}

/**
 * Register a new field type handler or override a built-in one.
 *
 * @example
 * registerFieldType('email', {
 *   defaultVariant: () => ({ type: 'text' }),
 *   emptyValue: () => '',
 *   toFormValue: (val) => val ?? '',
 *   toApiValue: (val, field) => (val === '' && field.isNullable ? null : val),
 *   fromJsonValue: (val) => val ?? '',
 * });
 */
export function registerFieldType(type: string, handler: FieldTypeHandler): void {
  registry.set(type, handler);
}

// ============================================================================
// Convenience Functions (with enum pre-checks)
// ============================================================================

/**
 * Get default variant for a field, with enum pre-check.
 * Fields with enumValues always get 'select' variant regardless of type.
 */
export function getDefaultVariant(field: ResourceFieldMinimal): FieldVariant {
  if (field.enumValues && field.enumValues.length > 0) {
    const options = field.enumValues.map((v) => ({ value: v, label: v }));
    return { type: 'select', options };
  }
  return getHandler(field.type).defaultVariant(field);
}

/**
 * Get empty/default value for a field, with enum pre-check.
 * Enum fields use null (nullable) or first enum value (required).
 */
export function getEmptyValue(field: ResourceFieldMinimal): any {
  if (field.enumValues && field.enumValues.length > 0) {
    return field.isNullable ? null : (field.enumValues[0] ?? '');
  }
  return getHandler(field.type).emptyValue(field);
}
