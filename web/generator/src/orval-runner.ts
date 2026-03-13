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
  /** Output directory for generated files (e.g., src/autocrud/generated) */
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
