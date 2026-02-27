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
  it('imports union type alias and all variant types', () => {
    const spec = buildUnionSpec();
    const gen = createTestGenerator(spec);
    (gen as any).extractResources();

    const union = gen.resources.find((r) => r.name === 'cat-or-dog')!;
    const client = (gen as any).genApiClient(union) as string;

    expect(client).toContain('import type { CatOrDog, Cat, Dog }');
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
