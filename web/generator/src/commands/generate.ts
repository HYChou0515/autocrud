/**
 * AutoCRUD Web Code Generator
 *
 * Only generates:
 * - Type definitions from OpenAPI
 * - Resource configuration registry
 * - Simple route files that use generic components
 */

import fs from 'node:fs';
import path from 'node:path';

export interface GenerateOptions {
  openapiPath?: string;
  basePath?: string;
  /** Proxy path prefix for Vite dev server (default: '/api'). */
  proxyPath?: string;
}

export async function generateCode(apiUrl: string, outputRoot: string, options: GenerateOptions = {}): Promise<void> {
  const ROOT = process.cwd();
  const SRC = path.join(ROOT, outputRoot);
  const GEN = path.join(SRC, 'autocrud/generated');
  const ROUTES = path.join(SRC, 'routes');

  const openapiPath = options.openapiPath ?? '/openapi.json';
  const specUrl = `${apiUrl}${openapiPath}`;

  console.log('🚀 AutoCRUD Web Code Generator');
  console.log(`📡 Fetching OpenAPI spec from ${specUrl}...\n`);

  const resp = await fetch(specUrl);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}: ${resp.statusText}`);

  const spec: any = await resp.json();
  console.log(`✅ ${spec.info.title} v${spec.info.version}`);

  // Detect or use provided base path
  const basePath = options.basePath ?? detectBasePath(spec);
  if (basePath) {
    console.log(`🔗 API base path: ${basePath}`);
  }

  const generator = new Generator(spec, ROOT, SRC, GEN, ROUTES, basePath);
  await generator.run();

  // Write .env file with proxy config
  const proxyPath = options.proxyPath ?? '/api';
  writeEnvFile(ROOT, apiUrl, proxyPath);
}

/**
 * Auto-detect API base path from OpenAPI spec paths.
 *
 * Collects all POST endpoints with a $ref request body schema,
 * strips the last segment (resource name) from each path,
 * and returns the common prefix if all prefixes are identical.
 *
 * @returns The common base path (e.g. '/foo/bar') or '' if paths are at root.
 */
export function detectBasePath(spec: any): string {
  const prefixes = new Set<string>();

  for (const [p, methods] of Object.entries<any>(spec.paths ?? {})) {
    if (!methods.post) continue;
    const bodySchema = methods.post.requestBody?.content?.['application/json']?.schema;
    if (!bodySchema) continue;
    // Accept both $ref (normal models) and anyOf/oneOf (union types)
    const isResource = bodySchema.$ref || hasRefMembers(bodySchema.anyOf) || hasRefMembers(bodySchema.oneOf);
    if (!isResource) continue;

    // Strip last segment: '/foo/bar/character' → '/foo/bar'
    const lastSlash = p.lastIndexOf('/');
    if (lastSlash <= 0) {
      prefixes.add('');
    } else {
      prefixes.add(p.substring(0, lastSlash));
    }
  }

  if (prefixes.size === 0) return '';
  if (prefixes.size === 1) return [...prefixes][0];

  // Multiple different prefixes — try to find longest common prefix
  const sorted = [...prefixes].sort();
  const first = sorted[0];
  const last = sorted[sorted.length - 1];
  let common = '';
  for (let i = 0; i < first.length; i++) {
    if (first[i] === last[i]) {
      common += first[i];
    } else {
      break;
    }
  }
  // Trim to last '/' boundary
  const trimmed = common.substring(0, common.lastIndexOf('/'));
  if (trimmed) {
    console.warn(`⚠️  Multiple path prefixes detected: ${sorted.join(', ')}. Using common prefix: ${trimmed}`);
  }
  return trimmed;
}

/**
 * Write or update .env file with API configuration.
 *
 * Sets:
 * - VITE_API_URL=<proxyPath>  (relative path, proxied by Vite dev server; override for prod)
 * - API_PROXY_TARGET=<backendUrl>  (Vite dev server proxy target, not exposed to browser)
 */
export function writeEnvFile(rootDir: string, backendUrl: string, proxyPath: string = '/api'): void {
  const envPath = path.join(rootDir, '.env');
  const envVars: Record<string, string> = {
    VITE_API_URL: proxyPath,
    API_PROXY_TARGET: backendUrl,
  };

  if (fs.existsSync(envPath)) {
    const content = fs.readFileSync(envPath, 'utf-8');
    const lines = content.split('\n');
    for (const [key, value] of Object.entries(envVars)) {
      const idx = lines.findIndex((l) => l.startsWith(`${key}=`));
      if (idx >= 0) {
        lines[idx] = `${key}=${value}`;
      } else {
        lines.push(`${key}=${value}`);
      }
    }
    fs.writeFileSync(envPath, lines.join('\n'), 'utf-8');
  } else {
    const content = Object.entries(envVars)
      .map(([key, value]) => `${key}=${value}`)
      .join('\n');
    fs.writeFileSync(envPath, content + '\n', 'utf-8');
  }
  console.log(`📝 .env: VITE_API_URL=${proxyPath}`);
  console.log(`📝 .env: API_PROXY_TARGET=${backendUrl}`);
}

/** @internal Exported for testing */
export class Generator {
  private spec: any;
  private ROOT: string;
  private SRC: string;
  private GEN: string;
  private ROUTES: string;
  private basePath: string;
  /** @internal Exposed for testing */
  resources: Resource[] = [];

  constructor(spec: any, root: string, src: string, gen: string, routes: string, basePath: string) {
    this.spec = spec;
    this.ROOT = root;
    this.SRC = src;
    this.GEN = gen;
    this.ROUTES = routes;
    this.basePath = basePath;
  }

  async run() {
    this.extractResources();
    this.extractCustomCreateActions();
    console.log(`📦 Resources: ${this.resources.map((r) => r.name).join(', ')}\n`);
    console.log('📝 Generating files...');

    this.writeFile(path.join(this.GEN, 'types.ts'), this.genTypes());
    this.writeFile(path.join(this.GEN, 'resources.ts'), this.genResourcesConfig());

    for (const r of this.resources) {
      this.writeFile(path.join(this.GEN, 'api', `${r.name}Api.ts`), this.genApiClient(r));
    }
    this.writeFile(path.join(this.GEN, 'api', 'index.ts'), this.genApiIndex());

    // Backup / restore API client & page
    this.writeFile(path.join(this.GEN, 'api', 'backupApi.ts'), this.genBackupApiClient());
    this.writeFile(path.join(this.ROUTES, 'autocrud-admin', 'backup.tsx'), this.genBackupPage());

    // Migrate API client & page
    this.writeFile(path.join(this.GEN, 'api', 'migrateApi.ts'), this.genMigrateApiClient());
    this.writeFile(path.join(this.ROUTES, 'autocrud-admin', 'migrate.tsx'), this.genMigratePage());

    this.writeFile(path.join(this.ROUTES, 'index.tsx'), this.genRootIndex());
    this.writeFile(path.join(this.ROUTES, 'autocrud-admin', 'index.tsx'), this.genDashboard());

    for (const r of this.resources) {
      this.writeFile(path.join(this.ROUTES, 'autocrud-admin', r.name, 'index.tsx'), this.genListRoute(r));
      this.writeFile(path.join(this.ROUTES, 'autocrud-admin', r.name, 'create.tsx'), this.genCreateRoute(r));
      this.writeFile(path.join(this.ROUTES, 'autocrud-admin', r.name, '$resourceId.tsx'), this.genDetailRoute(r));
    }

    const fileCount = 5 + this.resources.length * 4 + 2 + 2; // +2 backup, +2 migrate
    console.log(`\n✨ Done! Generated ${fileCount} files.`);
    console.log('\nNext steps:');
    console.log('  pnpm dev');
  }

  private extractResources() {
    const resourcePaths = new Map<string, string>();
    const prefix = this.basePath;

    // Build regex that matches {prefix}/{resourceName} (single segment after prefix)
    const pattern = prefix ? new RegExp(`^${escapeRegex(prefix)}\\/([^/]+)$`) : /^\/([^/]+)$/;

    // Also collect union type resources (POST body is anyOf/oneOf, not $ref)
    const unionResourceSchemas = new Map<string, any>();

    for (const [path, methods] of Object.entries<any>(this.spec.paths)) {
      if (!methods.post) continue;
      const match = path.match(pattern);
      if (!match) continue;

      const resourceName = match[1];
      const bodySchema = methods.post.requestBody?.content?.['application/json']?.schema;
      if (!bodySchema) continue;

      if (bodySchema.$ref) {
        resourcePaths.set(resourceName, bodySchema.$ref.split('/').pop()!);
      } else if (hasRefMembers(bodySchema.anyOf) || hasRefMembers(bodySchema.oneOf)) {
        // Union type: POST body is inline anyOf/oneOf with $ref members
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

    // Process union type resources
    for (const [name, bodySchema] of unionResourceSchemas) {
      const unionField = this.buildUnionResourceField(name, bodySchema);
      if (!unionField) continue;

      // schemaName for the union type alias (e.g. "CatOrDog")
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

  /**
   * Discover custom create actions from the x-autocrud-custom-create-actions
   * OpenAPI extension and attach them to the corresponding Resource entries.
   */
  private extractCustomCreateActions() {
    const actionsMap: Record<string, any[]> = this.spec['x-autocrud-custom-create-actions'] ?? {};
    if (Object.keys(actionsMap).length === 0) return;

    for (const resource of this.resources) {
      const rawActions = actionsMap[resource.name];
      if (!rawActions || rawActions.length === 0) continue;

      const actions: CustomCreateAction[] = [];
      for (const raw of rawActions) {
        // Derive the path segment name (last part of action path)
        const fullPath: string = raw.path;
        const pathSegment = fullPath.split('/').pop() || raw.operationId;

        // Build a unified action metadata object.  When bodySchema is set
        // we extract fields from the referenced schema.  Regardless of
        // whether bodySchema exists, we always collect path / query /
        // inline-body / file params so that mixed-parameter actions
        // (e.g. Pydantic model + Body(embed=True) + UploadFile + Query)
        // produce a single combined field list.
        const actionMeta: any = {
          name: pathSegment,
          path: fullPath,
          label: raw.label,
          operationId: raw.operationId,
        };
        const fields: Field[] = [];

        // --- Body-schema fields (Struct / Pydantic model) ---
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

        // --- Path / query params come first (they're typically IDs / selectors) ---
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

        // --- Body schema fields in the middle ---
        if (bodySchemaName) {
          const schema = this.spec.components?.schemas?.[bodySchemaName];
          // When body schema coexists with other param types (query, path,
          // inline body, file), prefix its fields with bodySchemaParamName so
          // that groupFieldsByParent() renders them inside a <Fieldset>.
          const hasOtherParams =
            !!raw.pathParams?.length ||
            !!raw.queryParams?.length ||
            !!raw.inlineBodyParams?.length ||
            !!raw.fileParams?.length;
          const prefix = hasOtherParams && raw.bodySchemaParamName ? raw.bodySchemaParamName : '';
          const bodyFields = this.extractFields(schema!, prefix, 1, 10);
          fields.push(...bodyFields);
        }

        // --- Inline body / file params come last ---
        // Use extractFields (via a virtual parent schema) so that object-type
        // inline params are expanded into dot-notation sub-fields with proper
        // Fieldset grouping — the same behaviour as the default POST form.
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

      // Deduplicate labels to prevent React key collisions and UI confusion.
      // If two actions share the same label, rename the later occurrences: "Foo (2)", "Foo (3)", …
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

  /**
   * Convert an OpenAPI query/path/inline-body parameter to a Field.
   * Delegates to parseField() — param.schema IS an OpenAPI property object.
   */
  private queryParamToField(param: { name: string; required: boolean; schema?: Record<string, any> }): Field {
    const field = this.parseField(param.name, param.schema ?? { type: 'string' }, param.required);
    if (field) return field;
    // Fallback (should not happen for simple scalar schemas)
    return {
      name: param.name,
      label: toLabel(param.name),
      type: 'string',
      tsType: 'string',
      isArray: false,
      isRequired: param.required,
      isNullable: false,
      zodType: param.required ? 'z.string()' : 'z.string().optional()',
    };
  }

  /**
   * Convert an OpenAPI file-parameter (format=binary) to a Field for form generation.
   */
  private fileParamToField(param: {
    name: string;
    required: boolean;
    schema?: { type?: string; format?: string };
  }): Field {
    const zodType = param.required ? 'z.instanceof(File)' : 'z.instanceof(File).optional()';
    return {
      name: param.name,
      label: toLabel(param.name),
      type: 'file',
      tsType: 'File',
      isArray: false,
      isRequired: param.required,
      isNullable: false,
      zodType,
    };
  }

  /**
   * Build a virtual root Field of type 'union' from a POST body anyOf/oneOf schema.
   * This is used for union type resources (e.g. Cat | Dog).
   */
  private buildUnionResourceField(resourceName: string, bodySchema: any): Field | null {
    const members = bodySchema.anyOf || bodySchema.oneOf;
    if (!members) return null;

    const refMembers = members.filter((m: any) => m.$ref);
    if (refMembers.length === 0) return null;

    // Determine discriminator
    const disc = bodySchema.discriminator;
    const discriminatorField = disc?.propertyName || this.detectDiscriminatorField(refMembers);
    if (!discriminatorField) return null;

    const variants: UnionVariant[] = [];
    const variantTsTypes: string[] = [];

    if (disc?.mapping) {
      // Use explicit discriminator mapping
      for (const [tag, refPath] of Object.entries<string>(disc.mapping)) {
        const schemaName = refPath.split('/').pop()!;
        const schema = this.resolveRef(refPath);
        const variantFields = this.parseSchemaFields(schema, discriminatorField);

        variants.push({ tag, label: toLabel(tag), schemaName, fields: variantFields });
        variantTsTypes.push(schemaName);
      }
    } else {
      // Infer from $ref members
      for (const member of refMembers) {
        const schemaName = member.$ref.split('/').pop()!;
        const schema = this.resolveRef(member.$ref);
        const variantFields: Field[] = [];
        let tag = schemaName;

        if (schema?.properties) {
          const variantRequired = new Set(schema.required ?? []);
          // Try to extract tag value from the discriminator field's const/enum
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
        variantTsTypes.push(schemaName);
      }
    }

    if (variants.length === 0) return null;

    const tsType = variantTsTypes.join(' | ');
    const zodVariants = variants.map((v) => {
      const zodFields = v.fields?.map((f) => `${f.name}: ${f.zodType}`).join(', ') || '';
      return `z.object({ ${discriminatorField}: z.literal('${v.tag}'), ${zodFields} })`;
    });
    const zodType = `z.discriminatedUnion('${discriminatorField}', [${zodVariants.join(', ')}])`;

    return {
      name: 'data',
      label: toLabel(resourceName),
      type: 'union',
      tsType,
      isArray: false,
      isRequired: true,
      isNullable: false,
      zodType,
      unionMeta: { discriminatorField, variants },
    };
  }

  /**
   * Detect a common discriminator field across union $ref members.
   * Looks for a field that exists in all variants and has const/enum with a single value.
   */
  private detectDiscriminatorField(refMembers: any[]): string | null {
    const schemas = refMembers.map((m: any) => this.resolveRef(m.$ref)).filter(Boolean);
    if (schemas.length === 0) return null;

    // Find property names common to ALL variants that look like discriminator tags
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

  private detectJobSchema(schema: any): boolean {
    // Detect if this schema is a Job type by checking for Job-specific fields
    const props = schema.properties ?? {};

    // A schema is considered a Job if it has most of the Job-specific fields
    const matchedFields = this.jobFields.filter((field) => field in props);

    // Require at least 3 of the Job-specific fields to be present
    return matchedFields.length >= 3;
  }

  /** Get the list of job management field names that actually exist in this resource's fields */
  private getJobHiddenFields(r: Resource): string[] {
    const jobMgmtFields = new Set(this.jobFields);
    // Only include fields that actually exist in the resource
    return r.fields.filter((f) => jobMgmtFields.has(f.name)).map((f) => f.name);
  }

  private extractFields(schema: any, parentPath: string = '', currentDepth: number = 1, maxDepth: number = 2): Field[] {
    const fields: Field[] = [];
    const required = new Set(schema.required ?? []);

    for (const [name, rawProp] of Object.entries<any>(schema.properties ?? {})) {
      const fullName = parentPath ? `${parentPath}.${name}` : name;

      // Resolve $ref if present
      let prop = rawProp;
      if (prop.$ref) {
        const resolved = this.resolveRef(prop.$ref);
        if (resolved) prop = resolved;
      }

      // Handle nullable $ref struct: anyOf: [$ref, {type:'null'}]
      // If this is a nullable reference to an expandable object, recurse to expand sub-fields
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

      // If this is a typed object (has properties) and we haven't exceeded max depth,
      // expand its sub-fields recursively instead of treating as opaque JSON
      // But skip Binary schemas — they should be treated as atomic binary fields
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

  private resolveRef(ref: string): any | null {
    // Handle refs like "#/components/schemas/ItemRarity"
    if (!ref.startsWith('#/components/schemas/')) {
      return null;
    }
    const schemaName = ref.split('/').pop();
    return this.spec.components?.schemas?.[schemaName!] ?? null;
  }

  /**
   * Parse all properties of a schema into Field[], optionally excluding a field by name.
   * Consolidates the repeated pattern of iterating schema.properties with parseField().
   */
  private parseSchemaFields(schema: any, exclude?: string): Field[] {
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

  /**
   * Detect if a resolved schema represents a Binary type.
   * Binary has a `data` property with contentEncoding: "base64".
   */
  private isBinarySchema(schema: any): boolean {
    if (schema?.type !== 'object' || !schema?.properties) return false;
    const dataProp = schema.properties.data;
    return dataProp?.contentEncoding === 'base64';
  }

  /**
   * Apply nullable/optional zod and TS type modifiers.
   */
  private applyNullableOptional(
    tsType: string,
    zodType: string,
    isNullable: boolean,
    isRequired: boolean,
  ): { tsType: string; zodType: string } {
    if (isNullable || !isRequired) {
      if (isNullable && !isRequired) {
        tsType += ' | null';
        zodType = `${zodType}.nullable().optional()`;
      } else if (isNullable) {
        tsType += ' | null';
        zodType = `${zodType}.nullable()`;
      } else {
        zodType = `${zodType}.optional()`;
      }
    }
    return { tsType, zodType };
  }

  /**
   * Try to parse a discriminated union (anyOf + discriminator with mapping).
   * Returns null if this is not a discriminated union pattern.
   */
  private tryParseDiscriminatedUnion(
    name: string,
    prop: any,
    types: any[],
    isNullable: boolean,
    isRequired: boolean,
  ): Field | null {
    // Resolve the union source: direct or nested inside nullable
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
    const variantTsTypes: string[] = [];

    for (const [tag, refPath] of Object.entries<string>(disc.mapping || {})) {
      const schemaName = refPath.split('/').pop()!;
      const schema = this.resolveRef(refPath);
      const variantFields = this.parseSchemaFields(schema, discriminatorField);

      variants.push({ tag, label: toLabel(tag), schemaName, fields: variantFields });
      variantTsTypes.push(schemaName);
    }

    let tsType = variantTsTypes.join(' | ');
    const zodVariants = variants.map((v) => {
      const zodFields = v.fields?.map((f) => `${f.name}: ${f.zodType}`).join(', ') || '';
      return `z.object({ ${discriminatorField}: z.literal('${v.tag}'), ${zodFields} })`;
    });
    let zodType = `z.discriminatedUnion('${discriminatorField}', [${zodVariants.join(', ')}])`;
    ({ tsType, zodType } = this.applyNullableOptional(tsType, zodType, isNullable, isRequired));

    return {
      name,
      label: toLabel(getLeafLabel(name)),
      type: 'union',
      tsType,
      isArray: false,
      isRequired,
      isNullable,
      zodType,
      unionMeta: { discriminatorField, variants },
    };
  }

  /**
   * Try to parse a simple union (multiple non-null primitive types, no $ref, no arrays).
   * Returns null if not applicable.
   */
  private tryParseSimpleUnion(name: string, types: any[], isNullable: boolean, isRequired: boolean): Field | null {
    if (types.length <= 1 || types.some((t: any) => t.$ref) || types.some((t: any) => t.type === 'array')) {
      return null;
    }

    const variants: UnionVariant[] = [];
    const variantTsTypes: string[] = [];
    const seenTags = new Set<string>();

    for (const t of types) {
      const primitiveType = t.type === 'integer' ? 'number' : t.type;
      // Deduplicate variants with the same normalized type (e.g. int|float both → number)
      if (seenTags.has(primitiveType)) continue;
      seenTags.add(primitiveType);
      variants.push({ tag: primitiveType, label: toLabel(primitiveType), type: primitiveType });
      variantTsTypes.push(primitiveType === 'integer' ? 'number' : primitiveType);
    }

    // After dedup, if only one variant remains, it's not really a union — return as plain field
    if (variants.length <= 1) {
      const singleType = variants[0]?.type ?? 'string';
      const singleZod = types.map((t: any) => {
        if (t.type === 'string') return 'z.string()';
        if (t.type === 'integer') return 'z.number().int()';
        if (t.type === 'number') return 'z.number()';
        if (t.type === 'boolean') return 'z.boolean()';
        return 'z.any()';
      });
      // Use z.union if multiple zod types (e.g. z.number().int() | z.number()), else single
      let zodType = singleZod.length > 1 ? `z.union([${singleZod.join(', ')}])` : (singleZod[0] ?? 'z.any()');
      let tsType = variantTsTypes[0] ?? 'any';
      ({ tsType, zodType } = this.applyNullableOptional(tsType, zodType, isNullable, isRequired));

      return {
        name,
        label: toLabel(getLeafLabel(name)),
        type: singleType,
        tsType,
        isArray: false,
        isRequired,
        isNullable,
        zodType,
      };
    }

    let tsType = variantTsTypes.join(' | ');
    const zodVariants = types.map((t: any) => {
      if (t.type === 'string') return 'z.string()';
      if (t.type === 'integer') return 'z.number().int()';
      if (t.type === 'number') return 'z.number()';
      if (t.type === 'boolean') return 'z.boolean()';
      return 'z.any()';
    });
    let zodType = `z.union([${zodVariants.join(', ')}])`;
    ({ tsType, zodType } = this.applyNullableOptional(tsType, zodType, isNullable, isRequired));

    return {
      name,
      label: toLabel(getLeafLabel(name)),
      type: 'union',
      tsType,
      isArray: false,
      isRequired,
      isNullable,
      zodType,
      unionMeta: { discriminatorField: '__type', variants },
    };
  }

  /**
   * Build discriminated union metadata from an items schema that contains anyOf/oneOf + discriminator.
   * Used by structural union array variants and array-of-discriminated-union fields.
   */
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
      const schemaName = refPath.split('/').pop()!;
      const schema = this.resolveRef(refPath);
      const variantFields = this.parseSchemaFields(schema, discriminatorField);

      variants.push({ tag, label: toLabel(tag), schemaName, fields: variantFields });
    }

    return { discriminatorField, variants };
  }

  /**
   * Try to parse a structural union (mixed: $ref, array, primitive without common discriminator).
   * Handles list[DiscriminatedUnion] by detecting items.anyOf + items.discriminator → itemUnionMeta.
   * Returns null if not applicable.
   */
  private tryParseStructuralUnion(
    name: string,
    types: any[],
    isNullable: boolean,
    isRequired: boolean,
    hasNullVariant: boolean = false,
  ): Field | null {
    if (types.length <= 1) return null;

    const variants: UnionVariant[] = [];
    const variantTsTypes: string[] = [];
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

        // Check if array items form a discriminated union
        const innerUnionMeta = this.buildDiscriminatedUnionMeta(itemSchema);
        if (innerUnionMeta) {
          // list[DiscriminatedUnion] — e.g. list[EventBodyX | EventBodyB | EventBodyA]
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
          variantTsTypes.push(unionLabel);
        } else {
          // Regular array variant: list[X]
          let resolvedItems = itemSchema;
          let schemaName = 'Array';
          if (itemSchema.$ref) {
            schemaName = itemSchema.$ref.split('/').pop()!;
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
          variantTsTypes.push(`${schemaName}[]`);
        }
      } else if (t.$ref) {
        const schemaName = t.$ref.split('/').pop()!;
        const resolved = this.resolveRef(t.$ref);
        const variantFields = this.parseSchemaFields(resolved);
        const tag = makeUniqueTag(schemaName);
        variants.push({
          tag,
          label: toLabel(schemaName),
          schemaName,
          fields: variantFields,
        });
        variantTsTypes.push(schemaName);
      } else if ((t.anyOf || t.oneOf) && t.discriminator) {
        // Nested discriminated union (e.g. msgspec wraps `X | B` as { anyOf+disc })
        // Flatten each inner variant as a separate structural union choice
        const innerMeta = this.buildDiscriminatedUnionMeta(t);
        if (innerMeta) {
          for (const iv of innerMeta.variants) {
            const tag = makeUniqueTag(iv.schemaName || iv.tag);
            // Inject discriminator field with constValue so the backend receives it on submit
            const discField: Field = {
              name: innerMeta.discriminatorField,
              label: toLabel(innerMeta.discriminatorField),
              type: 'string',
              tsType: 'string',
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
            variantTsTypes.push(iv.schemaName || iv.tag);
          }
        }
      } else if (t.type === 'object' && t.additionalProperties) {
        // Dict/map variant: dict[str, ValueType]
        let valueSchema = t.additionalProperties;
        let valueName = 'Any';
        if (valueSchema.$ref) {
          valueName = valueSchema.$ref.split('/').pop()!;
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
        variantTsTypes.push(`Record<string, ${valueName}>`);
      } else {
        const primitiveType = t.type === 'integer' ? 'number' : t.type || 'json';
        const tag = makeUniqueTag(primitiveType);
        variants.push({ tag, label: toLabel(primitiveType), type: primitiveType });
        variantTsTypes.push(primitiveType);
      }
    }

    // Add null as a selectable variant if the union contains {type:'null'}
    if (hasNullVariant) {
      const tag = makeUniqueTag('null');
      variants.push({ tag, label: 'None', type: 'null' });
      variantTsTypes.push('null');
    }

    let tsType = variantTsTypes.join(' | ');
    let zodType = 'z.any()';
    ({ tsType, zodType } = this.applyNullableOptional(tsType, zodType, isNullable, isRequired));

    return {
      name,
      label: toLabel(getLeafLabel(name)),
      type: 'union',
      tsType,
      isArray: false,
      isRequired,
      isNullable,
      zodType,
      unionMeta: { discriminatorField: '__variant', variants },
    };
  }

  private parseField(name: string, prop: any, isRequired: boolean): Field | null {
    let type = prop.type;
    let isArray = false;
    let isNullable = false;
    let enumValues: string[] | undefined;
    let enumSchemaName: string | undefined;
    let tsType = 'string';
    let zodType = 'z.string()';

    // Handle $ref references
    if (prop.$ref) {
      const refName = prop.$ref.split('/').pop()!;
      const refSchema = this.resolveRef(prop.$ref);
      if (refSchema) {
        // Track enum schema name so we can use it as the TS type
        if (refSchema.enum) {
          enumSchemaName = refName;
        }
        prop = refSchema;
        type = prop.type;
      }
    }

    // Detect const value (from tagged struct discriminator field)
    // prop.const is used by msgspec for tag=True structs
    if (prop.const !== undefined) {
      const constVal = String(prop.const);
      return {
        name,
        label: toLabel(getLeafLabel(name)),
        type: 'string',
        tsType: `'${constVal}'`,
        isArray: false,
        isRequired,
        isNullable: false,
        zodType: `z.literal('${constVal}')`,
        constValue: constVal,
      };
    }

    // Extract x-unique metadata (from Unique() annotation)
    const isUnique = !!prop['x-unique'];

    // Extract x-ref-* metadata (may be at top level for Annotated[str|None, Ref(...)])
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

      // Step 1: Discriminated union? (anyOf + discriminator)
      const discResult = this.tryParseDiscriminatedUnion(name, prop, types, isNullable, isRequired);
      if (discResult) return discResult;

      // Step 2: Simple union? (all primitives, no $ref, no array)
      const simpleResult = this.tryParseSimpleUnion(name, types, isNullable, isRequired);
      if (simpleResult) return simpleResult;

      // Step 3: Structural union? (mixed: $ref, array, primitive)
      const structResult = this.tryParseStructuralUnion(name, types, isNullable, isRequired, isNullable);
      if (structResult) return structResult;

      // Simple nullable (single non-null type) — original logic
      if (types.length > 0) {
        // Check for x-ref-* in anyOf branch (for Optional[Annotated[str, Ref(...)]])
        if (!ref && types[0]['x-ref-resource']) {
          ref = {
            resource: types[0]['x-ref-resource'],
            type: types[0]['x-ref-type'] ?? 'resource_id',
            ...(types[0]['x-ref-on-delete'] ? { onDelete: types[0]['x-ref-on-delete'] } : {}),
          };
        }
        prop = types[0];
        // Resolve $ref in anyOf
        if (prop.$ref) {
          const refName = prop.$ref.split('/').pop()!;
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
      // Resolve $ref in array items
      if (prop.$ref) {
        const refSchema = this.resolveRef(prop.$ref);
        if (refSchema) {
          prop = refSchema;
        }
      }

      // Handle nested arrays: list[list[...]] — the Field/form UI only supports
      // a single array depth, so deeply nested arrays fall back to JSON editing.
      if (prop.type === 'array') {
        // Recurse to compute the correct tsType / zodType for type generation,
        // but expose the field as a JSON editor since the form can't render
        // multi-dimensional arrays with structured controls.
        const innerField = this.parseField(name, prop, isRequired);
        if (innerField) {
          const wrappedTsType = `${innerField.tsType}[]`;
          const wrappedZodType = `z.array(${innerField.zodType})`;
          return {
            name,
            label: toLabel(getLeafLabel(name)),
            type: 'object',
            tsType: wrappedTsType,
            isArray: false,
            isRequired,
            isNullable,
            zodType: wrappedZodType,
          };
        }
      }

      // Handle array items that are a non-discriminated union (anyOf without discriminator).
      // Since a single-depth array of structural union IS supported by the form UI,
      // we let this fall through to `tryParseStructuralUnion` via the anyOf block below.
      if ((prop.anyOf || prop.oneOf) && !prop.discriminator) {
        // Re-enter parseField so that the anyOf/oneOf logic handles the union parsing,
        // then wrap the result with the outer array layer.
        const innerField = this.parseField(name, prop, isRequired);
        if (innerField) {
          const wrappedTsType = `(${innerField.tsType})[]`;
          const wrappedZodType = `z.array(${innerField.zodType})`;
          return {
            ...innerField,
            tsType: wrappedTsType,
            zodType: wrappedZodType,
            isArray: true,
          };
        }
      }

      // Detect array of discriminated union: items has anyOf/oneOf + discriminator
      const unionItems = (prop.anyOf || prop.oneOf) && prop.discriminator ? prop : null;
      if (unionItems) {
        const disc = unionItems.discriminator;
        const discriminatorField = disc.propertyName || 'type';
        const variants: UnionVariant[] = [];
        const variantTsTypes: string[] = [];

        for (const [tag, refPath] of Object.entries<string>(disc.mapping || {})) {
          const schemaName = refPath.split('/').pop()!;
          const itemSchema = this.resolveRef(refPath);
          const variantFields = this.parseSchemaFields(itemSchema, discriminatorField);

          variants.push({ tag, label: toLabel(tag), schemaName, fields: variantFields });
          variantTsTypes.push(schemaName);
        }

        tsType = `(${variantTsTypes.join(' | ')})[]`;
        const zodVariants = variants.map((v) => {
          const zodFields = v.fields?.map((f) => `${f.name}: ${f.zodType}`).join(', ') || '';
          return `z.object({ ${discriminatorField}: z.literal('${v.tag}'), ${zodFields} })`;
        });
        zodType = `z.array(z.discriminatedUnion('${discriminatorField}', [${zodVariants.join(', ')}]))`;

        ({ tsType, zodType } = this.applyNullableOptional(tsType, zodType, isNullable, isRequired));

        return {
          name,
          label: toLabel(getLeafLabel(name)),
          type: 'union',
          tsType,
          isArray: true,
          isRequired,
          isNullable,
          zodType,
          unionMeta: { discriminatorField, variants },
        };
      }

      type = prop.type;
    }

    // Detect Binary schema (object with data.contentEncoding === 'base64')
    if (this.isBinarySchema(prop)) {
      type = 'binary';
      tsType = 'Binary';
      zodType = 'z.any()';

      if (isArray) {
        tsType += '[]';
        zodType = `z.array(${zodType})`;
      }
      ({ tsType, zodType } = this.applyNullableOptional(tsType, zodType, isNullable, isRequired));
      return {
        name,
        label: toLabel(getLeafLabel(name)),
        type: 'binary',
        tsType,
        isArray,
        isRequired,
        isNullable,
        zodType,
      };
    }

    // Detect array of typed objects: extract item sub-fields and build proper z.object
    let itemFields: Field[] | undefined;
    if (isArray && type === 'object' && prop.properties) {
      itemFields = this.parseSchemaFields(prop);
      // Build proper z.object for array items (will be wrapped by z.array below)
      const innerIndent = '        ';
      const itemZodLines = itemFields.map((f) => `${innerIndent}${f.name}: ${f.zodType}`).join(',\n');
      zodType = `z.object({\n${itemZodLines}\n    })`;
      tsType = 'object';
    } else if (prop.enum) {
      enumValues = prop.enum;
      tsType = enumSchemaName ?? 'string';
      const enumLiterals = enumValues!.map((v) => `"${v}"`).join(', ');
      zodType = `z.enum([${enumLiterals}])`;

      // Single-element enum from tagged struct discriminator → treat as const
      if (enumValues!.length === 1) {
        const constVal = enumValues![0];
        tsType = `'${constVal}'`;
        zodType = `z.literal('${constVal}')`;

        ({ tsType, zodType } = this.applyNullableOptional(tsType, zodType, isNullable, isRequired));

        return {
          name,
          label: toLabel(getLeafLabel(name)),
          type: 'string',
          tsType,
          isArray: false,
          isRequired,
          isNullable,
          enumValues,
          zodType,
          constValue: constVal,
        };
      }
    } else if (type === 'string') {
      if (prop.format === 'date-time' || prop.format === 'date') {
        type = 'date'; // Mark as date type for ResourceForm to use DateTimePicker
        tsType = 'string';
        zodType = 'z.union([z.string(), z.date()])';
      } else if (looksLikeDatetime(name, prop)) {
        type = 'date'; // Heuristic: default/example value suggests datetime
        tsType = 'string';
        zodType = 'z.union([z.string(), z.date()])';
      } else if (prop.contentEncoding === 'base64') {
        tsType = 'Binary';
        zodType = 'z.any()'; // Binary handled separately
      } else {
        tsType = 'string';
        zodType = 'z.string()';
      }
    } else if (type === 'integer' || type === 'number') {
      tsType = 'number';
      zodType = type === 'integer' ? 'z.number().int()' : 'z.number()';
    } else if (type === 'boolean') {
      tsType = 'boolean';
      zodType = 'z.boolean()';
    } else if (type === 'object') {
      tsType = 'Record<string, any>';
      zodType = 'z.record(z.string(), z.any())';
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
      // Fallback for unrecognized schema types — use 'any' instead of silently defaulting to 'string'
      console.warn(
        `[autocrud-web-generator] Unrecognized schema type "${type}" for field "${name}", falling back to 'any'.`,
      );
      tsType = 'any';
      zodType = 'z.any()';
    }

    if (isArray) {
      tsType += '[]';
      zodType = `z.array(${zodType})`;
    }

    ({ tsType, zodType } = this.applyNullableOptional(tsType, zodType, isNullable, isRequired));

    // For nested fields like 'payload.event_type', use only the leaf part for labels
    return {
      name,
      label: toLabel(getLeafLabel(name)),
      type: type === 'integer' ? 'number' : type,
      tsType,
      isArray,
      isRequired,
      isNullable,
      enumValues,
      zodType,
      ...(itemFields ? { itemFields } : {}),
      ...(ref ? { ref } : {}),
      ...(isUnique ? { isUnique: true } : {}),
    };
  }

  private genTypes(): string {
    const enums: string[] = [];
    const interfaces: string[] = [];
    const SKIP = new Set(['ResourceMeta', 'RevisionInfo', 'RevisionStatus', 'RevisionListResponse']);

    for (const [name, schema] of Object.entries<any>(this.spec.components.schemas)) {
      if (SKIP.has(name)) continue;

      if (schema.enum) {
        const values = schema.enum.map((v: string) => `  "${v}" = "${v}"`).join(',\n');
        enums.push(`export enum ${name} {\n${values}\n}`);
      } else if (schema.properties) {
        const props = Object.entries<any>(schema.properties)
          .map(([k, v]) => {
            const field = this.parseField(k, v, schema.required?.includes(k) ?? false);
            if (!field) return '';
            const optional = field.isRequired ? '' : '?';
            return `  ${k}${optional}: ${field.tsType};`;
          })
          .filter(Boolean)
          .join('\n');
        interfaces.push(`export interface ${name} {\n${props}\n}`);
      }
    }

    // Generate union type aliases for union resources
    const unionAliases: string[] = [];
    for (const r of this.resources) {
      if (r.isUnion && r.unionVariantSchemaNames && r.unionVariantSchemaNames.length > 0) {
        unionAliases.push(`export type ${r.schemaName} = ${r.unionVariantSchemaNames.join(' | ')};`);
      }
    }

    const parts = [enums.join('\n\n'), interfaces.join('\n\n'), unionAliases.join('\n\n')].filter(Boolean);
    return `// Auto-generated by AutoCRUD Web Generator\n\n${parts.join('\n\n')}\n`;
  }

  private genResourcesConfig(): string {
    const configs = this.resources.map((r) => {
      const fields = r.fields.map((f) => serializeField(f));

      // Generate Zod schema with nested structure for dot-notation fields
      const zodFields = buildNestedZodFields(r.fields);

      const displayNameLine = r.displayNameField ? `    displayNameField: '${r.displayNameField}',\n` : '';

      // Generate customCreateActions if present
      let customActionsBlock = '';
      if (r.customCreateActions && r.customCreateActions.length > 0) {
        const actionEntries = r.customCreateActions.map((action) => {
          const actionFields = action.fields.map((f) => serializeField(f));
          const actionZodFields = buildNestedZodFields(action.fields);
          const methodName = toCamel(action.operationId);
          return `      {
        name: '${action.name}',
        label: '${action.label}',
        fields: ${JSON.stringify(actionFields, null, 10).replace(/"([^"]+)":/g, '$1:')},
        zodSchema: z.object({
${actionZodFields}
        }),
        apiMethod: ${r.camel}Api.${methodName},
      }`;
        });
        customActionsBlock = `
    customCreateActions: [
${actionEntries.join(',\n')}
    ],`;
      }

      return `  '${r.name}': {
    name: '${r.name}',
    label: '${r.label}',
    pluralLabel: '${r.label}s',
${displayNameLine}    schema: '${r.schemaName}',
    fields: ${JSON.stringify(fields, null, 6).replace(/"([^"]+)":/g, '$1:')},
    zodSchema: z.object({
${zodFields}
    }),
    apiClient: ${r.camel}Api,
    maxFormDepth: ${r.maxFormDepth},${
      r.isJob
        ? `
    defaultHiddenFields: ${JSON.stringify(this.getJobHiddenFields(r))},`
        : ''
    }${
      r.isUnion
        ? `
    isUnion: true,`
        : ''
    }${customActionsBlock}
  }`;
    });

    const imports = this.resources.map((r) => `import { ${r.camel}Api } from './api/${r.name}Api';`).join('\n');

    // Generate typed route helpers for RefLink/RefRevisionLink
    const resourceNameUnion = this.resources.map((r) => `'${r.name}'`).join(' | ');
    const detailRouteUnion = this.resources.map((r) => `'/autocrud-admin/${r.name}/$resourceId'`).join('\n  | ');
    const listRouteUnion = this.resources.map((r) => `'/autocrud-admin/${r.name}'`).join('\n  | ');
    const detailRouteCases = this.resources
      .map((r) => `  '${r.name}': '/autocrud-admin/${r.name}/$resourceId'`)
      .join(',\n');
    const listRouteCases = this.resources.map((r) => `  '${r.name}': '/autocrud-admin/${r.name}'`).join(',\n');

    // Generate per-resource field name union types
    const fieldNameTypes = this.resources
      .map((r) => {
        const fieldNames = r.fields.map((f) => `'${f.name}'`).join(' | ');
        return `export type ${r.pascal}FieldName = ${fieldNames};`;
      })
      .join('\n');

    // Generate ResourceFieldMap: resource name -> field name union
    const fieldMapEntries = this.resources.map((r) => `  '${r.name}': ${r.pascal}FieldName;`).join('\n');

    return `// Auto-generated by AutoCRUD Web Generator
import { resources as registry, applyCustomizations as applyCustomizationsImpl } from '../lib/resources';
import type { ResourceCustomizations as ResourceCustomizationsBase } from '../lib/resources';
import { z } from 'zod';
${imports}

/** Union type of all resource names */
export type ResourceName = ${resourceNameUnion};

/** Per-resource field name union types */
${fieldNameTypes}

/** Mapping from resource name to its field name union type */
export interface ResourceFieldMap {
${fieldMapEntries}
}

/** Type-safe customization config for all resources */
export type ResourceCustomizations = ResourceCustomizationsBase<ResourceFieldMap>;

/** Union type of all resource detail route paths */
export type ResourceDetailRoute =
  | ${detailRouteUnion};

/** Union type of all resource list route paths */
export type ResourceListRoute =
  | ${listRouteUnion};

/** Mapping from resource name to detail route path */
const detailRoutes: Record<ResourceName, ResourceDetailRoute> = {
${detailRouteCases},
};

/** Mapping from resource name to list route path */
const listRoutes: Record<ResourceName, ResourceListRoute> = {
${listRouteCases},
};

/** Get the detail route path for a resource (type-safe for TanStack Router) */
export function getResourceDetailRoute(resource: ResourceName): ResourceDetailRoute {
  return detailRoutes[resource];
}

/** Get the list route path for a resource (type-safe for TanStack Router) */
export function getResourceListRoute(resource: ResourceName): ResourceListRoute {
  return listRoutes[resource];
}

Object.assign(registry, {
${configs.join(',\n')}
});

/**
 * Apply type-safe customizations to the generated resources.
 * Call this in main.tsx after the resources are registered.
 */
export function applyCustomizations(customizations: ResourceCustomizations): void {
  applyCustomizationsImpl(customizations);
}

export { registry as resources };
`;
  }

  private genApiClient(r: Resource): string {
    const base = `${this.basePath}/${r.name}`;
    // Only import the main schema name; union variant types are not directly
    // referenced in the API client and would cause unused-import lint errors.
    const allTypeImports: string[] = [r.schemaName];
    // Add custom action body schema imports — only for pure-body-schema
    // actions where the type is used in the method signature `(data: Type)`.
    // Mixed-param actions use `Record<string, unknown>` so the type is unused.
    if (r.customCreateActions) {
      for (const action of r.customCreateActions) {
        if (action.bodySchemaName && !allTypeImports.includes(action.bodySchemaName)) {
          const hasOtherParams =
            !!action.pathParams?.length ||
            !!action.queryParams?.length ||
            !!action.inlineBodyParams?.length ||
            !!action.fileParams?.length;
          if (!hasOtherParams) {
            allTypeImports.push(action.bodySchemaName);
          }
        }
      }
    }
    const typeImports = allTypeImports.join(', ');

    const rerunMethod = r.isJob
      ? `
  rerun: (id: string) =>
    client.post<RevisionInfo>(\`\${BASE}/\${id}/rerun\`),
`
      : '';

    const logsMethod = r.isJob
      ? `
  getLogs: (id: string) =>
    client.get<string>(\`\${BASE}/\${id}/logs\`, { transformResponse: [(data: string) => data] }),
`
      : '';

    // Generate custom create action methods
    let customActionMethods = '';
    if (r.customCreateActions) {
      for (const action of r.customCreateActions) {
        const methodName = toCamel(action.operationId);

        if (action.bodySchemaName) {
          // Check if there are additional param types alongside the body schema
          const hasOtherParams =
            !!action.pathParams?.length ||
            !!action.queryParams?.length ||
            !!action.inlineBodyParams?.length ||
            !!action.fileParams?.length;

          if (!hasOtherParams) {
            // Pure body schema: simple typed method
            customActionMethods += `
  ${methodName}: (data: ${action.bodySchemaName}) =>
    client.post<RevisionInfo>('${action.path}', data),
`;
            continue;
          }

          // Mixed case: body schema + other param types.
          // We need to split allParams into: body schema fields (nested under
          // the handler param name), path/query params, inline body, and files.
          const hasPath = !!action.pathParams?.length;
          const hasQuery = !!action.queryParams?.length;
          const hasInlineBody = !!action.inlineBodyParams?.length;
          const hasFile = !!action.fileParams?.length;
          const bodySchemaParamName = action.bodySchemaParamName || 'body';
          const _bodyFieldNames = action.bodySchemaFieldNames || [];

          const urlExpr = hasPath
            ? '`' + action.path.replace(/\{(\w+)\}/g, (_, pname) => `\${allParams['${pname}'] as string}`) + '`'
            : `'${action.path}'`;

          const setupLines: string[] = [];
          let bodyVar = 'null';

          // Body schema fields are nested under bodySchemaParamName in form
          // values (dot-notation → nested object).  Use that directly.
          setupLines.push(`    const bodyObj = allParams['${bodySchemaParamName}'] as Record<string, unknown>;`);

          if (hasFile) {
            // Multipart/form-data: body schema as JSON string field
            setupLines.push('    const formData = new FormData();');
            setupLines.push(`    formData.append('${bodySchemaParamName}', JSON.stringify(bodyObj));`);
            if (hasInlineBody) {
              for (const p of action.inlineBodyParams!) {
                setupLines.push(`    formData.append('${p.name}', String(allParams['${p.name}']));`);
              }
            }
            for (const p of action.fileParams!) {
              setupLines.push(
                `    if (allParams['${p.name}'] instanceof File) formData.append('${p.name}', allParams['${p.name}'] as File);`,
              );
            }
            bodyVar = 'formData';
          } else if (hasInlineBody) {
            // JSON body: nest body schema + inline fields at top level
            const ibpEntries = action
              .inlineBodyParams!.map((p: any) => `'${p.name}': allParams['${p.name}']`)
              .join(', ');
            setupLines.push(`    const data = { '${bodySchemaParamName}': bodyObj, ${ibpEntries} };`);
            bodyVar = 'data';
          } else {
            // JSON body: just the body schema nested under param name
            setupLines.push(`    const data = { '${bodySchemaParamName}': bodyObj };`);
            bodyVar = 'data';
          }

          let configArg = '';
          if (hasQuery) {
            const qpEntries = action.queryParams!.map((p: any) => `${p.name}: allParams['${p.name}']`).join(', ');
            setupLines.push(`    const params = { ${qpEntries} };`);
            configArg = ', { params }';
          }

          const postArgs = `${urlExpr}, ${bodyVar}${configArg}`;
          customActionMethods += `
  ${methodName}: (allParams: Record<string, unknown>) => {
${setupLines.join('\n')}
    return client.post<RevisionInfo>(${postArgs});
  },
`;
          continue;
        }

        // Compositional: build URL, body, and config independently
        const hasPath = !!action.pathParams?.length;
        const hasQuery = !!action.queryParams?.length;
        const hasInlineBody = !!action.inlineBodyParams;
        const hasFile = !!action.fileParams?.length;

        // Step 1: URL expression
        const urlExpr = hasPath
          ? '`' + action.path.replace(/\{(\w+)\}/g, (_, pname) => `\${allParams['${pname}'] as string}`) + '`'
          : `'${action.path}'`;

        // Step 2: Body — FormData when files present, JSON object for inline body, null otherwise
        const bodyLines: string[] = [];
        let bodyVar = 'null';
        if (hasFile) {
          bodyLines.push('    const formData = new FormData();');
          // Append inline body params as form fields
          if (hasInlineBody) {
            for (const p of action.inlineBodyParams as any[]) {
              bodyLines.push(`    formData.append('${p.name}', String(allParams['${p.name}']));`);
            }
          }
          // Append file params
          for (const p of action.fileParams as any[]) {
            bodyLines.push(
              `    if (allParams['${p.name}'] instanceof File) formData.append('${p.name}', allParams['${p.name}'] as File);`,
            );
          }
          bodyVar = 'formData';
        } else if (hasInlineBody) {
          const ibpEntries = (action.inlineBodyParams as any[])
            .map((p: any) => `${p.name}: allParams['${p.name}']`)
            .join(', ');
          bodyLines.push(`    const data = { ${ibpEntries} };`);
          bodyVar = 'data';
        }

        // Step 3: Query params config
        const configLines: string[] = [];
        let configArg = '';
        if (hasQuery) {
          const qpEntries = action.queryParams!.map((p: any) => `${p.name}: allParams['${p.name}']`).join(', ');
          configLines.push(`    const params = { ${qpEntries} };`);
          configArg = ', { params }';
        }

        // Step 4: Assemble method
        const allSetupLines = [...bodyLines, ...configLines];
        if (allSetupLines.length === 0) {
          // Simple one-liner
          customActionMethods += `
  ${methodName}: (allParams: Record<string, unknown>) =>
    client.post<RevisionInfo>(${urlExpr}, ${bodyVar}${configArg}),
`;
        } else {
          const postArgs = `${urlExpr}, ${bodyVar}${configArg}`;
          customActionMethods += `
  ${methodName}: (allParams: Record<string, unknown>) => {
${allSetupLines.join('\n')}
    return client.post<RevisionInfo>(${postArgs});
  },
`;
        }
      }
    }

    return `// Auto-generated by AutoCRUD Web Generator
import { client } from '../../lib/client';
import type { ${typeImports} } from '../types';
import type { ResourceMeta, RevisionInfo, FullResource, RevisionListResponse, RevisionListParams, SearchParams } from '../../types/api';

const BASE = '${base}';

export const ${r.camel}Api = {
  create: (data: ${r.schemaName}) =>
    client.post<RevisionInfo>(BASE, data),

  list: (params?: SearchParams & { returns?: string }) =>
    client.get<FullResource<${r.schemaName}>[]>(BASE, { params }),

  count: (params?: SearchParams) =>
    client.get<number>(\`\${BASE}/count\`, { params }),

  get: (id: string, params?: { revision_id?: string; partial?: string[]; returns?: string; include_deleted?: boolean }) =>
    client.get<FullResource<${r.schemaName}>>(\`\${BASE}/\${id}\`, { params }),

  update: (id: string, data: ${r.schemaName}, params?: { change_status?: string; mode?: string }) =>
    client.put<RevisionInfo>(\`\${BASE}/\${id}\`, data, { params }),

  delete: (id: string) =>
    client.delete<ResourceMeta>(\`\${BASE}/\${id}\`),

  permanentlyDelete: (id: string) =>
    client.delete<ResourceMeta>(\`\${BASE}/\${id}/permanently\`),

  restore: (id: string) =>
    client.post<ResourceMeta>(\`\${BASE}/\${id}/restore\`),

  revisionList: (id: string, params?: RevisionListParams) =>
    client.get<RevisionListResponse>(\`\${BASE}/\${id}/revision-list\`, { params }),

  switchRevision: (id: string, revisionId: string) =>
    client.post<ResourceMeta>(\`\${BASE}/\${id}/switch/\${revisionId}\`),
${rerunMethod}${logsMethod}${customActionMethods}};
`;
  }

  private genApiIndex(): string {
    const exports = this.resources.map((r) => `export { ${r.camel}Api } from './${r.name}Api';`).join('\n');
    return `// Auto-generated by AutoCRUD Web Generator\n${exports}\nexport { backupApi } from './backupApi';\nexport { migrateApi } from './migrateApi';\n`;
  }

  // ── Backup / Restore ──────────────────────────────────────────

  private genBackupApiClient(): string {
    const perModel = this.resources
      .map(
        (r) => `
  /** Export ${r.label} data as .acbak archive */
  export${r.pascal}: (params?: Record<string, unknown>) =>
    client.get(\`/${r.name}/export\`, { params, responseType: 'blob' }),

  /** Import .acbak archive into ${r.label} */
  import${r.pascal}: (file: File, onDuplicate: OnDuplicate = 'overwrite') => {
    const form = new FormData();
    form.append('file', file);
    return client.post<ImportResult>(\`/${r.name}/import\`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      params: { on_duplicate: onDuplicate },
    });
  },`,
      )
      .join('\n');

    return `// Auto-generated by AutoCRUD Web Generator
import { client } from '../../lib/client';

export type OnDuplicate = 'overwrite' | 'skip' | 'raise_error';

export interface ImportResult {
  loaded: number;
  skipped: number;
  total: number;
}

export interface GlobalImportResult {
  [model: string]: ImportResult;
}

export const backupApi = {
  /** Download full backup (.acbak) for all models */
  exportAll: (models?: string[]) =>
    client.get('/_backup/export', {
      params: models ? { models } : undefined,
      responseType: 'blob',
    }),

  /** Upload .acbak archive (global import) */
  importAll: (file: File, onDuplicate: OnDuplicate = 'overwrite') => {
    const form = new FormData();
    form.append('file', file);
    return client.post<GlobalImportResult>('/_backup/import', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      params: { on_duplicate: onDuplicate },
    });
  },
${perModel}
};
`;
  }

  private genBackupPage(): string {
    const resourceNames = this.resources.map((r) => `'${r.name}'`).join(', ');
    return `// Auto-generated by AutoCRUD Web Generator
import { createFileRoute } from '@tanstack/react-router';
import { BackupRestore } from '../../lib/components/BackupRestore';

export const Route = createFileRoute('/autocrud-admin/backup')({
  component: BackupPage,
});

function BackupPage() {
  return <BackupRestore resourceNames={[${resourceNames}]} />;
}
`;
  }

  // ── Schema Migration ──────────────────────────────────────────

  private genMigrateApiClient(): string {
    return `// Auto-generated by AutoCRUD Web Generator

/** Progress message for a single resource during migration. */
export interface MigrateProgress {
  resource_id: string;
  status: 'migrating' | 'success' | 'failed' | 'skipped';
  message?: string;
  error?: string;
  timestamp?: string;
}

/** Final summary after migration completes. */
export interface MigrateResult {
  total: number;
  success: number;
  failed: number;
  skipped: number;
  errors: Array<{ resource_id: string; error: string }>;
  timestamp?: string;
}

/**
 * Parse a JSONL streaming response and invoke callbacks for each message.
 *
 * Progress messages (containing \`resource_id\`) are forwarded to \`onProgress\`.
 * The final summary message (containing \`total\`) is returned as the resolved value.
 */
async function streamMigrate(
  url: string,
  onProgress?: (p: MigrateProgress) => void,
  signal?: AbortSignal,
): Promise<MigrateResult> {
  const response = await fetch(url, { method: 'POST', signal });
  if (!response.ok) {
    const text = await response.text().catch(() => response.statusText);
    throw new Error(\`HTTP \${response.status}: \${text}\`);
  }

  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let result: MigrateResult | null = null;

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\\n');
    buffer = lines.pop()!; // keep the potentially incomplete last line

    for (const line of lines) {
      if (!line.trim()) continue;
      try {
        const data = JSON.parse(line);
        if ('total' in data && 'success' in data) {
          result = data as MigrateResult;
        } else if (onProgress) {
          onProgress(data as MigrateProgress);
        }
      } catch {
        // skip malformed lines
      }
    }
  }

  // Process any remaining buffer
  if (buffer.trim()) {
    try {
      const data = JSON.parse(buffer);
      if ('total' in data && 'success' in data) {
        result = data as MigrateResult;
      } else if (onProgress) {
        onProgress(data as MigrateProgress);
      }
    } catch {
      // skip
    }
  }

  if (!result) {
    throw new Error('No migration result received from server');
  }
  return result;
}

/** Resolve the API base URL used by the Axios client. */
function getBaseUrl(): string {
  return import.meta.env.VITE_API_URL || '/api';
}

export const migrateApi = {
  /**
   * Test migration (dry run) for a model.
   * No data is written — safe to run on production.
   */
  test: (
    modelName: string,
    onProgress?: (p: MigrateProgress) => void,
    signal?: AbortSignal,
  ): Promise<MigrateResult> =>
    streamMigrate(\`\${getBaseUrl()}/\${modelName}/migrate/test\`, onProgress, signal),

  /**
   * Execute migration for a model.
   * Migrated data is written back to storage.
   */
  execute: (
    modelName: string,
    onProgress?: (p: MigrateProgress) => void,
    signal?: AbortSignal,
  ): Promise<MigrateResult> =>
    streamMigrate(\`\${getBaseUrl()}/\${modelName}/migrate/execute\`, onProgress, signal),
};
`;
  }

  private genMigratePage(): string {
    const resourceNames = this.resources.map((r) => `'${r.name}'`).join(', ');
    return `// Auto-generated by AutoCRUD Web Generator
import { createFileRoute } from '@tanstack/react-router';
import { MigrationStatus } from '../../lib/components/MigrationStatus';

export const Route = createFileRoute('/autocrud-admin/migrate')({
  component: MigratePage,
});

function MigratePage() {
  return <MigrationStatus resourceNames={[${resourceNames}]} />;
}
`;
  }

  // ── Root / Dashboard ──────────────────────────────────────────

  private genRootIndex(): string {
    return `// Auto-generated by AutoCRUD Web Generator
import { createFileRoute, Link } from '@tanstack/react-router';
import { Container, Title, Text, Button, Stack, Paper, Group } from '@mantine/core';
import { IconArrowRight, IconDatabase } from '@tabler/icons-react';

export const Route = createFileRoute('/')({
  component: HomePage,
});

function HomePage() {
  return (
    <Container size="sm" style={{ marginTop: '10vh' }}>
      <Stack gap="xl">
        <Paper shadow="md" p="xl" radius="md">
          <Stack gap="lg">
            <Group gap="xs">
              <IconDatabase size={32} />
              <Title order={1}>AutoCRUD Web</Title>
            </Group>

            <Text size="lg" c="dimmed">
              歡迎使用 AutoCRUD 自動化管理介面
            </Text>

            <Text>
              這是一個由 AutoCRUD 後端自動生成的 React 管理介面。 點擊下方按鈕進入管理控制台。
            </Text>

            <Button
              component={Link}
              to="/autocrud-admin"
              size="lg"
              rightSection={<IconArrowRight size={20} />}
            >
              進入管理控制台
            </Button>
          </Stack>
        </Paper>
      </Stack>
    </Container>
  );
}
`;
  }
  private genDashboard(): string {
    return `// Auto-generated by AutoCRUD Web Generator
import { createFileRoute } from '@tanstack/react-router';
import { Dashboard } from '../../autocrud/lib/components/Dashboard';

export const Route = createFileRoute('/autocrud-admin/')({
  component: Dashboard,
});
`;
  }

  private genListRoute(r: Resource): string {
    if (r.isJob) {
      return `// Auto-generated by AutoCRUD Web Generator
import { createFileRoute } from '@tanstack/react-router';
import { JobTable } from '../../../autocrud/lib/components/JobTable';
import { getResource } from '../../../autocrud/lib/resources';
import type { ${r.schemaName} } from '../../../autocrud/generated/types';

export const Route = createFileRoute('/autocrud-admin/${r.name}/')({
  component: ListPage,
});

function ListPage() {
  const config = getResource('${r.name}')!;
  return <JobTable<${r.schemaName}> config={config} basePath="/autocrud-admin/${r.name}" />;
}
`;
    }

    return `// Auto-generated by AutoCRUD Web Generator
import { createFileRoute } from '@tanstack/react-router';
import { ResourceTable } from '../../../autocrud/lib/components/ResourceTable';
import { getResource } from '../../../autocrud/lib/resources';
import type { ${r.schemaName} } from '../../../autocrud/generated/types';

export const Route = createFileRoute('/autocrud-admin/${r.name}/')({
  component: ListPage,
});

function ListPage() {
  const config = getResource('${r.name}')!;
  return <ResourceTable<${r.schemaName}> config={config} basePath="/autocrud-admin/${r.name}" />;
}
`;
  }

  private genCreateRoute(r: Resource): string {
    return `// Auto-generated by AutoCRUD Web Generator
import { createFileRoute } from '@tanstack/react-router';
import { ResourceCreate } from '../../../autocrud/lib/components/ResourceCreate';
import { getResource } from '../../../autocrud/lib/resources';
import type { ${r.schemaName} } from '../../../autocrud/generated/types';

export const Route = createFileRoute('/autocrud-admin/${r.name}/create')({
  component: CreatePage,
});

function CreatePage() {
  const config = getResource('${r.name}')!;
  return <ResourceCreate<${r.schemaName}> config={config} basePath="/autocrud-admin/${r.name}" />;
}
`;
  }

  private genDetailRoute(r: Resource): string {
    return `// Auto-generated by AutoCRUD Web Generator
import { createFileRoute, useNavigate } from '@tanstack/react-router';
import { ResourceDetail } from '../../../autocrud/lib/components/ResourceDetail';
import { getResource } from '../../../autocrud/lib/resources';
import type { ${r.schemaName} } from '../../../autocrud/generated/types';

type DetailSearch = { revision?: string };

export const Route = createFileRoute('/autocrud-admin/${r.name}/$resourceId')({
  component: DetailPage,
  validateSearch: (search: Record<string, unknown>): DetailSearch => ({
    revision: typeof search.revision === 'string' ? search.revision : undefined,
  }),
});

function DetailPage() {
  const { resourceId } = Route.useParams();
  const { revision } = Route.useSearch();
  const navigate = useNavigate({ from: '/autocrud-admin/${r.name}/$resourceId' });

  const config = getResource('${r.name}')!;

  const handleRevisionChange = (rev: string | null) => {
    navigate({
      search: { revision: rev ?? undefined },
      replace: true,
    });
  };

  return (
    <ResourceDetail<${r.schemaName}>
      config={config}
      resourceId={resourceId}
      basePath="/autocrud-admin/${r.name}"${r.isJob ? '\n      isJob={true}' : ''}
      initialRevision={revision}
      onRevisionChange={handleRevisionChange}
    />
  );
}
`;
  }

  private writeFile(filePath: string, content: string) {
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    fs.writeFileSync(filePath, content, 'utf-8');
    console.log(`  ✅ ${path.relative(this.ROOT, filePath)}`);
  }
}

// Helper functions
function toPascal(s: string) {
  return s
    .split(/[-_\s]+/)
    .map((w) => w[0].toUpperCase() + w.slice(1))
    .join('');
}

function toCamel(s: string) {
  const p = toPascal(s);
  return p[0].toLowerCase() + p.slice(1);
}

function toLabel(s: string) {
  return s
    .split(/[-_]+/)
    .map((w) => w[0].toUpperCase() + w.slice(1))
    .join(' ');
}

/** Extract the leaf segment from a dot-notation field name for use as label source */
function getLeafLabel(name: string): string {
  return name.includes('.') ? name.split('.').pop()! : name;
}

/** Escape special regex characters in a string */
function escapeRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/** Check if an anyOf/oneOf array contains $ref members (i.e. union type) */
function hasRefMembers(arr: any[] | undefined): boolean {
  return Array.isArray(arr) && arr.some((item: any) => item.$ref);
}

/** ISO 8601 datetime pattern */
const ISO_DATETIME_RE = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}/;

/**
 * Compute max available depth from field name paths.
 * Mirrors the frontend computeMaxAvailableDepth logic: the deepest
 * dot-separated field name determines the depth, and fields with
 * itemFields add an extra level.  Minimum is 1.
 */
function computeMaxFieldDepth(fields: Field[]): number {
  let max = 1;
  for (const f of fields) {
    const d = f.name.split('.').length;
    if (d > max) max = d;
    if (f.itemFields && f.itemFields.length > 0 && d + 1 > max) max = d + 1;
  }
  return max;
}

/**
 * Heuristic: detect if a string field is actually a datetime
 * even when OpenAPI spec doesn't have format: "date-time".
 * Only checks default/example values for ISO datetime format.
 */
function looksLikeDatetime(_name: string, prop: any): boolean {
  if (typeof prop.default === 'string' && ISO_DATETIME_RE.test(prop.default)) return true;
  if (typeof prop.example === 'string' && ISO_DATETIME_RE.test(prop.example)) return true;
  return false;
}

// Type definitions
interface Resource {
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

/**
 * Custom create action discovered from x-autocrud-custom-create-actions.
 * Each action represents an alternative POST endpoint for creating a resource.
 */
interface CustomCreateAction {
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
}

interface FieldRef {
  resource: string;
  type: 'resource_id' | 'revision_id';
  onDelete?: string;
}

interface UnionVariant {
  tag: string;
  label: string;
  schemaName?: string; // For discriminated unions: schema name
  fields?: Field[]; // For discriminated unions: sub-fields of this variant
  type?: string; // For simple unions: primitive type ('string', 'number', 'boolean')
  isArray?: boolean; // For structural unions: variant is an array of items
  itemUnionMeta?: UnionMeta; // For structural unions: array items are a discriminated union
  isDict?: boolean; // For structural unions: variant is a dict/map
  dictValueFields?: Field[]; // For structural union dict variants: value schema fields
}

interface UnionMeta {
  discriminatorField: string; // The tag field name (e.g. 'type', 'kind')
  variants: UnionVariant[];
}

interface Field {
  name: string;
  label: string;
  type: string;
  tsType: string;
  isArray: boolean;
  isRequired: boolean;
  isNullable: boolean;
  enumValues?: string[];
  zodType?: string; // Zod validation type
  itemFields?: Field[]; // For arrays of typed objects: the item's sub-fields
  ref?: FieldRef; // Reference to another resource
  unionMeta?: UnionMeta; // For union fields: discriminator + variant info
  isUnique?: boolean; // Field has a unique constraint (from x-unique OpenAPI extension)
  constValue?: string; // Field has a const value (from tagged struct discriminator)
}

/**
 * Recursively serialize a Field into a plain object for JSON output.
 *
 * This is the SINGLE source of truth for field serialization — used for
 * top-level fields, itemFields sub-fields, and union variant sub-fields.
 * All metadata (ref, isUnique, itemFields, unionMeta, enumValues) is preserved
 * at every nesting level so the UI pipeline treats them identically.
 */
function serializeField(f: Field): any {
  const out: any = {
    name: f.name,
    label: f.label,
    type: f.type,
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

/**
 * Build nested z.object() structure from dot-notation field names.
 * e.g. fields with names ['payload.event_type', 'payload.extra_data', 'status']
 * become:
 *   payload: z.object({
 *       event_type: z.enum([...]),
 *       extra_data: z.record(z.string(), z.any()),
 *   }),
 *   status: z.enum([...]).optional(),
 */
function buildNestedZodFields(fields: Field[], indent: string = '    '): string {
  const topLevel: { name: string; zodType: string }[] = [];
  const nested: Record<string, Field[]> = {};

  for (const field of fields) {
    if (!field.zodType) continue;
    const dotIdx = field.name.indexOf('.');
    if (dotIdx === -1) {
      topLevel.push({ name: field.name, zodType: field.zodType });
    } else {
      const prefix = field.name.substring(0, dotIdx);
      const rest = field.name.substring(dotIdx + 1);
      if (!nested[prefix]) nested[prefix] = [];
      nested[prefix].push({ ...field, name: rest });
    }
  }

  const lines: string[] = [];

  // Nested groups first (e.g. payload: z.object({...}))
  for (const [prefix, subFields] of Object.entries(nested)) {
    const inner = buildNestedZodFields(subFields, indent + '    ');
    lines.push(`${indent}${prefix}: z.object({\n${inner}\n${indent}})`);
  }

  // Top-level scalar fields
  for (const f of topLevel) {
    lines.push(`${indent}${f.name}: ${f.zodType}`);
  }

  return lines.join(',\n');
}
