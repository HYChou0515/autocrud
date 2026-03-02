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
