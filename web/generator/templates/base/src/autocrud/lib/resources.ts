import type {
  ResourceMeta,
  RevisionInfo,
  JobRedirectInfo,
  FullResource,
  RevisionListParams,
  RevisionListResponse,
} from '../types/api';
import type { z } from 'zod';
import type { SearchCondition } from './components/table/types';
import type { MRT_SortingState } from 'mantine-react-table';

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
  /** For structural unions: this variant is an array of items */
  isArray?: boolean;
  /** For structural union array variants: each item is a discriminated union */
  itemUnionMeta?: UnionMeta;
  /** For structural unions: this variant is a dict (key-value map) */
  isDict?: boolean;
  /** For structural union dict variants: fields describing each dict value */
  dictValueFields?: ResourceField[];
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
  type: 'string' | 'number' | 'boolean' | 'date' | 'array' | 'object' | 'binary' | 'union' | 'file';
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
  // Whether this field has a unique constraint (from Unique() annotation)
  isUnique?: boolean;
  // Const value for tagged struct discriminator fields (auto-filled, hidden in form)
  constValue?: string;
}

/**
 * Custom create action — an alternative POST endpoint for creating a resource.
 * Discovered from the backend's @crud.create_action() decorator via OpenAPI extensions.
 */
export interface CustomCreateAction {
  /** Path segment name, e.g. "import-from-url" */
  name: string;
  /** Human-readable label, e.g. "Import from URL" */
  label: string;
  /** Fields for the action's request body form */
  fields: ResourceField[];
  /** Zod schema for validation (generated from action body schema) */
  zodSchema?: z.ZodObject<any>;
  /** API method to call when submitting this action */
  apiMethod: (data: any) => Promise<{ data: RevisionInfo | JobRedirectInfo }>;
  /** When set, action runs asynchronously via a Job resource */
  asyncMode?: 'job' | 'background';
  /** Job resource name for async_mode='job' actions (e.g. "generate-article-job") */
  jobResourceName?: string;
}

// ---------------------------------------------------------------------------
// Component-level configuration interfaces
// ---------------------------------------------------------------------------

/**
 * Configuration options for ResourceTable component.
 *
 * Can be set via `ResourceCustomizationConfig.table` (config-first) or
 * passed directly as props to `<ResourceTable>` (props override config).
 */
export interface TableConfig {
  /** Whether to show the "Create" button in the table header. Defaults to `true`. */
  canCreate?: boolean;
  /** Search conditions that are always applied to every API request.
   *  Useful for creating a table that only shows a slice of data
   *  (e.g. only resources with a specific tag). */
  alwaysSearchCondition?: SearchCondition[];
  /** Override the outer Container size. Accepts Mantine Container `size` prop values
   *  (e.g. `'sm'`, `'md'`, `'lg'`, `'xl'`, or a number for max-width in px).
   *  Defaults to `'xl'`. */
  width?: string | number;
  /** Initial page size. Defaults to `20`. */
  initPageSize?: number;
  /** Available page size options for the pagination selector. */
  rowPerPageOptions?: number[];
  /** Whether to wrap the table in a Mantine `<Container>`. Defaults to `true`.
   *  Set to `false` when embedding the table inside another layout. */
  wrappedInContainer?: boolean;
  /** Custom row click handler. Set to `false` to disable row click navigation.
   *  Defaults to navigating to the resource detail page. */
  onRowClick?: false | ((resourceId: string) => void);
  /** Hide the global free-text search input. Defaults to `false`. */
  disableGlobalSearch?: boolean;
  /** Hide the advanced search panel. Defaults to `false`. */
  disableAdvancedSearch?: boolean;
  /** Override the default sort state. Defaults to `[{ id: 'updated_time', desc: true }]`. */
  defaultSort?: MRT_SortingState;
  /** Override the table title. Defaults to `config.label`. */
  title?: string;
  /** Table density. Defaults to `'xs'`. */
  density?: 'xs' | 'md' | 'xl';
}

/**
 * Configuration options for ResourceCreate component.
 *
 * Can be set via `ResourceCustomizationConfig.create` (config-first) or
 * passed directly as props to `<ResourceCreate>` (props override config).
 */
export interface CreateConfig {
  /** When `true`, only show custom create actions (hide the standard form tab).
   *  Has no effect when there are no `customCreateActions`. Defaults to `false`. */
  customFormOnly?: boolean;
  /** Override the cancel / back button behaviour.
   *  Defaults to navigating to `basePath`. */
  onCancel?: () => void;
  /** Whether to wrap the form in a Mantine `<Container>`. Defaults to `true`. */
  wrappedInContainer?: boolean;
  /** Whether to show the Back button. Defaults to `true`. */
  showBackButton?: boolean;
  /** Override the page title. Defaults to `"Create {config.label}"`. */
  title?: string;
}

/**
 * Configuration options for ResourceDetail component.
 *
 * Can be set via `ResourceCustomizationConfig.detail` (config-first) or
 * passed directly as props to `<ResourceDetail>` (props override config).
 */
export interface DetailConfig {
  /** Whether to wrap in a Mantine `<Container>`. Defaults to `true`. */
  wrappedInContainer?: boolean;
  /** Whether to show the Back button. Defaults to `true`. */
  showBackButton?: boolean;
  /** Whether to show the Edit button. Defaults to `true`. */
  showEditButton?: boolean;
  /** Whether to show the Delete / Permanently Delete buttons. Defaults to `true`. */
  showDeleteButton?: boolean;
  /** Whether to show the Revision History section. Defaults to `true`. */
  showRevisionHistory?: boolean;
  /** Override the Back button / close behaviour.
   *  Defaults to navigating to `basePath`. */
  onClose?: () => void;
  /** Override the page title. Defaults to `"{config.label} Detail"`. */
  title?: string;
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
  /** Whether this resource is a union type (e.g. Cat | Dog) */
  isUnion?: boolean;
  // Zod schema for validation (generated from OpenAPI)
  zodSchema?: z.ZodObject<any>;
  /** Fields to hide by default in create/edit forms (e.g. job management fields).
   *  Hidden fields still participate in form submission with their default/initial values.
   *  Use `showHiddenFields` in customization to selectively reveal them. */
  defaultHiddenFields?: string[];
  /** Custom create actions — alternative ways to create this resource */
  customCreateActions?: CustomCreateAction[];
  /** Component-level config for ResourceTable (populated by applyCustomizations) */
  tableConfig?: TableConfig;
  /** Component-level config for ResourceCreate (populated by applyCustomizations) */
  createConfig?: CreateConfig;
  /** Component-level config for ResourceDetail (populated by applyCustomizations) */
  detailConfig?: DetailConfig;
  apiClient: {
    create: (data: T) => Promise<{ data: RevisionInfo }>;
    list: (params?: any) => Promise<{ data: FullResource<T>[] }>;
    count: (params?: any) => Promise<{ data: number }>;
    get: (id: string, params?: any) => Promise<{ data: FullResource<T> }>;
    update: (id: string, data: T, params?: any) => Promise<{ data: RevisionInfo }>;
    delete: (id: string) => Promise<{ data: ResourceMeta }>;
    permanentlyDelete: (id: string) => Promise<void>;
    restore: (id: string) => Promise<{ data: ResourceMeta }>;
    revisionList: (
      id: string,
      params?: RevisionListParams,
    ) => Promise<{ data: RevisionListResponse }>;
    switchRevision: (id: string, revisionId: string) => Promise<{ data: ResourceMeta }>;
    /** Rerun a completed/failed job (only available on job resources) */
    rerun?: (id: string) => Promise<{ data: RevisionInfo }>;
    /** Get execution logs for a job (only available on job resources) */
    getLogs?: (id: string) => Promise<{ data: string }>;
  };
}

/**
 * Registry of all resources (generated)
 */
export const resources: Record<string, ResourceConfig> = {};

/**
 * Mapping of async-create-job resource names to their parent resource names.
 * Populated by generated code from `x-autocrud-async-create-jobs`.
 * Used by the sidebar to group job resources under their parent.
 */
export const asyncCreateJobs: Record<string, string> = {};

/**
 * Check whether a resource is an auto-generated async-create job.
 */
export function isAsyncCreateJob(resourceName: string): boolean {
  return resourceName in asyncCreateJobs;
}

/**
 * Get the child async-create job resource names for a parent resource.
 */
export function getAsyncCreateJobChildren(parentResourceName: string): string[] {
  return Object.entries(asyncCreateJobs)
    .filter(([, parent]) => parent === parentResourceName)
    .map(([jobName]) => jobName);
}

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
  /** Reveal fields that are in `defaultHiddenFields` — makes them visible in forms again */
  showHiddenFields?: F[];
  /** Component-level customization for ResourceTable */
  table?: TableConfig;
  /** Component-level customization for ResourceCreate */
  create?: CreateConfig;
  /** Component-level customization for ResourceDetail */
  detail?: DetailConfig;
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
export function applyCustomizations(customizations: ResourceCustomizations<any>): void {
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

    // showHiddenFields: remove listed fields from defaultHiddenFields
    if (config.showHiddenFields && resource.defaultHiddenFields) {
      const showSet = new Set(config.showHiddenFields);
      resource.defaultHiddenFields = resource.defaultHiddenFields.filter((f) => !showSet.has(f));
    }

    // Component-level config overrides
    if (config.table) resource.tableConfig = { ...resource.tableConfig, ...config.table };
    if (config.create) resource.createConfig = { ...resource.createConfig, ...config.create };
    if (config.detail) resource.detailConfig = { ...resource.detailConfig, ...config.detail };

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
