import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import * as fs from 'fs/promises';
import * as fsSync from 'fs';
import * as path from 'path';
import * as os from 'os';
import { initProject } from './init.js';

describe('initProject', () => {
  let tmpDir: string;

  beforeEach(() => {
    tmpDir = fsSync.mkdtempSync(path.join(os.tmpdir(), 'autocrud-init-test-'));
    // Suppress console output during tests
    vi.spyOn(console, 'log').mockImplementation(() => {});
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(async () => {
    vi.restoreAllMocks();
    await fs.rm(tmpDir, { recursive: true, force: true });
  });

  it('creates a project with source files', async () => {
    await initProject('test-app', tmpDir);

    const projectPath = path.join(tmpDir, 'test-app');

    // Verify project directory exists
    const stat = await fs.stat(projectPath);
    expect(stat.isDirectory()).toBe(true);

    // Verify package.json is updated with project name
    const pkg = JSON.parse(await fs.readFile(path.join(projectPath, 'package.json'), 'utf-8'));
    expect(pkg.name).toBe('test-app');
  });

  it('excludes test files by default', async () => {
    await initProject('test-app', tmpDir);

    const srcDir = path.join(tmpDir, 'test-app', 'src');

    // Find all test files in the generated project
    const testFiles = await findTestFiles(srcDir);
    expect(testFiles).toHaveLength(0);
  });

  it('includes test files when includeTests is true', async () => {
    await initProject('test-app', tmpDir, { includeTests: true });

    const srcDir = path.join(tmpDir, 'test-app', 'src');

    // Find all test files in the generated project
    const testFiles = await findTestFiles(srcDir);
    expect(testFiles.length).toBeGreaterThan(0);
  });

  it('exits with error if directory already exists', async () => {
    const exitSpy = vi.spyOn(process, 'exit').mockImplementation((() => {}) as any);

    // Create the directory first
    await fs.mkdir(path.join(tmpDir, 'existing-app'));

    await initProject('existing-app', tmpDir);
    expect(exitSpy).toHaveBeenCalledWith(1);
  });

  // ---------------------------------------------------------------------------
  // Mantine version selection
  // ---------------------------------------------------------------------------

  it('defaults to Mantine 7 (no version-specific changes)', async () => {
    await initProject('test-app', tmpDir);

    const projectPath = path.join(tmpDir, 'test-app');
    const pkg = JSON.parse(await fs.readFile(path.join(projectPath, 'package.json'), 'utf-8'));

    // Should keep original v7 deps
    expect(pkg.dependencies['@mantine/core']).toMatch(/^\^7/);
    // Should still have mantine-form-zod-resolver
    expect(pkg.dependencies['mantine-form-zod-resolver']).toBeDefined();
    // Should NOT have pnpm overrides
    expect(pkg.pnpm).toBeUndefined();

    // .autocrudrc.json should exist with version 7
    const rc = JSON.parse(await fs.readFile(path.join(projectPath, '.autocrudrc.json'), 'utf-8'));
    expect(rc.mantineVersion).toBe('7');
  });

  it('applies Mantine 8 patches when mantineVersion is 8', async () => {
    await initProject('test-app', tmpDir, { mantineVersion: '8' });

    const projectPath = path.join(tmpDir, 'test-app');
    const pkg = JSON.parse(await fs.readFile(path.join(projectPath, 'package.json'), 'utf-8'));

    // Should have upgraded Mantine deps
    expect(pkg.dependencies['@mantine/core']).toMatch(/^\^8/);
    expect(pkg.dependencies['@mantine/form']).toMatch(/^\^8/);
    // React should be upgraded
    expect(pkg.dependencies['react']).toMatch(/^\^19/);
    // mantine-form-zod-resolver should be removed
    expect(pkg.dependencies['mantine-form-zod-resolver']).toBeUndefined();
    // Should have pnpm overrides
    expect(pkg.pnpm?.overrides?.['@mantine/core']).toMatch(/^\^8/);

    // .autocrudrc.json should record version 8
    const rc = JSON.parse(await fs.readFile(path.join(projectPath, '.autocrudrc.json'), 'utf-8'));
    expect(rc.mantineVersion).toBe('8');
  });

  it('patches zodResolver import for Mantine 8', async () => {
    await initProject('test-app', tmpDir, { mantineVersion: '8' });

    const formPath = path.join(
      tmpDir,
      'test-app',
      'src',
      'autocrud',
      'lib',
      'components',
      'form',
      'useResourceForm.ts',
    );
    const content = await fs.readFile(formPath, 'utf-8');
    expect(content).toContain("from '@mantine/form'");
    expect(content).not.toContain('mantine-form-zod-resolver');
  });
});

async function findTestFiles(dir: string): Promise<string[]> {
  const results: string[] = [];
  const TEST_FILE_RE = /\.(test|spec)\.[^.]+$/;

  async function walk(d: string) {
    let entries;
    try {
      entries = await fs.readdir(d, { withFileTypes: true });
    } catch {
      return;
    }
    for (const entry of entries) {
      const fullPath = path.join(d, entry.name);
      if (entry.isDirectory()) {
        await walk(fullPath);
      } else if (TEST_FILE_RE.test(entry.name)) {
        results.push(fullPath);
      }
    }
  }

  await walk(dir);
  return results;
}
