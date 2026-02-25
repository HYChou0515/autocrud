import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { detectBasePath, writeEnvFile } from './generate.js';

// ============================================================================
// detectBasePath
// ============================================================================
describe('detectBasePath', () => {
  it('returns empty string for root-level paths', () => {
    const spec = {
      paths: {
        '/character': {
          post: { requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/Character' } } } } },
        },
        '/skill': {
          post: { requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/Skill' } } } } },
        },
        '/character/{id}': { get: {} },
      },
    };
    expect(detectBasePath(spec)).toBe('');
  });

  it('detects common prefix from paths with single prefix', () => {
    const spec = {
      paths: {
        '/foo/bar/character': {
          post: { requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/Character' } } } } },
        },
        '/foo/bar/skill': {
          post: { requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/Skill' } } } } },
        },
        '/foo/bar/character/{id}': { get: {} },
        '/foo/bar/skill/{id}/revision-list': { get: {} },
      },
    };
    expect(detectBasePath(spec)).toBe('/foo/bar');
  });

  it('detects single-segment prefix', () => {
    const spec = {
      paths: {
        '/api/users': {
          post: { requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/User' } } } } },
        },
        '/api/posts': {
          post: { requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/Post' } } } } },
        },
      },
    };
    expect(detectBasePath(spec)).toBe('/api');
  });

  it('returns empty string when no POST endpoints exist', () => {
    const spec = {
      paths: {
        '/character/{id}': { get: {} },
      },
    };
    expect(detectBasePath(spec)).toBe('');
  });

  it('returns empty string when no paths exist', () => {
    expect(detectBasePath({ paths: {} })).toBe('');
    expect(detectBasePath({})).toBe('');
  });

  it('handles POST without $ref (non-resource)', () => {
    const spec = {
      paths: {
        '/character': {
          post: { requestBody: { content: { 'application/json': { schema: { type: 'object' } } } } },
        },
      },
    };
    expect(detectBasePath(spec)).toBe('');
  });

  it('finds longest common prefix when prefixes differ', () => {
    const spec = {
      paths: {
        '/api/v1/users': {
          post: { requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/User' } } } } },
        },
        '/api/v2/posts': {
          post: { requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/Post' } } } } },
        },
      },
    };
    // common prefix of '/api/v1' and '/api/v2' is '/api'
    expect(detectBasePath(spec)).toBe('/api');
  });

  it('returns empty when prefixes have no common path', () => {
    const spec = {
      paths: {
        '/users': {
          post: { requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/User' } } } } },
        },
        '/api/posts': {
          post: { requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/Post' } } } } },
        },
      },
    };
    // Prefixes: '' and '/api' → common is ''
    expect(detectBasePath(spec)).toBe('');
  });
});

// ============================================================================
// writeEnvFile
// ============================================================================
describe('writeEnvFile', () => {
  let tmpDir: string;

  beforeEach(() => {
    tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'autocrud-test-'));
  });

  afterEach(() => {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  });

  it('creates .env with VITE_API_URL when file does not exist', () => {
    writeEnvFile(tmpDir, 'http://localhost:8000');
    const content = fs.readFileSync(path.join(tmpDir, '.env'), 'utf-8');
    expect(content).toBe('VITE_API_URL=http://localhost:8000\n');
  });

  it('creates .env with base path in URL', () => {
    writeEnvFile(tmpDir, 'http://localhost:8000/foo/bar');
    const content = fs.readFileSync(path.join(tmpDir, '.env'), 'utf-8');
    expect(content).toBe('VITE_API_URL=http://localhost:8000/foo/bar\n');
  });

  it('updates existing VITE_API_URL line without removing other vars', () => {
    const envPath = path.join(tmpDir, '.env');
    fs.writeFileSync(envPath, 'MY_VAR=hello\nVITE_API_URL=http://old:3000\nOTHER=world\n');
    writeEnvFile(tmpDir, 'http://localhost:9000/api');
    const content = fs.readFileSync(envPath, 'utf-8');
    expect(content).toContain('VITE_API_URL=http://localhost:9000/api');
    expect(content).toContain('MY_VAR=hello');
    expect(content).toContain('OTHER=world');
    // Should not have duplicate VITE_API_URL
    expect(content.match(/VITE_API_URL/g)?.length).toBe(1);
  });

  it('adds VITE_API_URL to existing .env that does not have it', () => {
    const envPath = path.join(tmpDir, '.env');
    fs.writeFileSync(envPath, 'MY_VAR=hello\nOTHER=world');
    writeEnvFile(tmpDir, 'http://localhost:8000');
    const content = fs.readFileSync(envPath, 'utf-8');
    expect(content).toContain('VITE_API_URL=http://localhost:8000');
    expect(content).toContain('MY_VAR=hello');
    expect(content).toContain('OTHER=world');
  });
});
