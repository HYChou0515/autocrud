/**
 * Tests for codegen/api-gen.ts — API client, backup, migrate, index generation.
 */
import { describe, it, expect } from 'vitest';
import { OpenAPIParser } from '../openapi-parser.js';
import { genApiClient, genApiIndex, genBackupApiClient, genMigrateApiClient } from './api-gen.js';

// ─── Helpers ────────────────────────────────────────────────────────────────

function parse(spec: any, basePath = '') {
  return new OpenAPIParser(spec, basePath).parse();
}

function buildSimpleSpec(basePath = '') {
  const prefix = basePath || '';
  return {
    info: { title: 'Test', version: '1.0' },
    paths: {
      [`${prefix}/character`]: { post: { requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/Character' } } } } } },
      [`${prefix}/skill`]: { post: { requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/Skill' } } } } } },
    },
    components: {
      schemas: {
        Character: { type: 'object', properties: { name: { type: 'string' }, level: { type: 'integer' } }, required: ['name', 'level'] },
        Skill: { type: 'object', properties: { name: { type: 'string' } }, required: ['name'] },
      },
    },
  };
}

function buildUnionSpec() {
  return {
    info: { title: 'Test', version: '1.0' },
    paths: {
      '/character': { post: { requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/Character' } } } } } },
      '/cat-or-dog': {
        post: {
          requestBody: {
            content: {
              'application/json': {
                schema: {
                  anyOf: [{ $ref: '#/components/schemas/Cat' }, { $ref: '#/components/schemas/Dog' }],
                  discriminator: { propertyName: 'type', mapping: { Cat: '#/components/schemas/Cat', Dog: '#/components/schemas/Dog' } },
                },
              },
            },
          },
        },
      },
      '/character/{id}': { get: {} },
      '/cat-or-dog/{id}': { get: {} },
    },
    components: {
      schemas: {
        Character: { type: 'object', properties: { name: { type: 'string' }, level: { type: 'integer' } }, required: ['name', 'level'] },
        Cat: { type: 'object', properties: { type: { type: 'string', enum: ['Cat'] }, name: { type: 'string' }, color: { type: 'string' } }, required: ['type', 'name', 'color'] },
        Dog: { type: 'object', properties: { type: { type: 'string', enum: ['Dog'] }, name: { type: 'string' }, breed: { type: 'string' } }, required: ['type', 'name', 'breed'] },
      },
    },
  };
}

function buildCustomActionSpec() {
  return {
    paths: {
      '/article': { post: { requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/Article' } } } } } },
      '/article/import-from-url': { post: { summary: 'Import from URL (article)', 'x-autocrud-create-action': { resource: 'article', label: 'Import from URL' }, requestBody: { content: { 'application/json': { schema: { type: 'object', properties: { url: { type: 'string' } }, required: ['url'], title: 'ImportFromUrl' } } } } } },
    },
    'x-autocrud-custom-create-actions': {
      article: [{ path: '/article/import-from-url', label: 'Import from URL', operationId: 'import_from_url', bodySchema: 'ImportFromUrl' }],
    },
    components: {
      schemas: {
        Article: { type: 'object', properties: { content: { type: 'string' } }, required: ['content'] },
        ImportFromUrl: { type: 'object', properties: { url: { type: 'string' } }, required: ['url'] },
      },
    },
  };
}

function buildCharacterSpec(actionOverrides: Record<string, any>) {
  return {
    paths: {
      '/character': { post: { requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/Character' } } } } } },
      '/character/{id}': { get: {} },
    },
    'x-autocrud-custom-create-actions': {
      character: [{ path: '/character/action', label: 'Test Action', operationId: 'test_action', ...actionOverrides }],
    },
    components: {
      schemas: { Character: { type: 'object', properties: { name: { type: 'string' } }, required: ['name'] } },
    },
  };
}

function buildMixedBodySchemaCharacterSpec() {
  const base = buildCharacterSpec({
    bodySchema: 'Skill', bodySchemaParamName: 'f',
    queryParams: [{ name: 'x', required: true, schema: { type: 'integer' } }, { name: 'y', required: true, schema: { type: 'string' } }],
    inlineBodyParams: [{ name: 'name', required: true, schema: { type: 'string' } }],
    fileParams: [{ name: 'z', required: true, schema: { type: 'string', format: 'binary' } }],
  });
  (base.components.schemas as any).Skill = {
    type: 'object',
    properties: { skname: { type: 'string' }, description: { type: 'string' }, required_level: { type: 'integer' } },
    required: ['skname'],
  };
  return base;
}

function buildJobSpec() {
  return {
    info: { title: 'Test', version: '1.0' },
    paths: {
      '/game-event': { post: { requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/GameEvent' } } } } } },
      '/game-event/{id}': { get: {} },
    },
    components: {
      schemas: {
        GameEvent: {
          type: 'object',
          properties: {
            payload: { type: 'object' },
            status: { type: 'string', default: 'pending' },
            errmsg: { type: 'string', default: '' },
            retries: { type: 'integer', default: 0 },
            artifact: { anyOf: [{ type: 'object' }, { type: 'null' }] },
            periodic_interval_seconds: { type: 'number', default: 0 },
            periodic_max_runs: { type: 'integer', default: 0 },
            periodic_runs: { type: 'integer', default: 0 },
            periodic_initial_delay_seconds: { type: 'number', default: 0 },
          },
          required: ['payload'],
        },
      },
    },
  };
}

// ============================================================================
// genApiClient — union types
// ============================================================================
describe('genApiClient — union types', () => {
  it('generates API for union resource using CatOrDog type import', () => {
    const resources = parse(buildUnionSpec());
    const union = resources.find((r) => r.name === 'cat-or-dog')!;
    const code = genApiClient(union, '');

    expect(code).toContain('CatOrDog');
    expect(code).toContain("'/cat-or-dog'");
  });
});

// ============================================================================
// genApiClient — Job resource getLogs
// ============================================================================
describe('genApiClient — Job resource', () => {
  it('generates getLogs method for Job API', () => {
    const resources = parse(buildJobSpec());
    const code = genApiClient(resources[0], '');

    expect(code).toContain('getLogs:');
    expect(code).toContain('/logs');
    expect(code).toContain('transformResponse');
  });

  it('does NOT generate getLogs for non-Job resource', () => {
    const spec = {
      info: { title: 'Test', version: '1.0' },
      paths: {
        '/user': { post: { requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/User' } } } } } },
        '/user/{id}': { get: {} },
      },
      components: { schemas: { User: { type: 'object', properties: { name: { type: 'string' } }, required: ['name'] } } },
    };
    const resources = parse(spec);
    const code = genApiClient(resources[0], '');

    expect(code).not.toContain('getLogs');
  });
});

// ============================================================================
// genApiClient — custom action paths use BASE variable
// ============================================================================
describe('genApiClient — custom action paths use BASE variable', () => {
  it('pure body schema action path uses ${BASE}', () => {
    const resources = parse(buildCustomActionSpec());
    const article = resources.find((r) => r.name === 'article')!;
    const api = genApiClient(article, '');

    expect(api).toContain('${BASE}/import-from-url');
    expect(api).not.toMatch(/client\.post<RevisionInfo>\('\/article\//);
  });

  it('path param action uses ${BASE} in template literal', () => {
    const spec = buildCharacterSpec({
      path: '/character/{name}/new',
      pathParams: [{ name: 'name', required: true, schema: { type: 'string' } }],
    });
    const resources = parse(spec);
    const api = genApiClient(resources.find((r) => r.name === 'character')!, '');

    expect(api).toContain('${BASE}/');
    expect(api).not.toMatch(/`\/character\//);
  });

  it('query-only action uses ${BASE}', () => {
    const spec = buildCharacterSpec({
      queryParams: [{ name: 'name', required: true, schema: { type: 'string' } }],
    });
    const resources = parse(spec);
    const api = genApiClient(resources.find((r) => r.name === 'character')!, '');

    expect(api).toContain('${BASE}/action');
    expect(api).not.toMatch(/client\.post<RevisionInfo>\('\/character\//);
  });

  it('inline body action uses ${BASE}', () => {
    const spec = buildCharacterSpec({
      inlineBodyParams: [{ name: 'name', required: true, schema: { type: 'string' } }],
    });
    const resources = parse(spec);
    const api = genApiClient(resources.find((r) => r.name === 'character')!, '');

    expect(api).toContain('${BASE}/action');
    expect(api).not.toMatch(/client\.post<RevisionInfo>\('\/character\//);
  });

  it('mixed body schema with file/query action uses ${BASE}', () => {
    const resources = parse(buildMixedBodySchemaCharacterSpec());
    const api = genApiClient(resources.find((r) => r.name === 'character')!, '');

    expect(api).toContain('${BASE}/action');
    expect(api).not.toMatch(/client\.post<RevisionInfo>\('\/character\//);
  });

  it('respects non-empty basePath in custom action paths', () => {
    const spec = {
      paths: {
        '/api/character': { post: { requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/Character' } } } } } },
        '/api/character/{id}': { get: {} },
      },
      'x-autocrud-custom-create-actions': {
        character: [{
          path: '/api/character/action', label: 'Test Action', operationId: 'test_action',
          queryParams: [{ name: 'q', required: false, schema: { type: 'string' } }],
        }],
      },
      components: { schemas: { Character: { type: 'object', properties: { name: { type: 'string' } }, required: ['name'] } } },
    };
    const resources = parse(spec, '/api');
    const api = genApiClient(resources.find((r) => r.name === 'character')!, '/api');

    expect(api).toContain("const BASE = '/api/character'");
    expect(api).toContain('${BASE}/action');
    expect(api).not.toContain("'/api/character/action'");
  });

  it('strips resource prefix when action.path lacks basePath prefix', () => {
    const spec = {
      paths: {
        '/v1/autocrud/character': { post: { requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/Character' } } } } } },
        '/v1/autocrud/character/{id}': { get: {} },
      },
      'x-autocrud-custom-create-actions': {
        character: [{
          path: '/character/{name}/new', label: 'New Character1', operationId: 'create_new_character1',
          pathParams: [{ name: 'name', required: true, schema: { type: 'string' } }],
        }],
      },
      components: { schemas: { Character: { type: 'object', properties: { name: { type: 'string' } }, required: ['name'] } } },
    };
    const resources = parse(spec, '/v1/autocrud');
    const api = genApiClient(resources.find((r) => r.name === 'character')!, '/v1/autocrud');

    expect(api).toContain("const BASE = '/v1/autocrud/character'");
    expect(api).toContain('${BASE}/');
    expect(api).not.toContain('/character/${allParams');
    expect(api).not.toContain('/character/character/');
  });

  it('strips resource prefix for query-only action when action.path lacks basePath', () => {
    const spec = {
      paths: {
        '/v1/autocrud/character': { post: { requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/Character' } } } } } },
      },
      'x-autocrud-custom-create-actions': {
        character: [{
          path: '/character/create-custom', label: 'Custom Create', operationId: 'custom_create',
          queryParams: [{ name: 'name', required: true, schema: { type: 'string' } }],
        }],
      },
      components: { schemas: { Character: { type: 'object', properties: { name: { type: 'string' } }, required: ['name'] } } },
    };
    const resources = parse(spec, '/v1/autocrud');
    const api = genApiClient(resources.find((r) => r.name === 'character')!, '/v1/autocrud');

    expect(api).toContain("const BASE = '/v1/autocrud/character'");
    expect(api).toContain('${BASE}/create-custom');
    expect(api).not.toContain('/character/create-custom');
  });

  it('strips resource prefix for body-schema action when action.path lacks basePath', () => {
    const spec = {
      paths: {
        '/v1/autocrud/character': { post: { requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/Character' } } } } } },
      },
      'x-autocrud-custom-create-actions': {
        character: [{
          path: '/character/import', label: 'Import Character', operationId: 'import_character',
          bodySchema: 'ImportPayload',
        }],
      },
      components: {
        schemas: {
          Character: { type: 'object', properties: { name: { type: 'string' } }, required: ['name'] },
          ImportPayload: { type: 'object', properties: { url: { type: 'string' } }, required: ['url'] },
        },
      },
    };
    const resources = parse(spec, '/v1/autocrud');
    const api = genApiClient(resources.find((r) => r.name === 'character')!, '/v1/autocrud');

    expect(api).toContain("const BASE = '/v1/autocrud/character'");
    expect(api).toContain('${BASE}/import');
    expect(api).not.toContain('/character/import');
  });
});

// ============================================================================
// genBackupApiClient
// ============================================================================
describe('genBackupApiClient', () => {
  it('generates backupApi with global export/import and per-model methods', () => {
    const resources = parse(buildSimpleSpec());
    const code = genBackupApiClient(resources, '');

    expect(code).toContain('export const backupApi');
    expect(code).toContain('exportAll');
    expect(code).toContain('importAll');
    expect(code).toContain('exportCharacter');
    expect(code).toContain('importCharacter');
    expect(code).toContain('exportSkill');
    expect(code).toContain('importSkill');
  });

  it('uses Axios client for all backup requests', () => {
    const resources = parse(buildSimpleSpec());
    const code = genBackupApiClient(resources, '');

    expect(code).toContain("import { client } from '../../lib/client'");
    expect(code).toContain('client.get');
    expect(code).toContain('client.post');
  });

  it('includes basePath in global backup endpoints when basePath is empty', () => {
    const resources = parse(buildSimpleSpec());
    const code = genBackupApiClient(resources, '');

    expect(code).toContain("'/_backup/export'");
    expect(code).toContain("'/_backup/import'");
  });

  it('includes basePath in global backup endpoints when basePath is set', () => {
    const resources = parse(buildSimpleSpec('/v1'), '/v1');
    const code = genBackupApiClient(resources, '/v1');

    expect(code).toContain("'/v1/_backup/export'");
    expect(code).toContain("'/v1/_backup/import'");
  });

  it('includes basePath in per-model export/import when basePath is empty', () => {
    const resources = parse(buildSimpleSpec());
    const code = genBackupApiClient(resources, '');

    expect(code).toContain('`/character/export`');
    expect(code).toContain('`/character/import`');
    expect(code).toContain('`/skill/export`');
    expect(code).toContain('`/skill/import`');
  });

  it('includes basePath in per-model export/import when basePath is set', () => {
    const resources = parse(buildSimpleSpec('/v1'), '/v1');
    const code = genBackupApiClient(resources, '/v1');

    expect(code).toContain('`/v1/character/export`');
    expect(code).toContain('`/v1/character/import`');
    expect(code).toContain('`/v1/skill/export`');
    expect(code).toContain('`/v1/skill/import`');
  });

  it('supports OnDuplicate type and defaults to overwrite', () => {
    const resources = parse(buildSimpleSpec());
    const code = genBackupApiClient(resources, '');

    expect(code).toContain("export type OnDuplicate = 'overwrite' | 'skip' | 'raise_error'");
    expect(code).toContain("onDuplicate: OnDuplicate = 'overwrite'");
  });

  it('uses blob responseType for export and multipart for import', () => {
    const resources = parse(buildSimpleSpec());
    const code = genBackupApiClient(resources, '');

    expect(code).toContain("responseType: 'blob'");
    expect(code).toContain("'Content-Type': 'multipart/form-data'");
  });
});

// ============================================================================
// genMigrateApiClient
// ============================================================================
describe('genMigrateApiClient', () => {
  it('generates migrateApi with MigrateProgress and MigrateResult types', () => {
    const code = genMigrateApiClient('');

    expect(code).toContain('export interface MigrateProgress');
    expect(code).toContain('export interface MigrateResult');
    expect(code).toContain('async function streamMigrate');
    expect(code).toContain('export const migrateApi');
    expect(code).toContain('test:');
    expect(code).toContain('execute:');
    expect(code).toContain('/migrate/');
    expect(code).toContain("'test'");
    expect(code).toContain("'execute'");
    expect(code).toContain('function buildMigrateUrl');
    expect(code).toContain('export type RevisionScope');
  });

  it('MigrateProgress interface has correct fields', () => {
    const code = genMigrateApiClient('');

    expect(code).toContain('resource_id: string');
    expect(code).toContain("status: 'migrating' | 'success' | 'failed' | 'skipped'");
    expect(code).toContain('message?: string');
    expect(code).toContain('error?: string');
  });

  it('MigrateResult interface has correct fields', () => {
    const code = genMigrateApiClient('');

    expect(code).toContain('total: number');
    expect(code).toContain('success: number');
    expect(code).toContain('failed: number');
    expect(code).toContain('skipped: number');
    expect(code).toContain('errors: Array<{ resource_id: string; error: string }>');
  });

  it('streamMigrate handles AbortSignal', () => {
    const code = genMigrateApiClient('');
    expect(code).toContain('signal?: AbortSignal');
  });

  it('test and execute accept revisionId parameter', () => {
    const code = genMigrateApiClient('');
    expect(code).toContain('revisionId?: RevisionScope');
    expect(code).toContain('buildMigrateUrl(');
  });

  it('imports getBaseUrl from shared client module', () => {
    const code = genMigrateApiClient('');

    expect(code).toContain("import { getBaseUrl } from '../../lib/client'");
    expect(code).not.toContain('function getBaseUrl');
    expect(code).not.toContain('VITE_API_URL');
  });

  it('includes basePath in migrate URLs when basePath is empty', () => {
    const code = genMigrateApiClient('');
    expect(code).toContain('buildMigrateUrl(`${getBaseUrl()}`');
  });

  it('includes basePath in migrate URLs when basePath is set', () => {
    const code = genMigrateApiClient('/v1');
    expect(code).toContain('buildMigrateUrl(`${getBaseUrl()}/v1`');
  });
});

// ============================================================================
// genApiIndex — migrate export
// ============================================================================
describe('genApiIndex — migrate export', () => {
  it('includes migrateApi export alongside backupApi', () => {
    const resources = parse(buildSimpleSpec());
    const code = genApiIndex(resources);

    expect(code).toContain("export { backupApi } from './backupApi'");
    expect(code).toContain("export { migrateApi } from './migrateApi'");
  });

  it('exports all resource APIs plus backup and migrate', () => {
    const resources = parse(buildSimpleSpec());
    const code = genApiIndex(resources);

    expect(code).toContain('characterApi');
    expect(code).toContain('skillApi');
    expect(code).toContain('backupApi');
    expect(code).toContain('migrateApi');
  });
});
