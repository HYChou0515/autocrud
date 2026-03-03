import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import * as fs from 'fs/promises';
import * as fsSync from 'fs';
import * as path from 'path';
import * as os from 'os';
import { copyIntegrationFiles, simpleDiff, promptFileConflict } from './integrate.js';

// Mock @inquirer/prompts — we don't want real interactive prompts in tests
vi.mock('@inquirer/prompts', () => ({
  select: vi.fn(),
}));
import { select } from '@inquirer/prompts';
const mockSelect = vi.mocked(select);

// We test copyIntegrationFiles directly — the pure file-copy logic —
// without needing a running backend (which integrateProject requires via generateCode).

describe('copyIntegrationFiles', () => {
  let tmpDir: string;
  let templateSrc: string;
  let targetSrc: string;

  beforeEach(async () => {
    tmpDir = fsSync.mkdtempSync(path.join(os.tmpdir(), 'autocrud-integrate-test-'));
    templateSrc = path.join(tmpDir, 'template-src');
    targetSrc = path.join(tmpDir, 'target-src');

    // Create a minimal template structure (matching autocrud/ prefix used by copyIntegrationFiles)
    await fs.mkdir(path.join(templateSrc, 'autocrud', 'lib'), { recursive: true });
    await fs.mkdir(path.join(templateSrc, 'autocrud', 'types'), { recursive: true });
    await fs.mkdir(path.join(templateSrc, 'routes'), { recursive: true });

    // Template files
    await fs.writeFile(path.join(templateSrc, 'autocrud', 'lib', 'client.ts'), 'export const client = {};');
    await fs.writeFile(path.join(templateSrc, 'autocrud', 'lib', 'resources.ts'), 'export const registry = {};');
    await fs.writeFile(path.join(templateSrc, 'autocrud', 'types', 'api.ts'), 'export type FullResource = {};');
    await fs.writeFile(path.join(templateSrc, 'routes', '__root.tsx'), '<Root />');
    await fs.writeFile(path.join(templateSrc, 'routes', 'autocrud-admin.tsx'), '<Admin />');
    await fs.writeFile(path.join(templateSrc, 'App.tsx'), 'function App() {}');
    await fs.writeFile(path.join(templateSrc, 'main.tsx'), 'render(<App />)');
    await fs.writeFile(path.join(templateSrc, 'index.css'), 'body {}');
    await fs.writeFile(path.join(templateSrc, 'vite-env.d.ts'), '/// <reference />');

    // Create empty target directory
    await fs.mkdir(targetSrc, { recursive: true });
  });

  afterEach(async () => {
    await fs.rm(tmpDir, { recursive: true, force: true });
  });

  it('copies autocrud/lib/ directory', async () => {
    await copyIntegrationFiles(templateSrc, targetSrc, { force: true });

    const client = await fs.readFile(path.join(targetSrc, 'autocrud', 'lib', 'client.ts'), 'utf-8');
    expect(client).toBe('export const client = {};');

    const resources = await fs.readFile(path.join(targetSrc, 'autocrud', 'lib', 'resources.ts'), 'utf-8');
    expect(resources).toBe('export const registry = {};');
  });

  it('copies autocrud/types/ directory', async () => {
    await copyIntegrationFiles(templateSrc, targetSrc, { force: true });

    const api = await fs.readFile(path.join(targetSrc, 'autocrud', 'types', 'api.ts'), 'utf-8');
    expect(api).toBe('export type FullResource = {};');
  });

  it('copies layout route files', async () => {
    await copyIntegrationFiles(templateSrc, targetSrc, { force: true });

    const root = await fs.readFile(path.join(targetSrc, 'routes', '__root.tsx'), 'utf-8');
    expect(root).toBe('<Root />');

    const admin = await fs.readFile(path.join(targetSrc, 'routes', 'autocrud-admin.tsx'), 'utf-8');
    expect(admin).toBe('<Admin />');
  });

  it('copies essential app files when they do not exist', async () => {
    await copyIntegrationFiles(templateSrc, targetSrc, { force: true });

    const app = await fs.readFile(path.join(targetSrc, 'App.tsx'), 'utf-8');
    expect(app).toBe('function App() {}');

    const main = await fs.readFile(path.join(targetSrc, 'main.tsx'), 'utf-8');
    expect(main).toBe('render(<App />)');

    const css = await fs.readFile(path.join(targetSrc, 'index.css'), 'utf-8');
    expect(css).toBe('body {}');
  });

  it('does NOT overwrite existing essential app files', async () => {
    // Pre-create files with custom content
    await fs.writeFile(path.join(targetSrc, 'App.tsx'), 'MY CUSTOM APP');
    await fs.writeFile(path.join(targetSrc, 'main.tsx'), 'MY CUSTOM MAIN');

    await copyIntegrationFiles(templateSrc, targetSrc, { force: true });

    // Should preserve existing content
    const app = await fs.readFile(path.join(targetSrc, 'App.tsx'), 'utf-8');
    expect(app).toBe('MY CUSTOM APP');

    const main = await fs.readFile(path.join(targetSrc, 'main.tsx'), 'utf-8');
    expect(main).toBe('MY CUSTOM MAIN');

    // index.css didn't exist, so it should be copied
    const css = await fs.readFile(path.join(targetSrc, 'index.css'), 'utf-8');
    expect(css).toBe('body {}');
  });

  it('does NOT create or copy top-level config files', async () => {
    await copyIntegrationFiles(templateSrc, targetSrc, { force: true });

    await expect(fs.access(path.join(targetSrc, 'package.json'))).rejects.toThrow();
    await expect(fs.access(path.join(targetSrc, 'tsconfig.json'))).rejects.toThrow();
    await expect(fs.access(path.join(targetSrc, 'vite.config.ts'))).rejects.toThrow();
    await expect(fs.access(path.join(targetSrc, 'postcss.config.mjs'))).rejects.toThrow();
    await expect(fs.access(path.join(targetSrc, 'index.html'))).rejects.toThrow();
  });

  it('handles nested autocrud/lib/ subdirectories', async () => {
    await fs.mkdir(path.join(templateSrc, 'autocrud', 'lib', 'components'), { recursive: true });
    await fs.writeFile(path.join(templateSrc, 'autocrud', 'lib', 'components', 'Dashboard.tsx'), '<Dashboard />');

    await copyIntegrationFiles(templateSrc, targetSrc, { force: true });

    const dashboard = await fs.readFile(
      path.join(targetSrc, 'autocrud', 'lib', 'components', 'Dashboard.tsx'),
      'utf-8',
    );
    expect(dashboard).toBe('<Dashboard />');
  });

  it('gracefully handles missing template layout files', async () => {
    await fs.unlink(path.join(templateSrc, 'routes', 'autocrud-admin.tsx'));

    await copyIntegrationFiles(templateSrc, targetSrc, { force: true });

    const root = await fs.readFile(path.join(targetSrc, 'routes', '__root.tsx'), 'utf-8');
    expect(root).toBe('<Root />');

    await expect(fs.access(path.join(targetSrc, 'routes', 'autocrud-admin.tsx'))).rejects.toThrow();
  });

  describe('test file filtering', () => {
    beforeEach(async () => {
      await fs.mkdir(path.join(templateSrc, 'autocrud', 'lib'), { recursive: true });
      await fs.writeFile(path.join(templateSrc, 'autocrud', 'lib', 'client.ts'), 'export const client = {};');
      await fs.writeFile(path.join(templateSrc, 'autocrud', 'lib', 'client.test.ts'), 'test("client")');
      await fs.writeFile(path.join(templateSrc, 'autocrud', 'lib', 'resources.spec.ts'), 'test("resources")');
      await fs.mkdir(path.join(templateSrc, 'autocrud', 'lib', 'components'), { recursive: true });
      await fs.writeFile(path.join(templateSrc, 'autocrud', 'lib', 'components', 'Foo.tsx'), '<Foo />');
      await fs.writeFile(path.join(templateSrc, 'autocrud', 'lib', 'components', 'Foo.test.tsx'), 'test("Foo")');
      await fs.mkdir(path.join(templateSrc, 'autocrud', 'types'), { recursive: true });
      await fs.writeFile(path.join(templateSrc, 'autocrud', 'types', 'api.ts'), 'export type A = {};');
    });

    it('excludes test files by default', async () => {
      await copyIntegrationFiles(templateSrc, targetSrc, { force: true });

      const client = await fs.readFile(path.join(targetSrc, 'autocrud', 'lib', 'client.ts'), 'utf-8');
      expect(client).toBe('export const client = {};');

      const foo = await fs.readFile(path.join(targetSrc, 'autocrud', 'lib', 'components', 'Foo.tsx'), 'utf-8');
      expect(foo).toBe('<Foo />');

      await expect(fs.access(path.join(targetSrc, 'autocrud', 'lib', 'client.test.ts'))).rejects.toThrow();
      await expect(fs.access(path.join(targetSrc, 'autocrud', 'lib', 'resources.spec.ts'))).rejects.toThrow();
      await expect(fs.access(path.join(targetSrc, 'autocrud', 'lib', 'components', 'Foo.test.tsx'))).rejects.toThrow();
    });

    it('includes test files when includeTests is true', async () => {
      await copyIntegrationFiles(templateSrc, targetSrc, { includeTests: true, force: true });

      const client = await fs.readFile(path.join(targetSrc, 'autocrud', 'lib', 'client.ts'), 'utf-8');
      expect(client).toBe('export const client = {};');

      const testClient = await fs.readFile(path.join(targetSrc, 'autocrud', 'lib', 'client.test.ts'), 'utf-8');
      expect(testClient).toBe('test("client")');

      const specResources = await fs.readFile(path.join(targetSrc, 'autocrud', 'lib', 'resources.spec.ts'), 'utf-8');
      expect(specResources).toBe('test("resources")');

      const testFoo = await fs.readFile(path.join(targetSrc, 'autocrud', 'lib', 'components', 'Foo.test.tsx'), 'utf-8');
      expect(testFoo).toBe('test("Foo")');
    });
  });

  // ---------------------------------------------------------------------------
  // Conflict resolution tests
  // ---------------------------------------------------------------------------

  describe('conflict resolution', () => {
    beforeEach(() => {
      mockSelect.mockReset();
    });

    it('silently skips files with identical content (no prompt)', async () => {
      // Pre-create target with same content as template
      await fs.mkdir(path.join(targetSrc, 'routes'), { recursive: true });
      await fs.writeFile(path.join(targetSrc, 'routes', '__root.tsx'), '<Root />');

      await copyIntegrationFiles(templateSrc, targetSrc);

      // Should not have been prompted
      expect(mockSelect).not.toHaveBeenCalled();

      // Content should remain the same
      const root = await fs.readFile(path.join(targetSrc, 'routes', '__root.tsx'), 'utf-8');
      expect(root).toBe('<Root />');
    });

    it('prompts when layout file content differs', async () => {
      // Pre-create target with DIFFERENT content
      await fs.mkdir(path.join(targetSrc, 'routes'), { recursive: true });
      await fs.writeFile(path.join(targetSrc, 'routes', '__root.tsx'), '<MyCustomRoot />');

      // User chooses to skip
      mockSelect.mockResolvedValueOnce('skip');

      await copyIntegrationFiles(templateSrc, targetSrc);

      // Should have prompted at least once
      expect(mockSelect).toHaveBeenCalled();

      // Content should remain the user's version
      const root = await fs.readFile(path.join(targetSrc, 'routes', '__root.tsx'), 'utf-8');
      expect(root).toBe('<MyCustomRoot />');
    });

    it('overwrites when user chooses overwrite on changed layout file', async () => {
      await fs.mkdir(path.join(targetSrc, 'routes'), { recursive: true });
      await fs.writeFile(path.join(targetSrc, 'routes', '__root.tsx'), '<MyCustomRoot />');

      // User chooses to overwrite
      mockSelect.mockResolvedValueOnce('overwrite');

      await copyIntegrationFiles(templateSrc, targetSrc);

      // Content should be the template version
      const root = await fs.readFile(path.join(targetSrc, 'routes', '__root.tsx'), 'utf-8');
      expect(root).toBe('<Root />');
    });

    it('shows diff then asks again when user chooses diff', async () => {
      await fs.mkdir(path.join(targetSrc, 'routes'), { recursive: true });
      await fs.writeFile(path.join(targetSrc, 'routes', '__root.tsx'), '<MyCustomRoot />');

      // First select: show diff, second select: overwrite
      mockSelect.mockResolvedValueOnce('diff').mockResolvedValueOnce('overwrite');

      await copyIntegrationFiles(templateSrc, targetSrc);

      // Should have been prompted twice (diff then final decision)
      expect(mockSelect).toHaveBeenCalledTimes(2);

      // Content should be the template version (user chose overwrite after diff)
      const root = await fs.readFile(path.join(targetSrc, 'routes', '__root.tsx'), 'utf-8');
      expect(root).toBe('<Root />');
    });

    it('force mode skips all prompts and overwrites', async () => {
      await fs.mkdir(path.join(targetSrc, 'routes'), { recursive: true });
      await fs.writeFile(path.join(targetSrc, 'routes', '__root.tsx'), '<MyCustomRoot />');

      await copyIntegrationFiles(templateSrc, targetSrc, { force: true });

      // No prompts
      expect(mockSelect).not.toHaveBeenCalled();

      // Content should be overwritten
      const root = await fs.readFile(path.join(targetSrc, 'routes', '__root.tsx'), 'utf-8');
      expect(root).toBe('<Root />');
    });

    it('prompts for changed lib files too', async () => {
      // Pre-create lib file with different content
      await fs.mkdir(path.join(targetSrc, 'autocrud', 'lib'), { recursive: true });
      await fs.writeFile(path.join(targetSrc, 'autocrud', 'lib', 'client.ts'), 'MY CUSTOM CLIENT');

      // User chooses to skip
      mockSelect.mockResolvedValue('skip');

      await copyIntegrationFiles(templateSrc, targetSrc);

      // Should have been prompted
      expect(mockSelect).toHaveBeenCalled();

      // Content should remain custom
      const client = await fs.readFile(path.join(targetSrc, 'autocrud', 'lib', 'client.ts'), 'utf-8');
      expect(client).toBe('MY CUSTOM CLIENT');
    });

    it('creates new files without prompting even without force', async () => {
      // Target directory is empty — all files are new
      await copyIntegrationFiles(templateSrc, targetSrc);

      // No prompts needed for new files
      expect(mockSelect).not.toHaveBeenCalled();

      // Files should be created
      const root = await fs.readFile(path.join(targetSrc, 'routes', '__root.tsx'), 'utf-8');
      expect(root).toBe('<Root />');
    });
  });
});

// ---------------------------------------------------------------------------
// Unit tests for simpleDiff
// ---------------------------------------------------------------------------

describe('simpleDiff', () => {
  it('shows no changes for identical content', () => {
    const diff = simpleDiff('line1\nline2', 'line1\nline2', 'test.ts');
    expect(diff).toContain('  line1');
    expect(diff).toContain('  line2');
    // Only header lines start with --- / +++ ; no content lines should be prefixed
    const contentLines = diff.split('\n').slice(3); // skip header (---, +++, blank)
    for (const line of contentLines) {
      expect(line).not.toMatch(/^[+-] /);
    }
  });

  it('shows added and removed lines', () => {
    const diff = simpleDiff('old line', 'new line', 'test.ts');
    expect(diff).toContain('- old line');
    expect(diff).toContain('+ new line');
  });

  it('includes file label in header', () => {
    const diff = simpleDiff('a', 'b', 'routes/__root.tsx');
    expect(diff).toContain('--- existing routes/__root.tsx');
    expect(diff).toContain('+++ template routes/__root.tsx');
  });
});

// ---------------------------------------------------------------------------
// Unit tests for promptFileConflict
// ---------------------------------------------------------------------------

describe('promptFileConflict', () => {
  let tmpDir: string;

  beforeEach(async () => {
    tmpDir = fsSync.mkdtempSync(path.join(os.tmpdir(), 'autocrud-prompt-test-'));
    mockSelect.mockReset();
  });

  afterEach(async () => {
    await fs.rm(tmpDir, { recursive: true, force: true });
  });

  it('returns overwrite immediately when force is true', async () => {
    const src = path.join(tmpDir, 'src.ts');
    const dest = path.join(tmpDir, 'dest.ts');
    await fs.writeFile(src, 'template');
    await fs.writeFile(dest, 'custom');

    const action = await promptFileConflict('test.ts', src, dest, true);
    expect(action).toBe('overwrite');
    expect(mockSelect).not.toHaveBeenCalled();
  });

  it('returns skip when user selects skip', async () => {
    const src = path.join(tmpDir, 'src.ts');
    const dest = path.join(tmpDir, 'dest.ts');
    await fs.writeFile(src, 'template');
    await fs.writeFile(dest, 'custom');

    mockSelect.mockResolvedValueOnce('skip');

    const action = await promptFileConflict('test.ts', src, dest, false);
    expect(action).toBe('skip');
  });

  it('returns overwrite when user selects overwrite', async () => {
    const src = path.join(tmpDir, 'src.ts');
    const dest = path.join(tmpDir, 'dest.ts');
    await fs.writeFile(src, 'template');
    await fs.writeFile(dest, 'custom');

    mockSelect.mockResolvedValueOnce('overwrite');

    const action = await promptFileConflict('test.ts', src, dest, false);
    expect(action).toBe('overwrite');
  });

  it('shows diff then asks again when user selects diff', async () => {
    const src = path.join(tmpDir, 'src.ts');
    const dest = path.join(tmpDir, 'dest.ts');
    await fs.writeFile(src, 'template content');
    await fs.writeFile(dest, 'custom content');

    mockSelect.mockResolvedValueOnce('diff').mockResolvedValueOnce('skip');

    const action = await promptFileConflict('test.ts', src, dest, false);
    expect(action).toBe('skip');
    expect(mockSelect).toHaveBeenCalledTimes(2);
  });
});

// ============================================================================
// Template file content checks
// ============================================================================
describe('template content checks', () => {
  it('autocrud-admin.tsx uses @/ alias for resource imports', async () => {
    const templatePath = path.join(__dirname, '../../templates/base/src/routes/autocrud-admin.tsx');
    const content = await fs.readFile(templatePath, 'utf-8');
    expect(content).toContain("from '@/autocrud/lib/resources'");
    expect(content).not.toContain("from '../autocrud/lib/resources'");
  });

  it('ResourceCreate uses Container size="lg"', async () => {
    const templatePath = path.join(
      __dirname,
      '../../templates/base/src/autocrud/lib/components/form/ResourceCreate.tsx',
    );
    const content = await fs.readFile(templatePath, 'utf-8');
    expect(content).toContain('size="lg"');
    expect(content).not.toContain('size="md"');
  });

  it('vite.config.ts uses dynamic proxyPath from env instead of hardcoded /api', async () => {
    const templatePath = path.join(__dirname, '../../templates/base/vite.config.ts');
    const content = await fs.readFile(templatePath, 'utf-8');
    expect(content).toContain("const proxyPath = env.VITE_API_URL || '/api'");
    expect(content).toContain('[proxyPath]');
    expect(content).not.toMatch(/proxy:\s*\{\s*'\/api'/);
  });
});
