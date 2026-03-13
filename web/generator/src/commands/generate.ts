/**
 * AutoCRUD Web Code Generator — Entry Point
 *
 * Orchestrates:
 *   1. swagger-parser: load + validate + dereference OpenAPI spec
 *   2. Orval: generate TypeScript types + Zod schemas
 *   3. IR builder: build Resource[] from dereferenced spec
 *   4. Custom codegen: generate api/, routes/, resources.ts
 */

import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';

import SwaggerParser from '@apidevtools/swagger-parser';

import { IRBuilder, preScanSpec } from '../ir-builder.js';
import { CodeGenerator } from '../codegen/index.js';
import { runOrvalGenerate, discoverOrvalZodSchemas } from '../orval-runner.js';
import { hasRefMembers } from '../types.js';

// Re-export for backward compatibility (used by CLI and tests)
export { IRBuilder, preScanSpec } from '../ir-builder.js';
export type { PreScanResult } from '../ir-builder.js';
export { CodeGenerator } from '../codegen/index.js';
export type { Resource, Field, UnionVariant, UnionMeta, CustomCreateAction, FieldRef } from '../types.js';
export {
  sanitizeTsName,
  toPascal,
  toCamel,
  toLabel,
  getLeafLabel,
  escapeRegex,
  hasRefMembers,
  looksLikeDatetime,
  computeMaxFieldDepth,
  serializeField,
} from '../types.js';
export { genResourcesConfig, computeZodType, buildNestedZodFields } from '../codegen/resources-gen.js';
export { genApiClient, genApiIndex, genBackupApiClient, genMigrateApiClient } from '../codegen/api-gen.js';
export {
  genListRoute,
  genCreateRoute,
  genDetailRoute,
  genBackupPage,
  genMigratePage,
  genRootIndex,
  genDashboard,
} from '../codegen/routes-gen.js';

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

  // ── Step 1: Fetch spec via HTTP, then validate + dereference ─────────────
  // swagger-parser ≥12 doesn't ship an HTTP resolver, so we fetch ourselves.
  const resp = await fetch(specUrl);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}: ${resp.statusText}`);
  const specJson = await resp.text();
  const specObj = JSON.parse(specJson);

  // Validate (operates on in-memory object, no network needed)
  const rawSpec = (await SwaggerParser.validate(structuredClone(specObj))) as any;
  console.log(`✅ ${rawSpec.info.title} v${rawSpec.info.version}`);

  // Detect or use provided base path
  const basePath = options.basePath ?? detectBasePath(specObj);
  if (basePath) {
    console.log(`🔗 API base path: ${basePath}`);
  }

  // ── Step 2: Pre-scan (capture $ref metadata before dereference) ──────────
  const preScan = preScanSpec(specObj, basePath);

  // Save spec to temp file for Orval (needs file path input)
  const tempSpecPath = path.join(os.tmpdir(), `autocrud-openapi-${Date.now()}.json`);
  fs.writeFileSync(tempSpecPath, specJson, 'utf-8');

  // ── Step 3: Dereference spec (resolve all $refs inline) ──────────────────
  const dereferencedSpec = (await SwaggerParser.dereference(structuredClone(specObj))) as any;

  // ── Step 4: Orval generate types + Zod schemas ──────────────────────────
  let orvalSchemas: Map<string, string> | undefined;
  try {
    await runOrvalGenerate({ specPath: tempSpecPath, outputDir: GEN });
    orvalSchemas = discoverOrvalZodSchemas(GEN);
    if (orvalSchemas.size > 0) {
      console.log(`  📦 Discovered ${orvalSchemas.size} Orval Zod schemas`);
    }
  } catch (error) {
    console.warn('⚠️  Orval generation failed, falling back to custom generation only');
    console.warn(error);
  }

  // ── Step 5: Build IR from dereferenced spec ──────────────────────────────
  const builder = new IRBuilder(dereferencedSpec, basePath, preScan);
  const resources = builder.build();

  // ── Step 6: Custom codegen (api, routes, resources) ──────────────────────
  const codeGen = new CodeGenerator(
    resources,
    dereferencedSpec,
    ROOT,
    SRC,
    GEN,
    ROUTES,
    basePath,
    builder,
    orvalSchemas,
  );
  codeGen.run();

  // ── Step 7: Write .env file with proxy config ────────────────────────────
  const proxyPath = options.proxyPath ?? '/api';
  writeEnvFile(ROOT, apiUrl, proxyPath);

  // Cleanup temp file
  try {
    fs.unlinkSync(tempSpecPath);
  } catch {
    // ignore cleanup errors
  }
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
