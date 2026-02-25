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
