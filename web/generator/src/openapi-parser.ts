/**
 * OpenAPI Parser — extracts semantic IR from an OpenAPI spec.
 *
 * Converts OpenAPI schemas into the IR types defined in types.ts.
 * No code-generation logic lives here — only semantic parsing.
 */

import type {
  Field,
  FieldRef,
  UnionVariant,
  UnionMeta,
  Resource,
  CustomCreateAction,
} from './types.js';
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

/**
 * OpenAPIParser — stateless parser that converts an OpenAPI spec into IR Resources.
 *
 * @example
 * ```ts
 * const parser = new OpenAPIParser(spec, '/api/v1');
 * const resources = parser.parse();
 * ```
 */
export class OpenAPIParser {
  /** @internal Exposed for testing */
  resources: Resource[] = [];

  constructor(
    private spec: any,
    private basePath: string,
  ) {}

  /**
   * Parse the OpenAPI spec and return the list of resources.
   */
  parse(): Resource[] {
    this.resources = [];
    this.extractResources();
    this.extractCustomCreateActions();
    return this.resources;
  }

  // ── Resource Extraction ────────────────────────────────────────────────────

  private extractResources() {
    const resourcePaths = new Map<string, string>();
    const prefix = this.basePath;

    const pattern = prefix ? new RegExp(`^${escapeRegex(prefix)}\\/([^/]+)$`) : /^\/([^/]+)$/;
    const unionResourceSchemas = new Map<string, any>();

    for (const [path, methods] of Object.entries<any>(this.spec.paths)) {
      if (!methods.post) continue;
      const match = path.match(pattern);
      if (!match) continue;

      const resourceName = match[1];
      const bodySchema = methods.post.requestBody?.content?.['application/json']?.schema;
      if (!bodySchema) continue;

      if (bodySchema.$ref) {
        resourcePaths.set(resourceName, sanitizeTsName(bodySchema.$ref.split('/').pop()!));
      } else if (hasRefMembers(bodySchema.anyOf) || hasRefMembers(bodySchema.oneOf)) {
        unionResourceSchemas.set(resourceName, bodySchema);
      }
    }

    const SYSTEM_SCHEMAS = new Set(['ResourceMeta', 'RevisionInfo', 'RevisionStatus', 'RevisionListResponse']);

    for (const [name, schemaName] of resourcePaths) {
      if (SYSTEM_SCHEMAS.has(schemaName)) continue;

      const schema = this.spec.components.schemas[schemaName];
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

    for (const [name, bodySchema] of unionResourceSchemas) {
      const unionField = this.buildUnionResourceField(name, bodySchema);
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
        unionVariantSchemaNames: unionField.unionMeta!.variants.map((v) => v.schemaName).filter(Boolean) as string[],
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
          const schema = this.spec.components?.schemas?.[bodySchemaName!];
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
          const schema = this.spec.components?.schemas?.[bodySchemaName];
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

      let prop = rawProp;
      if (prop.$ref) {
        const resolved = this.resolveRef(prop.$ref);
        if (resolved) prop = resolved;
      }

      // Handle nullable $ref struct: anyOf: [$ref, {type:'null'}]
      if (rawProp.anyOf && !rawProp.discriminator && currentDepth < maxDepth) {
        const nonNullTypes = (rawProp.anyOf as any[]).filter((t: any) => t.type !== 'null');
        if (nonNullTypes.length === 1 && nonNullTypes[0].$ref) {
          const resolved = this.resolveRef(nonNullTypes[0].$ref);
          if (resolved && resolved.type === 'object' && resolved.properties && !this.isBinarySchema(resolved)) {
            const subFields = this.extractFields(resolved, fullName, currentDepth + 1, maxDepth);
            fields.push(...subFields);
            continue;
          }
        }
      }

      if (prop.type === 'object' && prop.properties && currentDepth < maxDepth && !this.isBinarySchema(prop)) {
        const subFields = this.extractFields(prop, fullName, currentDepth + 1, maxDepth);
        fields.push(...subFields);
      } else {
        const field = this.parseField(fullName, rawProp, required.has(name));
        if (field) fields.push(field);
      }
    }

    return fields;
  }

  // ── Core Field Parser ─────────────────────────────────────────────────────

  parseField(name: string, prop: any, isRequired: boolean): Field | null {
    let type: string = prop.type;
    let isArray = false;
    let isNullable = false;
    let enumValues: string[] | undefined;
    let enumSchemaName: string | undefined;

    // Handle $ref references
    if (prop.$ref) {
      const refName = sanitizeTsName(prop.$ref.split('/').pop()!);
      const refSchema = this.resolveRef(prop.$ref);
      if (refSchema) {
        if (refSchema.enum) {
          enumSchemaName = refName;
        }
        prop = refSchema;
        type = prop.type;
      }
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
      const types = prop.anyOf.filter((t: any) => t.type !== 'null');
      isNullable = prop.anyOf.some((t: any) => t.type === 'null');

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
        if (prop.$ref) {
          const refName = sanitizeTsName(prop.$ref.split('/').pop()!);
          const refSchema = this.resolveRef(prop.$ref);
          if (refSchema) {
            if (refSchema.enum) {
              enumSchemaName = refName;
            }
            prop = refSchema;
          }
        }
        type = prop.type;
      }
    }

    if (type === 'array') {
      isArray = true;
      prop = prop.items ?? {};
      if (prop.$ref) {
        const refSchema = this.resolveRef(prop.$ref);
        if (refSchema) {
          prop = refSchema;
        }
      }

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
          const itemSchema = this.resolveRef(refPath);
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
      const schemaName = sanitizeTsName(refPath.split('/').pop()!);
      const schema = this.resolveRef(refPath);
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
    if (types.length <= 1 || types.some((t: any) => t.$ref) || types.some((t: any) => t.type === 'array')) {
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
      // Map back to the original OpenAPI types for codegen to compute zod properly
      return {
        name,
        label: toLabel(getLeafLabel(name)),
        type: singleType as Field['type'],
        isArray: false,
        isRequired,
        isNullable,
        // Store the original OpenAPI types so codegen can generate z.union([z.number().int(), z.number()])
        // when needed (e.g. int|float → number with union zod)
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
      const schema = this.resolveRef(refPath);
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

    for (const t of types) {
      if (t.type === 'array') {
        const itemSchema = t.items ?? {};
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
          let schemaName = 'Array';
          if (itemSchema.$ref) {
            schemaName = sanitizeTsName(itemSchema.$ref.split('/').pop()!);
            const resolved = this.resolveRef(itemSchema.$ref);
            if (resolved) resolvedItems = resolved;
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
      } else if (t.$ref) {
        const schemaName = sanitizeTsName(t.$ref.split('/').pop()!);
        const resolved = this.resolveRef(t.$ref);
        const variantFields = this.parseSchemaFields(resolved);
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
        let valueSchema = t.additionalProperties;
        let valueName = 'Any';
        if (valueSchema.$ref) {
          valueName = sanitizeTsName(valueSchema.$ref.split('/').pop()!);
          const resolved = this.resolveRef(valueSchema.$ref);
          if (resolved) valueSchema = resolved;
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

  private buildUnionResourceField(resourceName: string, bodySchema: any): Field | null {
    const members = bodySchema.anyOf || bodySchema.oneOf;
    if (!members) return null;

    const refMembers = members.filter((m: any) => m.$ref);
    if (refMembers.length === 0) return null;

    const disc = bodySchema.discriminator;
    const discriminatorField = disc?.propertyName || this.detectDiscriminatorField(refMembers);
    if (!discriminatorField) return null;

    const variants: UnionVariant[] = [];

    if (disc?.mapping) {
      for (const [tag, refPath] of Object.entries<string>(disc.mapping)) {
        const schemaName = sanitizeTsName(refPath.split('/').pop()!);
        const schema = this.resolveRef(refPath);
        const variantFields = this.parseSchemaFields(schema, discriminatorField);
        variants.push({ tag, label: toLabel(tag), schemaName, fields: variantFields });
      }
    } else {
      for (const member of refMembers) {
        const schemaName = sanitizeTsName(member.$ref.split('/').pop()!);
        const schema = this.resolveRef(member.$ref);
        const variantFields: Field[] = [];
        let tag = schemaName;

        if (schema?.properties) {
          const variantRequired = new Set(schema.required ?? []);
          const discProp = schema.properties[discriminatorField];
          if (discProp?.const) tag = discProp.const;
          else if (discProp?.enum?.length === 1) tag = discProp.enum[0];

          for (const [subName, subProp] of Object.entries<any>(schema.properties)) {
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

  private detectDiscriminatorField(refMembers: any[]): string | null {
    const schemas = refMembers.map((m: any) => this.resolveRef(m.$ref)).filter(Boolean);
    if (schemas.length === 0) return null;

    const firstProps = Object.keys(schemas[0].properties ?? {});
    for (const propName of firstProps) {
      const isDiscriminator = schemas.every((s: any) => {
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

  /** Get the list of job management field names that actually exist in this resource's fields */
  getJobHiddenFields(r: Resource): string[] {
    const jobMgmtFields = new Set(this.jobFields);
    return r.fields.filter((f) => jobMgmtFields.has(f.name)).map((f) => f.name);
  }

  resolveRef(ref: string): any | null {
    if (!ref.startsWith('#/components/schemas/')) {
      return null;
    }
    const schemaName = ref.split('/').pop()!;
    return (
      this.spec.components?.schemas?.[schemaName] ?? this.spec.components?.schemas?.[sanitizeTsName(schemaName)] ?? null
    );
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

  fileParamToField(param: {
    name: string;
    required: boolean;
    schema?: { type?: string; format?: string };
  }): Field {
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
