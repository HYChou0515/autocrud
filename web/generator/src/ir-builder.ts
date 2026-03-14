/**
 * IR Builder — builds semantic IR from a **dereferenced** OpenAPI spec.
 *
 * Replaces the old OpenAPIParser. Uses swagger-parser's dereference output
 * (no $ref resolution needed) alongside pre-computed schema metadata
 * collected before dereference.
 *
 * Pipeline:
 *   raw spec → preScanSpec() → swagger-parser.dereference() → IRBuilder.build() → Resource[]
 */

import type { Field, FieldRef, UnionVariant, Resource, CustomCreateAction } from './types.js';
import {
  sanitizeTsName,
  toPascal,
  toCamel,
  toLabel,
  getLeafLabel,
  escapeRegex,
  hasRefMembers,
  looksLikeDatetime,
  computeMaxFieldDepth,
} from './types.js';

// ─── Pre-scan types ──────────────────────────────────────────────────────────

/**
 * Pre-scan metadata collected BEFORE swagger-parser dereference.
 * Captures $ref-dependent info that would be lost after dereference.
 */
export interface PreScanResult {
  /** resource name → schema name (from POST paths with $ref body) */
  resourceSchemaMap: Map<string, string>;
  /** resource name → variant schema names (from POST paths with anyOf/oneOf $ref body) */
  unionResourceVariants: Map<string, string[]>;
  /** schema name → enum values */
  enumSchemas: Map<string, string[]>;
}

/**
 * Scan a raw (non-dereferenced) OpenAPI spec to capture $ref metadata.
 * Must be called BEFORE swagger-parser dereference().
 */
export function preScanSpec(spec: any, basePath: string): PreScanResult {
  const resourceSchemaMap = new Map<string, string>();
  const unionResourceVariants = new Map<string, string[]>();
  const enumSchemas = new Map<string, string[]>();

  const prefix = basePath;
  const pattern = prefix ? new RegExp(`^${escapeRegex(prefix)}\\/([^/]+)$`) : /^\/([^/]+)$/;

  // Scan POST paths for resource schema mappings
  for (const [pathStr, methods] of Object.entries<any>(spec.paths ?? {})) {
    if (!methods.post) continue;
    const match = pathStr.match(pattern);
    if (!match) continue;

    const resourceName = match[1];
    const bodySchema = methods.post.requestBody?.content?.['application/json']?.schema;
    if (!bodySchema) continue;

    if (bodySchema.$ref) {
      resourceSchemaMap.set(resourceName, sanitizeTsName(bodySchema.$ref.split('/').pop()!));
    } else if (hasRefMembers(bodySchema.anyOf) || hasRefMembers(bodySchema.oneOf)) {
      const members = bodySchema.anyOf || bodySchema.oneOf;
      const variantNames = members.filter((m: any) => m.$ref).map((m: any) => sanitizeTsName(m.$ref.split('/').pop()!));
      unionResourceVariants.set(resourceName, variantNames);
    }
  }

  // Collect enum schemas
  for (const [name, schema] of Object.entries<any>(spec.components?.schemas ?? {})) {
    if (schema.enum) {
      enumSchemas.set(name, schema.enum);
    }
  }

  return { resourceSchemaMap, unionResourceVariants, enumSchemas };
}

// ─── IR Builder ──────────────────────────────────────────────────────────────

/**
 * IRBuilder — builds IR Resources from a fully dereferenced OpenAPI spec.
 *
 * @example
 * ```ts
 * const preScan = preScanSpec(rawSpec, basePath);
 * const dereferencedSpec = await SwaggerParser.dereference(rawSpec);
 * const builder = new IRBuilder(dereferencedSpec, basePath, preScan);
 * const resources = builder.build();
 * ```
 */
export class IRBuilder {
  /** @internal Exposed for testing */
  resources: Resource[] = [];

  constructor(
    private spec: any,
    private basePath: string,
    private preScan: PreScanResult,
  ) {}

  /**
   * Build IR Resources from the dereferenced spec.
   */
  build(): Resource[] {
    this.resources = [];
    this.extractResources();
    this.extractCustomCreateActions();
    return this.resources;
  }

  // ── Resource Extraction ────────────────────────────────────────────────────

  private extractResources() {
    const SYSTEM_SCHEMAS = new Set(['ResourceMeta', 'RevisionInfo', 'RevisionStatus', 'RevisionListResponse']);

    // Normal resources (from pre-scan resourceSchemaMap)
    for (const [name, schemaName] of this.preScan.resourceSchemaMap) {
      if (SYSTEM_SCHEMAS.has(schemaName)) continue;

      const schema = this.getSchema(schemaName);
      if (!schema?.properties) continue;

      const displayNameField =
        typeof schema['x-display-name-field'] === 'string' ? schema['x-display-name-field'] : undefined;

      const isJob = this.detectJobSchema(schema);
      const fields = this.extractFields(schema, '', 1, 10);
      const maxFormDepth = computeMaxFieldDepth(fields);

      this.resources.push({
        name,
        label: toLabel(name),
        pascal: toPascal(name),
        camel: toCamel(name),
        schemaName,
        displayNameField,
        fields,
        isJob,
        maxFormDepth,
      });
    }

    // Union resources (from pre-scan unionResourceVariants)
    for (const [name, variantSchemaNames] of this.preScan.unionResourceVariants) {
      // Read body schema from dereferenced spec paths
      const pathKey = this.basePath ? `${this.basePath}/${name}` : `/${name}`;
      const bodySchema = this.spec.paths?.[pathKey]?.post?.requestBody?.content?.['application/json']?.schema;
      if (!bodySchema) continue;

      const unionField = this.buildUnionResourceField(name, bodySchema, variantSchemaNames);
      if (!unionField) continue;

      const schemaName = toPascal(name);
      const unionFields = [unionField];
      this.resources.push({
        name,
        label: toLabel(name),
        pascal: toPascal(name),
        camel: toCamel(name),
        schemaName,
        fields: unionFields,
        isJob: false,
        maxFormDepth: computeMaxFieldDepth(unionFields),
        isUnion: true,
        unionVariantSchemaNames: variantSchemaNames,
      });
    }
  }

  // ── Custom Create Actions ─────────────────────────────────────────────────

  private extractCustomCreateActions() {
    const actionsMap: Record<string, any[]> = this.spec['x-autocrud-custom-create-actions'] ?? {};
    if (Object.keys(actionsMap).length === 0) return;

    for (const resource of this.resources) {
      const rawActions = actionsMap[resource.name];
      if (!rawActions || rawActions.length === 0) continue;

      const actions: CustomCreateAction[] = [];
      for (const raw of rawActions) {
        const fullPath: string = raw.path;
        const pathSegment = fullPath.split('/').pop() || raw.operationId;

        const actionMeta: any = {
          name: pathSegment,
          path: fullPath,
          label: raw.label,
          operationId: raw.operationId,
        };

        if (raw.asyncMode) {
          actionMeta.asyncMode = raw.asyncMode;
        }
        if (raw.jobResourceName) {
          actionMeta.jobResourceName = raw.jobResourceName;
        }

        const fields: Field[] = [];

        let bodySchemaName: string | undefined;
        if (raw.bodySchema) {
          bodySchemaName = raw.bodySchema as string;
          const schema = this.getSchema(bodySchemaName!);
          if (!schema?.properties) {
            console.warn(`⚠️  Custom action '${raw.label}': schema '${bodySchemaName}' not found, skipping`);
            continue;
          }
          actionMeta.bodySchemaName = bodySchemaName;
          actionMeta.bodySchemaFieldNames = Object.keys(schema.properties);
          if (raw.bodySchemaParamName) {
            actionMeta.bodySchemaParamName = raw.bodySchemaParamName;
          }
        }

        if (raw.pathParams?.length > 0) {
          const ppFields = (raw.pathParams as any[]).map((p: any) => this.queryParamToField(p));
          fields.push(...ppFields);
          actionMeta.pathParams = raw.pathParams;
        }
        if (raw.queryParams?.length > 0) {
          const qpFields = (raw.queryParams as any[]).map((p: any) => this.queryParamToField(p));
          fields.push(...qpFields);
          actionMeta.queryParams = raw.queryParams;
        }

        if (bodySchemaName) {
          const schema = this.getSchema(bodySchemaName);
          const hasOtherParams =
            !!raw.pathParams?.length ||
            !!raw.queryParams?.length ||
            !!raw.inlineBodyParams?.length ||
            !!raw.fileParams?.length;
          const prefix = hasOtherParams && raw.bodySchemaParamName ? raw.bodySchemaParamName : '';
          const bodyFields = this.extractFields(schema!, prefix, 1, 10);
          fields.push(...bodyFields);
        }

        if (raw.inlineBodyParams?.length > 0) {
          const virtualSchema = {
            type: 'object' as const,
            properties: Object.fromEntries((raw.inlineBodyParams as any[]).map((p: any) => [p.name, p.schema])),
            required: (raw.inlineBodyParams as any[]).filter((p: any) => p.required).map((p: any) => p.name),
          };
          const ibpFields = this.extractFields(virtualSchema, '', 1, 10);
          fields.push(...ibpFields);
          actionMeta.inlineBodyParams = raw.inlineBodyParams;
        }
        if (raw.fileParams?.length > 0) {
          const fpFields = (raw.fileParams as any[]).map((p: any) => this.fileParamToField(p));
          fields.push(...fpFields);
          actionMeta.fileParams = raw.fileParams;
        }

        if (fields.length === 0) {
          console.warn(
            `⚠️  Custom action '${raw.label}' for ${resource.name}: no bodySchema, pathParams, queryParams, inlineBodyParams, or fileParams, skipping`,
          );
          continue;
        }

        actionMeta.fields = fields;
        actions.push(actionMeta);
      }

      // Deduplicate labels
      const seenOriginalLabels = new Map<string, number>();
      for (const action of actions) {
        const originalLabel = action.label;
        const count = seenOriginalLabels.get(originalLabel) ?? 0;
        seenOriginalLabels.set(originalLabel, count + 1);
        if (count > 0) {
          const newLabel = `${originalLabel} (${count + 1})`;
          console.warn(
            `⚠️  Duplicate action label '${originalLabel}' for resource '${resource.name}' ` +
              `(operationId: '${action.operationId}'). Renaming to '${newLabel}' to prevent frontend crash.`,
          );
          action.label = newLabel;
        }
      }

      if (actions.length > 0) {
        resource.customCreateActions = actions;
      }
    }
  }

  // ── Field Extraction ──────────────────────────────────────────────────────

  extractFields(schema: any, parentPath: string = '', currentDepth: number = 1, maxDepth: number = 2): Field[] {
    const fields: Field[] = [];
    const required = new Set(schema.required ?? []);

    for (const [name, rawProp] of Object.entries<any>(schema.properties ?? {})) {
      const fullName = parentPath ? `${parentPath}.${name}` : name;

      // After dereference, $ref is already resolved inline — no resolveRef needed
      // (resolveIfRef is a lightweight fallback for robustness)
      const prop = this.resolveIfRef(rawProp);

      // Handle nullable struct: anyOf: [{type:'object', properties:...}, {type:'null'}]
      if (prop.anyOf && !prop.discriminator && currentDepth < maxDepth) {
        const nonNullTypes = (prop.anyOf as any[])
          .map((t: any) => this.resolveIfRef(t))
          .filter((t: any) => t.type !== 'null');
        if (
          nonNullTypes.length === 1 &&
          nonNullTypes[0].type === 'object' &&
          nonNullTypes[0].properties &&
          !this.isBinarySchema(nonNullTypes[0])
        ) {
          const isParentRequired = required.has(name);
          const subFields = this.extractFields(nonNullTypes[0], fullName, currentDepth + 1, maxDepth);
          // If the parent field is not required or is nullable,
          // propagate that to all expanded sub-fields so the form
          // doesn't mark them as required.
          for (const sf of subFields) {
            if (!isParentRequired) {
              sf.isRequired = false;
              sf.parentOptional = true;
            }
            sf.parentNullable = true; // anyOf with null → always nullable
          }
          fields.push(...subFields);
          continue;
        }
      }

      if (prop.type === 'object' && prop.properties && currentDepth < maxDepth && !this.isBinarySchema(prop)) {
        const isParentRequired = required.has(name);
        const subFields = this.extractFields(prop, fullName, currentDepth + 1, maxDepth);
        // If the parent object field is not required, propagate to sub-fields
        if (!isParentRequired) {
          for (const sf of subFields) {
            sf.isRequired = false;
            sf.parentOptional = true;
          }
        }
        fields.push(...subFields);
      } else {
        const field = this.parseField(fullName, rawProp, required.has(name));
        if (field) fields.push(field);
      }
    }

    return fields;
  }

  // ── Core Field Parser ─────────────────────────────────────────────────────

  parseField(name: string, rawPropInput: any, isRequired: boolean): Field | null {
    // Resolve $ref fallback for robustness
    let prop = this.resolveIfRef(rawPropInput);
    let type: string = prop.type;
    let isArray = false;
    let isNullable = false;
    let enumValues: string[] | undefined;
    let enumSchemaName: string | undefined;

    // After dereference, $ref is already resolved inline.
    // Detect enum schema name by matching enum values against pre-scan data.
    if (prop.enum) {
      enumSchemaName = this.findEnumSchemaName(prop.enum);
    }

    // Detect const value (from tagged struct discriminator field)
    if (prop.const !== undefined) {
      const constVal = String(prop.const);
      return {
        name,
        label: toLabel(getLeafLabel(name)),
        type: 'string',
        isArray: false,
        isRequired,
        isNullable: false,
        constValue: constVal,
      };
    }

    // Extract x-unique metadata
    const isUnique = !!prop['x-unique'];

    // Extract x-ref-* metadata
    let ref: FieldRef | undefined;
    if (prop['x-ref-resource']) {
      ref = {
        resource: prop['x-ref-resource'],
        type: prop['x-ref-type'] ?? 'resource_id',
        ...(prop['x-ref-on-delete'] ? { onDelete: prop['x-ref-on-delete'] } : {}),
      };
    }

    if (prop.anyOf) {
      const resolvedAnyOf = (prop.anyOf as any[]).map((t: any) => this.resolveIfRef(t));
      const types = resolvedAnyOf.filter((t: any) => t.type !== 'null');
      isNullable = resolvedAnyOf.some((t: any) => t.type === 'null');

      const discResult = this.tryParseDiscriminatedUnion(name, prop, types, isNullable, isRequired);
      if (discResult) return discResult;

      const simpleResult = this.tryParseSimpleUnion(name, types, isNullable, isRequired);
      if (simpleResult) return simpleResult;

      const structResult = this.tryParseStructuralUnion(name, types, isNullable, isRequired, isNullable);
      if (structResult) return structResult;

      // Simple nullable (single non-null type)
      if (types.length > 0) {
        if (!ref && types[0]['x-ref-resource']) {
          ref = {
            resource: types[0]['x-ref-resource'],
            type: types[0]['x-ref-type'] ?? 'resource_id',
            ...(types[0]['x-ref-on-delete'] ? { onDelete: types[0]['x-ref-on-delete'] } : {}),
          };
        }
        prop = types[0];
        // After dereference, no $ref to resolve — schema is inline
        if (prop.enum) {
          enumSchemaName = this.findEnumSchemaName(prop.enum);
        }
        type = prop.type;
      }
    }

    if (type === 'array') {
      isArray = true;
      prop = this.resolveIfRef(prop.items ?? {});
      // After dereference, items is already resolved inline (resolveIfRef is fallback)

      // Handle nested arrays: list[list[...]]
      if (prop.type === 'array') {
        const innerField = this.parseField(name, prop, isRequired);
        if (innerField) {
          return {
            name,
            label: toLabel(getLeafLabel(name)),
            type: 'object', // JSON editor fallback
            isArray: false,
            isRequired,
            isNullable,
            nestedArrayInner: innerField,
          };
        }
      }

      // Handle array items that are a non-discriminated union
      if ((prop.anyOf || prop.oneOf) && !prop.discriminator) {
        const innerField = this.parseField(name, prop, isRequired);
        if (innerField) {
          return {
            ...innerField,
            isArray: true,
          };
        }
      }

      // Detect array of discriminated union
      const unionItems = (prop.anyOf || prop.oneOf) && prop.discriminator ? prop : null;
      if (unionItems) {
        const disc = unionItems.discriminator;
        const discriminatorField = disc.propertyName || 'type';
        const variants: UnionVariant[] = [];

        for (const [tag, refPath] of Object.entries<string>(disc.mapping || {})) {
          const schemaName = sanitizeTsName(refPath.split('/').pop()!);
          // After dereference, look up schema by name from components.schemas
          const itemSchema = this.getSchema(schemaName);
          if (!itemSchema) continue;
          const variantFields = this.parseSchemaFields(itemSchema, discriminatorField);
          variants.push({ tag, label: toLabel(tag), schemaName, fields: variantFields });
        }

        return {
          name,
          label: toLabel(getLeafLabel(name)),
          type: 'union',
          isArray: true,
          isRequired,
          isNullable,
          unionMeta: { discriminatorField, variants },
        };
      }

      type = prop.type;
    }

    // Detect Binary schema
    if (this.isBinarySchema(prop)) {
      return {
        name,
        label: toLabel(getLeafLabel(name)),
        type: 'binary',
        isArray,
        isRequired,
        isNullable,
      };
    }

    // Array of typed objects
    let itemFields: Field[] | undefined;
    if (isArray && type === 'object' && prop.properties) {
      itemFields = this.parseSchemaFields(prop);
    } else if (prop.enum) {
      enumValues = prop.enum;
      // Single-element enum → const
      if (enumValues!.length === 1) {
        const constVal = enumValues![0];
        return {
          name,
          label: toLabel(getLeafLabel(name)),
          type: 'string',
          isArray: false,
          isRequired,
          isNullable,
          enumValues,
          constValue: constVal,
        };
      }
    } else if (type === 'string') {
      if (prop.format === 'date-time' || prop.format === 'date') {
        type = 'date';
      } else if (looksLikeDatetime(name, prop)) {
        type = 'date';
      } else if (prop.contentEncoding === 'base64') {
        type = 'binary';
      }
    } else if (type === 'integer') {
      // Keep 'integer' — codegen distinguishes z.number().int() vs z.number()
    } else if (type === 'number') {
      // stays 'number'
    } else if (type === 'boolean') {
      // stays 'boolean'
    } else if (type === 'object') {
      // stays 'object'
    } else if (type === 'null') {
      // Pure null type (e.g. Job artifact with D=NoneType) — the only valid
      // value is null.  Fall back to 'object' so the form/display layer has
      // a sensible type, and mark nullable so the Zod schema includes .nullable().
      isNullable = true;
      type = 'object';
    } else if (
      type &&
      type !== 'string' &&
      type !== 'integer' &&
      type !== 'number' &&
      type !== 'boolean' &&
      type !== 'object' &&
      type !== 'array' &&
      !prop.enum
    ) {
      console.warn(
        `[autocrud-web-generator] Unrecognized schema type "${type}" for field "${name}", falling back to 'object'.`,
      );
      type = 'object';
    }

    return {
      name,
      label: toLabel(getLeafLabel(name)),
      type: type as Field['type'],
      isArray,
      isRequired,
      isNullable,
      ...(enumValues ? { enumValues } : {}),
      ...(enumSchemaName ? { enumSchemaName } : {}),
      ...(itemFields ? { itemFields } : {}),
      ...(ref ? { ref } : {}),
      ...(isUnique ? { isUnique: true } : {}),
    };
  }

  // ── Union Parsers ─────────────────────────────────────────────────────────

  private tryParseDiscriminatedUnion(
    name: string,
    prop: any,
    types: any[],
    isNullable: boolean,
    isRequired: boolean,
  ): Field | null {
    let unionSource = prop;
    if (prop.discriminator) {
      unionSource = prop;
    } else if (types.length === 1 && types[0].anyOf && types[0].discriminator) {
      unionSource = types[0];
    }
    if (!unionSource.discriminator) return null;

    const disc = unionSource.discriminator;
    const discriminatorField = disc.propertyName || 'type';
    const variants: UnionVariant[] = [];

    for (const [tag, refPath] of Object.entries<string>(disc.mapping || {})) {
      // discriminator.mapping values survive dereference (they're regular strings)
      const schemaName = sanitizeTsName(refPath.split('/').pop()!);
      const schema = this.getSchema(schemaName);
      if (!schema) continue;
      const variantFields = this.parseSchemaFields(schema, discriminatorField);
      variants.push({ tag, label: toLabel(tag), schemaName, fields: variantFields });
    }

    return {
      name,
      label: toLabel(getLeafLabel(name)),
      type: 'union',
      isArray: false,
      isRequired,
      isNullable,
      unionMeta: { discriminatorField, variants },
    };
  }

  private tryParseSimpleUnion(name: string, types: any[], isNullable: boolean, isRequired: boolean): Field | null {
    // After dereference, check if types contain $ref-resolved objects or arrays
    if (types.length <= 1 || types.some((t: any) => t.type === 'array')) {
      return null;
    }
    // Check if any type is an object with properties (was originally a $ref to a schema)
    if (types.some((t: any) => t.type === 'object' && t.properties)) {
      return null;
    }

    const variants: UnionVariant[] = [];
    const seenTags = new Set<string>();

    for (const t of types) {
      const primitiveType = t.type === 'integer' ? 'number' : t.type;
      if (seenTags.has(primitiveType)) continue;
      seenTags.add(primitiveType);
      variants.push({ tag: primitiveType, label: toLabel(primitiveType), type: primitiveType });
    }

    // After dedup, if only one variant remains, it's not really a union
    if (variants.length <= 1) {
      const singleType = variants[0]?.type ?? 'string';
      return {
        name,
        label: toLabel(getLeafLabel(name)),
        type: singleType as Field['type'],
        isArray: false,
        isRequired,
        isNullable,
      };
    }

    return {
      name,
      label: toLabel(getLeafLabel(name)),
      type: 'union',
      isArray: false,
      isRequired,
      isNullable,
      unionMeta: { discriminatorField: '__type', variants },
    };
  }

  private buildDiscriminatedUnionMeta(
    itemsSchema: any,
  ): { discriminatorField: string; variants: UnionVariant[] } | null {
    const disc = itemsSchema?.discriminator;
    if (!disc) return null;
    const anyOfItems = itemsSchema.anyOf || itemsSchema.oneOf;
    if (!anyOfItems) return null;

    const discriminatorField = disc.propertyName || 'type';
    const variants: UnionVariant[] = [];

    for (const [tag, refPath] of Object.entries<string>(disc.mapping || {})) {
      const schemaName = sanitizeTsName(refPath.split('/').pop()!);
      const schema = this.getSchema(schemaName);
      if (!schema) continue;
      const variantFields = this.parseSchemaFields(schema, discriminatorField);
      variants.push({ tag, label: toLabel(tag), schemaName, fields: variantFields });
    }

    return { discriminatorField, variants };
  }

  private tryParseStructuralUnion(
    name: string,
    types: any[],
    isNullable: boolean,
    isRequired: boolean,
    hasNullVariant: boolean = false,
  ): Field | null {
    if (types.length <= 1) return null;

    const variants: UnionVariant[] = [];
    const usedTags = new Set<string>();

    const makeUniqueTag = (base: string): string => {
      let tag = base;
      let counter = 2;
      while (usedTags.has(tag)) {
        tag = `${base}_${counter++}`;
      }
      usedTags.add(tag);
      return tag;
    };

    for (const rawT of types) {
      const t = this.resolveIfRef(rawT);
      if (t.type === 'array') {
        const itemSchema = this.resolveIfRef(t.items ?? {});
        const innerUnionMeta = this.buildDiscriminatedUnionMeta(itemSchema);
        if (innerUnionMeta) {
          const innerNames = innerUnionMeta.variants.map((v) => v.schemaName).filter(Boolean);
          const unionLabel = `(${innerNames.join(' | ')})[]`;
          const tag = makeUniqueTag(`list_union`);
          variants.push({
            tag,
            label: unionLabel,
            fields: [],
            isArray: true,
            itemUnionMeta: {
              discriminatorField: innerUnionMeta.discriminatorField,
              variants: innerUnionMeta.variants,
            },
          });
        } else {
          let resolvedItems = itemSchema;
          const schemaName = this.findSchemaName(itemSchema) ?? 'Array';
          if (schemaName !== 'Array') {
            resolvedItems = this.getSchema(schemaName) ?? resolvedItems;
          }
          const variantFields = this.parseSchemaFields(resolvedItems);
          const tag = makeUniqueTag(`list_${schemaName}`);
          variants.push({
            tag,
            label: `${schemaName}[]`,
            schemaName,
            fields: variantFields,
            isArray: true,
          });
        }
      } else if (t.type === 'object' && t.properties) {
        // After dereference, $ref objects are inline. Try to find schema name by reference equality.
        const schemaName = this.findSchemaName(t) ?? toPascal(name);
        const variantFields = this.parseSchemaFields(t);
        const tag = makeUniqueTag(schemaName);
        variants.push({
          tag,
          label: toLabel(schemaName),
          schemaName,
          fields: variantFields,
        });
      } else if ((t.anyOf || t.oneOf) && t.discriminator) {
        const innerMeta = this.buildDiscriminatedUnionMeta(t);
        if (innerMeta) {
          for (const iv of innerMeta.variants) {
            const tag = makeUniqueTag(iv.schemaName || iv.tag);
            const discField: Field = {
              name: innerMeta.discriminatorField,
              label: toLabel(innerMeta.discriminatorField),
              type: 'string',
              isRequired: true,
              isNullable: false,
              isArray: false,
              constValue: iv.tag,
            };
            variants.push({
              tag,
              label: iv.label,
              schemaName: iv.schemaName,
              fields: [discField, ...(iv.fields || [])],
            });
          }
        }
      } else if (t.type === 'object' && t.additionalProperties) {
        let valueSchema = this.resolveIfRef(t.additionalProperties);
        let valueName = 'Any';
        const vsName = this.findSchemaName(valueSchema);
        if (vsName) {
          valueName = vsName;
          valueSchema = this.getSchema(vsName) ?? valueSchema;
        } else if (valueSchema.type) {
          valueName = valueSchema.type === 'integer' ? 'number' : valueSchema.type;
        }
        const dictValueFields = this.parseSchemaFields(valueSchema);
        const tag = makeUniqueTag(`dict_${valueName}`);
        variants.push({
          tag,
          label: `Dict[str, ${valueName}]`,
          isDict: true,
          dictValueFields,
        });
      } else {
        const primitiveType = t.type === 'integer' ? 'number' : t.type || 'json';
        const tag = makeUniqueTag(primitiveType);
        variants.push({ tag, label: toLabel(primitiveType), type: primitiveType });
      }
    }

    if (hasNullVariant) {
      const tag = makeUniqueTag('null');
      variants.push({ tag, label: 'None', type: 'null' });
    }

    return {
      name,
      label: toLabel(getLeafLabel(name)),
      type: 'union',
      isArray: false,
      isRequired,
      isNullable,
      unionMeta: { discriminatorField: '__variant', variants },
    };
  }

  // ── Union Resource Field Builder ──────────────────────────────────────────

  private buildUnionResourceField(resourceName: string, bodySchema: any, variantSchemaNames: string[]): Field | null {
    const members = bodySchema.anyOf || bodySchema.oneOf;
    if (!members) return null;
    if (members.length === 0) return null;

    const disc = bodySchema.discriminator;
    const discriminatorField = disc?.propertyName || this.detectDiscriminatorField(members);
    if (!discriminatorField) return null;

    const variants: UnionVariant[] = [];

    if (disc?.mapping) {
      // Mapping values are $ref-style strings that survive dereference
      for (const [tag, refPath] of Object.entries<string>(disc.mapping)) {
        const schemaName = sanitizeTsName(refPath.split('/').pop()!);
        const schema = this.getSchema(schemaName);
        if (!schema) continue;
        const variantFields = this.parseSchemaFields(schema, discriminatorField);
        variants.push({ tag, label: toLabel(tag), schemaName, fields: variantFields });
      }
    } else {
      // No mapping — pair inline members with pre-scan variant schema names
      for (let i = 0; i < members.length && i < variantSchemaNames.length; i++) {
        const member = members[i];
        const schemaName = variantSchemaNames[i];
        const variantFields: Field[] = [];
        let tag = schemaName;

        if (member.properties) {
          const variantRequired = new Set(member.required ?? []);
          const discProp = member.properties[discriminatorField];
          if (discProp?.const) tag = discProp.const;
          else if (discProp?.enum?.length === 1) tag = discProp.enum[0];

          for (const [subName, subProp] of Object.entries<any>(member.properties)) {
            if (subName === discriminatorField) continue;
            const subField = this.parseField(subName, subProp, variantRequired.has(subName));
            if (subField) variantFields.push(subField);
          }
        }

        variants.push({ tag, label: toLabel(tag), schemaName, fields: variantFields });
      }
    }

    if (variants.length === 0) return null;

    return {
      name: 'data',
      label: toLabel(resourceName),
      type: 'union',
      isArray: false,
      isRequired: true,
      isNullable: false,
      unionMeta: { discriminatorField, variants },
    };
  }

  // ── Helpers ───────────────────────────────────────────────────────────────

  /**
   * Look up a schema by name from components.schemas (post-dereference).
   * Replaces the old resolveRef() — direct name lookup instead of $ref parsing.
   */
  getSchema(name: string): any | null {
    return this.spec.components?.schemas?.[name] ?? this.spec.components?.schemas?.[sanitizeTsName(name)] ?? null;
  }

  /**
   * Resolve $ref if present, returning the schema from components.schemas.
   * This is a lightweight fallback for robustness — the spec should already be
   * dereferenced, but if a prop still has $ref (e.g., in test fixtures or
   * edge cases), resolve it gracefully.
   */
  resolveIfRef(prop: any): any {
    if (prop?.$ref && typeof prop.$ref === 'string') {
      const name = prop.$ref.split('/').pop()!;
      return this.getSchema(name) ?? prop;
    }
    return prop;
  }

  /**
   * Find a schema name by reference equality against components.schemas.
   * After dereference, swagger-parser uses the same object references.
   */
  findSchemaName(obj: any): string | undefined {
    for (const [name, schema] of Object.entries<any>(this.spec.components?.schemas ?? {})) {
      if (schema === obj) return name;
    }
    return undefined;
  }

  /**
   * Find an enum schema name by matching enum values against pre-scan data.
   */
  findEnumSchemaName(values: string[]): string | undefined {
    const sorted = JSON.stringify([...values].sort());
    for (const [name, enumValues] of this.preScan.enumSchemas) {
      if (JSON.stringify([...enumValues].sort()) === sorted) return name;
    }
    return undefined;
  }

  private detectDiscriminatorField(members: any[]): string | null {
    // After dereference, members are inline objects (no $ref)
    if (members.length === 0) return null;

    const firstProps = Object.keys(members[0].properties ?? {});
    for (const propName of firstProps) {
      const isDiscriminator = members.every((s: any) => {
        const p = s.properties?.[propName];
        if (!p) return false;
        return p.const !== undefined || (p.enum && p.enum.length === 1);
      });
      if (isDiscriminator) return propName;
    }
    return null;
  }

  private readonly jobFields = [
    'status',
    'errmsg',
    'retries',
    'artifact',
    'max_retries',
    'periodic_interval_seconds',
    'periodic_max_runs',
    'periodic_runs',
    'periodic_initial_delay_seconds',
    'last_heartbeat_at',
  ];

  detectJobSchema(schema: any): boolean {
    const props = schema.properties ?? {};
    const matchedFields = this.jobFields.filter((field) => field in props);
    return matchedFields.length >= 3;
  }

  /** Get the list of job management field names that actually exist in this resource's fields.
   *  Also matches dot-notation expanded sub-fields (e.g. artifact.process_times). */
  getJobHiddenFields(r: Resource): string[] {
    const jobMgmtFields = new Set(this.jobFields);
    return r.fields
      .filter((f) => {
        // Exact match (e.g. "status", "retries")
        if (jobMgmtFields.has(f.name)) return true;
        // Prefix match for expanded sub-fields (e.g. "artifact.process_times")
        const topLevel = f.name.split('.')[0];
        return jobMgmtFields.has(topLevel);
      })
      .map((f) => f.name);
  }

  isBinarySchema(schema: any): boolean {
    if (schema?.type !== 'object' || !schema?.properties) return false;
    const dataProp = schema.properties.data;
    return dataProp?.contentEncoding === 'base64';
  }

  parseSchemaFields(schema: any, exclude?: string): Field[] {
    const fields: Field[] = [];
    if (!schema?.properties) return fields;
    const required = new Set(schema.required ?? []);
    for (const [name, prop] of Object.entries<any>(schema.properties)) {
      if (exclude && name === exclude) continue;
      const field = this.parseField(name, prop, required.has(name));
      if (field) fields.push(field);
    }
    return fields;
  }

  queryParamToField(param: { name: string; required: boolean; schema?: Record<string, any> }): Field {
    const field = this.parseField(param.name, param.schema ?? { type: 'string' }, param.required);
    if (field) return field;
    return {
      name: param.name,
      label: toLabel(param.name),
      type: 'string',
      isArray: false,
      isRequired: param.required,
      isNullable: false,
    };
  }

  fileParamToField(param: { name: string; required: boolean; schema?: { type?: string; format?: string } }): Field {
    return {
      name: param.name,
      label: toLabel(param.name),
      type: 'file',
      isArray: false,
      isRequired: param.required,
      isNullable: false,
    };
  }
}
