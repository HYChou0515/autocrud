import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import * as fs from 'fs/promises';
import * as fsSync from 'fs';
import * as path from 'path';
import * as os from 'os';
import { copyIntegrationFiles } from './integrate.js';

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

    // Create a minimal template structure
    await fs.mkdir(path.join(templateSrc, 'lib'), { recursive: true });
    await fs.mkdir(path.join(templateSrc, 'types'), { recursive: true });
    await fs.mkdir(path.join(templateSrc, 'routes'), { recursive: true });

    // Template files
    await fs.writeFile(path.join(templateSrc, 'lib', 'client.ts'), 'export const client = {};');
    await fs.writeFile(path.join(templateSrc, 'lib', 'resources.ts'), 'export const registry = {};');
    await fs.writeFile(path.join(templateSrc, 'types', 'api.ts'), 'export type FullResource = {};');
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

  it('copies lib/ directory', async () => {
    await copyIntegrationFiles(templateSrc, targetSrc);

    const client = await fs.readFile(path.join(targetSrc, 'lib', 'client.ts'), 'utf-8');
    expect(client).toBe('export const client = {};');

    const resources = await fs.readFile(path.join(targetSrc, 'lib', 'resources.ts'), 'utf-8');
    expect(resources).toBe('export const registry = {};');
  });

  it('copies types/ directory', async () => {
    await copyIntegrationFiles(templateSrc, targetSrc);

    const api = await fs.readFile(path.join(targetSrc, 'types', 'api.ts'), 'utf-8');
    expect(api).toBe('export type FullResource = {};');
  });

  it('copies layout route files', async () => {
    await copyIntegrationFiles(templateSrc, targetSrc);

    const root = await fs.readFile(path.join(targetSrc, 'routes', '__root.tsx'), 'utf-8');
    expect(root).toBe('<Root />');

    const admin = await fs.readFile(path.join(targetSrc, 'routes', 'autocrud-admin.tsx'), 'utf-8');
    expect(admin).toBe('<Admin />');
  });

  it('copies essential app files when they do not exist', async () => {
    await copyIntegrationFiles(templateSrc, targetSrc);

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

    await copyIntegrationFiles(templateSrc, targetSrc);

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
    // copyIntegrationFiles only operates within the SRC directory.
    // Verify that no package.json, tsconfig.json, or vite.config.ts
    // are created inside targetSrc (or its children).
    await copyIntegrationFiles(templateSrc, targetSrc);

    // These config files should NOT appear inside the target src/ directory
    await expect(fs.access(path.join(targetSrc, 'package.json'))).rejects.toThrow();
    await expect(fs.access(path.join(targetSrc, 'tsconfig.json'))).rejects.toThrow();
    await expect(fs.access(path.join(targetSrc, 'vite.config.ts'))).rejects.toThrow();
    await expect(fs.access(path.join(targetSrc, 'postcss.config.mjs'))).rejects.toThrow();
    await expect(fs.access(path.join(targetSrc, 'index.html'))).rejects.toThrow();
  });

  it('handles nested lib/ subdirectories', async () => {
    await fs.mkdir(path.join(templateSrc, 'lib', 'components'), { recursive: true });
    await fs.writeFile(path.join(templateSrc, 'lib', 'components', 'Dashboard.tsx'), '<Dashboard />');

    await copyIntegrationFiles(templateSrc, targetSrc);

    const dashboard = await fs.readFile(path.join(targetSrc, 'lib', 'components', 'Dashboard.tsx'), 'utf-8');
    expect(dashboard).toBe('<Dashboard />');
  });

  it('gracefully handles missing template layout files', async () => {
    // Remove one layout file from template
    await fs.unlink(path.join(templateSrc, 'routes', 'autocrud-admin.tsx'));

    // Should not throw
    await copyIntegrationFiles(templateSrc, targetSrc);

    // The existing one should still be copied
    const root = await fs.readFile(path.join(targetSrc, 'routes', '__root.tsx'), 'utf-8');
    expect(root).toBe('<Root />');

    // Missing one should not exist
    await expect(fs.access(path.join(targetSrc, 'routes', 'autocrud-admin.tsx'))).rejects.toThrow();
  });
});
