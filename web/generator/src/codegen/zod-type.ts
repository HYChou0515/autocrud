/**
 * Compute Zod validation type strings from semantic IR Fields.
 *
 * This module is the SINGLE source of truth for zodType generation.
 * genResourcesConfig() uses computeZodType() to produce runtime validation schemas.
 */

import type { Field } from '../types.js';

/**
 * Compute the Zod validation expression string for a given Field.
 *
 * Maps the semantic IR to a Zod expression, handling:
 * - const/literal values
 * - enums
 * - arrays (simple and nested)
 * - typed object arrays (itemFields → z.object)
 * - unions (discriminated, simple, structural)
 * - binary, file, date, object
 * - nullable / optional modifiers
 */
export function computeZodType(f: Field): string {
  // Const value → z.literal
  if (f.constValue !== undefined && !f.enumValues) {
    let zodType = `z.literal('${f.constValue}')`;
    zodType = applyNullableOptionalZod(zodType, f.isNullable, f.isRequired);
    return zodType;
  }

  // Single-element enum → const/literal
  if (f.enumValues && f.enumValues.length === 1 && f.constValue !== undefined) {
    let zodType = `z.literal('${f.constValue}')`;
    zodType = applyNullableOptionalZod(zodType, f.isNullable, f.isRequired);
    return zodType;
  }

  // Nested array (list[list[...]])
  if (f.nestedArrayInner) {
    let zodType = `z.array(${computeZodType(f.nestedArrayInner)})`;
    zodType = applyNullableOptionalZod(zodType, f.isNullable, f.isRequired);
    return zodType;
  }

  // Union field
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
      // file handles its own optional — return early
      if (f.isArray) {
        zodType = `z.array(${zodType})`;
      }
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

  // Array of typed objects: build z.object from itemFields
  if (f.isArray && f.itemFields && f.itemFields.length > 0) {
    const innerIndent = '        ';
    const itemZodLines = f.itemFields.map((sf) => `${innerIndent}${sf.name}: ${computeZodType(sf)}`).join(',\n');
    zodType = `z.object({\n${itemZodLines}\n    })`;
  }

  if (f.isArray) {
    zodType = `z.array(${zodType})`;
  }

  zodType = applyNullableOptionalZod(zodType, f.isNullable, f.isRequired);
  return zodType;
}

/**
 * Compute Zod type for union fields (discriminated, simple, structural).
 */
function computeUnionZodType(f: Field): string {
  const meta = f.unionMeta!;
  let zodType: string;

  if (meta.discriminatorField === '__type') {
    // Simple union — z.union of primitives
    const zodVariants = meta.variants.map((v) => {
      if (v.type === 'string') return 'z.string()';
      if (v.type === 'integer' || v.type === 'number') return v.type === 'integer' ? 'z.number().int()' : 'z.number()';
      if (v.type === 'boolean') return 'z.boolean()';
      return 'z.any()';
    });
    zodType = `z.union([${zodVariants.join(', ')}])`;
  } else if (meta.discriminatorField === '__variant') {
    // Structural union — always z.any()
    zodType = 'z.any()';
  } else {
    // Discriminated union — z.discriminatedUnion
    const zodVariants = meta.variants.map((v) => {
      const zodFields = v.fields?.map((sf) => `${sf.name}: ${computeZodType(sf)}`).join(', ') || '';
      return `z.object({ ${meta.discriminatorField}: z.literal('${v.tag}'), ${zodFields} })`;
    });
    zodType = `z.discriminatedUnion('${meta.discriminatorField}', [${zodVariants.join(', ')}])`;
  }

  if (f.isArray) {
    zodType = `z.array(${zodType})`;
  }

  zodType = applyNullableOptionalZod(zodType, f.isNullable, f.isRequired);
  return zodType;
}

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
