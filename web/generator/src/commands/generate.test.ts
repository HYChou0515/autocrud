/**
 * Tests for generate.ts entry-point utilities (detectBasePath, writeEnvFile).
 * Parser & codegen tests are in their own test files.
 */
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
          post: {
            requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/Character' } } } },
          },
        },
        '/skill': {
          post: {
            requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/Skill' } } } },
          },
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
          post: {
            requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/Character' } } } },
          },
        },
        '/foo/bar/skill': {
          post: {
            requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/Skill' } } } },
          },
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
    const spec = { paths: { '/character/{id}': { get: {} } } };
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
    expect(detectBasePath(spec)).toBe('');
  });
});

// ============================================================================
// detectBasePath — union type support
// ============================================================================
describe('detectBasePath — union types', () => {
  it('includes union type POST endpoints (anyOf) in base path detection', () => {
    const spec = {
      paths: {
        '/api/cat-or-dog': {
          post: {
            requestBody: {
              content: {
                'application/json': {
                  schema: { anyOf: [{ $ref: '#/components/schemas/Cat' }, { $ref: '#/components/schemas/Dog' }] },
                },
              },
            },
          },
        },
        '/api/character': {
          post: {
            requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/Character' } } } },
          },
        },
      },
      components: { schemas: {} },
    };
    expect(detectBasePath(spec)).toBe('/api');
  });

  it('detects base path from only union type endpoints', () => {
    const spec = {
      paths: {
        '/api/cat-or-dog': {
          post: {
            requestBody: {
              content: {
                'application/json': {
                  schema: { anyOf: [{ $ref: '#/components/schemas/Cat' }, { $ref: '#/components/schemas/Dog' }] },
                },
              },
            },
          },
        },
      },
      components: { schemas: {} },
    };
    expect(detectBasePath(spec)).toBe('/api');
  });

  it('detects base path from oneOf union endpoints', () => {
    const spec = {
      paths: {
        '/v1/pets': {
          post: {
            requestBody: {
              content: {
                'application/json': {
                  schema: { oneOf: [{ $ref: '#/components/schemas/Cat' }, { $ref: '#/components/schemas/Dog' }] },
                },
              },
            },
          },
        },
      },
      components: { schemas: {} },
    };
    expect(detectBasePath(spec)).toBe('/v1');
  });

  it('returns empty for root-level union endpoints', () => {
    const spec = {
      paths: {
        '/cat-or-dog': {
          post: {
            requestBody: {
              content: {
                'application/json': {
                  schema: { anyOf: [{ $ref: '#/components/schemas/Cat' }, { $ref: '#/components/schemas/Dog' }] },
                },
              },
            },
          },
        },
      },
      components: { schemas: {} },
    };
    expect(detectBasePath(spec)).toBe('');
  });

  it('ignores anyOf without $ref members (non-resource)', () => {
    const spec = {
      paths: {
        '/something': {
          post: {
            requestBody: {
              content: {
                'application/json': { schema: { anyOf: [{ type: 'string' }, { type: 'number' }] } },
              },
            },
          },
        },
      },
      components: { schemas: {} },
    };
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

  it('creates .env with VITE_API_URL and API_PROXY_TARGET when file does not exist', () => {
    writeEnvFile(tmpDir, 'http://localhost:8000');
    const content = fs.readFileSync(path.join(tmpDir, '.env'), 'utf-8');
    expect(content).toContain('VITE_API_URL=/api');
    expect(content).toContain('API_PROXY_TARGET=http://localhost:8000');
  });

  it('creates .env with proxy target including base path', () => {
    writeEnvFile(tmpDir, 'http://localhost:8000/foo/bar');
    const content = fs.readFileSync(path.join(tmpDir, '.env'), 'utf-8');
    expect(content).toContain('VITE_API_URL=/api');
    expect(content).toContain('API_PROXY_TARGET=http://localhost:8000/foo/bar');
  });

  it('updates existing VITE_API_URL and API_PROXY_TARGET without removing other vars', () => {
    const envPath = path.join(tmpDir, '.env');
    fs.writeFileSync(envPath, 'MY_VAR=hello\nVITE_API_URL=http://old:3000\nOTHER=world\n');
    writeEnvFile(tmpDir, 'http://localhost:9000/api');
    const content = fs.readFileSync(envPath, 'utf-8');
    expect(content).toContain('VITE_API_URL=/api');
    expect(content).toContain('API_PROXY_TARGET=http://localhost:9000/api');
    expect(content).toContain('MY_VAR=hello');
    expect(content).toContain('OTHER=world');
    expect(content.match(/VITE_API_URL/g)?.length).toBe(1);
  });

  it('adds VITE_API_URL and API_PROXY_TARGET to existing .env', () => {
    const envPath = path.join(tmpDir, '.env');
    fs.writeFileSync(envPath, 'MY_VAR=hello\nOTHER=world');
    writeEnvFile(tmpDir, 'http://localhost:8000');
    const content = fs.readFileSync(envPath, 'utf-8');
    expect(content).toContain('VITE_API_URL=/api');
    expect(content).toContain('API_PROXY_TARGET=http://localhost:8000');
    expect(content).toContain('MY_VAR=hello');
    expect(content).toContain('OTHER=world');
  });

  it('uses custom proxyPath for VITE_API_URL', () => {
    writeEnvFile(tmpDir, 'http://localhost:8000', '/foo/bar');
    const content = fs.readFileSync(path.join(tmpDir, '.env'), 'utf-8');
    expect(content).toContain('VITE_API_URL=/foo/bar');
    expect(content).toContain('API_PROXY_TARGET=http://localhost:8000');
    expect(content).not.toContain('VITE_API_URL=/api');
  });

  it('defaults proxyPath to /api when not specified', () => {
    writeEnvFile(tmpDir, 'http://localhost:8000');
    const content = fs.readFileSync(path.join(tmpDir, '.env'), 'utf-8');
    expect(content).toContain('VITE_API_URL=/api');
  });
});
