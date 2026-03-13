/**
 * Shared test helpers for generator tests.
 *
 * Provides utilities to simulate the swagger-parser pipeline
 * (preScan → dereference → IRBuilder) using simple test specs with $refs.
 */

import { IRBuilder, preScanSpec } from './ir-builder.js';
import type { PreScanResult } from './ir-builder.js';
import type { Resource } from './types.js';

/**
 * Simple inline dereference for test specs.
 *
 * Replaces all `{ $ref: '#/components/schemas/Foo' }` with the actual schema object
 * from components.schemas. Uses reference equality (same object), mimicking
 * swagger-parser's dereference behavior.
 *
 * NOTE: Only handles local `#/components/schemas/` refs. Not suitable for
 * specs with external or deeply nested inter-schema circular refs.
 */
export function simpleDeref(spec: any): any {
  const clone = JSON.parse(JSON.stringify(spec));
  const schemas = clone.components?.schemas ?? {};

  function resolve(obj: any): any {
    if (obj === null || typeof obj !== 'object') return obj;
    if (obj.$ref && typeof obj.$ref === 'string' && obj.$ref.startsWith('#/components/schemas/')) {
      const name = obj.$ref.split('/').pop()!;
      return schemas[name] ?? obj;
    }
    if (Array.isArray(obj)) {
      for (let i = 0; i < obj.length; i++) {
        obj[i] = resolve(obj[i]);
      }
      return obj;
    }
    for (const key of Object.keys(obj)) {
      obj[key] = resolve(obj[key]);
    }
    return obj;
  }

  resolve(clone);
  return clone;
}

/**
 * Build IR from a raw spec (with $refs).
 *
 * Simulates the full swagger-parser pipeline:
 *   preScanSpec(raw) → simpleDeref(raw) → IRBuilder(deref).build()
 *
 * Returns the IRBuilder instance (for getJobHiddenFields etc.), the parsed resources,
 * and the dereferenced spec (for tests that need to read resolved properties).
 */
export function buildIR(
  spec: any,
  basePath = '',
): { resources: Resource[]; builder: IRBuilder; preScan: PreScanResult; derefSpec: any } {
  const preScan = preScanSpec(spec, basePath);
  const derefSpec = simpleDeref(spec);
  const builder = new IRBuilder(derefSpec, basePath, preScan);
  const resources = builder.build();
  return { resources, builder, preScan, derefSpec };
}

/**
 * Resolve $ref values in a property object against a schemas map.
 *
 * Use this in tests that construct inline prop objects with $ref values
 * to resolve them against the dereferenced spec's schemas.
 *
 * @example
 * ```ts
 * const { builder, derefSpec } = buildIR(spec);
 * const prop = derefProp(
 *   { anyOf: [{ $ref: '#/components/schemas/Foo' }, { type: 'null' }] },
 *   derefSpec.components.schemas
 * );
 * const field = builder.parseField('myField', prop, true);
 * ```
 */
export function derefProp(prop: any, schemas: Record<string, any>): any {
  if (!prop || typeof prop !== 'object') return prop;
  if (prop.$ref && typeof prop.$ref === 'string') {
    const name = prop.$ref.split('/').pop()!;
    return schemas[name] ?? prop;
  }
  if (Array.isArray(prop)) return prop.map((p) => derefProp(p, schemas));
  const result: any = {};
  for (const [k, v] of Object.entries(prop)) {
    result[k] = derefProp(v, schemas);
  }
  return result;
}
