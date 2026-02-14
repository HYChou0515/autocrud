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

export async function generateCode(apiUrl: string, outputRoot: string): Promise<void> {
  const ROOT = process.cwd();
  const SRC = path.join(ROOT, outputRoot);
  const GEN = path.join(SRC, 'generated');
  const ROUTES = path.join(SRC, 'routes');

  console.log('🚀 AutoCRUD Web Code Generator');
  console.log(`📡 Fetching OpenAPI spec from ${apiUrl}/openapi.json...\n`);

  const resp = await fetch(`${apiUrl}/openapi.json`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}: ${resp.statusText}`);

  const spec: any = await resp.json();
  console.log(`✅ ${spec.info.title} v${spec.info.version}`);

  const generator = new Generator(spec, ROOT, SRC, GEN, ROUTES);
  await generator.run();
}

class Generator {
  private spec: any;
  private ROOT: string;
  private SRC: string;
  private GEN: string;
  private ROUTES: string;
  private resources: Resource[] = [];

  constructor(spec: any, root: string, src: string, gen: string, routes: string) {
    this.spec = spec;
    this.ROOT = root;
    this.SRC = src;
    this.GEN = gen;
    this.ROUTES = routes;
  }

  async run() {
    this.extractResources();
    console.log(`📦 Resources: ${this.resources.map((r) => r.name).join(', ')}\n`);
    console.log('📝 Generating files...');

    this.writeFile(path.join(this.GEN, 'types.ts'), this.genTypes());
    this.writeFile(path.join(this.GEN, 'resources.ts'), this.genResourcesConfig());

    for (const r of this.resources) {
      this.writeFile(path.join(this.GEN, 'api', `${r.name}Api.ts`), this.genApiClient(r));
    }
    this.writeFile(path.join(this.GEN, 'api', 'index.ts'), this.genApiIndex());

    this.writeFile(path.join(this.ROUTES, 'index.tsx'), this.genRootIndex());
    this.writeFile(path.join(this.ROUTES, 'autocrud-admin', 'index.tsx'), this.genDashboard());

    for (const r of this.resources) {
      this.writeFile(path.join(this.ROUTES, 'autocrud-admin', r.name, 'index.tsx'), this.genListRoute(r));
      this.writeFile(path.join(this.ROUTES, 'autocrud-admin', r.name, 'create.tsx'), this.genCreateRoute(r));
      this.writeFile(path.join(this.ROUTES, 'autocrud-admin', r.name, '$resourceId.tsx'), this.genDetailRoute(r));
    }

    const fileCount = 5 + this.resources.length * 4;
    console.log(`\n✨ Done! Generated ${fileCount} files.`);
    console.log('\nNext steps:');
    console.log('  pnpm dev');
  }

  private extractResources() {
    const resourcePaths = new Map<string, string>();

    for (const [path, methods] of Object.entries<any>(this.spec.paths)) {
      if (!methods.post) continue;
      const match = path.match(/^\/([^/]+)$/);
      if (!match) continue;

      const resourceName = match[1];
      const schema = methods.post.requestBody?.content?.['application/json']?.schema?.$ref;
      if (schema) {
        resourcePaths.set(resourceName, schema.split('/').pop()!);
      }
    }

    const SYSTEM_SCHEMAS = new Set(['ResourceMeta', 'RevisionInfo', 'RevisionStatus', 'RevisionListResponse']);

    for (const [name, schemaName] of resourcePaths) {
      if (SYSTEM_SCHEMAS.has(schemaName)) continue;

      const schema = this.spec.components.schemas[schemaName];
      if (!schema?.properties) continue;

      const isJob = this.detectJobSchema(schema);
      const maxFormDepth = isJob ? 3 : 2;

      this.resources.push({
        name,
        label: toLabel(name),
        pascal: toPascal(name),
        camel: toCamel(name),
        schemaName,
        fields: this.extractFields(schema, '', 1, 10),
        isJob,
        maxFormDepth,
      });
    }
  }

  private detectJobSchema(schema: any): boolean {
    // Detect if this schema is a Job type by checking for Job-specific fields
    const props = schema.properties ?? {};
    const jobFields = [
      'status',
      'errmsg',
      'retries',
      'periodic_interval_seconds',
      'periodic_max_runs',
      'periodic_runs',
      'periodic_initial_delay_seconds',
    ];

    // A schema is considered a Job if it has most of the Job-specific fields
    const matchedFields = jobFields.filter((field) => field in props);

    // Require at least 3 of the Job-specific fields to be present
    return matchedFields.length >= 3;
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
   * Detect if a resolved schema represents a Binary type.
   * Binary has a `data` property with contentEncoding: "base64".
   */
  private isBinarySchema(schema: any): boolean {
    if (schema?.type !== 'object' || !schema?.properties) return false;
    const dataProp = schema.properties.data;
    return dataProp?.contentEncoding === 'base64';
  }

  private parseField(name: string, prop: any, isRequired: boolean): Field | null {
    let type = prop.type;
    let isArray = false;
    let isNullable = false;
    let enumValues: string[] | undefined;
    let tsType = 'string';
    let zodType = 'z.string()';

    // Handle $ref references
    if (prop.$ref) {
      const refSchema = this.resolveRef(prop.$ref);
      if (refSchema) {
        prop = refSchema;
        type = prop.type;
      }
    }

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
          const refSchema = this.resolveRef(prop.$ref);
          if (refSchema) {
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
      const labelSource = name.includes('.') ? name.split('.').pop()! : name;
      return {
        name,
        label: toLabel(labelSource),
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
      itemFields = [];
      const itemRequired = new Set(prop.required ?? []);
      for (const [subName, subProp] of Object.entries<any>(prop.properties)) {
        const subField = this.parseField(subName, subProp, itemRequired.has(subName));
        if (subField) itemFields.push(subField);
      }
      // Build proper z.object for array items (will be wrapped by z.array below)
      const innerIndent = '        ';
      const itemZodLines = itemFields.map((f) => `${innerIndent}${f.name}: ${f.zodType}`).join(',\n');
      zodType = `z.object({\n${itemZodLines}\n    })`;
      tsType = 'object';
    } else if (prop.enum) {
      enumValues = prop.enum;
      tsType = 'string';
      const enumLiterals = enumValues!.map((v) => `"${v}"`).join(', ');
      zodType = `z.enum([${enumLiterals}])`;
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
    }

    if (isArray) {
      tsType += '[]';
      zodType = `z.array(${zodType})`;
    }

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

    // For nested fields like 'payload.event_type', use only the leaf part for labels
    const labelSource = name.includes('.') ? name.split('.').pop()! : name;

    return {
      name,
      label: toLabel(labelSource),
      type: type === 'integer' ? 'number' : type,
      tsType,
      isArray,
      isRequired,
      isNullable,
      enumValues,
      zodType,
      ...(itemFields ? { itemFields } : {}),
      ...(ref ? { ref } : {}),
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

    return `// Auto-generated by AutoCRUD Web Generator\n\n${enums.join('\n\n')}\n\n${interfaces.join('\n\n')}\n`;
  }

  private genResourcesConfig(): string {
    const configs = this.resources.map((r) => {
      const fields = r.fields.map((f) => {
        const fieldConfig: any = {
          name: f.name,
          label: f.label,
          type: f.type,
          isArray: f.isArray,
          isRequired: f.isRequired,
          isNullable: f.isNullable,
        };
        // Include enum values if present
        if (f.enumValues && f.enumValues.length > 0) {
          fieldConfig.enumValues = f.enumValues;
        }
        // Include item sub-fields for array of typed objects
        if (f.itemFields && f.itemFields.length > 0) {
          fieldConfig.itemFields = f.itemFields.map((sf: Field) => {
            const subConfig: any = {
              name: sf.name,
              label: sf.label,
              type: sf.type,
              isArray: sf.isArray,
              isRequired: sf.isRequired,
              isNullable: sf.isNullable,
            };
            if (sf.enumValues && sf.enumValues.length > 0) {
              subConfig.enumValues = sf.enumValues;
            }
            return subConfig;
          });
        }
        // Include ref metadata for resource references
        if (f.ref) {
          fieldConfig.ref = f.ref;
        }
        return fieldConfig;
      });

      // Generate Zod schema with nested structure for dot-notation fields
      const zodFields = buildNestedZodFields(r.fields);

      return `  '${r.name}': {
    name: '${r.name}',
    label: '${r.label}',
    pluralLabel: '${r.label}s',
    schema: '${r.schemaName}',
    fields: ${JSON.stringify(fields, null, 6).replace(/"([^"]+)":/g, '$1:')},
    zodSchema: z.object({
${zodFields}
    }),
    apiClient: ${r.camel}Api,
    isJob: ${r.isJob},
    maxFormDepth: ${r.maxFormDepth},
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
    const fieldNameTypes = this.resources.map((r) => {
      const fieldNames = r.fields.map((f) => `'${f.name}'`).join(' | ');
      return `export type ${r.pascal}FieldName = ${fieldNames};`;
    }).join('\n');

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
    return `// Auto-generated by AutoCRUD Web Generator
import { client } from '../../lib/client';
import type { ${r.schemaName} } from '../types';
import type { ResourceMeta, RevisionInfo, FullResource, RevisionListResponse, SearchParams } from '../../types/api';

const BASE = '/${r.name}';

export const ${r.camel}Api = {
  create: (data: ${r.schemaName}) =>
    client.post<RevisionInfo>(BASE, data),

  listFull: (params?: SearchParams & { returns?: string }) =>
    client.get<FullResource<${r.schemaName}>[]>(\`\${BASE}/full\`, { params }),

  count: (params?: SearchParams) =>
    client.get<number>(\`\${BASE}/count\`, { params }),

  getFull: (id: string, params?: { revision_id?: string; partial?: string[]; returns?: string }) =>
    client.get<FullResource<${r.schemaName}>>(\`\${BASE}/\${id}/full\`, { params }),

  update: (id: string, data: ${r.schemaName}, params?: { change_status?: string; mode?: string }) =>
    client.put<RevisionInfo>(\`\${BASE}/\${id}\`, data, { params }),

  delete: (id: string) =>
    client.delete<ResourceMeta>(\`\${BASE}/\${id}\`),

  restore: (id: string) =>
    client.post<ResourceMeta>(\`\${BASE}/\${id}/restore\`),

  revisionList: (id: string) =>
    client.get<RevisionListResponse>(\`\${BASE}/\${id}/revision-list\`),
};
`;
  }

  private genApiIndex(): string {
    const exports = this.resources.map((r) => `export { ${r.camel}Api } from './${r.name}Api';`).join('\n');
    return `// Auto-generated by AutoCRUD Web Generator\n${exports}\n`;
  }
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
              這是一個由 AutoCRUD 後端自動生成的 React 管理介面。
              點擊下方按鈕進入管理控制台。
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
import { Dashboard } from '../../lib/components/Dashboard';

export const Route = createFileRoute('/autocrud-admin/')({
  component: Dashboard,
});
`;
  }

  private genListRoute(r: Resource): string {
    if (r.isJob) {
      return `// Auto-generated by AutoCRUD Web Generator
import { createFileRoute } from '@tanstack/react-router';
import { JobTable } from '../../../lib/components/JobTable';
import { getResource } from '../../../lib/resources';
import type { ${r.schemaName} } from '../../../generated/types';

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
import { ResourceTable } from '../../../lib/components/ResourceTable';
import { getResource } from '../../../lib/resources';
import type { ${r.schemaName} } from '../../../generated/types';

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
    if (r.isJob) {
      return `// Auto-generated by AutoCRUD Web Generator
import { createFileRoute } from '@tanstack/react-router';
import { JobEnqueue } from '../../../lib/components/JobEnqueue';
import { getResource } from '../../../lib/resources';
import type { ${r.schemaName} } from '../../../generated/types';

export const Route = createFileRoute('/autocrud-admin/${r.name}/create')({
  component: CreatePage,
});

function CreatePage() {
  const config = getResource('${r.name}')!;
  return <JobEnqueue<${r.schemaName}> config={config} basePath="/autocrud-admin/${r.name}" />;
}
`;
    }

    return `// Auto-generated by AutoCRUD Web Generator
import { createFileRoute } from '@tanstack/react-router';
import { ResourceCreate } from '../../../lib/components/ResourceCreate';
import { getResource } from '../../../lib/resources';
import type { ${r.schemaName} } from '../../../generated/types';

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
import { ResourceDetail } from '../../../lib/components/ResourceDetail';
import { getResource } from '../../../lib/resources';
import type { ${r.schemaName} } from '../../../generated/types';

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

/** ISO 8601 datetime pattern */
const ISO_DATETIME_RE = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}/;

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
  fields: Field[];
  isJob: boolean;
  maxFormDepth: number;
}

interface FieldRef {
  resource: string;
  type: 'resource_id' | 'revision_id';
  onDelete?: string;
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
