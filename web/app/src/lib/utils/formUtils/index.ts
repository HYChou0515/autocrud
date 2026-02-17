/**
 * Form Utilities Module
 *
 * Provides reusable utilities for form data processing, validation,
 * and transformations extracted from ResourceForm component.
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
export type { FieldTypeHandler, FieldType, ResourceFieldMinimal } from './fieldTypeRegistry';

// ============================================================================
// Path Utilities (nested object access)
// ============================================================================
export { getByPath, setByPath } from './paths';

// ============================================================================
// Data Converters (type conversion utilities)
// ============================================================================
export { toLabel, fileToBase64, binaryFormValueToApi } from './converters';

// ============================================================================
// Field Type Inference (UI variant and type detection)
// ============================================================================
export { inferDefaultVariant, inferSimpleUnionType, createEmptyItemForFields } from './fieldTypes';

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
