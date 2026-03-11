/**
 * Compute TypeScript type strings from semantic IR Fields.
 *
 * This module is the SINGLE source of truth for tsType generation.
 * genTypes() uses computeTsType() to produce interface property types.
 */

import type { Field } from '../types.js';
import { sanitizeTsName } from '../types.js';

/**
 * Compute the TypeScript type string for a given Field.
 *
 * Maps the semantic IR to a TS type expression, handling:
 * - enums (enumSchemaName or literal union)
 * - const literals
 * - arrays
 * - nested arrays (nestedArrayInner)
 * - unions (discriminated, simple, structural)
 * - binary
 * - nullable / optional
 */
export function computeTsType(f: Field): string {
  // Const value → literal type
  if (f.constValue !== undefined && !f.enumValues) {
    let tsType = `'${f.constValue}'`;
    tsType = applyNullableOptionalTs(tsType, f.isNullable, f.isRequired);
    return tsType;
  }

  // Nested array (list[list[...]])
  if (f.nestedArrayInner) {
    let tsType = `${computeTsType(f.nestedArrayInner)}[]`;
    tsType = applyNullableOptionalTs(tsType, f.isNullable, f.isRequired);
    return tsType;
  }

  // Union field with unionMeta
  if (f.unionMeta) {
    return computeUnionTsType(f);
  }

  let tsType: string;

  switch (f.type) {
    case 'binary':
      tsType = 'Binary';
      break;
    case 'file':
      tsType = 'File';
      break;
    case 'date':
      tsType = 'string';
      break;
    case 'integer':
    case 'number':
      tsType = 'number';
      break;
    case 'boolean':
      tsType = 'boolean';
      break;
    case 'object':
      tsType = 'Record<string, any>';
      break;
    case 'string':
      if (f.enumValues) {
        if (f.enumValues.length === 1 && f.constValue !== undefined) {
          tsType = `'${f.constValue}'`;
        } else {
          tsType = f.enumSchemaName ?? 'string';
        }
      } else {
        tsType = 'string';
      }
      break;
    default:
      tsType = 'any';
  }

  if (f.isArray) {
    tsType += '[]';
  }

  tsType = applyNullableOptionalTs(tsType, f.isNullable, f.isRequired);
  return tsType;
}

/**
 * Compute tsType for a union field (discriminated, simple, or structural).
 */
function computeUnionTsType(f: Field): string {
  const meta = f.unionMeta!;
  const variantTypes: string[] = [];

  for (const v of meta.variants) {
    if (v.schemaName) {
      variantTypes.push(v.schemaName);
    } else if (v.type) {
      variantTypes.push(v.type === 'integer' ? 'number' : v.type);
    } else if (v.isArray) {
      // Array variant in structural union
      if (v.itemUnionMeta) {
        const innerNames = v.itemUnionMeta.variants.map((iv) => iv.schemaName).filter(Boolean);
        variantTypes.push(`(${innerNames.join(' | ')})[]`);
      } else {
        variantTypes.push(`${v.schemaName ?? 'Array'}[]`);
      }
    } else if (v.isDict) {
      const valueName = v.dictValueFields && v.dictValueFields.length > 0 ? 'any' : 'Any';
      // Reconstruct dict label → Record<string, X>
      const labelMatch = v.label.match(/Dict\[str, (\w+)\]/);
      if (labelMatch) {
        variantTypes.push(`Record<string, ${labelMatch[1]}>`);
      } else {
        variantTypes.push(`Record<string, ${valueName}>`);
      }
    } else {
      variantTypes.push('any');
    }
  }

  let tsType = variantTypes.join(' | ');

  if (f.isArray) {
    tsType = `(${tsType})[]`;
  }

  tsType = applyNullableOptionalTs(tsType, f.isNullable, f.isRequired);
  return tsType;
}

function applyNullableOptionalTs(tsType: string, isNullable: boolean, isRequired: boolean): string {
  if (isNullable) {
    tsType += ' | null';
  }
  return tsType;
}

// ─── genTypes: generate the types.ts file content ────────────────────────────

/**
 * Generate TypeScript type definitions (enums, interfaces, union aliases)
 * from the OpenAPI components schemas AND the parsed resources.
 *
 * @param spec - The raw OpenAPI spec (for components.schemas)
 * @param resources - Parsed IR resources
 * @param parseFieldFn - A function to parse a single field from an OpenAPI property
 */
export function genTypes(
  spec: any,
  resources: import('../types.js').Resource[],
  parseFieldFn: (name: string, prop: any, isRequired: boolean) => Field | null,
): string {
  const enums: string[] = [];
  const interfaces: string[] = [];
  const SKIP = new Set(['ResourceMeta', 'RevisionInfo', 'RevisionStatus', 'RevisionListResponse']);

  for (const [name, schema] of Object.entries<any>(spec.components.schemas)) {
    if (SKIP.has(name)) continue;

    if (schema.enum) {
      const values = schema.enum.map((v: string) => `  "${v}" = "${v}"`).join(',\n');
      enums.push(`export enum ${name} {\n${values}\n}`);
    } else if (schema.properties) {
      const props = Object.entries<any>(schema.properties)
        .map(([k, v]) => {
          const field = parseFieldFn(k, v, schema.required?.includes(k) ?? false);
          if (!field) return '';
          const tsType = computeTsType(field);
          const optional = field.isRequired ? '' : '?';
          return `  ${k}${optional}: ${tsType};`;
        })
        .filter(Boolean)
        .join('\n');
      interfaces.push(`export interface ${name} {\n${props}\n}`);
    }
  }

  const unionAliases: string[] = [];
  for (const r of resources) {
    if (r.isUnion && r.unionVariantSchemaNames && r.unionVariantSchemaNames.length > 0) {
      unionAliases.push(`export type ${r.schemaName} = ${r.unionVariantSchemaNames.join(' | ')};`);
    }
  }

  const parts = [enums.join('\n\n'), interfaces.join('\n\n'), unionAliases.join('\n\n')].filter(Boolean);
  return `// Auto-generated by AutoCRUD Web Generator\n\n${parts.join('\n\n')}\n`;
}
