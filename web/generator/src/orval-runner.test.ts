/**
 * Tests for orval-runner.ts — Orval post-processing.
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';

import { postProcessOrvalOutput } from './orval-runner.js';

describe('postProcessOrvalOutput', () => {
  let tmpDir: string;

  beforeEach(() => {
    tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'orval-test-'));
  });

  afterEach(() => {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  });

  it('replaces z.array() with z.array(z.any())', () => {
    const typesPath = path.join(tmpDir, 'types.ts');
    fs.writeFileSync(typesPath, `export const itemSchema = z.object({ tags: z.array() });\n`);

    postProcessOrvalOutput(tmpDir);

    const result = fs.readFileSync(typesPath, 'utf-8');
    expect(result).toContain('z.array(z.any())');
    expect(result).not.toMatch(/z\.array\(\)/);
  });

  it('replaces zod.array() with zod.array(zod.any()) (namespace import)', () => {
    const typesPath = path.join(tmpDir, 'types.ts');
    fs.writeFileSync(typesPath, `export const itemSchema = zod.object({ tags: zod.array() });\n`);

    postProcessOrvalOutput(tmpDir);

    const result = fs.readFileSync(typesPath, 'utf-8');
    expect(result).toContain('zod.array(zod.any())');
    expect(result).not.toMatch(/zod\.array\(\)/);
  });

  it('does not modify z.array(z.string()) or other valid arrays', () => {
    const typesPath = path.join(tmpDir, 'types.ts');
    const original = `export const itemSchema = z.object({ tags: z.array(z.string()), data: z.array(z.number()) });\n`;
    fs.writeFileSync(typesPath, original);

    postProcessOrvalOutput(tmpDir);

    const result = fs.readFileSync(typesPath, 'utf-8');
    expect(result).toBe(original);
  });

  it('handles multiple z.array() occurrences', () => {
    const typesPath = path.join(tmpDir, 'types.ts');
    fs.writeFileSync(
      typesPath,
      `export const schema = z.object({ a: z.array(), b: z.array(), c: z.array(z.string()) });\n`,
    );

    postProcessOrvalOutput(tmpDir);

    const result = fs.readFileSync(typesPath, 'utf-8');
    expect(result).toContain('a: z.array(z.any())');
    expect(result).toContain('b: z.array(z.any())');
    expect(result).toContain('c: z.array(z.string())');
  });

  it('does nothing when types.ts does not exist', () => {
    // Should not throw
    expect(() => postProcessOrvalOutput(tmpDir)).not.toThrow();
  });

  it('does nothing when no z.array() patterns exist', () => {
    const typesPath = path.join(tmpDir, 'types.ts');
    const original = `export const schema = z.object({ name: z.string() });\n`;
    fs.writeFileSync(typesPath, original);

    postProcessOrvalOutput(tmpDir);

    const result = fs.readFileSync(typesPath, 'utf-8');
    expect(result).toBe(original);
  });
});
