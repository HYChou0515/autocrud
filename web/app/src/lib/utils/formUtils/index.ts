/**
 * Form Utilities Module
 *
 * All field-type-specific logic is centralized in the Field Type Registry.
 * To add a new field type, use registerFieldType().
 */

// ============================================================================
// Types
// ============================================================================
export type { BinaryFormValue } from './types';

// ============================================================================
// Field Type Registry (centralized type dispatch)
// ============================================================================
export {
  getHandler,
  getDefaultVariant,
  getEmptyValue,
  registerFieldType,
  inferSimpleUnionType,
  // Built-in handlers (for testing, extension, or override)
  stringHandler,
  numberHandler,
  booleanHandler,
  dateHandler,
  objectHandler,
  binaryHandler,
  unionHandler,
  arrayHandler,
} from './fieldTypeRegistry';
export type {
  FieldTypeHandler,
  FieldType,
  FieldVariant,
  ResourceFieldMinimal,
} from './fieldTypeRegistry';

// ============================================================================
// Path Utilities (nested object access)
// ============================================================================
export { getByPath, setByPath } from './paths';

// ============================================================================
// Data Converters (type conversion utilities)
// ============================================================================
export { toLabel, fileToBase64, binaryFormValueToApi } from './converters';

// ============================================================================
// Field Grouping (depth-based visibility computation)
// ============================================================================
export { computeVisibleFieldsAndGroups, computeMaxAvailableDepth } from './fieldGrouping';

// ============================================================================
// Data Transformers (bidirectional API ↔ Form conversions)
// ============================================================================
export {
  isCollapsedChild,
  processInitialValues,
  formValuesToApiObject,
  applyJsonToForm,
} from './transformers';

// ============================================================================
// Validators (JSON validation and preprocessing)
// ============================================================================
export { validateJsonFields, parseAndValidateJson, preprocessArrayFields } from './validators';
