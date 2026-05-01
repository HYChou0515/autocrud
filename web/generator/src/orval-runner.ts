/**
 * Orval Runner — generates TypeScript types and Zod schemas via Orval.
 *
 * Two runs:
 * 1. Types:  Orval with 'zod' client → generates TS types + Zod schemas
 *    (Zod schemas are re-exported for resources.ts; types are re-exported for route files)
 *
 * For the types-only run, we generate to a temp target and keep only the schemas.
 */

import { generate } from 'orval';
import fs from 'node:fs';
import path from 'node:path';

export interface OrvalOptions {
  /** Path to saved OpenAPI spec JSON file */
  specPath: string;
  /** Output directory for generated files (e.g., src/specstar/generated) */
  outputDir: string;
}

/**
 * Run Orval to generate TypeScript types from OpenAPI spec.
 *
 * Uses 'zod' client to produce:
 * - TypeScript type definitions (enums, interfaces, union aliases)
 * - Zod validation schemas for each component schema
 *
 * Output files:
 * - {outputDir}/types.ts  — TypeScript types + Zod schemas
 */
export async function runOrvalGenerate(options: OrvalOptions): Promise<void> {
  const { specPath, outputDir } = options;

  fs.mkdirSync(outputDir, { recursive: true });

  console.log('🔧 Running Orval — generating types + Zod schemas...');

  try {
    await generate(
      {
        input: specPath,
        output: {
          target: path.join(outputDir, 'types.ts'),
          client: 'zod',
          mode: 'single',
          override: {
            zod: {
              strict: {
                param: false,
                query: false,
                header: false,
                body: false,
                response: false,
              },
              generateEachHttpStatus: false,
            },
          },
        },
      },
      undefined,
      { clean: false },
    );

    console.log('  ✅ Orval types + Zod generation complete');

    // Post-process: fix z.array() without inner type (from list[Any])
    postProcessOrvalOutput(outputDir);
  } catch (error) {
    console.error('  ❌ Orval generation failed:', error);
    throw error;
  }
}

/**
 * Discover Orval-generated Zod schema export names from the output file.
 *
 * Scans the generated types.ts for `export const <name> = z.` patterns
 * and returns a map of schemaName → zodExportName.
 *
 * @param outputDir - Directory containing the generated types.ts
 * @returns Map from PascalCase schema name to the actual Orval export name
 */
export function discoverOrvalZodSchemas(outputDir: string): Map<string, string> {
  const typesPath = path.join(outputDir, 'types.ts');
  const result = new Map<string, string>();

  if (!fs.existsSync(typesPath)) {
    console.warn('⚠️  Orval output not found, skipping Zod schema discovery');
    return result;
  }

  const content = fs.readFileSync(typesPath, 'utf-8');

  // Match patterns like: export const characterSchema = z. or export const character = z.
  const schemaPattern = /export\s+const\s+(\w+)\s*=\s*z\./g;
  let match;
  while ((match = schemaPattern.exec(content)) !== null) {
    const exportName = match[1];
    result.set(exportName, exportName);
  }

  return result;
}

/**
 * Post-process Orval-generated types.ts to fix invalid Zod expressions.
 *
 * Orval may emit `z.array()` without an inner type for `list[Any]`
 * (OpenAPI `{"type": "array"}` without `items`).  This is invalid in Zod
 * and causes `tsc -b` errors.  We patch it to `z.array(z.any())`.
 *
 * ## Why string-replace instead of generating correctly from the start?
 *
 * Orval is a third-party code generator we cannot control.  When it encounters
 * OpenAPI `{"type": "array"}` without an `items` schema (which is what Python's
 * `list[Any]` produces), it emits the invalid `z.array()`.  Since Orval does
 * not expose a transformer hook to customize Zod code-gen, post-processing its
 * output is the standard workaround.
 *
 * Our own fallback path (computeZodType in resources-gen.ts) already produces
 * `z.array(z.any())` correctly from the start.  This post-process only targets
 * the Orval-generated types.ts file.
 *
 * ## Safety
 *
 * - The regex `/\b(zod|z)\.array\(\)/g` only matches empty-argument `.array()`.
 *   It will NOT modify valid expressions like `z.array(z.string())`.
 * - `z.array()` (no argument) is ALWAYS invalid in Zod, so replacement is
 *   unconditionally correct.
 *
 * ## Risks
 *
 * - If Orval changes its import namespace (currently `zod` or `z`), the regex
 *   may miss new patterns.  The `\b` word-boundary and alternation `(zod|z)`
 *   cover the two known variants.
 * - If Orval starts emitting multi-line `.array(\n)` the regex would not match.
 *   This is unlikely given Orval's single-line codegen style.
 *
 * ## When to consider rewriting
 *
 * - If Orval adds a Zod transformer/plugin API that lets us customize the
 *   output at generation time, we should remove this post-process and use
 *   the official hook instead.
 * - If Orval fixes the `list[Any]` bug upstream, this function becomes a
 *   no-op and can be removed (the regex simply won't match).
 *
 * @param outputDir - Directory containing the generated types.ts
 */
export function postProcessOrvalOutput(outputDir: string): void {
  const typesPath = path.join(outputDir, 'types.ts');
  if (!fs.existsSync(typesPath)) return;

  const content = fs.readFileSync(typesPath, 'utf-8');
  // Match z.array() or zod.array() with no argument — but NOT z.array(something).
  // Orval uses `import * as zod from 'zod'` so the namespace is 'zod', not 'z'.
  //
  // Why: Orval emits invalid `z.array()` for Python `list[Any]` (OpenAPI array without items).
  //      We cannot control Orval's codegen — no transformer hook is available.
  // Safety: `z.array()` is ALWAYS invalid in Zod, so this replacement is unconditionally correct.
  //         The regex only matches empty-arg .array(); it won't touch z.array(z.string()) etc.
  // Risks: If Orval changes its import namespace beyond `zod`/`z`, or emits multi-line
  //        `.array(\n)`, this regex would miss.  Both are unlikely given Orval's codegen style.
  // Rewrite when: Orval adds a Zod transformer/plugin API, or fixes this bug upstream.
  const fixed = content.replace(/\b(zod|z)\.array\(\)/g, '$1.array($1.any())');
  if (fixed !== content) {
    fs.writeFileSync(typesPath, fixed, 'utf-8');
    console.log('  🔧 Fixed empty .array() → .array(.any()) in Orval output');
  }
}
