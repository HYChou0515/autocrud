/**
 * AutoCRUD Web Integrate Command
 *
 * Integrates generated code into an existing React project without
 * overwriting top-level config files (package.json, tsconfig, vite.config, etc.).
 *
 * Only copies:
 * - src/autocrud/lib/ (components, hooks, utils, client.ts, resources.ts, etc.)
 * - src/autocrud/types/ (api.ts)
 * - src/routes/__root.tsx, src/routes/autocrud-admin.tsx (layout routes)
 * Then runs generate to produce autocrud/generated/ and route files.
 *
 * When a target file already exists and differs from the template, an
 * interactive prompt lets the user choose: skip, overwrite, or show diff
 * before deciding.  Use --force to skip all prompts and overwrite.
 */

import * as fs from 'fs/promises';
import * as path from 'path';
import { fileURLToPath } from 'url';
import { select } from '@inquirer/prompts';
import { generateCode, type GenerateOptions } from './generate.js';
import { type MantineVersion, patchPackageJson, patchSourceFiles, writeVersionConfig } from '../mantineVersion.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

export interface IntegrateOptions extends GenerateOptions {
  includeTests?: boolean;
  /** Skip all interactive prompts and overwrite changed files. */
  force?: boolean;
  /** Mantine major version (7 or 8). Defaults to 7. */
  mantineVersion?: MantineVersion;
}

export async function integrateProject(
  apiUrl: string,
  outputRoot: string,
  options: IntegrateOptions = {},
): Promise<void> {
  const mantineVersion = options.mantineVersion ?? '7';
  console.log(`\n🔗 AutoCRUD Web Integration Mode (Mantine ${mantineVersion})\n`);

  const ROOT = process.cwd();
  const SRC = path.join(ROOT, outputRoot);
  const templatePath = path.join(__dirname, '../../templates/base');
  const templateSrc = path.join(templatePath, 'src');

  // Check that the output directory exists (we're integrating into an existing project)
  try {
    await fs.access(SRC);
  } catch {
    console.error(`❌ Error: Output directory "${SRC}" does not exist.`);
    console.error('   Integration mode requires an existing project. Use "init" for new projects.');
    process.exit(1);
  }

  await copyIntegrationFiles(templateSrc, SRC, {
    includeTests: options.includeTests ?? false,
    force: options.force ?? false,
    baseDir: SRC,
  });

  console.log('\n🚀 Running code generation...\n');

  // Run generate
  await generateCode(apiUrl, outputRoot, options);

  // Apply Mantine version-specific patches
  await patchPackageJson(ROOT, mantineVersion);
  await patchSourceFiles(SRC, mantineVersion);
  await writeVersionConfig(ROOT, mantineVersion);

  // Print integration checklist
  const proxyPath = options.proxyPath ?? '/api';
  printChecklist(mantineVersion, proxyPath);
}

// ---------------------------------------------------------------------------
// File conflict resolution
// ---------------------------------------------------------------------------

type ConflictAction = 'skip' | 'overwrite';

/**
 * Check whether `src` and `dest` have identical content.
 * Returns true when dest does not exist or content is identical.
 */
async function filesAreEqual(src: string, dest: string): Promise<boolean> {
  try {
    await fs.access(dest);
  } catch {
    return false; // dest doesn't exist → not "equal", needs copy
  }
  const [srcBuf, destBuf] = await Promise.all([fs.readFile(src), fs.readFile(dest)]);
  return srcBuf.equals(destBuf);
}

/**
 * Produce a simple unified-style diff between two strings.
 */
export function simpleDiff(oldContent: string, newContent: string, label: string): string {
  const oldLines = oldContent.split('\n');
  const newLines = newContent.split('\n');
  const lines: string[] = [`--- existing ${label}`, `+++ template ${label}`, ''];

  const maxLen = Math.max(oldLines.length, newLines.length);
  for (let i = 0; i < maxLen; i++) {
    const oldLine = i < oldLines.length ? oldLines[i] : undefined;
    const newLine = i < newLines.length ? newLines[i] : undefined;

    if (oldLine === newLine) {
      lines.push(`  ${oldLine}`);
    } else {
      if (oldLine !== undefined) lines.push(`\x1b[31m- ${oldLine}\x1b[0m`);
      if (newLine !== undefined) lines.push(`\x1b[32m+ ${newLine}\x1b[0m`);
    }
  }
  return lines.join('\n');
}

/**
 * Prompt the user to decide how to handle a file conflict.
 * When `force` is true the prompt is skipped and 'overwrite' is returned.
 */
export async function promptFileConflict(
  relPath: string,
  srcPath: string,
  destPath: string,
  force: boolean,
): Promise<ConflictAction> {
  if (force) return 'overwrite';

  // First ask: skip / overwrite / show diff
  const action = await select<'skip' | 'overwrite' | 'diff'>({
    message: `File "${relPath}" has been modified. What would you like to do?`,
    choices: [
      { name: 'Skip — keep your version', value: 'skip' },
      { name: 'Overwrite — use template version', value: 'overwrite' },
      { name: 'Show diff — then decide', value: 'diff' },
    ],
  });

  if (action !== 'diff') return action;

  // Show diff, then ask again (skip or overwrite only)
  const [srcContent, destContent] = await Promise.all([fs.readFile(srcPath, 'utf-8'), fs.readFile(destPath, 'utf-8')]);
  console.log('\n' + simpleDiff(destContent, srcContent, relPath) + '\n');

  return select<ConflictAction>({
    message: `After reviewing the diff for "${relPath}":`,
    choices: [
      { name: 'Skip — keep your version', value: 'skip' },
      { name: 'Overwrite — use template version', value: 'overwrite' },
    ],
  });
}

/**
 * Copy a single file from `src` to `dest`, prompting on conflict.
 * Returns the action taken: 'copied', 'skipped' (unchanged), 'skip' or 'overwrite'.
 */
async function copyFileWithConflictCheck(
  srcPath: string,
  destPath: string,
  relPath: string,
  force: boolean,
): Promise<'created' | 'unchanged' | 'skipped' | 'overwritten'> {
  // Dest doesn't exist → always copy
  let destExists = true;
  try {
    await fs.access(destPath);
  } catch {
    destExists = false;
  }

  if (!destExists) {
    await fs.copyFile(srcPath, destPath);
    return 'created';
  }

  // Content identical → skip silently
  if (await filesAreEqual(srcPath, destPath)) {
    return 'unchanged';
  }

  // Content differs → prompt (or force)
  const action = await promptFileConflict(relPath, srcPath, destPath, force);
  if (action === 'overwrite') {
    await fs.copyFile(srcPath, destPath);
    return 'overwritten';
  }
  return 'skipped';
}

// ---------------------------------------------------------------------------
// Copy integration files with conflict resolution
// ---------------------------------------------------------------------------

interface CopyOptions {
  includeTests?: boolean;
  force?: boolean;
  /** Absolute path used to derive relative display paths. */
  baseDir?: string;
}

export async function copyIntegrationFiles(templateSrc: string, SRC: string, options: CopyOptions = {}): Promise<void> {
  const force = options.force ?? false;
  const baseDir = options.baseDir ?? SRC;

  console.log('📂 Copying AutoCRUD library files...');

  // 1. Copy src/autocrud/lib/ directory
  const libSrc = path.join(templateSrc, 'autocrud/lib');
  const libDest = path.join(SRC, 'autocrud/lib');
  await copyDir(libSrc, libDest, { includeTests: options.includeTests, force, baseDir });
  console.log('  ✅ autocrud/lib/ (components, hooks, utils, client)');

  // 2. Copy src/autocrud/types/ directory
  const typesSrc = path.join(templateSrc, 'autocrud/types');
  const typesDest = path.join(SRC, 'autocrud/types');
  await copyDir(typesSrc, typesDest, { includeTests: options.includeTests, force, baseDir });
  console.log('  ✅ autocrud/types/ (API type definitions)');

  // 3. Copy layout route files (with conflict check)
  const routesSrc = path.join(templateSrc, 'routes');
  const routesDest = path.join(SRC, 'routes');
  await fs.mkdir(routesDest, { recursive: true });

  const layoutFiles = ['__root.tsx', 'autocrud-admin.tsx'];
  for (const file of layoutFiles) {
    const src = path.join(routesSrc, file);
    const dest = path.join(routesDest, file);
    try {
      await fs.access(src);
    } catch {
      console.warn(`  ⚠️  Template routes/${file} not found, skipping`);
      continue;
    }
    const relPath = path.relative(baseDir, dest);
    const result = await copyFileWithConflictCheck(src, dest, relPath, force);
    logCopyResult(`routes/${file}`, result);
  }

  // 4. Copy essential app files (only if they don't already exist)
  const essentialFiles = ['index.css', 'App.tsx', 'main.tsx', 'vite-env.d.ts'];
  for (const file of essentialFiles) {
    const src = path.join(templateSrc, file);
    const dest = path.join(SRC, file);
    try {
      await fs.access(dest);
      // File exists — don't overwrite, skip
      console.log(`  ⏭️  ${file} (exists, skipped)`);
    } catch {
      // File doesn't exist — copy it
      try {
        await fs.access(src);
        await fs.copyFile(src, dest);
        console.log(`  ✅ ${file}`);
      } catch {
        // Template file doesn't exist either, skip
      }
    }
  }
}

function logCopyResult(label: string, result: 'created' | 'unchanged' | 'skipped' | 'overwritten'): void {
  switch (result) {
    case 'created':
      console.log(`  ✅ ${label}`);
      break;
    case 'unchanged':
      console.log(`  ⏭️  ${label} (unchanged)`);
      break;
    case 'skipped':
      console.log(`  ⏭️  ${label} (skipped by user)`);
      break;
    case 'overwritten':
      console.log(`  🔄 ${label} (overwritten)`);
      break;
  }
}

function printChecklist(mantineVersion: MantineVersion = '7', proxyPath: string = '/api'): void {
  const isV8 = mantineVersion === '8';

  const mantinePkgs = isV8
    ? '@mantine/core@^8 @mantine/dates@^8 @mantine/form@^8 @mantine/hooks@^8 @mantine/notifications@^8'
    : '@mantine/core @mantine/dates @mantine/form @mantine/hooks @mantine/notifications';

  const zodResolverPkg = isV8 ? '' : 'mantine-form-zod-resolver';
  const reactPkgs = isV8 ? 'react@^19 react-dom@^19' : '';

  console.log('\n' + '='.repeat(60));
  console.log(`📋 Integration Checklist (Mantine ${mantineVersion})`);
  console.log('='.repeat(60));
  console.log(`
Please verify the following manual steps:

1. 📦 Dependencies — Add required packages:
   pnpm add ${mantinePkgs} \\
     @tabler/icons-react @tanstack/react-router \\
     @tanstack/react-virtual axios clsx dayjs ${zodResolverPkg ? zodResolverPkg + ' ' : ''}\\
     mantine-react-table@2.0.0-beta.9 react-markdown remark-gfm zod \\
     @monaco-editor/react${reactPkgs ? ' \\\n     ' + reactPkgs : ''}

   pnpm add -D @tanstack/router-plugin postcss-preset-mantine \\
     postcss-simple-vars${isV8 ? ' @types/react@^19 @types/react-dom@^19' : ''}

2. ⚙️  tsconfig.app.json — Add path alias:
   {
     "compilerOptions": {
       "baseUrl": ".",
       "paths": { "@/*": ["./src/*"] }
     }
   }

3. 🔧 vite.config.ts — Add TanStack Router plugin + alias + proxy:
   import { TanStackRouterVite } from '@tanstack/router-plugin/vite'
   import path from 'path'

   export default defineConfig({
     plugins: [TanStackRouterVite({ quoteStyle: 'single' }), react()],
     resolve: { alias: { '@': path.resolve(__dirname, './src') } },
     server: {
       proxy: {
         '${proxyPath}': {
           target: 'http://localhost:8000',
           changeOrigin: true,
           rewrite: (p) => p.replace(new RegExp('^${proxyPath.replace(/\//g, '\\/')}'), ''),
         },
       },
     },
   })

4. 🎨 postcss.config.mjs — Add Mantine preset:
   export default {
     plugins: {
       'postcss-preset-mantine': {},
       'postcss-simple-vars': {
         variables: {
           'mantine-breakpoint-xs': '36em',
           'mantine-breakpoint-sm': '48em',
           'mantine-breakpoint-md': '62em',
           'mantine-breakpoint-lg': '75em',
           'mantine-breakpoint-xl': '88em',
         },
       },
     },
   }

5. 🏠 App entry — Wrap your app with MantineProvider:
   import { MantineProvider } from '@mantine/core'
   import '@mantine/core/styles.css'
   import '@mantine/notifications/styles.css'
   import '@mantine/dates/styles.css'
${
  isV8
    ? `
6. ⚠️  Note: Mantine 8 requires React 19. zodResolver is now built into
   @mantine/form — mantine-form-zod-resolver has been automatically patched
   to import from @mantine/form instead.
   mantine-react-table peer dependency warnings can be safely ignored.

7. 📄 See INTEGRATION.md for detailed step-by-step guide.
`
    : `
6. 📄 See INTEGRATION.md for detailed step-by-step guide.
`
}`);
}

// ---------------------------------------------------------------------------
// Recursive directory copy with conflict resolution
// ---------------------------------------------------------------------------

const TEST_FILE_RE = /\.(test|spec)\.[^.]+$/;

interface CopyDirOptions {
  includeTests?: boolean;
  force?: boolean;
  /** Absolute base path for computing relative display paths. */
  baseDir?: string;
}

async function copyDir(src: string, dest: string, options: CopyDirOptions = {}): Promise<void> {
  const force = options.force ?? false;
  const baseDir = options.baseDir ?? dest;

  await fs.mkdir(dest, { recursive: true });
  const entries = await fs.readdir(src, { withFileTypes: true });

  for (const entry of entries) {
    const srcPath = path.join(src, entry.name);
    const destPath = path.join(dest, entry.name);

    // Skip test files unless explicitly included
    if (!options.includeTests && TEST_FILE_RE.test(entry.name)) {
      continue;
    }

    if (entry.isDirectory()) {
      await copyDir(srcPath, destPath, options);
    } else {
      const relPath = path.relative(baseDir, destPath);
      const result = await copyFileWithConflictCheck(srcPath, destPath, relPath, force);
      // Only log non-trivial results to avoid spamming for large dirs
      if (result === 'skipped' || result === 'overwritten') {
        logCopyResult(relPath, result);
      }
    }
  }
}
