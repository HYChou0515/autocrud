/**
 * Tests for codegen/resources-gen.ts — Resource registry configuration generation.
 */
import { describe, it, expect } from 'vitest';
import { buildIR } from '../test-helpers.js';
import { genResourcesConfig } from './resources-gen.js';

// ─── Helpers ────────────────────────────────────────────────────────────────

function parseAndGenConfig(spec: any, basePath = '') {
  const { resources, builder } = buildIR(spec, basePath);
  return genResourcesConfig(resources, basePath, spec, (r) => builder.getJobHiddenFields(r));
}

function buildSimpleSpec(basePath = '') {
  const prefix = basePath || '';
  return {
    info: { title: 'Test', version: '1.0' },
    paths: {
      [`${prefix}/character`]: {
        post: {
          requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/Character' } } } },
        },
      },
      [`${prefix}/skill`]: {
        post: { requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/Skill' } } } } },
      },
    },
    components: {
      schemas: {
        Character: {
          type: 'object',
          properties: { name: { type: 'string' }, level: { type: 'integer' } },
          required: ['name', 'level'],
        },
        Skill: { type: 'object', properties: { name: { type: 'string' } }, required: ['name'] },
      },
    },
  };
}

function buildUnionSpec() {
  return {
    info: { title: 'Test', version: '1.0' },
    paths: {
      '/character': {
        post: {
          requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/Character' } } } },
        },
      },
      '/cat-or-dog': {
        post: {
          requestBody: {
            content: {
              'application/json': {
                schema: {
                  anyOf: [{ $ref: '#/components/schemas/Cat' }, { $ref: '#/components/schemas/Dog' }],
                  discriminator: {
                    propertyName: 'type',
                    mapping: { Cat: '#/components/schemas/Cat', Dog: '#/components/schemas/Dog' },
                  },
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
        Character: {
          type: 'object',
          properties: { name: { type: 'string' }, level: { type: 'integer' } },
          required: ['name', 'level'],
        },
        Cat: {
          type: 'object',
          properties: { type: { type: 'string', enum: ['Cat'] }, name: { type: 'string' }, color: { type: 'string' } },
          required: ['type', 'name', 'color'],
        },
        Dog: {
          type: 'object',
          properties: { type: { type: 'string', enum: ['Dog'] }, name: { type: 'string' }, breed: { type: 'string' } },
          required: ['type', 'name', 'breed'],
        },
      },
    },
  };
}

function buildJobSpec() {
  return {
    info: { title: 'Test', version: '1.0' },
    paths: {
      '/game-event': {
        post: {
          requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/GameEvent' } } } },
        },
      },
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
// genResourcesConfig — union types
// ============================================================================
describe('genResourcesConfig — union types', () => {
  it('generates union resource config with isUnion flag', () => {
    const code = parseAndGenConfig(buildUnionSpec());
    expect(code).toContain('isUnion: true');
    expect(code).toContain("'cat-or-dog'");
  });

  it('generates both normal and union resource configs', () => {
    const code = parseAndGenConfig(buildUnionSpec());
    expect(code).toContain("'character'");
    expect(code).toContain("'cat-or-dog'");
  });
});

// ============================================================================
// genResourcesConfig — Job defaultHiddenFields
// ============================================================================
describe('genResourcesConfig — Job defaultHiddenFields', () => {
  it('includes defaultHiddenFields for Job resource', () => {
    const code = parseAndGenConfig(buildJobSpec());
    expect(code).toContain('defaultHiddenFields:');
    expect(code).toContain('status');
    expect(code).toContain('errmsg');
    expect(code).toContain('retries');
  });

  it('includes artifact in defaultHiddenFields for Job resource with artifact', () => {
    const code = parseAndGenConfig(buildJobSpec());
    expect(code).toContain('defaultHiddenFields:');
    expect(code).toContain("'artifact'");
  });

  it('hides expanded artifact sub-fields (dot-notation) in defaultHiddenFields', () => {
    // When artifact is a typed struct (e.g. GameEventArtifact),
    // extractFields expands it to artifact.process_times etc.
    // These expanded fields should still be hidden.
    const spec = {
      info: { title: 'Test', version: '1.0' },
      paths: {
        '/game-event': {
          post: {
            requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/GameEvent' } } } },
          },
        },
        '/game-event/{id}': { get: {} },
      },
      components: {
        schemas: {
          GameEventArtifact: {
            type: 'object',
            properties: { process_times: { type: 'number' } },
            required: ['process_times'],
          },
          GameEvent: {
            type: 'object',
            properties: {
              payload: { type: 'object', properties: { event_type: { type: 'string' } }, required: ['event_type'] },
              status: { type: 'string', default: 'pending' },
              errmsg: { type: 'string', default: '' },
              artifact: {
                anyOf: [{ $ref: '#/components/schemas/GameEventArtifact' }, { type: 'null' }],
                default: null,
              },
              retries: { type: 'integer', default: 0 },
              max_retries: { type: 'integer', default: 0 },
              periodic_interval_seconds: { type: 'number', default: 0 },
              periodic_max_runs: { type: 'integer', default: 0 },
              periodic_runs: { type: 'integer', default: 0 },
              periodic_initial_delay_seconds: { type: 'number', default: 0 },
              last_heartbeat_at: { type: 'string' },
            },
            required: ['payload'],
          },
        },
      },
    };
    const code = parseAndGenConfig(spec);
    expect(code).toContain('defaultHiddenFields:');
    // artifact.process_times should be in hidden fields
    const hiddenMatch = code.match(/defaultHiddenFields:\s*\[([^\]]*)\]/);
    expect(hiddenMatch).not.toBeNull();
    const hiddenFields = hiddenMatch![1];
    expect(hiddenFields).toContain('artifact.process_times');
  });

  it('does NOT include defaultHiddenFields for non-Job resource', () => {
    const spec = {
      info: { title: 'Test', version: '1.0' },
      paths: {
        '/user': {
          post: { requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/User' } } } } },
        },
        '/user/{id}': { get: {} },
      },
      components: {
        schemas: { User: { type: 'object', properties: { name: { type: 'string' } }, required: ['name'] } },
      },
    };
    const code = parseAndGenConfig(spec);
    expect(code).not.toContain('defaultHiddenFields');
  });

  it('does NOT include isJob property in output', () => {
    const code = parseAndGenConfig(buildJobSpec());
    expect(code).not.toContain('isJob:');
  });
});

// ============================================================================
// genResourcesConfig — custom actions with bodySchema
// ============================================================================
describe('genResourcesConfig — custom create actions', () => {
  function buildCustomActionSpec() {
    return {
      paths: {
        '/article': {
          post: {
            requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/Article' } } } },
          },
        },
        '/article/import-from-url': {
          post: {
            summary: 'Import',
            'x-autocrud-create-action': { resource: 'article', label: 'Import from URL' },
            requestBody: {
              content: {
                'application/json': {
                  schema: {
                    type: 'object',
                    properties: { url: { type: 'string' } },
                    required: ['url'],
                    title: 'ImportFromUrl',
                  },
                },
              },
            },
          },
        },
      },
      'x-autocrud-custom-create-actions': {
        article: [
          {
            path: '/article/import-from-url',
            label: 'Import from URL',
            operationId: 'import_from_url',
            bodySchema: 'ImportFromUrl',
          },
        ],
      },
      components: {
        schemas: {
          Article: { type: 'object', properties: { content: { type: 'string' } }, required: ['content'] },
          ImportFromUrl: { type: 'object', properties: { url: { type: 'string' } }, required: ['url'] },
        },
      },
    };
  }

  it('generates customCreateActions block', () => {
    const code = parseAndGenConfig(buildCustomActionSpec());
    expect(code).toContain('customCreateActions');
    expect(code).toContain('Import from URL');
  });
});

// ============================================================================
// genResourcesConfig — constValue serialization
// ============================================================================
describe('genResourcesConfig — constValue serialization', () => {
  it('preserves constValue in field serialization', () => {
    const spec = {
      info: { title: 'Test', version: '1.0' },
      paths: {
        '/item': {
          post: {
            requestBody: {
              content: {
                'application/json': {
                  schema: { $ref: '#/components/schemas/Carrot' },
                },
              },
            },
          },
        },
      },
      components: {
        schemas: {
          Carrot: {
            type: 'object',
            properties: { type: { type: 'string', enum: ['Carrot'] }, weight: { type: 'number' } },
            required: ['type', 'weight'],
          },
        },
      },
    };
    const code = parseAndGenConfig(spec);
    expect(code).toContain('constValue: "Carrot"');
  });
});

// ============================================================================
// genResourcesConfig — enum serialization
// ============================================================================
describe('genResourcesConfig — enum serialization', () => {
  it('serializes enumValues in resource config', () => {
    const spec = {
      info: { title: 'Test', version: '1.0' },
      paths: {
        '/character': {
          post: {
            requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/Character' } } } },
          },
        },
      },
      'x-autocrud-custom-create-actions': {
        character: [
          {
            path: '/character/action',
            label: 'Test Action',
            operationId: 'test_action',
            queryParams: [
              { name: 'role', required: true, schema: { type: 'string', enum: ['warrior', 'mage', 'archer'] } },
            ],
          },
        ],
      },
      components: {
        schemas: { Character: { type: 'object', properties: { name: { type: 'string' } }, required: ['name'] } },
      },
    };
    const code = parseAndGenConfig(spec);
    expect(code).toContain('enumValues');
    expect(code).toContain('warrior');
  });
});

// ============================================================================
// genResourcesConfig — async create action metadata
// ============================================================================
describe('genResourcesConfig — async create action metadata', () => {
  function buildAsyncCreateActionSpec() {
    return {
      paths: {
        '/article': {
          post: {
            requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/Article' } } } },
          },
        },
        '/article/generate-article': {
          post: {
            requestBody: {
              content: {
                'application/json': {
                  schema: {
                    type: 'object',
                    properties: { prompt: { type: 'string' }, title: { type: 'string' } },
                    required: ['prompt', 'title'],
                    title: 'ArticleRequest',
                  },
                },
              },
            },
          },
        },
        '/generate-article-job': { get: {} },
        '/generate-article-job/{id}': { get: {} },
      },
      'x-autocrud-custom-create-actions': {
        article: [
          {
            path: '/article/generate-article',
            label: 'Generate',
            operationId: 'generate_article',
            bodySchema: 'ArticleRequest',
            asyncMode: 'job',
            jobResourceName: 'generate-article-job',
          },
        ],
      },
      'x-autocrud-async-create-jobs': { 'generate-article-job': 'article' },
      components: {
        schemas: {
          Article: {
            type: 'object',
            properties: { title: { type: 'string' }, content: { type: 'string' } },
            required: ['title', 'content'],
          },
          ArticleRequest: {
            type: 'object',
            properties: { prompt: { type: 'string' }, title: { type: 'string' } },
            required: ['prompt', 'title'],
          },
        },
      },
    };
  }

  it('emits asyncMode and jobResourceName in resource config', () => {
    const code = parseAndGenConfig(buildAsyncCreateActionSpec());
    expect(code).toContain("asyncMode: 'job'");
    expect(code).toContain("jobResourceName: 'generate-article-job'");
  });

  it('does not emit asyncMode for sync actions', () => {
    const spec = {
      paths: {
        '/article': {
          post: {
            requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/Article' } } } },
          },
        },
        '/article/import-from-url': { post: {} },
      },
      'x-autocrud-custom-create-actions': {
        article: [
          {
            path: '/article/import-from-url',
            label: 'Import',
            operationId: 'import_from_url',
            bodySchema: 'ImportFromUrl',
          },
        ],
      },
      components: {
        schemas: {
          Article: { type: 'object', properties: { content: { type: 'string' } }, required: ['content'] },
          ImportFromUrl: { type: 'object', properties: { url: { type: 'string' } }, required: ['url'] },
        },
      },
    };
    const code = parseAndGenConfig(spec);
    expect(code).not.toContain('asyncMode');
    expect(code).not.toContain('jobResourceName');
  });

  it('emits asyncCreateJobs mapping from x-autocrud-async-create-jobs', () => {
    const code = parseAndGenConfig(buildAsyncCreateActionSpec());
    expect(code).toContain('asyncCreateJobs');
    expect(code).toContain("'generate-article-job': 'article'");
  });

  it('emits tableConfig.canCreate=false for async create job resources', () => {
    // Build a spec where generate-article-job is a full resource (with POST)
    const spec = {
      ...buildAsyncCreateActionSpec(),
      paths: {
        ...buildAsyncCreateActionSpec().paths,
        '/generate-article-job': {
          post: {
            requestBody: {
              content: {
                'application/json': {
                  schema: { $ref: '#/components/schemas/GenerateArticleJob' },
                },
              },
            },
          },
        },
      },
      components: {
        schemas: {
          ...buildAsyncCreateActionSpec().components.schemas,
          GenerateArticleJob: {
            type: 'object',
            properties: {
              payload: { type: 'object' },
              status: { type: 'string', default: 'pending' },
            },
            required: ['payload'],
          },
        },
      },
    };
    const code = parseAndGenConfig(spec);
    // The generate-article-job resource config block should contain tableConfig
    // Find the config block inside Object.assign(registry, { ... })
    const registryBlock = code.split('Object.assign(registry,')[1]?.split('});')[0] ?? '';
    const jobConfigStart = registryBlock.indexOf("'generate-article-job':");
    expect(jobConfigStart).toBeGreaterThan(-1);
    const jobConfigBlock = registryBlock.substring(jobConfigStart, jobConfigStart + 800);
    expect(jobConfigBlock).toContain('tableConfig: { canCreate: false }');
  });

  it('does NOT emit tableConfig.canCreate for parent resource (article)', () => {
    const spec = {
      ...buildAsyncCreateActionSpec(),
      paths: {
        ...buildAsyncCreateActionSpec().paths,
        '/generate-article-job': {
          post: {
            requestBody: {
              content: {
                'application/json': {
                  schema: { $ref: '#/components/schemas/GenerateArticleJob' },
                },
              },
            },
          },
        },
      },
      components: {
        schemas: {
          ...buildAsyncCreateActionSpec().components.schemas,
          GenerateArticleJob: {
            type: 'object',
            properties: { payload: { type: 'object' } },
            required: ['payload'],
          },
        },
      },
    };
    const code = parseAndGenConfig(spec);
    // Extract the article config block from the registry
    const registryBlock = code.split('Object.assign(registry,')[1]?.split('});')[0] ?? '';
    const articleStart = registryBlock.indexOf("'article':");
    const jobStart = registryBlock.indexOf("'generate-article-job':");
    const articleBlock = registryBlock.substring(articleStart, jobStart);
    expect(articleBlock).not.toContain('tableConfig');
  });

  it('does NOT emit tableConfig.canCreate for regular job resource not in asyncCreateJobs', () => {
    const code = parseAndGenConfig(buildJobSpec());
    expect(code).not.toContain('tableConfig');
  });

  it('does not emit asyncCreateJobs when no async jobs exist', () => {
    const spec = {
      paths: {
        '/article': {
          post: {
            requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/Article' } } } },
          },
        },
        '/article/import-from-url': { post: {} },
      },
      'x-autocrud-custom-create-actions': {
        article: [
          {
            path: '/article/import-from-url',
            label: 'Import',
            operationId: 'import_from_url',
            bodySchema: 'ImportFromUrl',
          },
        ],
      },
      components: {
        schemas: {
          Article: { type: 'object', properties: { content: { type: 'string' } }, required: ['content'] },
          ImportFromUrl: { type: 'object', properties: { url: { type: 'string' } }, required: ['url'] },
        },
      },
    };
    const code = parseAndGenConfig(spec);
    expect(code).not.toContain('asyncCreateJobs');
  });
});

// ============================================================================
// genResourcesConfig — setApiBasePath injection
// ============================================================================
describe('genResourcesConfig — setApiBasePath injection', () => {
  it('emits setApiBasePath with basePath when basePath is non-empty', () => {
    const spec = {
      paths: {
        '/v1/autocrud/character': {
          post: {
            requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/Character' } } } },
          },
        },
      },
      components: {
        schemas: { Character: { type: 'object', properties: { name: { type: 'string' } }, required: ['name'] } },
      },
    };
    const code = parseAndGenConfig(spec, '/v1/autocrud');

    expect(code).toContain("import { setApiBasePath } from '../lib/client'");
    expect(code).toContain("setApiBasePath('/v1/autocrud')");
  });

  it('emits setApiBasePath with empty string when no basePath', () => {
    const spec = {
      paths: {
        '/character': {
          post: {
            requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/Character' } } } },
          },
        },
      },
      components: {
        schemas: { Character: { type: 'object', properties: { name: { type: 'string' } }, required: ['name'] } },
      },
    };
    const code = parseAndGenConfig(spec, '');

    expect(code).toContain("setApiBasePath('')");
  });
});

// ============================================================================
// genResourcesConfig — structural union field serialization
// ============================================================================
describe('genResourcesConfig — structural union field serialization', () => {
  it('serializes isArray in structural union variant', () => {
    const spec = {
      info: { title: 'Test', version: '1.0' },
      paths: {
        '/payload': {
          post: {
            requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/Payload' } } } },
          },
        },
        '/payload/{id}': { get: {} },
      },
      components: {
        schemas: {
          EventBodyX: {
            type: 'object',
            properties: {
              type: { type: 'string', enum: ['EventBodyX'], const: 'EventBodyX' },
              good: { type: 'string' },
              great: { type: 'integer' },
            },
            required: ['type', 'good', 'great'],
          },
          Payload: {
            type: 'object',
            properties: {
              name: { type: 'string' },
              event_x3: {
                anyOf: [
                  { type: 'array', items: { $ref: '#/components/schemas/EventBodyX' } },
                  { $ref: '#/components/schemas/EventBodyX' },
                ],
              },
            },
            required: ['name'],
          },
        },
      },
    };
    const code = parseAndGenConfig(spec);
    expect(code).toContain('isArray: true');
    expect(code).toContain('__variant');
  });
});

// ============================================================================
// buildNestedZodFields — nullable optional struct grouping
// ============================================================================
describe('buildNestedZodFields — nullable optional struct grouping', () => {
  it('nested group from nullable optional parent gets .nullable().optional()', () => {
    const spec = {
      info: { title: 'Test', version: '1.0' },
      paths: {
        '/game-event': {
          post: {
            requestBody: {
              content: {
                'application/json': {
                  schema: { $ref: '#/components/schemas/GameEvent' },
                },
              },
            },
          },
        },
        '/game-event/{id}': { get: {} },
      },
      components: {
        schemas: {
          GameEventArtifact: {
            type: 'object',
            properties: {
              process_times: { type: 'number' },
            },
            required: ['process_times'],
          },
          GameEvent: {
            type: 'object',
            properties: {
              payload: {
                type: 'object',
                properties: { event_type: { type: 'string' } },
                required: ['event_type'],
              },
              status: { type: 'string', default: 'pending' },
              artifact: {
                anyOf: [{ $ref: '#/components/schemas/GameEventArtifact' }, { type: 'null' }],
                default: null,
              },
            },
            required: ['payload'],
          },
        },
      },
    };
    const code = parseAndGenConfig(spec);
    // artifact z.object should be nullable and optional
    expect(code).toMatch(/artifact:\s*z\.object\(\{[^}]*\}\)\.nullable\(\)\.optional\(\)/);
  });

  it('nested group from required parent should NOT get .optional()', () => {
    const spec = {
      info: { title: 'Test', version: '1.0' },
      paths: {
        '/game-event': {
          post: {
            requestBody: {
              content: {
                'application/json': {
                  schema: { $ref: '#/components/schemas/GameEvent' },
                },
              },
            },
          },
        },
        '/game-event/{id}': { get: {} },
      },
      components: {
        schemas: {
          GameEvent: {
            type: 'object',
            properties: {
              payload: {
                type: 'object',
                properties: { event_type: { type: 'string' } },
                required: ['event_type'],
              },
            },
            required: ['payload'],
          },
        },
      },
    };
    const code = parseAndGenConfig(spec);
    // payload z.object should NOT be optional or nullable (it's required)
    expect(code).toMatch(/payload:\s*z\.object\(\{[^}]*\}\)[,\s]/);
    expect(code).not.toMatch(/payload:\s*z\.object\(\{[^}]*\}\)\.optional\(\)/);
    expect(code).not.toMatch(/payload:\s*z\.object\(\{[^}]*\}\)\.nullable\(\)/);
  });
});
