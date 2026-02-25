/**
 * AutoCRUD Web Integrate Command
 *
 * Integrates generated code into an existing React project without
 * overwriting top-level config files (package.json, tsconfig, vite.config, etc.).
 *
 * Only copies:
 * - src/lib/ (components, hooks, utils, client.ts, resources.ts, etc.)
 * - src/types/ (api.ts)
 * - src/routes/__root.tsx, src/routes/autocrud-admin.tsx (layout routes)
 * Then runs generate to produce generated/ and route files.
 */

import * as fs from 'fs/promises';
import * as path from 'path';
import { fileURLToPath } from 'url';
import { generateCode, type GenerateOptions } from './generate.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

export async function integrateProject(
  apiUrl: string,
  outputRoot: string,
  options: GenerateOptions = {},
): Promise<void> {
  console.log('\n🔗 AutoCRUD Web Integration Mode\n');

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

  // Copy essential source files (non-destructive to top-level configs)
  console.log('📂 Copying AutoCRUD library files...');

  // 1. Copy src/lib/ directory
  const libSrc = path.join(templateSrc, 'lib');
  const libDest = path.join(SRC, 'lib');
  await copyDir(libSrc, libDest);
  console.log('  ✅ lib/ (components, hooks, utils, client)');

  // 2. Copy src/types/ directory
  const typesSrc = path.join(templateSrc, 'types');
  const typesDest = path.join(SRC, 'types');
  await copyDir(typesSrc, typesDest);
  console.log('  ✅ types/ (API type definitions)');

  // 3. Copy layout route files
  const routesSrc = path.join(templateSrc, 'routes');
  const routesDest = path.join(SRC, 'routes');
  await fs.mkdir(routesDest, { recursive: true });

  const layoutFiles = ['__root.tsx', 'autocrud-admin.tsx'];
  for (const file of layoutFiles) {
    const src = path.join(routesSrc, file);
    const dest = path.join(routesDest, file);
    try {
      await fs.access(src);
      await fs.copyFile(src, dest);
      console.log(`  ✅ routes/${file}`);
    } catch {
      console.warn(`  ⚠️  Template routes/${file} not found, skipping`);
    }
  }

  // 4. Copy essential app files
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

  console.log('\n🚀 Running code generation...\n');

  // Run generate
  await generateCode(apiUrl, outputRoot, options);

  // Print integration checklist
  printChecklist();
}

function printChecklist(): void {
  console.log('\n' + '='.repeat(60));
  console.log('📋 Integration Checklist');
  console.log('='.repeat(60));
  console.log(`
Please verify the following manual steps:

1. 📦 Dependencies — Add required packages:
   pnpm add @mantine/core @mantine/dates @mantine/form @mantine/hooks \\
     @mantine/notifications @tabler/icons-react @tanstack/react-router \\
     @tanstack/react-virtual axios clsx dayjs mantine-form-zod-resolver \\
     mantine-react-table@2.0.0-beta.9 react-markdown remark-gfm zod \\
     @monaco-editor/react

   pnpm add -D @tanstack/router-plugin postcss-preset-mantine \\
     postcss-simple-vars

2. ⚙️  tsconfig.app.json — Add path alias:
   {
     "compilerOptions": {
       "baseUrl": ".",
       "paths": { "@/*": ["./src/*"] }
     }
   }

3. 🔧 vite.config.ts — Add TanStack Router plugin + alias:
   import { TanStackRouterVite } from '@tanstack/router-plugin/vite'
   import path from 'path'

   export default defineConfig({
     plugins: [TanStackRouterVite({ quoteStyle: 'single' }), react()],
     resolve: { alias: { '@': path.resolve(__dirname, './src') } },
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

6. 📄 See INTEGRATION.md for detailed step-by-step guide.
`);
}

async function copyDir(src: string, dest: string): Promise<void> {
  await fs.mkdir(dest, { recursive: true });
  const entries = await fs.readdir(src, { withFileTypes: true });

  for (const entry of entries) {
    const srcPath = path.join(src, entry.name);
    const destPath = path.join(dest, entry.name);

    if (entry.isDirectory()) {
      await copyDir(srcPath, destPath);
    } else {
      await fs.copyFile(srcPath, destPath);
    }
  }
}
