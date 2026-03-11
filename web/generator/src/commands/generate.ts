/**
 * AutoCRUD Web Code Generator — Entry Point
 *
 * Orchestrates: fetch OpenAPI spec → parse to IR → generate code files.
 *
 * The heavy lifting is delegated to:
 * - OpenAPIParser (openapi-parser.ts) — spec → IR Resources
 * - CodeGenerator (codegen/index.ts) — IR → .ts/.tsx files
 */

import fs from 'node:fs';
import path from 'node:path';

import { OpenAPIParser } from '../openapi-parser.js';
import { CodeGenerator } from '../codegen/index.js';
import { hasRefMembers } from '../types.js';

// Re-export for backward compatibility (used by CLI and tests)
export { OpenAPIParser } from '../openapi-parser.js';
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
export { computeTsType, genTypes } from '../codegen/ts-type.js';
export { computeZodType, buildNestedZodFields } from '../codegen/zod-type.js';
export { genResourcesConfig } from '../codegen/resources-gen.js';
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

  const resp = await fetch(specUrl);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}: ${resp.statusText}`);

  const spec: any = await resp.json();
  console.log(`✅ ${spec.info.title} v${spec.info.version}`);

  // Detect or use provided base path
  const basePath = options.basePath ?? detectBasePath(spec);
  if (basePath) {
    console.log(`🔗 API base path: ${basePath}`);
  }

  // Parse OpenAPI → IR
  const parser = new OpenAPIParser(spec, basePath);
  const resources = parser.parse();

  // Generate code from IR
  const codeGen = new CodeGenerator(resources, spec, ROOT, SRC, GEN, ROUTES, basePath, parser);
  codeGen.run();

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
