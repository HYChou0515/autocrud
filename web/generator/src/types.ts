/**
 * AutoCRUD Web Generator — Intermediate Representation (IR) Types
 *
 * These types represent the **semantic** information extracted from an OpenAPI
 * spec, decoupled from any code-generation concerns (no tsType / zodType).
 *
 * The pipeline is: OpenAPI JSON → OpenAPIParser → IR (these types) → CodeGen → .ts/.tsx files
 */

// ─── Field-level types ───────────────────────────────────────────────────────

/**
 * Reference metadata for fields that point to another resource.
 */
export interface FieldRef {
  resource: string;
  type: 'resource_id' | 'revision_id';
  onDelete?: string;
}

/**
 * A single variant of a discriminated, simple, or structural union field.
 */
export interface UnionVariant {
  /** Discriminator tag value */
  tag: string;
  /** Display label for this variant */
  label: string;
  /** For discriminated unions: schema name */
  schemaName?: string;
  /** For discriminated unions: sub-fields of this variant */
  fields?: Field[];
  /** For simple unions: primitive type ('string', 'number', 'boolean') */
  type?: string;
  /** For structural unions: variant is an array of items */
  isArray?: boolean;
  /** For structural union array variants: each item is a discriminated union */
  itemUnionMeta?: UnionMeta;
  /** For structural unions: variant is a dict/map */
  isDict?: boolean;
  /** For structural union dict variants: fields describing each dict value */
  dictValueFields?: Field[];
}

/**
 * Union metadata for fields that are union types.
 */
export interface UnionMeta {
  /** The tag field name (e.g. 'type', 'kind'), '__type' for simple unions, '__variant' for structural */
  discriminatorField: string;
  /** Available variant options */
  variants: UnionVariant[];
}

/**
 * Semantic field description — the core IR type.
 *
 * Contains only the information needed to **describe** a field's structure.
 * Code-generation artifacts (TypeScript type strings, Zod expressions) are
 * computed by the codegen layer from these semantic properties.
 */
export interface Field {
  name: string;
  label: string;
  /**
   * Semantic type.  Preserves 'integer' vs 'number' distinction from OpenAPI.
   * codegen maps 'integer' → TS 'number' and 'integer' → z.number().int().
   */
  type: 'string' | 'number' | 'integer' | 'boolean' | 'date' | 'object' | 'binary' | 'union' | 'file' | 'array';
  isArray: boolean;
  isRequired: boolean;
  isNullable: boolean;
  /** Enum values for select/radio inputs (from OpenAPI enum) */
  enumValues?: string[];
  /**
   * When the enum originates from a $ref schema, this stores the schema name
   * (e.g. 'ItemRarity') so that codegen can emit the proper TS type name
   * instead of a generic 'string'.
   */
  enumSchemaName?: string;
  /** For arrays of typed objects: the item's sub-fields */
  itemFields?: Field[];
  /** Reference to another resource (from Ref/RefRevision annotations) */
  ref?: FieldRef;
  /** For union fields: discriminator + variant info */
  unionMeta?: UnionMeta;
  /** Whether this field has a unique constraint (from Unique() annotation) */
  isUnique?: boolean;
  /** Const value for tagged struct discriminator fields (auto-filled, hidden in form) */
  constValue?: string;
  /**
   * For nested-array fields that should render as JSON editor,
   * stores the pre-computed inner type representation so codegen can wrap it.
   * e.g. list[list[int]] → nestedArrayInner describes the inner list[int].
   */
  nestedArrayInner?: Field;
}

// ─── Custom Create Actions ───────────────────────────────────────────────────

/**
 * Custom create action discovered from x-autocrud-custom-create-actions.
 * Each action represents an alternative POST endpoint for creating a resource.
 */
export interface CustomCreateAction {
  /** URL path segment after the resource name, e.g. "import-from-url" */
  name: string;
  /** Full API path, e.g. "/article/import-from-url" */
  path: string;
  /** Human-readable label, e.g. "Import from URL" */
  label: string;
  /** Python function name / OpenAPI operationId */
  operationId: string;
  /** Request body schema name in components (body-based actions) */
  bodySchemaName?: string;
  /** Handler parameter name for the body schema (e.g. 'f' when `f: Skill`) */
  bodySchemaParamName?: string;
  /** Property names belonging to the body schema (for API client body construction) */
  bodySchemaFieldNames?: string[];
  /** Path parameters (path-param-based actions, e.g. /{name}/new) */
  pathParams?: Array<{ name: string; required: boolean; schema: { type?: string } }>;
  /** Query parameters (query-param-based actions) */
  queryParams?: Array<{ name: string; required: boolean; schema: { type?: string } }>;
  /** Inline body params from Body(embed=True) style (flat JSON body) */
  inlineBodyParams?: Array<{ name: string; required: boolean; schema: { type?: string } }>;
  /** File upload params from UploadFile (multipart/form-data) */
  fileParams?: Array<{ name: string; required: boolean; schema: { type?: string; format?: string } }>;
  /** Extracted fields from the body schema, path/query/inline-body/file params */
  fields: Field[];
  /** Async execution mode — 'job' delegates to a Job resource */
  asyncMode?: 'job' | 'background';
  /** Job resource name for async_mode='job' actions (e.g. "generate-article-job") */
  jobResourceName?: string;
}

// ─── Resource-level types ────────────────────────────────────────────────────

/**
 * A fully parsed resource — the top-level IR unit.
 */
export interface Resource {
  name: string;
  label: string;
  pascal: string;
  camel: string;
  schemaName: string;
  displayNameField?: string;
  fields: Field[];
  isJob: boolean;
  maxFormDepth: number;
  isUnion?: boolean;
  unionVariantSchemaNames?: string[];
  customCreateActions?: CustomCreateAction[];
}

// ─── Helper functions ────────────────────────────────────────────────────────

/** Sanitize a schema name from OpenAPI $ref for use as a TypeScript identifier. */
export function sanitizeTsName(name: string): string {
  return name.replace(/\./g, '_');
}

export function toPascal(s: string): string {
  return s
    .split(/[-_\s]+/)
    .map((w) => w[0].toUpperCase() + w.slice(1))
    .join('');
}

export function toCamel(s: string): string {
  const p = toPascal(s);
  return p[0].toLowerCase() + p.slice(1);
}

export function toLabel(s: string): string {
  return s
    .split(/[-_]+/)
    .map((w) => w[0].toUpperCase() + w.slice(1))
    .join(' ');
}

/** Extract the leaf segment from a dot-notation field name for use as label source */
export function getLeafLabel(name: string): string {
  return name.includes('.') ? name.split('.').pop()! : name;
}

/** Escape special regex characters in a string */
export function escapeRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/** Check if an anyOf/oneOf array contains $ref members (i.e. union type) */
export function hasRefMembers(arr: any[] | undefined): boolean {
  return Array.isArray(arr) && arr.some((item: any) => item.$ref);
}

/** ISO 8601 datetime pattern */
const ISO_DATETIME_RE = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}/;

/**
 * Heuristic: detect if a string field is actually a datetime
 * even when OpenAPI spec doesn't have format: "date-time".
 * Only checks default/example values for ISO datetime format.
 */
export function looksLikeDatetime(_name: string, prop: any): boolean {
  if (typeof prop.default === 'string' && ISO_DATETIME_RE.test(prop.default)) return true;
  if (typeof prop.example === 'string' && ISO_DATETIME_RE.test(prop.example)) return true;
  return false;
}

/**
 * Compute max available depth from field name paths.
 * Mirrors the frontend computeMaxAvailableDepth logic.
 */
export function computeMaxFieldDepth(fields: Field[]): number {
  let max = 1;
  for (const f of fields) {
    const depth = f.name.split('.').length + (f.itemFields ? 1 : 0);
    if (depth > max) max = depth;
  }
  return max;
}

/**
 * Recursively serialize a Field into a plain object for JSON output.
 *
 * This is the SINGLE source of truth for field serialization — used for
 * top-level fields, itemFields sub-fields, and union variant sub-fields.
 * All metadata (ref, isUnique, itemFields, unionMeta, enumValues) is preserved
 * at every nesting level so the UI pipeline treats them identically.
 */
export function serializeField(f: Field): any {
  const out: any = {
    name: f.name,
    label: f.label,
    type: f.type === 'integer' ? 'number' : f.type,
    isArray: f.isArray,
    isRequired: f.isRequired,
    isNullable: f.isNullable,
  };
  if (f.enumValues && f.enumValues.length > 0) {
    out.enumValues = f.enumValues;
  }
  if (f.itemFields && f.itemFields.length > 0) {
    out.itemFields = f.itemFields.map(serializeField);
  }
  if (f.ref) {
    out.ref = f.ref;
  }
  if (f.isUnique) {
    out.isUnique = true;
  }
  if (f.constValue !== undefined) {
    out.constValue = f.constValue;
  }
  if (f.unionMeta) {
    out.unionMeta = {
      discriminatorField: f.unionMeta.discriminatorField,
      variants: f.unionMeta.variants.map((v) => {
        const variant: any = { tag: v.tag, label: v.label };
        if (v.schemaName) variant.schemaName = v.schemaName;
        if (v.type) variant.type = v.type;
        if (v.isArray) variant.isArray = true;
        if (v.fields && v.fields.length > 0) {
          variant.fields = v.fields.map(serializeField);
        }
        if (v.itemUnionMeta) {
          variant.itemUnionMeta = {
            discriminatorField: v.itemUnionMeta.discriminatorField,
            variants: v.itemUnionMeta.variants.map((iv) => {
              const innerVariant: any = { tag: iv.tag, label: iv.label };
              if (iv.schemaName) innerVariant.schemaName = iv.schemaName;
              if (iv.type) innerVariant.type = iv.type;
              if (iv.isArray) innerVariant.isArray = true;
              if (iv.fields && iv.fields.length > 0) {
                innerVariant.fields = iv.fields.map(serializeField);
              }
              return innerVariant;
            }),
          };
        }
        if (v.isDict) variant.isDict = true;
        if (v.dictValueFields && v.dictValueFields.length > 0) {
          variant.dictValueFields = v.dictValueFields.map(serializeField);
        }
        return variant;
      }),
    };
  }
  return out;
}
