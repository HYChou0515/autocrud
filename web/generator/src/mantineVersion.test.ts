import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import * as fs from 'fs/promises';
import * as fsSync from 'fs';
import * as path from 'path';
import * as os from 'os';
import {
  type MantineVersion,
  getVersionDeps,
  patchPackageJson,
  patchSourceFiles,
  writeVersionConfig,
  readVersionConfig,
  readRc,
  validateMantineVersion,
} from './mantineVersion.js';

describe('mantineVersion', () => {
  let tmpDir: string;

  beforeEach(() => {
    tmpDir = fsSync.mkdtempSync(path.join(os.tmpdir(), 'specstar-mantine-test-'));
  });

  afterEach(async () => {
    await fs.rm(tmpDir, { recursive: true, force: true });
  });

  // ---------------------------------------------------------------------------
  // validateMantineVersion
  // ---------------------------------------------------------------------------

  describe('validateMantineVersion', () => {
    it('returns "7" for input "7"', () => {
      expect(validateMantineVersion('7')).toBe('7');
    });

    it('returns "8" for input "8"', () => {
      expect(validateMantineVersion('8')).toBe('8');
    });

    it('throws for invalid version', () => {
      expect(() => validateMantineVersion('6')).toThrow('Invalid Mantine version "6"');
      expect(() => validateMantineVersion('9')).toThrow('Invalid Mantine version "9"');
      expect(() => validateMantineVersion('')).toThrow('Invalid Mantine version ""');
    });
  });

  // ---------------------------------------------------------------------------
  // getVersionDeps
  // ---------------------------------------------------------------------------

  describe('getVersionDeps', () => {
    it('returns empty changes for v7', () => {
      const deps = getVersionDeps('7');
      expect(Object.keys(deps.dependencies)).toHaveLength(0);
      expect(Object.keys(deps.devDependencies)).toHaveLength(0);
      expect(deps.removeDeps).toHaveLength(0);
    });

    it('returns Mantine 8 dependency overrides for v8', () => {
      const deps = getVersionDeps('8');
      expect(deps.dependencies['@mantine/core']).toMatch(/^\^8/);
      expect(deps.dependencies['@mantine/form']).toMatch(/^\^8/);
      expect(deps.dependencies['react']).toMatch(/^\^19/);
      expect(deps.dependencies['react-dom']).toMatch(/^\^19/);
      // mantine-form-zod-resolver should NOT be removed — it works with both v7 and v8
      expect(deps.removeDeps).not.toContain('mantine-form-zod-resolver');
    });

    it('includes pnpm overrides for v8 to handle MRT peerDep', () => {
      const deps = getVersionDeps('8');
      expect(deps.pnpmOverrides).toBeDefined();
      expect(deps.pnpmOverrides!['@mantine/core']).toMatch(/^\^8/);
    });
  });

  // ---------------------------------------------------------------------------
  // patchPackageJson
  // ---------------------------------------------------------------------------

  describe('patchPackageJson', () => {
    async function writeTestPkg(deps: Record<string, string>, devDeps: Record<string, string> = {}) {
      const pkg = {
        name: 'test-app',
        dependencies: { ...deps },
        devDependencies: { ...devDeps },
      };
      await fs.writeFile(path.join(tmpDir, 'package.json'), JSON.stringify(pkg, null, 2));
    }

    it('does nothing for v7', async () => {
      await writeTestPkg({
        '@mantine/core': '^7.17.8',
        'mantine-form-zod-resolver': '^1.3.0',
      });

      await patchPackageJson(tmpDir, '7');

      const pkg = JSON.parse(await fs.readFile(path.join(tmpDir, 'package.json'), 'utf-8'));
      expect(pkg.dependencies['@mantine/core']).toBe('^7.17.8');
      expect(pkg.dependencies['mantine-form-zod-resolver']).toBe('^1.3.0');
    });

    it('upgrades Mantine deps to v8', async () => {
      await writeTestPkg(
        {
          '@mantine/core': '^7.17.8',
          '@mantine/dates': '^7.17.8',
          '@mantine/form': '^7.17.8',
          '@mantine/hooks': '^7.17.8',
          '@mantine/notifications': '^7.17.8',
          'mantine-form-zod-resolver': '^1.3.0',
          react: '^18.3.1',
          'react-dom': '^18.3.1',
        },
        {
          '@types/react': '^18.3.18',
          '@types/react-dom': '^18.3.5',
        },
      );

      await patchPackageJson(tmpDir, '8');

      const pkg = JSON.parse(await fs.readFile(path.join(tmpDir, 'package.json'), 'utf-8'));
      // Mantine deps upgraded
      expect(pkg.dependencies['@mantine/core']).toMatch(/^\^8/);
      expect(pkg.dependencies['@mantine/form']).toMatch(/^\^8/);
      expect(pkg.dependencies['@mantine/dates']).toMatch(/^\^8/);
      expect(pkg.dependencies['@mantine/hooks']).toMatch(/^\^8/);
      expect(pkg.dependencies['@mantine/notifications']).toMatch(/^\^8/);
      // React upgraded
      expect(pkg.dependencies['react']).toMatch(/^\^19/);
      expect(pkg.dependencies['react-dom']).toMatch(/^\^19/);
      // mantine-form-zod-resolver should be preserved (works with both v7 and v8)
      expect(pkg.dependencies['mantine-form-zod-resolver']).toBe('^1.3.0');
      // devDeps @types upgraded
      expect(pkg.devDependencies['@types/react']).toMatch(/^\^19/);
      expect(pkg.devDependencies['@types/react-dom']).toMatch(/^\^19/);
    });

    it('adds pnpm overrides for v8', async () => {
      await writeTestPkg({
        '@mantine/core': '^7.17.8',
        'mantine-react-table': '2.0.0-beta.9',
        react: '^18.3.1',
        'react-dom': '^18.3.1',
      });

      await patchPackageJson(tmpDir, '8');

      const pkg = JSON.parse(await fs.readFile(path.join(tmpDir, 'package.json'), 'utf-8'));
      expect(pkg.pnpm).toBeDefined();
      expect(pkg.pnpm.overrides).toBeDefined();
      expect(pkg.pnpm.overrides['@mantine/core']).toMatch(/^\^8/);
    });

    it('preserves existing pnpm config when adding overrides', async () => {
      const pkg = {
        name: 'test-app',
        dependencies: { '@mantine/core': '^7.17.8', react: '^18.3.1', 'react-dom': '^18.3.1' },
        devDependencies: {},
        pnpm: { shamefullyHoist: true },
      };
      await fs.writeFile(path.join(tmpDir, 'package.json'), JSON.stringify(pkg, null, 2));

      await patchPackageJson(tmpDir, '8');

      const result = JSON.parse(await fs.readFile(path.join(tmpDir, 'package.json'), 'utf-8'));
      expect(result.pnpm.shamefullyHoist).toBe(true);
      expect(result.pnpm.overrides['@mantine/core']).toMatch(/^\^8/);
    });
  });

  // ---------------------------------------------------------------------------
  // patchSourceFiles
  // ---------------------------------------------------------------------------

  describe('patchSourceFiles', () => {
    it('does nothing for v7', async () => {
      const srcDir = path.join(tmpDir, 'src');
      const formDir = path.join(srcDir, 'specstar/lib/components/form');
      await fs.mkdir(formDir, { recursive: true });
      await fs.writeFile(
        path.join(formDir, 'useResourceForm.ts'),
        "import { zodResolver } from 'mantine-form-zod-resolver';",
      );

      await patchSourceFiles(srcDir, '7');

      const content = await fs.readFile(path.join(formDir, 'useResourceForm.ts'), 'utf-8');
      expect(content).toContain("from 'mantine-form-zod-resolver'");
    });

    it('does not patch zodResolver import for v8 (mantine-form-zod-resolver works with v8)', async () => {
      const srcDir = path.join(tmpDir, 'src');
      const formDir = path.join(srcDir, 'specstar/lib/components/form');
      await fs.mkdir(formDir, { recursive: true });
      await fs.writeFile(
        path.join(formDir, 'useResourceForm.ts'),
        "import { zodResolver } from 'mantine-form-zod-resolver';\nconst v = zodResolver(config.zodSchema);\nimport { useForm } from '@mantine/form';",
      );

      await patchSourceFiles(srcDir, '8');

      const content = await fs.readFile(path.join(formDir, 'useResourceForm.ts'), 'utf-8');
      // Import should remain unchanged — mantine-form-zod-resolver works with Mantine 8
      expect(content).toContain("import { zodResolver } from 'mantine-form-zod-resolver';");
      // No `as any` hack needed
      expect(content).toContain('zodResolver(config.zodSchema)');
      expect(content).not.toContain('zodResolver(config.zodSchema as any)');
    });

    it('skips gracefully if file does not exist', async () => {
      const srcDir = path.join(tmpDir, 'src');
      // Don't create the file — should not throw
      await expect(patchSourceFiles(srcDir, '8')).resolves.toBeUndefined();
    });

    it('does nothing to files since no source patches are needed', async () => {
      const srcDir = path.join(tmpDir, 'src');
      const formDir = path.join(srcDir, 'specstar/lib/components/form');
      await fs.mkdir(formDir, { recursive: true });
      const original =
        "import { zodResolver } from 'mantine-form-zod-resolver';\nconst v = zodResolver(config.zodSchema);";
      await fs.writeFile(path.join(formDir, 'useResourceForm.ts'), original);

      await patchSourceFiles(srcDir, '8');

      const content = await fs.readFile(path.join(formDir, 'useResourceForm.ts'), 'utf-8');
      expect(content).toBe(original);
    });
  });

  // ---------------------------------------------------------------------------
  // writeVersionConfig / readVersionConfig
  // ---------------------------------------------------------------------------

  describe('writeVersionConfig', () => {
    it('writes .specstarrc.json with version 7', async () => {
      await writeVersionConfig(tmpDir, '7');

      const content = JSON.parse(await fs.readFile(path.join(tmpDir, '.specstarrc.json'), 'utf-8'));
      expect(content.mantineVersion).toBe('7');
    });

    it('writes .specstarrc.json with version 8', async () => {
      await writeVersionConfig(tmpDir, '8');

      const content = JSON.parse(await fs.readFile(path.join(tmpDir, '.specstarrc.json'), 'utf-8'));
      expect(content.mantineVersion).toBe('8');
    });
  });

  describe('readVersionConfig', () => {
    it('returns stored version', async () => {
      await writeVersionConfig(tmpDir, '8');
      const version = await readVersionConfig(tmpDir);
      expect(version).toBe('8');
    });

    it('returns "7" as default when file does not exist', async () => {
      const version = await readVersionConfig(tmpDir);
      expect(version).toBe('7');
    });

    it('returns "7" as default when file is invalid JSON', async () => {
      await fs.writeFile(path.join(tmpDir, '.specstarrc.json'), 'not json');
      const version = await readVersionConfig(tmpDir);
      expect(version).toBe('7');
    });

    it('returns "7" as default when mantineVersion field is unexpected', async () => {
      await fs.writeFile(path.join(tmpDir, '.specstarrc.json'), '{"mantineVersion": "6"}');
      const version = await readVersionConfig(tmpDir);
      expect(version).toBe('7');
    });
  });

  // ---------------------------------------------------------------------------
  // readRc — the whole config, not just the Mantine version
  // ---------------------------------------------------------------------------

  describe('readRc', () => {
    it('returns an empty config when the file does not exist', async () => {
      expect(await readRc(tmpDir)).toEqual({});
    });

    it('returns an empty config when the file is invalid JSON', async () => {
      await fs.writeFile(path.join(tmpDir, '.specstarrc.json'), 'not json');
      expect(await readRc(tmpDir)).toEqual({});
    });

    it('returns an empty config when the file is not an object', async () => {
      await fs.writeFile(path.join(tmpDir, '.specstarrc.json'), '"a string"');
      expect(await readRc(tmpDir)).toEqual({});
    });

    it('reads the branding overrides', async () => {
      await fs.writeFile(path.join(tmpDir, '.specstarrc.json'), '{"title": "My Console", "logo": "/acme.svg"}');
      const rc = await readRc(tmpDir);
      expect(rc.title).toBe('My Console');
      expect(rc.logo).toBe('/acme.svg');
    });
  });

  // ---------------------------------------------------------------------------
  // writeVersionConfig — must not clobber unrelated config
  // ---------------------------------------------------------------------------

  describe('writeVersionConfig preserves unrelated config', () => {
    // `integrate` runs against an existing project, so a whole-file rewrite
    // would silently drop branding the developer had already configured.
    it('keeps branding overrides that are already in the file', async () => {
      await fs.writeFile(path.join(tmpDir, '.specstarrc.json'), '{"title": "My Console", "logo": "/acme.svg"}');
      await writeVersionConfig(tmpDir, '8');
      expect(await readRc(tmpDir)).toEqual({ mantineVersion: '8', title: 'My Console', logo: '/acme.svg' });
    });

    it('still writes a fresh config when no file exists', async () => {
      await writeVersionConfig(tmpDir, '8');
      expect(await readRc(tmpDir)).toEqual({ mantineVersion: '8' });
    });

    it('overwrites a corrupt config rather than failing', async () => {
      await fs.writeFile(path.join(tmpDir, '.specstarrc.json'), 'not json');
      await writeVersionConfig(tmpDir, '7');
      expect(await readRc(tmpDir)).toEqual({ mantineVersion: '7' });
    });
  });
});
