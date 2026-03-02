import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { detectBasePath, writeEnvFile, Generator } from './generate.js';

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
    // Should not have duplicate VITE_API_URL
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
});

// ============================================================================
// Helper: build a mock OpenAPI spec with Cat | Dog union type resource
// ============================================================================
function buildUnionSpec(basePath: string = '') {
  const prefix = basePath ? basePath : '';
  return {
    info: { title: 'Test', version: '1.0' },
    paths: {
      [`${prefix}/character`]: {
        post: {
          requestBody: {
            content: { 'application/json': { schema: { $ref: '#/components/schemas/Character' } } },
          },
        },
      },
      [`${prefix}/cat-or-dog`]: {
        post: {
          requestBody: {
            content: {
              'application/json': {
                schema: {
                  anyOf: [{ $ref: '#/components/schemas/Cat' }, { $ref: '#/components/schemas/Dog' }],
                  discriminator: {
                    propertyName: 'type',
                    mapping: {
                      Cat: '#/components/schemas/Cat',
                      Dog: '#/components/schemas/Dog',
                    },
                  },
                },
              },
            },
          },
        },
      },
      [`${prefix}/cat-or-dog/{id}`]: { get: {} },
      [`${prefix}/character/{id}`]: { get: {} },
    },
    components: {
      schemas: {
        Character: {
          type: 'object',
          properties: {
            name: { type: 'string' },
            level: { type: 'integer' },
          },
          required: ['name', 'level'],
        },
        Cat: {
          type: 'object',
          properties: {
            type: { type: 'string', enum: ['Cat'] },
            name: { type: 'string' },
            color: { type: 'string' },
          },
          required: ['type', 'name', 'color'],
        },
        Dog: {
          type: 'object',
          properties: {
            type: { type: 'string', enum: ['Dog'] },
            name: { type: 'string' },
            breed: { type: 'string' },
          },
          required: ['type', 'name', 'breed'],
        },
      },
    },
  };
}

/** Create a Generator instance for testing (no file I/O) */
function createTestGenerator(spec: any, basePath: string = '') {
  return new Generator(spec, '/tmp', '/tmp/src', '/tmp/src/generated', '/tmp/src/routes', basePath);
}

// ============================================================================
// detectBasePath — union type support
// ============================================================================
describe('detectBasePath — union types', () => {
  it('includes union type POST endpoints (anyOf) in base path detection', () => {
    const spec = buildUnionSpec('/api');
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
                  schema: {
                    anyOf: [{ $ref: '#/components/schemas/Cat' }, { $ref: '#/components/schemas/Dog' }],
                  },
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
                  schema: {
                    oneOf: [{ $ref: '#/components/schemas/Cat' }, { $ref: '#/components/schemas/Dog' }],
                  },
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
                  schema: {
                    anyOf: [{ $ref: '#/components/schemas/Cat' }, { $ref: '#/components/schemas/Dog' }],
                  },
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
                'application/json': {
                  schema: {
                    anyOf: [{ type: 'string' }, { type: 'number' }],
                  },
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
});

// ============================================================================
// extractResources — union type support
// ============================================================================
describe('extractResources — union types', () => {
  it('extracts union type resource alongside normal resources', () => {
    const spec = buildUnionSpec();
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();

    expect(gen.resources).toHaveLength(2);

    const names = gen.resources.map((r) => r.name).sort();
    expect(names).toEqual(['cat-or-dog', 'character']);
  });

  it('marks union resource with isUnion=true', () => {
    const spec = buildUnionSpec();
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();

    const union = gen.resources.find((r) => r.name === 'cat-or-dog')!;
    expect(union.isUnion).toBe(true);
    expect(union.unionVariantSchemaNames).toEqual(['Cat', 'Dog']);
  });

  it('does not mark normal resource as union', () => {
    const spec = buildUnionSpec();
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();

    const normal = gen.resources.find((r) => r.name === 'character')!;
    expect(normal.isUnion).toBeUndefined();
  });

  it('union resource has a single field of type "union"', () => {
    const spec = buildUnionSpec();
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();

    const union = gen.resources.find((r) => r.name === 'cat-or-dog')!;
    expect(union.fields).toHaveLength(1);

    const field = union.fields[0];
    expect(field.type).toBe('union');
    expect(field.name).toBe('data');
    expect(field.isRequired).toBe(true);
    expect(field.unionMeta).toBeDefined();
    expect(field.unionMeta!.discriminatorField).toBe('type');
    expect(field.unionMeta!.variants).toHaveLength(2);
  });

  it('union field variants contain correct sub-fields (excluding discriminator)', () => {
    const spec = buildUnionSpec();
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();

    const union = gen.resources.find((r) => r.name === 'cat-or-dog')!;
    const variants = union.fields[0].unionMeta!.variants;

    const cat = variants.find((v) => v.tag === 'Cat')!;
    expect(cat.schemaName).toBe('Cat');
    const catFieldNames = cat.fields!.map((f) => f.name).sort();
    expect(catFieldNames).toEqual(['color', 'name']);

    const dog = variants.find((v) => v.tag === 'Dog')!;
    expect(dog.schemaName).toBe('Dog');
    const dogFieldNames = dog.fields!.map((f) => f.name).sort();
    expect(dogFieldNames).toEqual(['breed', 'name']);
  });

  it('union resource schemaName is PascalCase of resource name', () => {
    const spec = buildUnionSpec();
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();

    const union = gen.resources.find((r) => r.name === 'cat-or-dog')!;
    expect(union.schemaName).toBe('CatOrDog');
    expect(union.pascal).toBe('CatOrDog');
    expect(union.camel).toBe('catOrDog');
  });

  it('handles union POST body without explicit discriminator mapping', () => {
    const spec = {
      info: { title: 'Test', version: '1.0' },
      paths: {
        '/pet': {
          post: {
            requestBody: {
              content: {
                'application/json': {
                  schema: {
                    anyOf: [{ $ref: '#/components/schemas/Cat' }, { $ref: '#/components/schemas/Dog' }],
                    // No discriminator — should infer from component schemas
                  },
                },
              },
            },
          },
        },
      },
      components: {
        schemas: {
          Cat: {
            type: 'object',
            properties: {
              kind: { type: 'string', enum: ['Cat'] },
              whiskers: { type: 'boolean' },
            },
            required: ['kind', 'whiskers'],
          },
          Dog: {
            type: 'object',
            properties: {
              kind: { type: 'string', enum: ['Dog'] },
              bark: { type: 'boolean' },
            },
            required: ['kind', 'bark'],
          },
        },
      },
    };

    const gen = createTestGenerator(spec);
    (gen as any).extractResources();

    const union = gen.resources.find((r) => r.name === 'pet')!;
    expect(union).toBeDefined();
    expect(union.isUnion).toBe(true);

    const meta = union.fields[0].unionMeta!;
    expect(meta.discriminatorField).toBe('kind');
    expect(meta.variants).toHaveLength(2);
    // Tag values should be inferred from enum values
    expect(meta.variants.map((v) => v.tag).sort()).toEqual(['Cat', 'Dog']);
  });

  it('skips union if no discriminator can be detected', () => {
    const spec = {
      info: { title: 'Test', version: '1.0' },
      paths: {
        '/thing': {
          post: {
            requestBody: {
              content: {
                'application/json': {
                  schema: {
                    anyOf: [{ $ref: '#/components/schemas/Alpha' }, { $ref: '#/components/schemas/Beta' }],
                  },
                },
              },
            },
          },
        },
      },
      components: {
        schemas: {
          Alpha: {
            type: 'object',
            properties: { x: { type: 'number' } },
            required: ['x'],
          },
          Beta: {
            type: 'object',
            properties: { y: { type: 'number' } },
            required: ['y'],
          },
        },
      },
    };

    const gen = createTestGenerator(spec);
    (gen as any).extractResources();

    // No discriminator field → should be skipped
    const thing = gen.resources.find((r) => r.name === 'thing');
    expect(thing).toBeUndefined();
  });

  it('handles oneOf union schemas the same as anyOf', () => {
    const spec = {
      info: { title: 'Test', version: '1.0' },
      paths: {
        '/animal': {
          post: {
            requestBody: {
              content: {
                'application/json': {
                  schema: {
                    oneOf: [{ $ref: '#/components/schemas/Cat' }, { $ref: '#/components/schemas/Dog' }],
                    discriminator: {
                      propertyName: 'type',
                      mapping: {
                        Cat: '#/components/schemas/Cat',
                        Dog: '#/components/schemas/Dog',
                      },
                    },
                  },
                },
              },
            },
          },
        },
      },
      components: {
        schemas: {
          Cat: {
            type: 'object',
            properties: {
              type: { type: 'string', enum: ['Cat'] },
              meow: { type: 'boolean' },
            },
            required: ['type', 'meow'],
          },
          Dog: {
            type: 'object',
            properties: {
              type: { type: 'string', enum: ['Dog'] },
              bark: { type: 'boolean' },
            },
            required: ['type', 'bark'],
          },
        },
      },
    };

    const gen = createTestGenerator(spec);
    (gen as any).extractResources();

    const union = gen.resources.find((r) => r.name === 'animal')!;
    expect(union).toBeDefined();
    expect(union.isUnion).toBe(true);
    expect(union.fields[0].unionMeta!.discriminatorField).toBe('type');
  });
});

// ============================================================================
// genTypes — union type alias generation
// ============================================================================
describe('genTypes — union types', () => {
  it('generates union type alias alongside normal interfaces', () => {
    const spec = buildUnionSpec();
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();

    const types = (gen as any).genTypes() as string;

    // Normal interface
    expect(types).toContain('export interface Character {');
    expect(types).toContain('export interface Cat {');
    expect(types).toContain('export interface Dog {');

    // Union type alias
    expect(types).toContain('export type CatOrDog = Cat | Dog;');
  });

  it('does not generate union alias for non-union resources', () => {
    const spec = {
      info: { title: 'Test', version: '1.0' },
      paths: {
        '/user': {
          post: {
            requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/User' } } } },
          },
        },
      },
      components: {
        schemas: {
          User: {
            type: 'object',
            properties: { name: { type: 'string' } },
            required: ['name'],
          },
        },
      },
    };

    const gen = createTestGenerator(spec);
    (gen as any).extractResources();
    const types = (gen as any).genTypes() as string;

    expect(types).toContain('export interface User {');
    expect(types).not.toContain('export type');
  });
});

// ============================================================================
// genApiClient — union type imports
// ============================================================================
describe('genApiClient — union types', () => {
  it('imports only the union type alias, not individual variant types', () => {
    const spec = buildUnionSpec();
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();

    const union = gen.resources.find((r) => r.name === 'cat-or-dog')!;
    const client = (gen as any).genApiClient(union) as string;

    expect(client).toContain("import type { CatOrDog } from '../types';");
    // Should NOT import individual variant types (Cat, Dog) separately
    expect(client).not.toMatch(/import type \{[^}]*\bCat\b/);
    expect(client).not.toMatch(/import type \{[^}]*\bDog\b/);
  });

  it('normal resource only imports its own type', () => {
    const spec = buildUnionSpec();
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();

    const normal = gen.resources.find((r) => r.name === 'character')!;
    const client = (gen as any).genApiClient(normal) as string;

    expect(client).toContain("import type { Character } from '../types';");
    expect(client).not.toContain('Cat');
  });
});

// ============================================================================
// genResourcesConfig — union resource config
// ============================================================================
describe('genResourcesConfig — union types', () => {
  it('includes isUnion: true for union resources', () => {
    const spec = buildUnionSpec();
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();

    const config = (gen as any).genResourcesConfig() as string;

    // Union resource should have isUnion: true
    expect(config).toContain('isUnion: true');
  });

  it('does not include isUnion for normal resources', () => {
    const spec = {
      info: { title: 'Test', version: '1.0' },
      paths: {
        '/user': {
          post: {
            requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/User' } } } },
          },
        },
      },
      components: {
        schemas: {
          User: {
            type: 'object',
            properties: { name: { type: 'string' } },
            required: ['name'],
          },
        },
      },
    };

    const gen = createTestGenerator(spec);
    (gen as any).extractResources();
    const config = (gen as any).genResourcesConfig() as string;

    expect(config).not.toContain('isUnion');
  });

  it('union resource config contains unionMeta with variants', () => {
    const spec = buildUnionSpec();
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();

    const config = (gen as any).genResourcesConfig() as string;

    // Should include discriminatorField and variant tags
    expect(config).toContain('discriminatorField');
    expect(config).toContain('tag: "Cat"');
    expect(config).toContain('tag: "Dog"');
  });
});

// ============================================================================
// parseField — array of discriminated union (e.g. list[Equipment | Item])
// ============================================================================
describe('parseField — array of union', () => {
  /** Minimal spec with a Character that has equipments: list[Equipment | Item] */
  function buildArrayUnionSpec() {
    return {
      info: { title: 'Test', version: '1.0' },
      paths: {
        '/character': {
          post: {
            requestBody: {
              content: { 'application/json': { schema: { $ref: '#/components/schemas/Character' } } },
            },
          },
        },
        '/character/{id}': { get: {} },
      },
      components: {
        schemas: {
          Character: {
            type: 'object',
            properties: {
              name: { type: 'string' },
              equipments: {
                type: 'array',
                items: {
                  anyOf: [{ $ref: '#/components/schemas/Equipment' }, { $ref: '#/components/schemas/Item' }],
                  discriminator: {
                    propertyName: 'type',
                    mapping: {
                      Equipment: '#/components/schemas/Equipment',
                      Item: '#/components/schemas/Item',
                    },
                  },
                },
                default: [],
              },
            },
            required: ['name'],
          },
          Equipment: {
            type: 'object',
            properties: {
              type: { type: 'string', enum: ['Equipment'] },
              name: { type: 'string' },
              attack_bonus: { type: 'integer' },
            },
            required: ['type', 'name', 'attack_bonus'],
          },
          Item: {
            type: 'object',
            properties: {
              type: { type: 'string', enum: ['Item'] },
              name: { type: 'string' },
              description: { type: 'string' },
            },
            required: ['type', 'name'],
          },
        },
      },
    };
  }

  it('parseField returns type=union and isArray=true for array of discriminated union', () => {
    const spec = buildArrayUnionSpec();
    const gen = createTestGenerator(spec);
    const equipmentsProp = spec.components.schemas.Character.properties.equipments;
    const field = (gen as any).parseField('equipments', equipmentsProp, false);

    expect(field).toBeDefined();
    expect(field.type).toBe('union');
    expect(field.isArray).toBe(true);
  });

  it('parseField produces unionMeta with correct discriminatorField', () => {
    const spec = buildArrayUnionSpec();
    const gen = createTestGenerator(spec);
    const equipmentsProp = spec.components.schemas.Character.properties.equipments;
    const field = (gen as any).parseField('equipments', equipmentsProp, false);

    expect(field.unionMeta).toBeDefined();
    expect(field.unionMeta.discriminatorField).toBe('type');
  });

  it('parseField produces correct variant tags', () => {
    const spec = buildArrayUnionSpec();
    const gen = createTestGenerator(spec);
    const equipmentsProp = spec.components.schemas.Character.properties.equipments;
    const field = (gen as any).parseField('equipments', equipmentsProp, false);

    const tags = field.unionMeta.variants.map((v: any) => v.tag);
    expect(tags).toContain('Equipment');
    expect(tags).toContain('Item');
  });

  it('parseField variant sub-fields exclude discriminator field', () => {
    const spec = buildArrayUnionSpec();
    const gen = createTestGenerator(spec);
    const equipmentsProp = spec.components.schemas.Character.properties.equipments;
    const field = (gen as any).parseField('equipments', equipmentsProp, false);

    const equipVariant = field.unionMeta.variants.find((v: any) => v.tag === 'Equipment');
    expect(equipVariant).toBeDefined();
    const fieldNames = equipVariant.fields.map((f: any) => f.name);
    expect(fieldNames).toContain('name');
    expect(fieldNames).toContain('attack_bonus');
    expect(fieldNames).not.toContain('type'); // discriminator excluded
  });

  it('parseField generates correct zod type for array of union', () => {
    const spec = buildArrayUnionSpec();
    const gen = createTestGenerator(spec);
    const equipmentsProp = spec.components.schemas.Character.properties.equipments;
    const field = (gen as any).parseField('equipments', equipmentsProp, false);

    expect(field.zodType).toContain('z.array(');
    expect(field.zodType).toContain('z.discriminatedUnion(');
  });

  it('extractFields includes array-of-union field with unionMeta', () => {
    const spec = buildArrayUnionSpec();
    const gen = createTestGenerator(spec);
    const schema = spec.components.schemas.Character;
    const fields = (gen as any).extractFields(schema, '', 1, 2);
    const equip = fields.find((f: any) => f.name === 'equipments');

    expect(equip).toBeDefined();
    expect(equip.type).toBe('union');
    expect(equip.isArray).toBe(true);
    expect(equip.unionMeta).toBeDefined();
    expect(equip.unionMeta.variants.length).toBe(2);
  });

  it('genResourcesConfig serializes array-of-union with unionMeta', () => {
    const spec = buildArrayUnionSpec();
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();
    const config = (gen as any).genResourcesConfig() as string;

    // Should contain unionMeta for equipments
    expect(config).toContain('unionMeta');
    expect(config).toContain('discriminatorField');
    expect(config).toContain('"Equipment"');
    expect(config).toContain('"Item"');
    // Should mark isArray: true
    expect(config).toContain('isArray: true');
  });
});

// ============================================================================
// Custom Create Actions
// ============================================================================

/** Build a spec with custom create actions */
function buildCustomActionSpec() {
  return {
    paths: {
      '/article': {
        post: {
          requestBody: {
            content: {
              'application/json': {
                schema: { $ref: '#/components/schemas/Article' },
              },
            },
          },
        },
      },
      '/article/import-from-url': {
        post: {
          summary: 'Import from URL (article)',
          'x-autocrud-create-action': {
            resource: 'article',
            label: 'Import from URL',
          },
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
      '/article/import-from-multiple': {
        post: {
          summary: 'Import from Multiple (article)',
          'x-autocrud-create-action': {
            resource: 'article',
            label: 'Import from Multiple',
          },
          requestBody: {
            content: {
              'application/json': {
                schema: {
                  type: 'object',
                  properties: { urls: { type: 'array', items: { type: 'string' } } },
                  required: ['urls'],
                  title: 'ImportFromMultiple',
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
        {
          path: '/article/import-from-multiple',
          label: 'Import from Multiple',
          operationId: 'import_from_multiple',
          bodySchema: 'ImportFromMultiple',
        },
      ],
    },
    components: {
      schemas: {
        Article: {
          type: 'object',
          properties: {
            content: { type: 'string' },
          },
          required: ['content'],
        },
        ImportFromUrl: {
          type: 'object',
          properties: {
            url: { type: 'string' },
          },
          required: ['url'],
        },
        ImportFromMultiple: {
          type: 'object',
          properties: {
            urls: { type: 'array', items: { type: 'string' } },
            separator: { type: 'string' },
          },
          required: ['urls'],
        },
      },
    },
  };
}

// ============================================================================
// Custom Create Actions — comprehensive compositional tests
// ============================================================================

// Helper: builds a character-resource spec with arbitrary custom action params
function buildCharacterSpec(actionOverrides: Record<string, any>) {
  return {
    paths: {
      '/character': {
        post: {
          requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/Character' } } } },
        },
      },
      '/character/{id}': { get: {} },
    },
    'x-autocrud-custom-create-actions': {
      character: [
        {
          path: '/character/action',
          label: 'Test Action',
          operationId: 'test_action',
          ...actionOverrides,
        },
      ],
    },
    components: {
      schemas: {
        Character: { type: 'object', properties: { name: { type: 'string' } }, required: ['name'] },
      },
    },
  };
}

// ── extractCustomCreateActions — body schema ────────────────────────────────
describe('extractCustomCreateActions — bodySchema', () => {
  it('attaches custom actions with body schema to matching resource', () => {
    const spec = buildCustomActionSpec();
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();
    (gen as any).extractCustomCreateActions();

    const article = gen.resources.find((r) => r.name === 'article');
    expect(article).toBeDefined();
    expect(article!.customCreateActions).toBeDefined();
    expect(article!.customCreateActions!.length).toBe(2);
  });

  it('populates action name, label, path, bodySchemaName', () => {
    const spec = buildCustomActionSpec();
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();
    (gen as any).extractCustomCreateActions();

    const actions = gen.resources.find((r) => r.name === 'article')!.customCreateActions!;
    expect(actions[0].name).toBe('import-from-url');
    expect(actions[0].label).toBe('Import from URL');
    expect(actions[0].path).toBe('/article/import-from-url');
    expect(actions[0].bodySchemaName).toBe('ImportFromUrl');
    expect(actions[0].operationId).toBe('import_from_url');
  });

  it('extracts fields from action body schema', () => {
    const spec = buildCustomActionSpec();
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();
    (gen as any).extractCustomCreateActions();

    const actions = gen.resources.find((r) => r.name === 'article')!.customCreateActions!;
    expect(actions[0].fields.length).toBe(1);
    expect(actions[0].fields[0].name).toBe('url');
    expect(actions[0].fields[0].isRequired).toBe(true);
    expect(actions[1].fields.length).toBe(2);
    const urlsField = actions[1].fields.find((f) => f.name === 'urls');
    expect(urlsField).toBeDefined();
    expect(urlsField!.isArray).toBe(true);
  });

  it('does nothing when no x-autocrud-custom-create-actions', () => {
    const spec = {
      paths: {
        '/article': {
          post: {
            requestBody: {
              content: { 'application/json': { schema: { $ref: '#/components/schemas/Article' } } },
            },
          },
        },
      },
      components: {
        schemas: {
          Article: { type: 'object', properties: { content: { type: 'string' } }, required: ['content'] },
        },
      },
    };
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();
    (gen as any).extractCustomCreateActions();

    const article = gen.resources.find((r) => r.name === 'article');
    expect(article).toBeDefined();
    expect(article!.customCreateActions).toBeUndefined();
  });

  it('skips actions without any recognised param types', () => {
    const spec = buildCharacterSpec({});
    // Remove the default overrides — action has no params at all
    const action = spec['x-autocrud-custom-create-actions'].character[0];
    delete action.path;
    spec['x-autocrud-custom-create-actions'].character[0] = {
      path: '/character/no-params',
      label: 'No Params',
      operationId: 'no_params',
    };
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();
    (gen as any).extractCustomCreateActions();
    const character = gen.resources.find((r) => r.name === 'character')!;
    expect(character.customCreateActions).toBeUndefined();
  });
});

// ── extractCustomCreateActions — compositional param combos ─────────────────
describe('extractCustomCreateActions — compositional', () => {
  it('handles Q only', () => {
    const spec = buildCharacterSpec({
      queryParams: [{ name: 'name', required: true, schema: { type: 'string' } }],
    });
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();
    (gen as any).extractCustomCreateActions();
    const action = gen.resources.find((r) => r.name === 'character')!.customCreateActions![0];
    expect(action.fields.length).toBe(1);
    expect(action.fields[0].name).toBe('name');
    expect(action.queryParams).toBeDefined();
    expect(action.pathParams).toBeUndefined();
    expect(action.inlineBodyParams).toBeUndefined();
    expect(action.fileParams).toBeUndefined();
  });

  it('handles P only', () => {
    const spec = buildCharacterSpec({
      path: '/character/{name}/new',
      pathParams: [{ name: 'name', required: true, schema: { type: 'string' } }],
    });
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();
    (gen as any).extractCustomCreateActions();
    const action = gen.resources.find((r) => r.name === 'character')!.customCreateActions![0];
    expect(action.fields.length).toBe(1);
    expect(action.fields[0].name).toBe('name');
    expect(action.pathParams).toBeDefined();
  });

  it('handles IB only', () => {
    const spec = buildCharacterSpec({
      inlineBodyParams: [
        { name: 'name', required: true, schema: { type: 'string' } },
        { name: 'age', required: false, schema: { type: 'integer' } },
      ],
    });
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();
    (gen as any).extractCustomCreateActions();
    const action = gen.resources.find((r) => r.name === 'character')!.customCreateActions![0];
    expect(action.fields.length).toBe(2);
    expect(action.inlineBodyParams).toBeDefined();
  });

  it('handles F only', () => {
    const spec = buildCharacterSpec({
      fileParams: [{ name: 'avatar', required: true, schema: { type: 'string', format: 'binary' } }],
    });
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();
    (gen as any).extractCustomCreateActions();
    const action = gen.resources.find((r) => r.name === 'character')!.customCreateActions![0];
    expect(action.fields.length).toBe(1);
    expect(action.fields[0].name).toBe('avatar');
    expect(action.fields[0].type).toBe('file');
    expect(action.fields[0].tsType).toBe('File');
    expect(action.fileParams).toBeDefined();
  });

  it('handles P + Q', () => {
    const spec = buildCharacterSpec({
      path: '/character/{name}/new',
      pathParams: [{ name: 'name', required: true, schema: { type: 'string' } }],
      queryParams: [{ name: 'level', required: false, schema: { type: 'integer' } }],
    });
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();
    (gen as any).extractCustomCreateActions();
    const action = gen.resources.find((r) => r.name === 'character')!.customCreateActions![0];
    expect(action.fields.length).toBe(2);
    expect(action.pathParams).toBeDefined();
    expect(action.queryParams).toBeDefined();
  });

  it('handles Q + IB', () => {
    const spec = buildCharacterSpec({
      queryParams: [{ name: 'x', required: true, schema: { type: 'integer' } }],
      inlineBodyParams: [{ name: 'name', required: true, schema: { type: 'string' } }],
    });
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();
    (gen as any).extractCustomCreateActions();
    const action = gen.resources.find((r) => r.name === 'character')!.customCreateActions![0];
    expect(action.fields.length).toBe(2);
    expect(action.queryParams).toBeDefined();
    expect(action.inlineBodyParams).toBeDefined();
  });

  it('handles Q + F', () => {
    const spec = buildCharacterSpec({
      queryParams: [{ name: 'x', required: true, schema: { type: 'integer' } }],
      fileParams: [{ name: 'doc', required: true, schema: { type: 'string', format: 'binary' } }],
    });
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();
    (gen as any).extractCustomCreateActions();
    const action = gen.resources.find((r) => r.name === 'character')!.customCreateActions![0];
    expect(action.fields.length).toBe(2);
    expect(action.fields[0].type).toBe('number');
    expect(action.fields[1].type).toBe('file');
    expect(action.queryParams).toBeDefined();
    expect(action.fileParams).toBeDefined();
  });

  it('handles IB + F', () => {
    const spec = buildCharacterSpec({
      inlineBodyParams: [{ name: 'title', required: true, schema: { type: 'string' } }],
      fileParams: [{ name: 'attachment', required: true, schema: { type: 'string', format: 'binary' } }],
    });
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();
    (gen as any).extractCustomCreateActions();
    const action = gen.resources.find((r) => r.name === 'character')!.customCreateActions![0];
    expect(action.fields.length).toBe(2);
    expect(action.inlineBodyParams).toBeDefined();
    expect(action.fileParams).toBeDefined();
  });

  it('handles Q + IB + F (the create_new_character4 case)', () => {
    const spec = buildCharacterSpec({
      queryParams: [
        { name: 'x', required: true, schema: { type: 'integer' } },
        { name: 'y', required: true, schema: { type: 'string' } },
      ],
      inlineBodyParams: [{ name: 'name', required: true, schema: { type: 'string' } }],
      fileParams: [{ name: 'z', required: true, schema: { type: 'string', format: 'binary' } }],
    });
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();
    (gen as any).extractCustomCreateActions();
    const action = gen.resources.find((r) => r.name === 'character')!.customCreateActions![0];
    expect(action.fields.length).toBe(4);
    expect(action.queryParams).toBeDefined();
    expect(action.inlineBodyParams).toBeDefined();
    expect(action.fileParams).toBeDefined();
    // Verify field types
    expect(action.fields.find((f: any) => f.name === 'x')!.type).toBe('number');
    expect(action.fields.find((f: any) => f.name === 'name')!.type).toBe('string');
    expect(action.fields.find((f: any) => f.name === 'z')!.type).toBe('file');
  });

  it('handles P + Q + IB + F', () => {
    const spec = buildCharacterSpec({
      path: '/character/{id}/upload',
      pathParams: [{ name: 'id', required: true, schema: { type: 'string' } }],
      queryParams: [{ name: 'x', required: true, schema: { type: 'integer' } }],
      inlineBodyParams: [{ name: 'desc', required: false, schema: { type: 'string' } }],
      fileParams: [{ name: 'img', required: true, schema: { type: 'string', format: 'binary' } }],
    });
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();
    (gen as any).extractCustomCreateActions();
    const action = gen.resources.find((r) => r.name === 'character')!.customCreateActions![0];
    expect(action.fields.length).toBe(4);
    expect(action.pathParams).toBeDefined();
    expect(action.queryParams).toBeDefined();
    expect(action.inlineBodyParams).toBeDefined();
    expect(action.fileParams).toBeDefined();
  });

  it('file field has zodType z.instanceof(File)', () => {
    const spec = buildCharacterSpec({
      fileParams: [{ name: 'doc', required: true, schema: { type: 'string', format: 'binary' } }],
    });
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();
    (gen as any).extractCustomCreateActions();
    const action = gen.resources.find((r) => r.name === 'character')!.customCreateActions![0];
    expect(action.fields[0].zodType).toBe('z.instanceof(File)');
  });

  it('query field has zodType with z.number for numbers (delegates to parseField)', () => {
    const spec = buildCharacterSpec({
      queryParams: [
        { name: 'count', required: true, schema: { type: 'integer' } },
        { name: 'name', required: false, schema: { type: 'string' } },
      ],
    });
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();
    (gen as any).extractCustomCreateActions();
    const action = gen.resources.find((r) => r.name === 'character')!.customCreateActions![0];
    expect(action.fields[0].zodType).toBe('z.number().int()');
    expect(action.fields[1].zodType).toBe('z.string().optional()');
  });
});

// ── genApiClient — compositional ────────────────────────────────────────────
describe('genApiClient — compositional', () => {
  it('bodySchema → typed body POST', () => {
    const spec = buildCustomActionSpec();
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();
    (gen as any).extractCustomCreateActions();
    const article = gen.resources.find((r) => r.name === 'article')!;
    const api = (gen as any).genApiClient(article) as string;
    expect(api).toContain('importFromUrl');
    expect(api).toContain('(data: ImportFromUrl)');
    expect(api).toContain("'/article/import-from-url', data");
  });

  it('Q only → null body + params', () => {
    const spec = buildCharacterSpec({
      queryParams: [{ name: 'name', required: true, schema: { type: 'string' } }],
    });
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();
    (gen as any).extractCustomCreateActions();
    const api = (gen as any).genApiClient(gen.resources.find((r) => r.name === 'character')!) as string;
    expect(api).toContain('null, { params }');
    expect(api).toContain("allParams['name']");
  });

  it('P only → URL interpolation + null body', () => {
    const spec = buildCharacterSpec({
      path: '/character/{name}/new',
      pathParams: [{ name: 'name', required: true, schema: { type: 'string' } }],
    });
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();
    (gen as any).extractCustomCreateActions();
    const api = (gen as any).genApiClient(gen.resources.find((r) => r.name === 'character')!) as string;
    expect(api).toContain("allParams['name'] as string");
    expect(api).toContain('null');
    expect(api).not.toContain('{name}');
  });

  it('IB only → data body POST', () => {
    const spec = buildCharacterSpec({
      inlineBodyParams: [
        { name: 'name', required: true, schema: { type: 'string' } },
        { name: 'age', required: false, schema: { type: 'integer' } },
      ],
    });
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();
    (gen as any).extractCustomCreateActions();
    const api = (gen as any).genApiClient(gen.resources.find((r) => r.name === 'character')!) as string;
    expect(api).toContain("data = { name: allParams['name'], age: allParams['age'] }");
    expect(api).toContain("'/character/action', data");
    expect(api).not.toContain('null');
  });

  it('F only → FormData POST', () => {
    const spec = buildCharacterSpec({
      fileParams: [{ name: 'avatar', required: true, schema: { type: 'string', format: 'binary' } }],
    });
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();
    (gen as any).extractCustomCreateActions();
    const api = (gen as any).genApiClient(gen.resources.find((r) => r.name === 'character')!) as string;
    expect(api).toContain('new FormData()');
    expect(api).toContain("formData.append('avatar'");
    expect(api).toContain('formData)');
    expect(api).not.toContain('null');
  });

  it('P + Q → URL interpolation + null body + query params', () => {
    const spec = buildCharacterSpec({
      path: '/character/{name}/new',
      pathParams: [{ name: 'name', required: true, schema: { type: 'string' } }],
      queryParams: [{ name: 'level', required: false, schema: { type: 'integer' } }],
    });
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();
    (gen as any).extractCustomCreateActions();
    const api = (gen as any).genApiClient(gen.resources.find((r) => r.name === 'character')!) as string;
    expect(api).toContain("allParams['name'] as string");
    expect(api).toContain("allParams['level']");
    expect(api).toContain('null, { params }');
  });

  it('Q + IB → data body + query params', () => {
    const spec = buildCharacterSpec({
      queryParams: [{ name: 'x', required: true, schema: { type: 'integer' } }],
      inlineBodyParams: [{ name: 'name', required: true, schema: { type: 'string' } }],
    });
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();
    (gen as any).extractCustomCreateActions();
    const api = (gen as any).genApiClient(gen.resources.find((r) => r.name === 'character')!) as string;
    expect(api).toContain("data = { name: allParams['name'] }");
    expect(api).toContain("params = { x: allParams['x'] }");
    expect(api).toContain('data, { params }');
    expect(api).not.toContain('null');
  });

  it('Q + F → FormData body + query params', () => {
    const spec = buildCharacterSpec({
      queryParams: [{ name: 'x', required: true, schema: { type: 'integer' } }],
      fileParams: [{ name: 'doc', required: true, schema: { type: 'string', format: 'binary' } }],
    });
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();
    (gen as any).extractCustomCreateActions();
    const api = (gen as any).genApiClient(gen.resources.find((r) => r.name === 'character')!) as string;
    expect(api).toContain('new FormData()');
    expect(api).toContain("formData.append('doc'");
    expect(api).toContain("params = { x: allParams['x'] }");
    expect(api).toContain('formData, { params }');
  });

  it('IB + F → FormData with inline body appended', () => {
    const spec = buildCharacterSpec({
      inlineBodyParams: [{ name: 'title', required: true, schema: { type: 'string' } }],
      fileParams: [{ name: 'file', required: true, schema: { type: 'string', format: 'binary' } }],
    });
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();
    (gen as any).extractCustomCreateActions();
    const api = (gen as any).genApiClient(gen.resources.find((r) => r.name === 'character')!) as string;
    expect(api).toContain('new FormData()');
    expect(api).toContain("formData.append('title', String(allParams['title']))");
    expect(api).toContain("formData.append('file'");
    expect(api).toContain('formData)');
    // No data = { ... } — everything goes in FormData
    expect(api).not.toContain('const data =');
  });

  it('Q + IB + F → FormData with inline body + query params (create_new_character4 case)', () => {
    const spec = buildCharacterSpec({
      queryParams: [
        { name: 'x', required: true, schema: { type: 'integer' } },
        { name: 'y', required: true, schema: { type: 'string' } },
      ],
      inlineBodyParams: [{ name: 'name', required: true, schema: { type: 'string' } }],
      fileParams: [{ name: 'z', required: true, schema: { type: 'string', format: 'binary' } }],
    });
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();
    (gen as any).extractCustomCreateActions();
    const api = (gen as any).genApiClient(gen.resources.find((r) => r.name === 'character')!) as string;
    expect(api).toContain('new FormData()');
    expect(api).toContain("formData.append('name', String(allParams['name']))");
    expect(api).toContain("formData.append('z'");
    expect(api).toContain("params = { x: allParams['x'], y: allParams['y'] }");
    expect(api).toContain('formData, { params }');
    expect(api).not.toContain('null');
  });

  it('P + Q + IB + F → URL interpolation + FormData + query params', () => {
    const spec = buildCharacterSpec({
      path: '/character/{id}/upload',
      pathParams: [{ name: 'id', required: true, schema: { type: 'string' } }],
      queryParams: [{ name: 'x', required: true, schema: { type: 'integer' } }],
      inlineBodyParams: [{ name: 'desc', required: false, schema: { type: 'string' } }],
      fileParams: [{ name: 'img', required: true, schema: { type: 'string', format: 'binary' } }],
    });
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();
    (gen as any).extractCustomCreateActions();
    const api = (gen as any).genApiClient(gen.resources.find((r) => r.name === 'character')!) as string;
    expect(api).toContain("allParams['id'] as string");
    expect(api).toContain('new FormData()');
    expect(api).toContain("formData.append('desc'");
    expect(api).toContain("formData.append('img'");
    expect(api).toContain("params = { x: allParams['x'] }");
    expect(api).toContain('formData, { params }');
  });
});

// ── genResourcesConfig with custom actions ──────────────────────────────────
describe('genResourcesConfig with custom actions', () => {
  it('includes customCreateActions in resource config', () => {
    const spec = buildCustomActionSpec();
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();
    (gen as any).extractCustomCreateActions();
    const config = (gen as any).genResourcesConfig() as string;
    expect(config).toContain('customCreateActions');
    expect(config).toContain("name: 'import-from-url'");
    expect(config).toContain("label: 'Import from URL'");
    expect(config).toContain('articleApi.importFromUrl');
    expect(config).toContain('articleApi.importFromMultiple');
  });

  it('generates zod schemas for custom action fields', () => {
    const spec = buildCustomActionSpec();
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();
    (gen as any).extractCustomCreateActions();
    const config = (gen as any).genResourcesConfig() as string;
    expect(config).toContain('z.object');
    expect(config).toContain('z.string()');
    expect(config).toContain('z.array(z.string())');
  });

  it('generates zod with z.instanceof(File) for file fields', () => {
    const spec = buildCharacterSpec({
      queryParams: [{ name: 'x', required: true, schema: { type: 'integer' } }],
      fileParams: [{ name: 'z', required: true, schema: { type: 'string', format: 'binary' } }],
    });
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();
    (gen as any).extractCustomCreateActions();
    const config = (gen as any).genResourcesConfig() as string;
    expect(config).toContain('z.instanceof(File)');
    expect(config).toContain('z.number().int()');
  });

  it('serializes file fields with type "file"', () => {
    const spec = buildCharacterSpec({
      fileParams: [{ name: 'avatar', required: true, schema: { type: 'string', format: 'binary' } }],
    });
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();
    (gen as any).extractCustomCreateActions();
    const config = (gen as any).genResourcesConfig() as string;
    expect(config).toContain('type: "file"');
  });
});

// ── duplicate label deduplication ───────────────────────────────────────────
describe('extractCustomCreateActions — duplicate label deduplication', () => {
  function buildDuplicateLabelSpec() {
    return {
      info: { title: 'Test', version: '1.0' },
      paths: {
        '/character': {
          post: {
            requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/Character' } } } },
          },
        },
        '/character/import-a': {
          post: {
            operationId: 'import_a',
            parameters: [{ name: 'url', in: 'query', required: true, schema: { type: 'string' } }],
          },
        },
        '/character/import-b': {
          post: {
            operationId: 'import_b',
            parameters: [{ name: 'url', in: 'query', required: true, schema: { type: 'string' } }],
          },
        },
        '/character/import-c': {
          post: {
            operationId: 'import_c',
            parameters: [{ name: 'url', in: 'query', required: true, schema: { type: 'string' } }],
          },
        },
        '/character/{id}': { get: {} },
      },
      'x-autocrud-custom-create-actions': {
        character: [
          {
            path: '/character/import-a',
            label: 'Import',
            operationId: 'import_a',
            queryParams: [{ name: 'url', required: true, schema: { type: 'string' } }],
          },
          {
            path: '/character/import-b',
            label: 'Import',
            operationId: 'import_b',
            queryParams: [{ name: 'url', required: true, schema: { type: 'string' } }],
          },
          {
            path: '/character/import-c',
            label: 'Import',
            operationId: 'import_c',
            queryParams: [{ name: 'url', required: true, schema: { type: 'string' } }],
          },
        ],
      },
      components: {
        schemas: {
          Character: { type: 'object', properties: { name: { type: 'string' } }, required: ['name'] },
        },
      },
    };
  }

  it('renames second duplicate label to "<label> (2)"', () => {
    const spec = buildDuplicateLabelSpec();
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();
    (gen as any).extractCustomCreateActions();
    const labels = gen.resources.find((r) => r.name === 'character')!.customCreateActions!.map((a) => a.label);
    expect(labels).toContain('Import');
    expect(labels).toContain('Import (2)');
  });

  it('renames third duplicate label to "<label> (3)"', () => {
    const spec = buildDuplicateLabelSpec();
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();
    (gen as any).extractCustomCreateActions();
    const labels = gen.resources.find((r) => r.name === 'character')!.customCreateActions!.map((a) => a.label);
    expect(labels).toContain('Import (3)');
  });

  it('all three actions are preserved (not dropped)', () => {
    const spec = buildDuplicateLabelSpec();
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();
    (gen as any).extractCustomCreateActions();
    expect(gen.resources.find((r) => r.name === 'character')!.customCreateActions).toHaveLength(3);
  });

  it('unique labels are not renamed', () => {
    const spec = {
      ...buildDuplicateLabelSpec(),
      'x-autocrud-custom-create-actions': {
        character: [
          {
            path: '/character/import-a',
            label: 'Import A',
            operationId: 'import_a',
            queryParams: [{ name: 'url', required: true, schema: { type: 'string' } }],
          },
          {
            path: '/character/import-b',
            label: 'Import B',
            operationId: 'import_b',
            queryParams: [{ name: 'url', required: true, schema: { type: 'string' } }],
          },
        ],
      },
    };
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();
    (gen as any).extractCustomCreateActions();
    const labels = gen.resources.find((r) => r.name === 'character')!.customCreateActions!.map((a) => a.label);
    expect(labels).toEqual(['Import A', 'Import B']);
  });
});

// ── extractCustomCreateActions — enum support ───────────────────────────────
describe('extractCustomCreateActions — enum support', () => {
  it('queryParam with enum produces enumValues and z.enum zodType', () => {
    const spec = buildCharacterSpec({
      queryParams: [{ name: 'role', required: true, schema: { type: 'string', enum: ['warrior', 'mage', 'archer'] } }],
    });
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();
    (gen as any).extractCustomCreateActions();
    const action = gen.resources.find((r) => r.name === 'character')!.customCreateActions![0];
    const roleField = action.fields.find((f: any) => f.name === 'role');
    expect(roleField).toBeDefined();
    expect(roleField!.enumValues).toEqual(['warrior', 'mage', 'archer']);
    expect(roleField!.type).toBe('string');
    expect(roleField!.zodType).toBe('z.enum(["warrior", "mage", "archer"])');
  });

  it('inlineBodyParam with enum produces enumValues and z.enum zodType', () => {
    const spec = buildCharacterSpec({
      inlineBodyParams: [
        { name: 'role', required: true, schema: { type: 'string', enum: ['warrior', 'mage', 'archer'] } },
      ],
    });
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();
    (gen as any).extractCustomCreateActions();
    const action = gen.resources.find((r) => r.name === 'character')!.customCreateActions![0];
    const roleField = action.fields.find((f: any) => f.name === 'role');
    expect(roleField).toBeDefined();
    expect(roleField!.enumValues).toEqual(['warrior', 'mage', 'archer']);
    expect(roleField!.zodType).toBe('z.enum(["warrior", "mage", "archer"])');
  });

  it('pathParam with enum produces enumValues and z.enum zodType', () => {
    const spec = buildCharacterSpec({
      path: '/character/{role}/new',
      pathParams: [{ name: 'role', required: true, schema: { type: 'string', enum: ['warrior', 'mage', 'archer'] } }],
    });
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();
    (gen as any).extractCustomCreateActions();
    const action = gen.resources.find((r) => r.name === 'character')!.customCreateActions![0];
    const roleField = action.fields.find((f: any) => f.name === 'role');
    expect(roleField).toBeDefined();
    expect(roleField!.enumValues).toEqual(['warrior', 'mage', 'archer']);
    expect(roleField!.zodType).toBe('z.enum(["warrior", "mage", "archer"])');
  });

  it('optional enum param produces z.enum().optional()', () => {
    const spec = buildCharacterSpec({
      queryParams: [{ name: 'role', required: false, schema: { type: 'string', enum: ['warrior', 'mage', 'archer'] } }],
    });
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();
    (gen as any).extractCustomCreateActions();
    const action = gen.resources.find((r) => r.name === 'character')!.customCreateActions![0];
    const roleField = action.fields.find((f: any) => f.name === 'role');
    expect(roleField!.zodType).toBe('z.enum(["warrior", "mage", "archer"]).optional()');
    expect(roleField!.isRequired).toBe(false);
  });

  it('genResourcesConfig serializes enum field with enumValues', () => {
    const spec = buildCharacterSpec({
      queryParams: [{ name: 'role', required: true, schema: { type: 'string', enum: ['warrior', 'mage', 'archer'] } }],
    });
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();
    (gen as any).extractCustomCreateActions();
    const config = (gen as any).genResourcesConfig() as string;
    expect(config).toContain('enumValues');
    expect(config).toContain('warrior');
    expect(config).toContain('mage');
    expect(config).toContain('archer');
    expect(config).toContain('z.enum(["warrior", "mage", "archer"])');
  });

  it('date-time format in queryParam produces type "date" and z.union', () => {
    const spec = buildCharacterSpec({
      queryParams: [{ name: 'created_at', required: true, schema: { type: 'string', format: 'date-time' } }],
    });
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();
    (gen as any).extractCustomCreateActions();
    const action = gen.resources.find((r) => r.name === 'character')!.customCreateActions![0];
    const field = action.fields.find((f: any) => f.name === 'created_at');
    expect(field!.type).toBe('date');
    expect(field!.zodType).toBe('z.union([z.string(), z.date()])');
  });

  it('enum + non-enum mixed params all handled correctly', () => {
    const spec = buildCharacterSpec({
      queryParams: [
        { name: 'name', required: true, schema: { type: 'string' } },
        { name: 'role', required: true, schema: { type: 'string', enum: ['warrior', 'mage'] } },
        { name: 'level', required: false, schema: { type: 'integer' } },
      ],
    });
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();
    (gen as any).extractCustomCreateActions();
    const action = gen.resources.find((r) => r.name === 'character')!.customCreateActions![0];
    expect(action.fields.length).toBe(3);

    const nameField = action.fields.find((f: any) => f.name === 'name');
    expect(nameField!.type).toBe('string');
    expect(nameField!.enumValues).toBeUndefined();
    expect(nameField!.zodType).toBe('z.string()');

    const roleField = action.fields.find((f: any) => f.name === 'role');
    expect(roleField!.type).toBe('string');
    expect(roleField!.enumValues).toEqual(['warrior', 'mage']);
    expect(roleField!.zodType).toBe('z.enum(["warrior", "mage"])');

    const levelField = action.fields.find((f: any) => f.name === 'level');
    expect(levelField!.type).toBe('number');
    expect(levelField!.enumValues).toBeUndefined();
    expect(levelField!.zodType).toBe('z.number().int().optional()');
  });
});

// ============================================================================
// parseField — constValue detection for tagged struct discriminators
// ============================================================================
describe('parseField — constValue for tagged struct discriminators', () => {
  /** Spec with tagged structs (tag=True) producing const and single-element enum */
  function buildTaggedStructSpec() {
    return {
      info: { title: 'Test', version: '1.0' },
      paths: {
        '/job': {
          post: {
            requestBody: {
              content: {
                'application/json': {
                  schema: { $ref: '#/components/schemas/Job' },
                },
              },
            },
          },
        },
        '/job/{id}': { get: {} },
      },
      components: {
        schemas: {
          Job: {
            type: 'object',
            properties: {
              name: { type: 'string' },
              fruit: {
                anyOf: [{ $ref: '#/components/schemas/Apple' }, { $ref: '#/components/schemas/Banana' }],
                discriminator: {
                  propertyName: 'type',
                  mapping: {
                    Apple: '#/components/schemas/Apple',
                    Banana: '#/components/schemas/Banana',
                  },
                },
              },
              carrot: { $ref: '#/components/schemas/Carrot' },
            },
            required: ['name', 'fruit', 'carrot'],
          },
          Apple: {
            type: 'object',
            properties: {
              type: { const: 'Apple' },
              color: { type: 'string' },
            },
            required: ['type', 'color'],
          },
          Banana: {
            type: 'object',
            properties: {
              type: { const: 'Banana' },
              length: { type: 'number' },
            },
            required: ['type', 'length'],
          },
          Carrot: {
            type: 'object',
            properties: {
              type: { type: 'string', enum: ['Carrot'] },
              weight: { type: 'number' },
            },
            required: ['type', 'weight'],
          },
        },
      },
    };
  }

  it('parseField detects prop.const and returns constValue', () => {
    const spec = buildTaggedStructSpec();
    const gen = createTestGenerator(spec);
    const typeProp = { const: 'Apple' };
    const field = (gen as any).parseField('type', typeProp, true);

    expect(field).toBeDefined();
    expect(field.constValue).toBe('Apple');
    expect(field.type).toBe('string');
    expect(field.zodType).toBe("z.literal('Apple')");
  });

  it('parseField detects single-element enum and returns constValue', () => {
    const spec = buildTaggedStructSpec();
    const gen = createTestGenerator(spec);
    const typeProp = { type: 'string', enum: ['Carrot'] };
    const field = (gen as any).parseField('type', typeProp, true);

    expect(field).toBeDefined();
    expect(field.constValue).toBe('Carrot');
    expect(field.type).toBe('string');
    expect(field.zodType).toBe("z.literal('Carrot')");
  });

  it('parseField does NOT set constValue for multi-element enum', () => {
    const spec = buildTaggedStructSpec();
    const gen = createTestGenerator(spec);
    const typeProp = { type: 'string', enum: ['warrior', 'mage'] };
    const field = (gen as any).parseField('role', typeProp, true);

    expect(field).toBeDefined();
    expect(field.constValue).toBeUndefined();
    expect(field.enumValues).toEqual(['warrior', 'mage']);
  });

  it('extractFields expands tagged struct ($ref) and produces constValue on discriminator field', () => {
    const spec = buildTaggedStructSpec();
    const gen = createTestGenerator(spec);
    const carrotSchema = spec.components.schemas.Job.properties.carrot;
    // Simulate extracting fields for the carrot $ref — we call extractFields on the Carrot schema
    const carrotFields = (gen as any).extractFields(spec.components.schemas.Carrot, 'carrot', 1, 2);
    const typeField = carrotFields.find((f: any) => f.name === 'carrot.type');

    expect(typeField).toBeDefined();
    expect(typeField.constValue).toBe('Carrot');
  });

  it('serializeField preserves constValue in genResourcesConfig output', () => {
    const spec = buildTaggedStructSpec();
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();
    const code = (gen as any).genResourcesConfig();

    // The Carrot struct's type field (single-element enum) should produce constValue
    expect(code).toContain('constValue: "Carrot"');
  });
});

// ============================================================================
// Job resource — defaultHiddenFields & unified ResourceCreate route
// ============================================================================
describe('Job resource — defaultHiddenFields', () => {
  function buildJobSpec() {
    return {
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
              payload: { type: 'object' },
              status: { type: 'string', default: 'pending' },
              errmsg: { type: 'string', default: '' },
              retries: { type: 'integer', default: 0 },
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

  it('detects Job schema and sets isJob=true', () => {
    const spec = buildJobSpec();
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();
    const r = gen.resources[0];
    expect(r.isJob).toBe(true);
    // Simple payload (no nested fields) → maxFormDepth computed from actual fields (depth 1)
    expect(r.maxFormDepth).toBe(1);
  });

  it('genCreateRoute generates ResourceCreate (not JobEnqueue) for Job', () => {
    const spec = buildJobSpec();
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();
    const code = (gen as any).genCreateRoute(gen.resources[0]);

    expect(code).toContain('ResourceCreate');
    expect(code).not.toContain('JobEnqueue');
  });

  it('computes maxFormDepth from nested payload struct fields', () => {
    // Job whose payload is a nested struct with depth-2 fields (payload.x)
    const spec = {
      info: { title: 'Test', version: '1.0' },
      paths: {
        '/my-job': {
          post: {
            requestBody: {
              content: {
                'application/json': {
                  schema: { $ref: '#/components/schemas/MyJob' },
                },
              },
            },
          },
        },
        '/my-job/{id}': { get: {} },
      },
      components: {
        schemas: {
          MyJob: {
            type: 'object',
            properties: {
              payload: { $ref: '#/components/schemas/MyPayload' },
              status: { type: 'string', default: 'pending' },
              errmsg: { type: 'string', default: '' },
              retries: { type: 'integer', default: 0 },
              periodic_interval_seconds: { type: 'number', default: 0 },
              periodic_max_runs: { type: 'integer', default: 0 },
              periodic_runs: { type: 'integer', default: 0 },
              periodic_initial_delay_seconds: { type: 'number', default: 0 },
            },
            required: ['payload'],
          },
          MyPayload: {
            type: 'object',
            properties: {
              event_type: { type: 'string' },
              description: { type: 'string' },
            },
            required: ['event_type'],
          },
        },
      },
    };
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();
    const r = gen.resources[0];
    expect(r.isJob).toBe(true);
    // payload.event_type and payload.description are depth 2
    expect(r.maxFormDepth).toBe(2);
  });

  it('genResourcesConfig includes defaultHiddenFields for Job resource', () => {
    const spec = buildJobSpec();
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();
    const code = (gen as any).genResourcesConfig();

    expect(code).toContain('defaultHiddenFields:');
    expect(code).toContain('status');
    expect(code).toContain('errmsg');
    expect(code).toContain('retries');
  });

  it('genResourcesConfig does NOT include defaultHiddenFields for non-Job resource', () => {
    // Use a simple non-job spec
    const spec = {
      info: { title: 'Test', version: '1.0' },
      paths: {
        '/user': {
          post: {
            requestBody: {
              content: {
                'application/json': {
                  schema: { $ref: '#/components/schemas/User' },
                },
              },
            },
          },
        },
        '/user/{id}': { get: {} },
      },
      components: {
        schemas: {
          User: {
            type: 'object',
            properties: { name: { type: 'string' } },
            required: ['name'],
          },
        },
      },
    };
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();
    const code = (gen as any).genResourcesConfig();

    expect(code).not.toContain('defaultHiddenFields');
  });

  it('genResourcesConfig does NOT include isJob property', () => {
    const spec = buildJobSpec();
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();
    const code = (gen as any).genResourcesConfig();

    expect(code).not.toContain('isJob:');
  });
});

// ============================================================================
// extractFields — nullable $ref struct expansion
// ============================================================================
describe('extractFields — nullable $ref struct expansion', () => {
  /** Spec with a nullable struct field: EventBodyX | None → anyOf: [$ref, {type:'null'}] */
  function buildNullableRefSpec() {
    return {
      info: { title: 'Test', version: '1.0' },
      paths: {
        '/game-event': {
          post: {
            requestBody: {
              content: {
                'application/json': {
                  schema: { $ref: '#/components/schemas/GameEventPayload' },
                },
              },
            },
          },
        },
        '/game-event/{id}': { get: {} },
      },
      components: {
        schemas: {
          EventBodyX: {
            type: 'object',
            properties: {
              type: { type: 'string', enum: ['EventBodyX'] },
              good: { type: 'string' },
              great: { type: 'integer' },
            },
            required: ['type', 'good', 'great'],
          },
          GameEventPayload: {
            type: 'object',
            properties: {
              name: { type: 'string' },
              // Non-nullable struct — should be expanded
              event_x2: { $ref: '#/components/schemas/EventBodyX' },
              // Nullable struct — anyOf [$ref, null] — should ALSO be expanded
              event_x: {
                anyOf: [{ $ref: '#/components/schemas/EventBodyX' }, { type: 'null' }],
              },
            },
            required: ['name', 'event_x2'],
          },
        },
      },
    };
  }

  it('expands non-nullable $ref struct into dot-notation sub-fields', () => {
    const spec = buildNullableRefSpec();
    const gen = createTestGenerator(spec);
    const schema = spec.components.schemas.GameEventPayload;
    const fields = (gen as any).extractFields(schema, '', 1, 2);

    // event_x2 should be expanded to event_x2.type, event_x2.good, event_x2.great
    const x2Fields = fields.filter((f: any) => f.name.startsWith('event_x2.'));
    expect(x2Fields.length).toBe(3);
    expect(x2Fields.map((f: any) => f.name).sort()).toEqual(['event_x2.good', 'event_x2.great', 'event_x2.type']);
  });

  it('expands nullable $ref struct (anyOf [$ref, null]) into dot-notation sub-fields', () => {
    const spec = buildNullableRefSpec();
    const gen = createTestGenerator(spec);
    const schema = spec.components.schemas.GameEventPayload;
    const fields = (gen as any).extractFields(schema, '', 1, 2);

    // event_x (nullable) should ALSO be expanded to event_x.type, event_x.good, event_x.great
    const xFields = fields.filter((f: any) => f.name.startsWith('event_x.'));
    expect(xFields.length).toBe(3);
    expect(xFields.map((f: any) => f.name).sort()).toEqual(['event_x.good', 'event_x.great', 'event_x.type']);
  });

  it('does NOT expand nullable $ref struct when depth exceeds maxDepth', () => {
    const spec = buildNullableRefSpec();
    const gen = createTestGenerator(spec);
    const schema = spec.components.schemas.GameEventPayload;
    // maxDepth=1 means we can only go 1 level deep — nested struct should collapse
    const fields = (gen as any).extractFields(schema, '', 1, 1);

    // event_x should NOT be expanded — should remain as a single field
    const xDotFields = fields.filter((f: any) => f.name.startsWith('event_x.'));
    expect(xDotFields.length).toBe(0);

    // But it should still exist as a single field
    const xField = fields.find((f: any) => f.name === 'event_x');
    expect(xField).toBeDefined();
  });

  it('does NOT expand nullable $ref when resolved schema has no properties (not a struct)', () => {
    const spec = buildNullableRefSpec();
    // Add a non-struct schema (e.g. enum)
    spec.components.schemas.GameEventPayload.properties.status = {
      anyOf: [{ $ref: '#/components/schemas/MyEnum' }, { type: 'null' }],
    };
    (spec.components.schemas as any).MyEnum = {
      type: 'string',
      enum: ['active', 'inactive'],
    };

    const gen = createTestGenerator(spec);
    const schema = spec.components.schemas.GameEventPayload;
    const fields = (gen as any).extractFields(schema, '', 1, 2);

    // status should NOT be expanded — it's an enum, not a struct
    const statusDotFields = fields.filter((f: any) => f.name.startsWith('status.'));
    expect(statusDotFields.length).toBe(0);
    const statusField = fields.find((f: any) => f.name === 'status');
    expect(statusField).toBeDefined();
  });
});

// ============================================================================
// parseField — structural union (anyOf with $ref / array members, no discriminator)
// e.g. list[EventBodyX] | EventBodyX, list[A] | B, list[A] | list[B]
// ============================================================================
describe('parseField — structural union', () => {
  /** Helper: build spec with EventBodyX schema */
  function buildStructuralUnionSpec() {
    return {
      info: { title: 'Test', version: '1.0' },
      paths: {
        '/payload': {
          post: {
            requestBody: {
              content: {
                'application/json': {
                  schema: { $ref: '#/components/schemas/Payload' },
                },
              },
            },
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
          EventBodyA: {
            type: 'object',
            properties: {
              type: { type: 'string', enum: ['EventBodyA'], const: 'EventBodyA' },
              extra_info_a: { type: 'string' },
              extra_value_a: { type: 'integer' },
            },
            required: ['type', 'extra_info_a', 'extra_value_a'],
          },
          Payload: {
            type: 'object',
            properties: {
              name: { type: 'string' },
            },
            required: ['name'],
          },
        },
      },
    };
  }

  // ---- Pattern 1: list[A] | A ----
  it('parses list[A] | A as structural union with 2 variants', () => {
    const spec = buildStructuralUnionSpec();
    const prop = {
      anyOf: [
        { type: 'array', items: { $ref: '#/components/schemas/EventBodyX' } },
        { $ref: '#/components/schemas/EventBodyX' },
      ],
    };
    const gen = createTestGenerator(spec);
    const field = (gen as any).parseField('event_x3', prop, true);

    expect(field).toBeDefined();
    expect(field.type).toBe('union');
    expect(field.isArray).toBe(false); // The union itself is not an array
    expect(field.unionMeta).toBeDefined();
    expect(field.unionMeta.discriminatorField).toBe('__variant');
    expect(field.unionMeta.variants).toHaveLength(2);
  });

  it('list[A] | A: array variant has isArray=true and correct fields', () => {
    const spec = buildStructuralUnionSpec();
    const prop = {
      anyOf: [
        { type: 'array', items: { $ref: '#/components/schemas/EventBodyX' } },
        { $ref: '#/components/schemas/EventBodyX' },
      ],
    };
    const gen = createTestGenerator(spec);
    const field = (gen as any).parseField('event_x3', prop, true);

    const arrayVariant = field.unionMeta.variants.find((v: any) => v.isArray);
    expect(arrayVariant).toBeDefined();
    expect(arrayVariant.tag).toContain('EventBodyX');
    expect(arrayVariant.label).toContain('[]');
    expect(arrayVariant.fields).toBeDefined();
    expect(arrayVariant.fields.length).toBeGreaterThan(0);
    // Should have good, great fields (type is constValue, skipped or included)
    const fieldNames = arrayVariant.fields.map((f: any) => f.name);
    expect(fieldNames).toContain('good');
    expect(fieldNames).toContain('great');
  });

  it('list[A] | A: single variant has isArray=false/undefined and correct fields', () => {
    const spec = buildStructuralUnionSpec();
    const prop = {
      anyOf: [
        { type: 'array', items: { $ref: '#/components/schemas/EventBodyX' } },
        { $ref: '#/components/schemas/EventBodyX' },
      ],
    };
    const gen = createTestGenerator(spec);
    const field = (gen as any).parseField('event_x3', prop, true);

    const singleVariant = field.unionMeta.variants.find((v: any) => !v.isArray);
    expect(singleVariant).toBeDefined();
    expect(singleVariant.tag).toBe('EventBodyX');
    expect(singleVariant.schemaName).toBe('EventBodyX');
    expect(singleVariant.fields).toBeDefined();
    const fieldNames = singleVariant.fields.map((f: any) => f.name);
    expect(fieldNames).toContain('good');
    expect(fieldNames).toContain('great');
  });

  // ---- Pattern 2: list[A] | B (different schemas) ----
  it('parses list[A] | B as structural union with 2 variants', () => {
    const spec = buildStructuralUnionSpec();
    const prop = {
      anyOf: [
        { type: 'array', items: { $ref: '#/components/schemas/EventBodyX' } },
        { $ref: '#/components/schemas/EventBodyA' },
      ],
    };
    const gen = createTestGenerator(spec);
    const field = (gen as any).parseField('mixed', prop, true);

    expect(field.type).toBe('union');
    expect(field.unionMeta.discriminatorField).toBe('__variant');
    expect(field.unionMeta.variants).toHaveLength(2);

    const arrayVariant = field.unionMeta.variants.find((v: any) => v.isArray);
    expect(arrayVariant).toBeDefined();
    expect(arrayVariant.fields.map((f: any) => f.name)).toContain('good');

    const singleVariant = field.unionMeta.variants.find((v: any) => !v.isArray);
    expect(singleVariant).toBeDefined();
    expect(singleVariant.schemaName).toBe('EventBodyA');
    expect(singleVariant.fields.map((f: any) => f.name)).toContain('extra_info_a');
  });

  // ---- Pattern 3: list[A] | A | null (nullable) ----
  it('parses list[A] | A | null as nullable structural union', () => {
    const spec = buildStructuralUnionSpec();
    const prop = {
      anyOf: [
        { type: 'array', items: { $ref: '#/components/schemas/EventBodyX' } },
        { $ref: '#/components/schemas/EventBodyX' },
        { type: 'null' },
      ],
    };
    const gen = createTestGenerator(spec);
    const field = (gen as any).parseField('event_x3', prop, false);

    expect(field.type).toBe('union');
    expect(field.isNullable).toBe(true);
    expect(field.unionMeta.variants).toHaveLength(3); // list_EventBodyX, EventBodyX, null

    // Null variant should be selectable
    const nullVariant = field.unionMeta.variants.find((v: any) => v.type === 'null');
    expect(nullVariant).toBeDefined();
    expect(nullVariant.tag).toBe('null');
    expect(nullVariant.label).toBe('None');
  });

  // ---- Pattern 4: A | B (two $ref, no discriminator) ----
  it('parses A | B (two $ref, no discriminator) as structural union', () => {
    const spec = buildStructuralUnionSpec();
    const prop = {
      anyOf: [{ $ref: '#/components/schemas/EventBodyX' }, { $ref: '#/components/schemas/EventBodyA' }],
    };
    const gen = createTestGenerator(spec);
    const field = (gen as any).parseField('mixed_obj', prop, true);

    expect(field.type).toBe('union');
    expect(field.unionMeta.discriminatorField).toBe('__variant');
    expect(field.unionMeta.variants).toHaveLength(2);

    const variantTags = field.unionMeta.variants.map((v: any) => v.tag);
    expect(variantTags).toContain('EventBodyX');
    expect(variantTags).toContain('EventBodyA');

    // Each variant should have fields
    for (const v of field.unionMeta.variants) {
      expect(v.fields).toBeDefined();
      expect(v.fields.length).toBeGreaterThan(0);
    }
  });

  // ---- Pattern 5: list[A] | list[B] ----
  it('parses list[A] | list[B] as structural union with 2 array variants', () => {
    const spec = buildStructuralUnionSpec();
    const prop = {
      anyOf: [
        { type: 'array', items: { $ref: '#/components/schemas/EventBodyX' } },
        { type: 'array', items: { $ref: '#/components/schemas/EventBodyA' } },
      ],
    };
    const gen = createTestGenerator(spec);
    const field = (gen as any).parseField('lists', prop, true);

    expect(field.type).toBe('union');
    expect(field.unionMeta.discriminatorField).toBe('__variant');
    expect(field.unionMeta.variants).toHaveLength(2);

    // Both variants should be arrays
    for (const v of field.unionMeta.variants) {
      expect(v.isArray).toBe(true);
      expect(v.fields).toBeDefined();
      expect(v.fields.length).toBeGreaterThan(0);
    }
  });

  // ---- Pattern 6: mixed $ref + primitive ----
  it('parses $ref | string as structural union with object + primitive variants', () => {
    const spec = buildStructuralUnionSpec();
    const prop = {
      anyOf: [{ $ref: '#/components/schemas/EventBodyX' }, { type: 'string' }],
    };
    const gen = createTestGenerator(spec);
    const field = (gen as any).parseField('mixed_prim', prop, true);

    expect(field.type).toBe('union');
    expect(field.unionMeta.discriminatorField).toBe('__variant');
    expect(field.unionMeta.variants).toHaveLength(2);

    const objVariant = field.unionMeta.variants.find((v: any) => v.schemaName === 'EventBodyX');
    expect(objVariant).toBeDefined();
    expect(objVariant.fields.length).toBeGreaterThan(0);

    const primVariant = field.unionMeta.variants.find((v: any) => v.type === 'string');
    expect(primVariant).toBeDefined();
    expect(primVariant.tag).toBe('string');
  });

  // ---- serializeField preserves isArray on variants ----
  it('serializeField preserves isArray on union variants', () => {
    const spec = buildStructuralUnionSpec();
    const prop = {
      anyOf: [
        { type: 'array', items: { $ref: '#/components/schemas/EventBodyX' } },
        { $ref: '#/components/schemas/EventBodyX' },
      ],
    };
    const gen = createTestGenerator(spec);
    const field = (gen as any).parseField('event_x3', prop, true);

    // Access the private serializeField function via genResourcesConfig integration
    // We verify isArray survives serialization by checking the config output
    spec.components.schemas.Payload.properties.event_x3 = prop;
    spec.components.schemas.Payload.required = ['name', 'event_x3'];
    (gen as any).extractResources();
    const config = (gen as any).genResourcesConfig() as string;

    expect(config).toContain('isArray: true');
    expect(config).toContain('__variant');
  });

  // ---- Pattern 7: list[DiscriminatedUnion] | SingleRef ----
  // This is the bug scenario: list[EventBodyX | EventBodyB | EventBodyA] | EventBodyX | EventBodyB
  // The array items form a discriminated union (anyOf + discriminator)
  it('parses list[DiscriminatedUnion] | SingleRef as structural union with itemUnionMeta', () => {
    const spec = buildStructuralUnionSpec();
    // Add EventBodyB schema
    spec.components.schemas.EventBodyB = {
      type: 'object',
      properties: {
        type: { type: 'string', enum: ['EventBodyB'], const: 'EventBodyB' },
        beta_info: { type: 'string' },
      },
      required: ['type', 'beta_info'],
    };

    const prop = {
      anyOf: [
        {
          type: 'array',
          items: {
            anyOf: [
              { $ref: '#/components/schemas/EventBodyX' },
              { $ref: '#/components/schemas/EventBodyB' },
              { $ref: '#/components/schemas/EventBodyA' },
            ],
            discriminator: {
              propertyName: 'type',
              mapping: {
                EventBodyX: '#/components/schemas/EventBodyX',
                EventBodyB: '#/components/schemas/EventBodyB',
                EventBodyA: '#/components/schemas/EventBodyA',
              },
            },
          },
        },
        { $ref: '#/components/schemas/EventBodyX' },
        { $ref: '#/components/schemas/EventBodyB' },
      ],
    };
    const gen = createTestGenerator(spec);
    const field = (gen as any).parseField('event_x3', prop, true);

    expect(field).toBeDefined();
    expect(field.type).toBe('union');
    expect(field.unionMeta.discriminatorField).toBe('__variant');
    expect(field.unionMeta.variants).toHaveLength(3);

    // First variant: array with discriminated union items
    const arrayVariant = field.unionMeta.variants.find((v: any) => v.isArray);
    expect(arrayVariant).toBeDefined();
    expect(arrayVariant.tag).toBe('list_union');
    expect(arrayVariant.fields).toEqual([]); // No direct fields — fields are in itemUnionMeta
    expect(arrayVariant.itemUnionMeta).toBeDefined();
    expect(arrayVariant.itemUnionMeta.discriminatorField).toBe('type');
    expect(arrayVariant.itemUnionMeta.variants).toHaveLength(3);

    // Verify inner variants
    const innerTags = arrayVariant.itemUnionMeta.variants.map((v: any) => v.tag);
    expect(innerTags).toContain('EventBodyX');
    expect(innerTags).toContain('EventBodyB');
    expect(innerTags).toContain('EventBodyA');

    // Each inner variant should have fields (minus discriminator field)
    const xVariant = arrayVariant.itemUnionMeta.variants.find((v: any) => v.tag === 'EventBodyX');
    expect(xVariant).toBeDefined();
    expect(xVariant.fields.map((f: any) => f.name)).toContain('good');
    expect(xVariant.fields.map((f: any) => f.name)).toContain('great');
    expect(xVariant.fields.map((f: any) => f.name)).not.toContain('type'); // discriminator excluded

    const bVariant = arrayVariant.itemUnionMeta.variants.find((v: any) => v.tag === 'EventBodyB');
    expect(bVariant).toBeDefined();
    expect(bVariant.fields.map((f: any) => f.name)).toContain('beta_info');

    // Non-array variants
    const nonArrayVariants = field.unionMeta.variants.filter((v: any) => !v.isArray);
    expect(nonArrayVariants).toHaveLength(2);
    const nonArrayTags = nonArrayVariants.map((v: any) => v.tag);
    expect(nonArrayTags).toContain('EventBodyX');
    expect(nonArrayTags).toContain('EventBodyB');
  });

  it('list[DiscriminatedUnion] label contains all inner variant names', () => {
    const spec = buildStructuralUnionSpec();
    spec.components.schemas.EventBodyB = {
      type: 'object',
      properties: {
        type: { type: 'string', enum: ['EventBodyB'], const: 'EventBodyB' },
        beta_info: { type: 'string' },
      },
      required: ['type', 'beta_info'],
    };

    const prop = {
      anyOf: [
        {
          type: 'array',
          items: {
            anyOf: [{ $ref: '#/components/schemas/EventBodyX' }, { $ref: '#/components/schemas/EventBodyB' }],
            discriminator: {
              propertyName: 'type',
              mapping: {
                EventBodyX: '#/components/schemas/EventBodyX',
                EventBodyB: '#/components/schemas/EventBodyB',
              },
            },
          },
        },
        { $ref: '#/components/schemas/EventBodyA' },
      ],
    };
    const gen = createTestGenerator(spec);
    const field = (gen as any).parseField('event_x3', prop, true);

    const arrayVariant = field.unionMeta.variants.find((v: any) => v.isArray);
    expect(arrayVariant.label).toContain('EventBodyX');
    expect(arrayVariant.label).toContain('EventBodyB');
    expect(arrayVariant.label).toContain('[]');
  });

  it('serializeField preserves itemUnionMeta on array variants', () => {
    const spec = buildStructuralUnionSpec();
    spec.components.schemas.EventBodyB = {
      type: 'object',
      properties: {
        type: { type: 'string', enum: ['EventBodyB'], const: 'EventBodyB' },
        beta_info: { type: 'string' },
      },
      required: ['type', 'beta_info'],
    };

    spec.components.schemas.Payload.properties.event_x3 = {
      anyOf: [
        {
          type: 'array',
          items: {
            anyOf: [{ $ref: '#/components/schemas/EventBodyX' }, { $ref: '#/components/schemas/EventBodyB' }],
            discriminator: {
              propertyName: 'type',
              mapping: {
                EventBodyX: '#/components/schemas/EventBodyX',
                EventBodyB: '#/components/schemas/EventBodyB',
              },
            },
          },
        },
        { $ref: '#/components/schemas/EventBodyX' },
      ],
    };
    spec.components.schemas.Payload.required = ['name', 'event_x3'];

    const gen = createTestGenerator(spec);
    (gen as any).extractResources();
    const config = (gen as any).genResourcesConfig() as string;

    expect(config).toContain('itemUnionMeta');
    expect(config).toContain('discriminatorField');
    expect(config).toContain('EventBodyX');
    expect(config).toContain('EventBodyB');
  });

  // ---- Pattern 8: Actual msgspec output for list[X|B|A] | X | B ----
  // msgspec wraps |X|B as a nested discriminated union, NOT as separate $refs!
  // Real OpenAPI: anyOf: [ {type:array, items:{anyOf+disc}}, {anyOf+disc} ]
  it('parses nested discriminated union (actual msgspec output) and flattens variants', () => {
    const spec = buildStructuralUnionSpec();
    spec.components.schemas.EventBodyB = {
      type: 'object',
      properties: {
        type: { type: 'string', enum: ['EventBodyB'], const: 'EventBodyB' },
        some_field: { type: 'string' },
        cooldown_seconds: { type: 'integer' },
      },
      required: ['type', 'some_field', 'cooldown_seconds'],
    };

    // This is the ACTUAL OpenAPI from msgspec for:
    // event_x3: list[EventBodyX | EventBodyB | EventBodyA] | EventBodyX | EventBodyB
    const prop = {
      anyOf: [
        {
          type: 'array',
          items: {
            anyOf: [
              { $ref: '#/components/schemas/EventBodyX' },
              { $ref: '#/components/schemas/EventBodyB' },
              { $ref: '#/components/schemas/EventBodyA' },
            ],
            discriminator: {
              propertyName: 'type',
              mapping: {
                EventBodyX: '#/components/schemas/EventBodyX',
                EventBodyB: '#/components/schemas/EventBodyB',
                EventBodyA: '#/components/schemas/EventBodyA',
              },
            },
          },
        },
        {
          anyOf: [{ $ref: '#/components/schemas/EventBodyX' }, { $ref: '#/components/schemas/EventBodyB' }],
          discriminator: {
            propertyName: 'type',
            mapping: {
              EventBodyX: '#/components/schemas/EventBodyX',
              EventBodyB: '#/components/schemas/EventBodyB',
            },
          },
        },
      ],
    };
    const gen = createTestGenerator(spec);
    const field = (gen as any).parseField('event_x3', prop, true);

    expect(field).toBeDefined();
    expect(field.type).toBe('union');
    expect(field.unionMeta.discriminatorField).toBe('__variant');

    // Should have 3 variants: list_union, EventBodyX, EventBodyB
    // The nested discriminated union should be FLATTENED into separate variants
    expect(field.unionMeta.variants).toHaveLength(3);

    // Array variant with itemUnionMeta
    const arrayVariant = field.unionMeta.variants.find((v: any) => v.isArray);
    expect(arrayVariant).toBeDefined();
    expect(arrayVariant.itemUnionMeta).toBeDefined();
    expect(arrayVariant.itemUnionMeta.variants).toHaveLength(3);

    // Flattened non-array variants from the nested discriminated union
    const nonArrayVariants = field.unionMeta.variants.filter((v: any) => !v.isArray);
    expect(nonArrayVariants).toHaveLength(2);
    const tags = nonArrayVariants.map((v: any) => v.tag);
    expect(tags).toContain('EventBodyX');
    expect(tags).toContain('EventBodyB');

    // Each flattened variant should have fields
    const xVariant = nonArrayVariants.find((v: any) => v.tag === 'EventBodyX');
    expect(xVariant.fields.length).toBeGreaterThan(0);
    expect(xVariant.fields.map((f: any) => f.name)).toContain('good');

    const bVariant = nonArrayVariants.find((v: any) => v.tag === 'EventBodyB');
    expect(bVariant.fields.length).toBeGreaterThan(0);
    expect(bVariant.fields.map((f: any) => f.name)).toContain('some_field');
  });

  // ---- Pattern 9: list[EventBodyA] | EventBodyX | None ----
  // Null is a legitimate selectable variant, not just a nullable marker
  it('parses null as a selectable variant in structural union', () => {
    const spec = buildStructuralUnionSpec();
    // event_x6: list[EventBodyA] | EventBodyX | EventBodyX | None
    // OpenAPI: anyOf: [{type:array, items:{$ref:A}}, {type:null}, {$ref:X}]
    const prop = {
      anyOf: [
        { type: 'array', items: { $ref: '#/components/schemas/EventBodyA' } },
        { type: 'null' },
        { $ref: '#/components/schemas/EventBodyX' },
      ],
    };
    const gen = createTestGenerator(spec);
    const field = (gen as any).parseField('event_x6', prop, false);

    expect(field).toBeDefined();
    expect(field.type).toBe('union');
    expect(field.unionMeta.discriminatorField).toBe('__variant');

    // Should have 3 variants: list_EventBodyA (array), null, EventBodyX (object)
    expect(field.unionMeta.variants).toHaveLength(3);

    // Array variant
    const arrayVariant = field.unionMeta.variants.find((v: any) => v.isArray);
    expect(arrayVariant).toBeDefined();
    expect(arrayVariant.label).toContain('EventBodyA');

    // Null variant — must be selectable
    const nullVariant = field.unionMeta.variants.find((v: any) => v.type === 'null');
    expect(nullVariant).toBeDefined();
    expect(nullVariant.tag).toBe('null');
    expect(nullVariant.label).toBe('None');

    // Object variant
    const objVariant = field.unionMeta.variants.find((v: any) => v.schemaName === 'EventBodyX');
    expect(objVariant).toBeDefined();
    expect(objVariant.fields.length).toBeGreaterThan(0);

    // Field should also be marked nullable
    expect(field.isNullable).toBe(true);
  });

  // ---- Pattern 10: list[EventBodyA] | dict[str, EventBodyX] ----
  // dict (additionalProperties) should be a recognized variant
  it('parses dict (additionalProperties) as a variant in structural union', () => {
    const spec = buildStructuralUnionSpec();
    // event_x7: list[EventBodyA] | dict[str, EventBodyX]
    // OpenAPI: anyOf: [{type:array, items:{$ref:A}}, {type:object, additionalProperties:{$ref:X}}]
    const prop = {
      anyOf: [
        { type: 'array', items: { $ref: '#/components/schemas/EventBodyA' } },
        {
          type: 'object',
          additionalProperties: { $ref: '#/components/schemas/EventBodyX' },
        },
      ],
    };
    const gen = createTestGenerator(spec);
    const field = (gen as any).parseField('event_x7', prop, true);

    expect(field).toBeDefined();
    expect(field.type).toBe('union');
    expect(field.unionMeta.discriminatorField).toBe('__variant');

    // Should have 2 variants: list_EventBodyA (array), dict_EventBodyX (dict)
    expect(field.unionMeta.variants).toHaveLength(2);

    // Array variant
    const arrayVariant = field.unionMeta.variants.find((v: any) => v.isArray);
    expect(arrayVariant).toBeDefined();

    // Dict variant
    const dictVariant = field.unionMeta.variants.find((v: any) => v.isDict);
    expect(dictVariant).toBeDefined();
    expect(dictVariant.tag).toBe('dict_EventBodyX');
    expect(dictVariant.label).toContain('EventBodyX');
    // Dict variant should carry value fields (the schema of dict values)
    expect(dictVariant.dictValueFields).toBeDefined();
    expect(dictVariant.dictValueFields.length).toBeGreaterThan(0);
    expect(dictVariant.dictValueFields.map((f: any) => f.name)).toContain('good');
  });
});

// ============================================================================
// parseField — nested arrays (list[list[...]])
// ============================================================================
describe('parseField — nested arrays', () => {
  function buildNestedArraySpec() {
    return {
      info: { title: 'Test', version: '1.0' },
      paths: {
        '/payload': {
          post: {
            requestBody: {
              content: {
                'application/json': {
                  schema: { $ref: '#/components/schemas/Payload' },
                },
              },
            },
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
          EventBodyA: {
            type: 'object',
            properties: {
              type: { type: 'string', enum: ['EventBodyA'], const: 'EventBodyA' },
              extra_info_a: { type: 'string' },
              extra_value_a: { type: 'integer' },
            },
            required: ['type', 'extra_info_a', 'extra_value_a'],
          },
          EventBodyB: {
            type: 'object',
            properties: {
              type: { type: 'string', enum: ['EventBodyB'], const: 'EventBodyB' },
              some_field: { type: 'string' },
              cooldown_seconds: { type: 'integer' },
            },
            required: ['type', 'some_field', 'cooldown_seconds'],
          },
          Payload: {
            type: 'object',
            properties: { name: { type: 'string' } },
            required: ['name'],
          },
        },
      },
    };
  }

  // ---- Pattern: list[list[string]] ----
  // Nested arrays (depth > 1) fall back to JSON-editor field since the form UI
  // only supports a single level of array nesting.
  it('parses list[list[string]] as JSON fallback with correct tsType/zodType', () => {
    const spec = buildNestedArraySpec();
    const prop = {
      type: 'array',
      items: {
        type: 'array',
        items: { type: 'string' },
      },
    };
    const gen = createTestGenerator(spec);
    const field = (gen as any).parseField('nested_strings', prop, true);

    expect(field).toBeDefined();
    expect(field.tsType).toBe('string[][]');
    expect(field.zodType).toBe('z.array(z.array(z.string()))');
    // Falls back to JSON editor (type=object, isArray=false)
    expect(field.type).toBe('object');
    expect(field.isArray).toBe(false);
  });

  // ---- Pattern: list[list[int]] ----
  it('parses list[list[int]] as JSON fallback with correct tsType/zodType', () => {
    const spec = buildNestedArraySpec();
    const prop = {
      type: 'array',
      items: {
        type: 'array',
        items: { type: 'integer' },
      },
    };
    const gen = createTestGenerator(spec);
    const field = (gen as any).parseField('matrix', prop, true);

    expect(field).toBeDefined();
    expect(field.tsType).toBe('number[][]');
    expect(field.zodType).toBe('z.array(z.array(z.number().int()))');
    expect(field.type).toBe('object');
    expect(field.isArray).toBe(false);
  });

  // ---- Pattern: list[list[list[string]]] (triple nesting) ----
  it('parses list[list[list[string]]] as JSON fallback with correct tsType/zodType', () => {
    const spec = buildNestedArraySpec();
    const prop = {
      type: 'array',
      items: {
        type: 'array',
        items: {
          type: 'array',
          items: { type: 'string' },
        },
      },
    };
    const gen = createTestGenerator(spec);
    const field = (gen as any).parseField('cube', prop, true);

    expect(field).toBeDefined();
    expect(field.tsType).toBe('string[][][]');
    expect(field.zodType).toBe('z.array(z.array(z.array(z.string())))');
    expect(field.type).toBe('object');
    expect(field.isArray).toBe(false);
  });

  // ---- Pattern: list[list[DiscriminatedUnion]] ----
  it('parses list[list[X | Y]] as JSON fallback with correct tsType', () => {
    const spec = buildNestedArraySpec();
    // list[list[EventBodyX | EventBodyB]]
    const prop = {
      type: 'array',
      items: {
        type: 'array',
        items: {
          anyOf: [{ $ref: '#/components/schemas/EventBodyX' }, { $ref: '#/components/schemas/EventBodyB' }],
          discriminator: {
            propertyName: 'type',
            mapping: {
              EventBodyX: '#/components/schemas/EventBodyX',
              EventBodyB: '#/components/schemas/EventBodyB',
            },
          },
        },
      },
    };
    const gen = createTestGenerator(spec);
    const field = (gen as any).parseField('nested_union', prop, true);

    expect(field).toBeDefined();
    // Falls back to JSON editor for nested arrays
    expect(field.type).toBe('object');
    expect(field.isArray).toBe(false);
    // tsType should still contain double array notation
    expect(field.tsType).toContain('[][]');
    expect(field.tsType).not.toBe('string[]');
  });

  // ---- Pattern: event_x8: list[list[list[EventBodyX | EventBodyB] | EventBodyB | EventBodyA]] ----
  // This is the actual msgspec output for the deeply nested type
  it('parses event_x8: list[list[list[X|B] | B | A]] as JSON fallback (the actual bug scenario)', () => {
    const spec = buildNestedArraySpec();
    const prop = {
      type: 'array',
      items: {
        type: 'array',
        items: {
          anyOf: [
            {
              type: 'array',
              items: {
                anyOf: [{ $ref: '#/components/schemas/EventBodyX' }, { $ref: '#/components/schemas/EventBodyB' }],
                discriminator: {
                  propertyName: 'type',
                  mapping: {
                    EventBodyX: '#/components/schemas/EventBodyX',
                    EventBodyB: '#/components/schemas/EventBodyB',
                  },
                },
              },
            },
            {
              anyOf: [{ $ref: '#/components/schemas/EventBodyB' }, { $ref: '#/components/schemas/EventBodyA' }],
              discriminator: {
                propertyName: 'type',
                mapping: {
                  EventBodyB: '#/components/schemas/EventBodyB',
                  EventBodyA: '#/components/schemas/EventBodyA',
                },
              },
            },
          ],
        },
      },
    };
    const gen = createTestGenerator(spec);
    const field = (gen as any).parseField('event_x8', prop, true);

    expect(field).toBeDefined();
    // Should NOT be 'string' — that was the original bug
    expect(field.tsType).not.toBe('string[]');
    expect(field.tsType).not.toBe('string[][]');
    // Falls back to JSON editor for multi-dimensional arrays
    expect(field.type).toBe('object');
    expect(field.isArray).toBe(false);
    // tsType should still be correctly computed with nested arrays
    expect(field.tsType).toContain('[][]');
  });

  // ---- Pattern: list[list[$ref]] (nested array of objects) ----
  it('parses list[list[$ref]] as JSON fallback with correct tsType', () => {
    const spec = buildNestedArraySpec();
    const prop = {
      type: 'array',
      items: {
        type: 'array',
        items: { $ref: '#/components/schemas/EventBodyX' },
      },
    };
    const gen = createTestGenerator(spec);
    const field = (gen as any).parseField('nested_objects', prop, true);

    expect(field).toBeDefined();
    // Falls back to JSON editor
    expect(field.type).toBe('object');
    expect(field.isArray).toBe(false);
    expect(field.tsType).toContain('[][]');
    expect(field.tsType).not.toBe('string[]');
  });

  // ---- Single-depth array of non-discriminated union is still supported ----
  it('list[X | Y] (single-depth anyOf without discriminator) still becomes union array', () => {
    const spec = buildNestedArraySpec();
    // list[EventBodyX | EventBodyA] — structural union at depth 1
    const prop = {
      type: 'array',
      items: {
        anyOf: [{ $ref: '#/components/schemas/EventBodyX' }, { $ref: '#/components/schemas/EventBodyA' }],
      },
    };
    const gen = createTestGenerator(spec);
    const field = (gen as any).parseField('single_depth', prop, true);

    expect(field).toBeDefined();
    expect(field.isArray).toBe(true);
    expect(field.type).toBe('union');
    expect(field.unionMeta).toBeDefined();
    expect(field.unionMeta.discriminatorField).toBe('__variant');
    expect(field.unionMeta.variants).toHaveLength(2);
  });

  // ---- Fallback: parseField should produce 'any' for unrecognized schemas ----
  it('falls back to any for unrecognized schema type instead of string', () => {
    const spec = buildNestedArraySpec();
    // A schema with unknown type that doesn't match any known pattern
    const prop = {
      type: 'foobar', // Not a real OpenAPI type
    };
    const gen = createTestGenerator(spec);
    const field = (gen as any).parseField('unknown_field', prop, true);

    expect(field).toBeDefined();
    // Should be 'any' rather than 'string' for unrecognized types
    expect(field.tsType).toBe('any');
    expect(field.zodType).toBe('z.any()');
  });
});
