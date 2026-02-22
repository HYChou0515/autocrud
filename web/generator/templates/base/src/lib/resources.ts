import type {
  ResourceMeta,
  RevisionInfo,
  FullResource,
  RevisionListParams,
  RevisionListResponse,
} from '../types/api';
import type { z } from 'zod';

/**
 * Field variant types - allows customization of input component
 * 支援不同的 UI variant
 */
export type FieldVariant =
  | { type: 'text' }
  | { type: 'textarea'; rows?: number }
  | { type: 'monaco'; language?: string; height?: number }
  | { type: 'markdown'; height?: number }
  | { type: 'number'; min?: number; max?: number; step?: number }
  | { type: 'slider'; sliderMin?: number; sliderMax?: number; step?: number }
  | { type: 'select'; options?: { value: string; label: string }[] }
  | { type: 'checkbox' }
  | { type: 'switch' }
  | { type: 'date' }
  | { type: 'file'; accept?: string; multiple?: boolean }
  | { type: 'json'; height?: number }
  | { type: 'tags'; maxTags?: number; splitChars?: string[] }
  | { type: 'array'; itemType?: 'text' | 'number'; minItems?: number; maxItems?: number }
  | { type: 'union'; variant?: 'radio.group' | 'radio.card' };

/**
 * Reference metadata for fields that point to another resource
 */
export interface FieldRef {
  resource: string;
  type: 'resource_id' | 'revision_id';
  onDelete?: 'dangling' | 'set_null' | 'cascade';
}

/**
 * Union variant definition for discriminated or simple union fields
 */
export interface UnionVariant {
  /** Discriminator tag value */
  tag: string;
  /** Display label for this variant */
  label: string;
  /** For discriminated unions: schema name */
  schemaName?: string;
  /** For discriminated unions: sub-fields of this variant */
  fields?: ResourceField[];
  /** For simple unions: primitive type ('string', 'number', 'boolean') */
  type?: string;
}

/**
 * Union metadata for fields that are union types
 */
export interface UnionMeta {
  /** The discriminator field name (e.g. 'type', 'kind') or '__type' for simple unions */
  discriminatorField: string;
  /** Available variant options */
  variants: UnionVariant[];
}

/**
 * Resource field definition for meta-programming
 */
export interface ResourceField {
  name: string;
  label: string;
  type: 'string' | 'number' | 'boolean' | 'date' | 'array' | 'object' | 'binary' | 'union';
  isArray: boolean;
  isRequired: boolean;
  isNullable: boolean;
  // Enum values for select/radio inputs (from OpenAPI enum)
  enumValues?: string[];
  // Variant system - allows post-generation customization
  variant?: FieldVariant;
  // For arrays of typed objects: the item's sub-fields
  itemFields?: ResourceField[];
  // Reference to another resource (from Ref/RefRevision annotations)
  ref?: FieldRef;
  // For union fields: discriminator + variant info
  unionMeta?: UnionMeta;
}

/**
 * Resource configuration for code generation and runtime
 */
export interface ResourceConfig<T = any> {
  name: string;
  label: string;
  pluralLabel: string;
  schema: string;
  /** Optional field name to display as a human-friendly label for this resource. */
  displayNameField?: string;
  fields: ResourceField[];
  indexedFields?: string[];
  /** Default max depth for form field expansion. Fields deeper than this render as JSON editors. */
  maxFormDepth?: number;
  // Zod schema for validation (generated from OpenAPI)
  zodSchema?: z.ZodObject<any>;
  apiClient: {
    create: (data: T) => Promise<{ data: RevisionInfo }>;
    listFull: (params?: any) => Promise<{ data: FullResource<T>[] }>;
    count: (params?: any) => Promise<{ data: number }>;
    getFull: (id: string, params?: any) => Promise<{ data: FullResource<T> }>;
    update: (id: string, data: T, params?: any) => Promise<{ data: RevisionInfo }>;
    delete: (id: string) => Promise<{ data: ResourceMeta }>;
    restore: (id: string) => Promise<{ data: ResourceMeta }>;
    revisionList: (
      id: string,
      params?: RevisionListParams,
    ) => Promise<{ data: RevisionListResponse }>;
    switchRevision: (id: string, revisionId: string) => Promise<{ data: ResourceMeta }>;
  };
}

/**
 * Registry of all resources (generated)
 */
export const resources: Record<string, ResourceConfig> = {};

/**
 * Per-field customization options
 */
export interface FieldCustomization {
  /** Override the UI variant for this field */
  variant?: FieldVariant;
  /** Override or add reference metadata */
  ref?: FieldRef;
  /** Override the field label */
  label?: string;
}

/**
 * Per-resource customization options.
 *
 * The field name type F provides IDE autocomplete for known fields.
 * Unknown field names produce a runtime warning via applyCustomizations().
 */
export interface ResourceCustomizationConfig<F extends string = string> {
  /** Field-level customizations keyed by field name */
  fields?: Partial<Record<F, FieldCustomization>>;
  /** Override the Zod schema (receives the generated schema for extension) */
  zodSchema?: (generated: z.ZodObject<any>) => z.ZodObject<any>;
  /** Override max form depth */
  maxFormDepth?: number;
  /** Override resource label */
  label?: string;
  /** Override resource plural label */
  pluralLabel?: string;
}

/**
 * Type-safe customizations map — generic over a ResourceFieldMap interface.
 *
 * Usage (generated code provides the concrete ResourceFieldMap):
 * ```ts
 * const customizations: ResourceCustomizations = {
 *   character: {
 *     fields: {
 *       special_ability: { variant: { type: 'textarea', rows: 5 } },
 *       // 'typo_field' would be a TypeScript error ✅
 *     },
 *   },
 * };
 * ```
 */
export type ResourceCustomizations<FieldMap = Record<string, string>> = {
  [K in keyof FieldMap]?: ResourceCustomizationConfig<FieldMap[K] & string>;
};

/**
 * Apply customizations to the registered resources.
 * Merges field-level and resource-level overrides into the registry.
 */
export function applyCustomizations(
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  customizations: ResourceCustomizations<any>,
): void {
  for (const [resourceName, config] of Object.entries(customizations)) {
    if (!config) continue;
    const resource = resources[resourceName];
    if (!resource) {
      console.warn(`⚠️ Customization: resource '${resourceName}' not found, skipping`);
      continue;
    }

    // Resource-level overrides
    if (config.label) resource.label = config.label;
    if (config.pluralLabel) resource.pluralLabel = config.pluralLabel;
    if (config.maxFormDepth !== undefined) resource.maxFormDepth = config.maxFormDepth;
    if (config.zodSchema && resource.zodSchema) {
      resource.zodSchema = config.zodSchema(resource.zodSchema);
    }

    // Field-level overrides
    if (config.fields) {
      for (const [fieldName, fieldConfig] of Object.entries(config.fields)) {
        if (!fieldConfig) continue;
        const field = resource.fields.find((f) => f.name === fieldName);
        if (!field) {
          console.warn(
            `⚠️ Customization: field '${fieldName}' not found in resource '${resourceName}', skipping`,
          );
          continue;
        }
        if (fieldConfig.variant) field.variant = fieldConfig.variant;
        if (fieldConfig.ref) field.ref = fieldConfig.ref;
        if (fieldConfig.label) field.label = fieldConfig.label;
      }
    }
  }
  console.log('✅ Resource customizations applied');
}

/**
 * Get resource config by name
 */
export function getResource(name: string): ResourceConfig | undefined {
  return resources[name];
}

/**
 * Get all resource names
 */
export function getResourceNames(): string[] {
  return Object.keys(resources);
}
