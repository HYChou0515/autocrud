/**
 * Generate the resources.ts registry file.
 *
 * Zod schemas strategy:
 * - If Orval generated a Zod schema for the resource → import from Orval output
 * - If the resource has dot-notation fields or Orval schema unavailable → generate inline (fallback)
 */

import type { Resource, Field } from '../types.js';
import { toCamel, serializeField } from '../types.js';

// ─── Zod Type Helpers (fallback — moved from deleted zod-type.ts) ───────────

function applyNullableOptionalZod(zodType: string, isNullable: boolean, isRequired: boolean): string {
  if (isNullable && !isRequired) {
    zodType = `${zodType}.nullable().optional()`;
  } else if (isNullable) {
    zodType = `${zodType}.nullable()`;
  } else if (!isRequired) {
    zodType = `${zodType}.optional()`;
  }
  return zodType;
}

/**
 * Compute the Zod validation expression string for a given Field.
 */
export function computeZodType(f: Field): string {
  if (f.constValue !== undefined && !f.enumValues) {
    const zodType = `z.literal('${f.constValue}')`;
    return applyNullableOptionalZod(zodType, f.isNullable, f.isRequired);
  }
  if (f.enumValues && f.enumValues.length === 1 && f.constValue !== undefined) {
    const zodType = `z.literal('${f.constValue}')`;
    return applyNullableOptionalZod(zodType, f.isNullable, f.isRequired);
  }
  if (f.nestedArrayInner) {
    const zodType = `z.array(${computeZodType(f.nestedArrayInner)})`;
    return applyNullableOptionalZod(zodType, f.isNullable, f.isRequired);
  }
  if (f.unionMeta) {
    return computeUnionZodType(f);
  }

  let zodType: string;
  switch (f.type) {
    case 'binary':
      zodType = 'z.any()';
      break;
    case 'file':
      zodType = f.isRequired ? 'z.instanceof(File)' : 'z.instanceof(File).optional()';
      if (f.isArray) zodType = `z.array(${zodType})`;
      return zodType;
    case 'date':
      zodType = 'z.union([z.string(), z.date()])';
      break;
    case 'integer':
      zodType = 'z.number().int()';
      break;
    case 'number':
      zodType = 'z.number()';
      break;
    case 'boolean':
      zodType = 'z.boolean()';
      break;
    case 'object':
      zodType = 'z.record(z.string(), z.any())';
      break;
    case 'string':
      if (f.enumValues) {
        const enumLiterals = f.enumValues.map((v) => `"${v}"`).join(', ');
        zodType = `z.enum([${enumLiterals}])`;
      } else {
        zodType = 'z.string()';
      }
      break;
    default:
      zodType = 'z.any()';
  }

  if (f.isArray && f.itemFields && f.itemFields.length > 0) {
    const innerIndent = '        ';
    const itemZodLines = f.itemFields.map((sf) => `${innerIndent}${sf.name}: ${computeZodType(sf)}`).join(',\n');
    zodType = `z.object({\n${itemZodLines}\n    })`;
  }
  if (f.isArray) zodType = `z.array(${zodType})`;
  return applyNullableOptionalZod(zodType, f.isNullable, f.isRequired);
}

function computeUnionZodType(f: Field): string {
  const meta = f.unionMeta!;
  let zodType: string;

  if (meta.discriminatorField === '__type') {
    const zodVariants = meta.variants.map((v) => {
      if (v.type === 'string') return 'z.string()';
      if (v.type === 'integer' || v.type === 'number') return v.type === 'integer' ? 'z.number().int()' : 'z.number()';
      if (v.type === 'boolean') return 'z.boolean()';
      return 'z.any()';
    });
    zodType = `z.union([${zodVariants.join(', ')}])`;
  } else if (meta.discriminatorField === '__variant') {
    zodType = 'z.any()';
  } else {
    const zodVariants = meta.variants.map((v) => {
      const zodFields = v.fields?.map((sf) => `${sf.name}: ${computeZodType(sf)}`).join(', ') || '';
      return `z.object({ ${meta.discriminatorField}: z.literal('${v.tag}'), ${zodFields} })`;
    });
    zodType = `z.discriminatedUnion('${meta.discriminatorField}', [${zodVariants.join(', ')}])`;
  }

  if (f.isArray) zodType = `z.array(${zodType})`;
  return applyNullableOptionalZod(zodType, f.isNullable, f.isRequired);
}

/**
 * Build nested z.object() structure from dot-notation field names.
 *
 * e.g. fields with names ['payload.event_type', 'payload.extra_data', 'status']
 * become:
 *   payload: z.object({
 *       event_type: z.enum([...]),
 *       extra_data: z.record(z.string(), z.any()),
 *   }),
 *   status: z.enum([...]).optional(),
 */
export function buildNestedZodFields(fields: Field[], indent: string = '    '): string {
  const topLevel: { name: string; zodType: string }[] = [];
  const nested: Record<string, Field[]> = {};

  for (const field of fields) {
    const zodType = computeZodType(field);
    const dotIdx = field.name.indexOf('.');
    if (dotIdx === -1) {
      topLevel.push({ name: field.name, zodType });
    } else {
      const prefix = field.name.substring(0, dotIdx);
      const rest = field.name.substring(dotIdx + 1);
      if (!nested[prefix]) nested[prefix] = [];
      nested[prefix].push({ ...field, name: rest });
    }
  }

  const lines: string[] = [];
  for (const [prefix, subFields] of Object.entries(nested)) {
    const inner = buildNestedZodFields(subFields, indent + '    ');
    lines.push(`${indent}${prefix}: z.object({\n${inner}\n${indent}})`);
  }
  for (const f of topLevel) {
    lines.push(`${indent}${f.name}: ${f.zodType}`);
  }
  return lines.join(',\n');
}

// ─── Helpers ────────────────────────────────────────────────────────────────

/** Check if any field uses dot-notation (indicating nested object flattening). */
function hasDotNotationFields(fields: Field[]): boolean {
  return fields.some((f) => f.name.includes('.'));
}

/**
 * Build the zodSchema expression for a resource.
 *
 * Uses Orval-imported schema when available and the resource has no dot-notation fields.
 * Falls back to custom inline z.object({...}) otherwise.
 */
function buildZodSchemaExpr(r: Resource, orvalSchemas?: Map<string, string>): string {
  const orvalExport = orvalSchemas?.get(r.schemaName);
  if (orvalExport && !hasDotNotationFields(r.fields)) {
    return orvalExport;
  }
  // Fallback: inline z.object
  const zodFields = buildNestedZodFields(r.fields);
  return `z.object({\n${zodFields}\n    })`;
}

// ─── Main Generation ────────────────────────────────────────────────────────

/**
 * Generate the resources config registry code.
 *
 * @param resources - Parsed IR resources
 * @param basePath - API base path
 * @param spec - Raw OpenAPI spec (for x-autocrud-async-create-jobs)
 * @param getJobHiddenFields - Function to get job hidden fields for a resource
 * @param orvalSchemas - Map of PascalCase schema name → Orval Zod export name (optional)
 */
export function genResourcesConfig(
  resources: Resource[],
  basePath: string,
  spec: any,
  getJobHiddenFields: (r: Resource) => string[],
  orvalSchemas?: Map<string, string>,
): string {
  // Determine which Orval schemas are actually used
  const usedOrvalImports: string[] = [];
  if (orvalSchemas) {
    for (const r of resources) {
      const orvalExport = orvalSchemas.get(r.schemaName);
      if (orvalExport && !hasDotNotationFields(r.fields)) {
        usedOrvalImports.push(orvalExport);
      }
    }
  }

  const configs = resources.map((r) => {
    const fields = r.fields.map((f) => serializeField(f));
    const zodSchemaExpr = buildZodSchemaExpr(r, orvalSchemas);
    const displayNameLine = r.displayNameField ? `    displayNameField: '${r.displayNameField}',\n` : '';

    let customActionsBlock = '';
    if (r.customCreateActions && r.customCreateActions.length > 0) {
      const actionEntries = r.customCreateActions.map((action) => {
        const actionFields = action.fields.map((f) => serializeField(f));
        const actionZodFields = buildNestedZodFields(action.fields);
        const methodName = toCamel(action.operationId);
        const asyncLines: string[] = [];
        if (action.asyncMode) {
          asyncLines.push(`        asyncMode: '${action.asyncMode}',`);
        }
        if (action.jobResourceName) {
          asyncLines.push(`        jobResourceName: '${action.jobResourceName}',`);
        }
        const asyncBlock = asyncLines.length > 0 ? '\n' + asyncLines.join('\n') : '';
        return `      {
        name: '${action.name}',
        label: '${action.label}',
        fields: ${JSON.stringify(actionFields, null, 10).replace(/"([^"]+)":/g, '$1:')},
        zodSchema: z.object({
${actionZodFields}
        }),
        apiMethod: ${r.camel}Api.${methodName},${asyncBlock}
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
    zodSchema: ${zodSchemaExpr},
    apiClient: ${r.camel}Api,
    maxFormDepth: ${r.maxFormDepth},${
      r.isJob
        ? `
    defaultHiddenFields: ${JSON.stringify(getJobHiddenFields(r))},`
        : ''
    }${
      r.isUnion
        ? `
    isUnion: true,`
        : ''
    }${customActionsBlock}
  }`;
  });

  const imports = resources.map((r) => `import { ${r.camel}Api } from './api/${r.name}Api';`).join('\n');

  // Import Orval Zod schemas if any are used
  const orvalImportLine =
    usedOrvalImports.length > 0 ? `import { ${usedOrvalImports.join(', ')} } from './types';\n` : '';

  const resourceNameUnion = resources.map((r) => `'${r.name}'`).join(' | ');
  const detailRouteUnion = resources.map((r) => `'/autocrud-admin/${r.name}/$resourceId'`).join('\n  | ');
  const listRouteUnion = resources.map((r) => `'/autocrud-admin/${r.name}'`).join('\n  | ');
  const detailRouteCases = resources.map((r) => `  '${r.name}': '/autocrud-admin/${r.name}/$resourceId'`).join(',\n');
  const listRouteCases = resources.map((r) => `  '${r.name}': '/autocrud-admin/${r.name}'`).join(',\n');

  const fieldNameTypes = resources
    .map((r) => {
      const fieldNames = r.fields.map((f) => `'${f.name}'`).join(' | ');
      return `export type ${r.pascal}FieldName = ${fieldNames};`;
    })
    .join('\n');

  const fieldMapEntries = resources.map((r) => `  '${r.name}': ${r.pascal}FieldName;`).join('\n');

  const asyncJobsMap: Record<string, string> = spec['x-autocrud-async-create-jobs'] ?? {};
  let asyncJobsBlock = '';
  if (Object.keys(asyncJobsMap).length > 0) {
    const entries = Object.entries(asyncJobsMap)
      .map(([jobName, parentName]) => `  '${jobName}': '${parentName}'`)
      .join(',\n');
    asyncJobsBlock = `
import { asyncCreateJobs } from '../lib/resources';
Object.assign(asyncCreateJobs, {
${entries},
});
`;
  }

  return `// Auto-generated by AutoCRUD Web Generator
import { resources as registry, applyCustomizations as applyCustomizationsImpl } from '../lib/resources';
import type { ResourceCustomizations as ResourceCustomizationsBase } from '../lib/resources';
import { setApiBasePath } from '../lib/client';
import { z } from 'zod';
${orvalImportLine}${imports}

// Inject API base path so blob URLs and other non-Axios URL constructions
// include the correct prefix (e.g. '/v1/autocrud/blobs/upload').
setApiBasePath('${basePath}');

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
${asyncJobsBlock}
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
