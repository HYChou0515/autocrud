/**
 * Tests for OpenAPIParser — OpenAPI spec → IR Resource parsing.
 *
 * Covers: extractResources, extractCustomCreateActions, parseField, extractFields,
 * union parsing (discriminated, simple, structural), job detection, nested arrays.
 *
 * NOTE: tsType/zodType are NOT on the IR Field — use computeTsType/computeZodType
 * from codegen layer for those checks.
 */
import { describe, it, expect } from 'vitest';
import { OpenAPIParser } from './openapi-parser.js';
import { computeTsType } from './codegen/ts-type.js';
import { computeZodType } from './codegen/zod-type.js';

// ─── Helpers ────────────────────────────────────────────────────────────────

function createParser(spec: any, basePath: string = ''): OpenAPIParser {
  return new OpenAPIParser(spec, basePath);
}

function buildUnionSpec(basePath: string = '') {
  const prefix = basePath || '';
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
                    mapping: { Cat: '#/components/schemas/Cat', Dog: '#/components/schemas/Dog' },
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
          properties: { name: { type: 'string' }, level: { type: 'integer' } },
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
        { path: '/character/action', label: 'Test Action', operationId: 'test_action', ...actionOverrides },
      ],
    },
    components: {
      schemas: {
        Character: { type: 'object', properties: { name: { type: 'string' } }, required: ['name'] },
      },
    },
  };
}

function buildCustomActionSpec() {
  return {
    paths: {
      '/article': {
        post: {
          requestBody: {
            content: { 'application/json': { schema: { $ref: '#/components/schemas/Article' } } },
          },
        },
      },
      '/article/import-from-url': {
        post: {
          summary: 'Import from URL (article)',
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
      '/article/import-from-multiple': {
        post: {
          summary: 'Import from Multiple (article)',
          'x-autocrud-create-action': { resource: 'article', label: 'Import from Multiple' },
          requestBody: {
            content: {
              'application/json': {
                schema: {
                  type: 'object',
                  properties: { urls: { type: 'array', items: { type: 'string' } }, separator: { type: 'string' } },
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
        { path: '/article/import-from-url', label: 'Import from URL', operationId: 'import_from_url', bodySchema: 'ImportFromUrl' },
        { path: '/article/import-from-multiple', label: 'Import from Multiple', operationId: 'import_from_multiple', bodySchema: 'ImportFromMultiple' },
      ],
    },
    components: {
      schemas: {
        Article: { type: 'object', properties: { content: { type: 'string' } }, required: ['content'] },
        ImportFromUrl: { type: 'object', properties: { url: { type: 'string' } }, required: ['url'] },
        ImportFromMultiple: {
          type: 'object',
          properties: { urls: { type: 'array', items: { type: 'string' } }, separator: { type: 'string' } },
          required: ['urls'],
        },
      },
    },
  };
}

function buildSimpleSpec(basePath: string = '') {
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
        post: {
          requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/Skill' } } } },
        },
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

// ============================================================================
// extractResources — union type support
// ============================================================================
describe('extractResources — union types', () => {
  it('extracts union type resource alongside normal resources', () => {
    const resources = createParser(buildUnionSpec()).parse();
    expect(resources).toHaveLength(2);
    const names = resources.map((r) => r.name).sort();
    expect(names).toEqual(['cat-or-dog', 'character']);
  });

  it('marks union resource with isUnion=true', () => {
    const resources = createParser(buildUnionSpec()).parse();
    const union = resources.find((r) => r.name === 'cat-or-dog')!;
    expect(union.isUnion).toBe(true);
    expect(union.unionVariantSchemaNames).toEqual(['Cat', 'Dog']);
  });

  it('does not mark normal resource as union', () => {
    const resources = createParser(buildUnionSpec()).parse();
    const normal = resources.find((r) => r.name === 'character')!;
    expect(normal.isUnion).toBeUndefined();
  });

  it('union resource has a single field of type "union"', () => {
    const resources = createParser(buildUnionSpec()).parse();
    const union = resources.find((r) => r.name === 'cat-or-dog')!;
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
    const resources = createParser(buildUnionSpec()).parse();
    const union = resources.find((r) => r.name === 'cat-or-dog')!;
    const variants = union.fields[0].unionMeta!.variants;
    const cat = variants.find((v) => v.tag === 'Cat')!;
    expect(cat.schemaName).toBe('Cat');
    expect(cat.fields!.map((f) => f.name).sort()).toEqual(['color', 'name']);
    const dog = variants.find((v) => v.tag === 'Dog')!;
    expect(dog.schemaName).toBe('Dog');
    expect(dog.fields!.map((f) => f.name).sort()).toEqual(['breed', 'name']);
  });

  it('union resource schemaName is PascalCase of resource name', () => {
    const resources = createParser(buildUnionSpec()).parse();
    const union = resources.find((r) => r.name === 'cat-or-dog')!;
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
                  schema: { anyOf: [{ $ref: '#/components/schemas/Cat' }, { $ref: '#/components/schemas/Dog' }] },
                },
              },
            },
          },
        },
      },
      components: {
        schemas: {
          Cat: { type: 'object', properties: { kind: { type: 'string', enum: ['Cat'] }, whiskers: { type: 'boolean' } }, required: ['kind', 'whiskers'] },
          Dog: { type: 'object', properties: { kind: { type: 'string', enum: ['Dog'] }, bark: { type: 'boolean' } }, required: ['kind', 'bark'] },
        },
      },
    };
    const resources = createParser(spec).parse();
    const union = resources.find((r) => r.name === 'pet')!;
    expect(union).toBeDefined();
    expect(union.isUnion).toBe(true);
    const meta = union.fields[0].unionMeta!;
    expect(meta.discriminatorField).toBe('kind');
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
                  schema: { anyOf: [{ $ref: '#/components/schemas/Alpha' }, { $ref: '#/components/schemas/Beta' }] },
                },
              },
            },
          },
        },
      },
      components: {
        schemas: {
          Alpha: { type: 'object', properties: { x: { type: 'number' } }, required: ['x'] },
          Beta: { type: 'object', properties: { y: { type: 'number' } }, required: ['y'] },
        },
      },
    };
    const resources = createParser(spec).parse();
    expect(resources.find((r) => r.name === 'thing')).toBeUndefined();
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
                      mapping: { Cat: '#/components/schemas/Cat', Dog: '#/components/schemas/Dog' },
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
          Cat: { type: 'object', properties: { type: { type: 'string', enum: ['Cat'] }, meow: { type: 'boolean' } }, required: ['type', 'meow'] },
          Dog: { type: 'object', properties: { type: { type: 'string', enum: ['Dog'] }, bark: { type: 'boolean' } }, required: ['type', 'bark'] },
        },
      },
    };
    const resources = createParser(spec).parse();
    const union = resources.find((r) => r.name === 'animal')!;
    expect(union).toBeDefined();
    expect(union.isUnion).toBe(true);
    expect(union.fields[0].unionMeta!.discriminatorField).toBe('type');
  });
});

// ============================================================================
// parseField — array of discriminated union
// ============================================================================
describe('parseField — array of union', () => {
  function buildArrayUnionSpec() {
    return {
      info: { title: 'Test', version: '1.0' },
      paths: {
        '/character': { post: { requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/Character' } } } } } },
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
                    mapping: { Equipment: '#/components/schemas/Equipment', Item: '#/components/schemas/Item' },
                  },
                },
                default: [],
              },
            },
            required: ['name'],
          },
          Equipment: {
            type: 'object',
            properties: { type: { type: 'string', enum: ['Equipment'] }, name: { type: 'string' }, attack_bonus: { type: 'integer' } },
            required: ['type', 'name', 'attack_bonus'],
          },
          Item: {
            type: 'object',
            properties: { type: { type: 'string', enum: ['Item'] }, name: { type: 'string' }, description: { type: 'string' } },
            required: ['type', 'name'],
          },
        },
      },
    };
  }

  it('parseField returns type=union and isArray=true for array of discriminated union', () => {
    const spec = buildArrayUnionSpec();
    const parser = createParser(spec);
    const prop = spec.components.schemas.Character.properties.equipments;
    const field = parser.parseField('equipments', prop, false);
    expect(field).toBeDefined();
    expect(field!.type).toBe('union');
    expect(field!.isArray).toBe(true);
  });

  it('parseField produces unionMeta with correct discriminatorField', () => {
    const spec = buildArrayUnionSpec();
    const parser = createParser(spec);
    const prop = spec.components.schemas.Character.properties.equipments;
    const field = parser.parseField('equipments', prop, false);
    expect(field!.unionMeta).toBeDefined();
    expect(field!.unionMeta!.discriminatorField).toBe('type');
  });

  it('parseField produces correct variant tags', () => {
    const spec = buildArrayUnionSpec();
    const parser = createParser(spec);
    const prop = spec.components.schemas.Character.properties.equipments;
    const field = parser.parseField('equipments', prop, false);
    const tags = field!.unionMeta!.variants.map((v: any) => v.tag);
    expect(tags).toContain('Equipment');
    expect(tags).toContain('Item');
  });

  it('parseField variant sub-fields exclude discriminator field', () => {
    const spec = buildArrayUnionSpec();
    const parser = createParser(spec);
    const prop = spec.components.schemas.Character.properties.equipments;
    const field = parser.parseField('equipments', prop, false);
    const equipVariant = field!.unionMeta!.variants.find((v: any) => v.tag === 'Equipment');
    const fieldNames = equipVariant!.fields!.map((f: any) => f.name);
    expect(fieldNames).toContain('name');
    expect(fieldNames).toContain('attack_bonus');
    expect(fieldNames).not.toContain('type');
  });

  it('parseField generates correct zod type for array of union', () => {
    const spec = buildArrayUnionSpec();
    const parser = createParser(spec);
    const prop = spec.components.schemas.Character.properties.equipments;
    const field = parser.parseField('equipments', prop, false);
    const zodType = computeZodType(field!);
    expect(zodType).toContain('z.array(');
    expect(zodType).toContain('z.discriminatedUnion(');
  });

  it('extractFields includes array-of-union field with unionMeta', () => {
    const spec = buildArrayUnionSpec();
    const parser = createParser(spec);
    const fields = parser.extractFields(spec.components.schemas.Character, '', 1, 2);
    const equip = fields.find((f: any) => f.name === 'equipments');
    expect(equip).toBeDefined();
    expect(equip!.type).toBe('union');
    expect(equip!.isArray).toBe(true);
    expect(equip!.unionMeta).toBeDefined();
    expect(equip!.unionMeta!.variants.length).toBe(2);
  });
});

// ============================================================================
// extractCustomCreateActions — bodySchema
// ============================================================================
describe('extractCustomCreateActions — bodySchema', () => {
  it('attaches custom actions with body schema to matching resource', () => {
    const resources = createParser(buildCustomActionSpec()).parse();
    const article = resources.find((r) => r.name === 'article');
    expect(article).toBeDefined();
    expect(article!.customCreateActions).toBeDefined();
    expect(article!.customCreateActions!.length).toBe(2);
  });

  it('populates action name, label, path, bodySchemaName', () => {
    const resources = createParser(buildCustomActionSpec()).parse();
    const actions = resources.find((r) => r.name === 'article')!.customCreateActions!;
    expect(actions[0].name).toBe('import-from-url');
    expect(actions[0].label).toBe('Import from URL');
    expect(actions[0].path).toBe('/article/import-from-url');
    expect(actions[0].bodySchemaName).toBe('ImportFromUrl');
    expect(actions[0].operationId).toBe('import_from_url');
  });

  it('extracts fields from action body schema', () => {
    const resources = createParser(buildCustomActionSpec()).parse();
    const actions = resources.find((r) => r.name === 'article')!.customCreateActions!;
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
          post: { requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/Article' } } } } },
        },
      },
      components: {
        schemas: { Article: { type: 'object', properties: { content: { type: 'string' } }, required: ['content'] } },
      },
    };
    const resources = createParser(spec).parse();
    const article = resources.find((r) => r.name === 'article');
    expect(article).toBeDefined();
    expect(article!.customCreateActions).toBeUndefined();
  });

  it('skips actions without any recognised param types', () => {
    const spec = buildCharacterSpec({});
    spec['x-autocrud-custom-create-actions'].character[0] = {
      path: '/character/no-params', label: 'No Params', operationId: 'no_params',
    };
    const resources = createParser(spec).parse();
    const character = resources.find((r) => r.name === 'character')!;
    expect(character.customCreateActions).toBeUndefined();
  });
});

// ============================================================================
// extractCustomCreateActions — compositional param combos
// ============================================================================
describe('extractCustomCreateActions — compositional', () => {
  it('handles Q only', () => {
    const spec = buildCharacterSpec({
      queryParams: [{ name: 'name', required: true, schema: { type: 'string' } }],
    });
    const resources = createParser(spec).parse();
    const action = resources.find((r) => r.name === 'character')!.customCreateActions![0];
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
    const resources = createParser(spec).parse();
    const action = resources.find((r) => r.name === 'character')!.customCreateActions![0];
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
    const resources = createParser(spec).parse();
    const action = resources.find((r) => r.name === 'character')!.customCreateActions![0];
    expect(action.fields.length).toBe(2);
    expect(action.inlineBodyParams).toBeDefined();
  });

  it('handles F only', () => {
    const spec = buildCharacterSpec({
      fileParams: [{ name: 'avatar', required: true, schema: { type: 'string', format: 'binary' } }],
    });
    const resources = createParser(spec).parse();
    const action = resources.find((r) => r.name === 'character')!.customCreateActions![0];
    expect(action.fields.length).toBe(1);
    expect(action.fields[0].name).toBe('avatar');
    expect(action.fields[0].type).toBe('file');
    expect(computeTsType(action.fields[0])).toBe('File');
    expect(action.fileParams).toBeDefined();
  });

  it('handles P + Q', () => {
    const spec = buildCharacterSpec({
      path: '/character/{name}/new',
      pathParams: [{ name: 'name', required: true, schema: { type: 'string' } }],
      queryParams: [{ name: 'level', required: false, schema: { type: 'integer' } }],
    });
    const resources = createParser(spec).parse();
    const action = resources.find((r) => r.name === 'character')!.customCreateActions![0];
    expect(action.fields.length).toBe(2);
    expect(action.pathParams).toBeDefined();
    expect(action.queryParams).toBeDefined();
  });

  it('handles Q + IB', () => {
    const spec = buildCharacterSpec({
      queryParams: [{ name: 'x', required: true, schema: { type: 'integer' } }],
      inlineBodyParams: [{ name: 'name', required: true, schema: { type: 'string' } }],
    });
    const resources = createParser(spec).parse();
    const action = resources.find((r) => r.name === 'character')!.customCreateActions![0];
    expect(action.fields.length).toBe(2);
    expect(action.queryParams).toBeDefined();
    expect(action.inlineBodyParams).toBeDefined();
  });

  it('handles Q + F', () => {
    const spec = buildCharacterSpec({
      queryParams: [{ name: 'x', required: true, schema: { type: 'integer' } }],
      fileParams: [{ name: 'doc', required: true, schema: { type: 'string', format: 'binary' } }],
    });
    const resources = createParser(spec).parse();
    const action = resources.find((r) => r.name === 'character')!.customCreateActions![0];
    expect(action.fields.length).toBe(2);
    // NOTE: IR type is 'integer' for query param, codegen maps to 'number'
    expect(action.fields.find((f: any) => f.name === 'x')!.type).toBe('integer');
    expect(action.fields.find((f: any) => f.name === 'doc')!.type).toBe('file');
    expect(action.queryParams).toBeDefined();
    expect(action.fileParams).toBeDefined();
  });

  it('handles IB + F', () => {
    const spec = buildCharacterSpec({
      inlineBodyParams: [{ name: 'title', required: true, schema: { type: 'string' } }],
      fileParams: [{ name: 'attachment', required: true, schema: { type: 'string', format: 'binary' } }],
    });
    const resources = createParser(spec).parse();
    const action = resources.find((r) => r.name === 'character')!.customCreateActions![0];
    expect(action.fields.length).toBe(2);
    expect(action.inlineBodyParams).toBeDefined();
    expect(action.fileParams).toBeDefined();
  });

  it('handles Q + IB + F', () => {
    const spec = buildCharacterSpec({
      queryParams: [
        { name: 'x', required: true, schema: { type: 'integer' } },
        { name: 'y', required: true, schema: { type: 'string' } },
      ],
      inlineBodyParams: [{ name: 'name', required: true, schema: { type: 'string' } }],
      fileParams: [{ name: 'z', required: true, schema: { type: 'string', format: 'binary' } }],
    });
    const resources = createParser(spec).parse();
    const action = resources.find((r) => r.name === 'character')!.customCreateActions![0];
    expect(action.fields.length).toBe(4);
    expect(action.queryParams).toBeDefined();
    expect(action.inlineBodyParams).toBeDefined();
    expect(action.fileParams).toBeDefined();
    expect(action.fields.find((f: any) => f.name === 'x')!.type).toBe('integer');
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
    const resources = createParser(spec).parse();
    const action = resources.find((r) => r.name === 'character')!.customCreateActions![0];
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
    const resources = createParser(spec).parse();
    const action = resources.find((r) => r.name === 'character')!.customCreateActions![0];
    expect(computeZodType(action.fields[0])).toBe('z.instanceof(File)');
  });

  it('query field has zodType with z.number for integers', () => {
    const spec = buildCharacterSpec({
      queryParams: [
        { name: 'count', required: true, schema: { type: 'integer' } },
        { name: 'name', required: false, schema: { type: 'string' } },
      ],
    });
    const resources = createParser(spec).parse();
    const action = resources.find((r) => r.name === 'character')!.customCreateActions![0];
    expect(computeZodType(action.fields[0])).toBe('z.number().int()');
    expect(computeZodType(action.fields[1])).toBe('z.string().optional()');
  });
});

// ============================================================================
// extractCustomCreateActions — duplicate label deduplication
// ============================================================================
describe('extractCustomCreateActions — duplicate label deduplication', () => {
  function buildDuplicateLabelSpec() {
    return {
      info: { title: 'Test', version: '1.0' },
      paths: {
        '/character': {
          post: { requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/Character' } } } } },
        },
        '/character/import-a': { post: { operationId: 'import_a', parameters: [{ name: 'url', in: 'query', required: true, schema: { type: 'string' } }] } },
        '/character/import-b': { post: { operationId: 'import_b', parameters: [{ name: 'url', in: 'query', required: true, schema: { type: 'string' } }] } },
        '/character/import-c': { post: { operationId: 'import_c', parameters: [{ name: 'url', in: 'query', required: true, schema: { type: 'string' } }] } },
        '/character/{id}': { get: {} },
      },
      'x-autocrud-custom-create-actions': {
        character: [
          { path: '/character/import-a', label: 'Import', operationId: 'import_a', queryParams: [{ name: 'url', required: true, schema: { type: 'string' } }] },
          { path: '/character/import-b', label: 'Import', operationId: 'import_b', queryParams: [{ name: 'url', required: true, schema: { type: 'string' } }] },
          { path: '/character/import-c', label: 'Import', operationId: 'import_c', queryParams: [{ name: 'url', required: true, schema: { type: 'string' } }] },
        ],
      },
      components: { schemas: { Character: { type: 'object', properties: { name: { type: 'string' } }, required: ['name'] } } },
    };
  }

  it('renames second duplicate label to "<label> (2)"', () => {
    const resources = createParser(buildDuplicateLabelSpec()).parse();
    const labels = resources.find((r) => r.name === 'character')!.customCreateActions!.map((a) => a.label);
    expect(labels).toContain('Import');
    expect(labels).toContain('Import (2)');
  });

  it('renames third duplicate label to "<label> (3)"', () => {
    const resources = createParser(buildDuplicateLabelSpec()).parse();
    const labels = resources.find((r) => r.name === 'character')!.customCreateActions!.map((a) => a.label);
    expect(labels).toContain('Import (3)');
  });

  it('all three actions are preserved', () => {
    const resources = createParser(buildDuplicateLabelSpec()).parse();
    expect(resources.find((r) => r.name === 'character')!.customCreateActions).toHaveLength(3);
  });

  it('unique labels are not renamed', () => {
    const spec = {
      info: { title: 'Test', version: '1.0' },
      paths: {
        '/character': { post: { requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/Character' } } } } } },
        '/character/import-a': { post: {} },
        '/character/import-b': { post: {} },
        '/character/{id}': { get: {} },
      },
      'x-autocrud-custom-create-actions': {
        character: [
          { path: '/character/import-a', label: 'Import A', operationId: 'import_a', queryParams: [{ name: 'url', required: true, schema: { type: 'string' } }] },
          { path: '/character/import-b', label: 'Import B', operationId: 'import_b', queryParams: [{ name: 'url', required: true, schema: { type: 'string' } }] },
        ],
      },
      components: { schemas: { Character: { type: 'object', properties: { name: { type: 'string' } }, required: ['name'] } } },
    };
    const resources = createParser(spec).parse();
    const labels = resources.find((r) => r.name === 'character')!.customCreateActions!.map((a) => a.label);
    expect(labels).toEqual(['Import A', 'Import B']);
  });
});

// ============================================================================
// extractCustomCreateActions — enum support
// ============================================================================
describe('extractCustomCreateActions — enum support', () => {
  it('queryParam with enum produces enumValues', () => {
    const spec = buildCharacterSpec({
      queryParams: [{ name: 'role', required: true, schema: { type: 'string', enum: ['warrior', 'mage', 'archer'] } }],
    });
    const resources = createParser(spec).parse();
    const action = resources.find((r) => r.name === 'character')!.customCreateActions![0];
    const roleField = action.fields.find((f: any) => f.name === 'role');
    expect(roleField).toBeDefined();
    expect(roleField!.enumValues).toEqual(['warrior', 'mage', 'archer']);
    expect(roleField!.type).toBe('string');
    expect(computeZodType(roleField!)).toBe('z.enum(["warrior", "mage", "archer"])');
  });

  it('inlineBodyParam with enum produces enumValues', () => {
    const spec = buildCharacterSpec({
      inlineBodyParams: [{ name: 'role', required: true, schema: { type: 'string', enum: ['warrior', 'mage', 'archer'] } }],
    });
    const resources = createParser(spec).parse();
    const roleField = resources.find((r) => r.name === 'character')!.customCreateActions![0].fields.find((f: any) => f.name === 'role');
    expect(roleField!.enumValues).toEqual(['warrior', 'mage', 'archer']);
    expect(computeZodType(roleField!)).toBe('z.enum(["warrior", "mage", "archer"])');
  });

  it('pathParam with enum produces enumValues', () => {
    const spec = buildCharacterSpec({
      path: '/character/{role}/new',
      pathParams: [{ name: 'role', required: true, schema: { type: 'string', enum: ['warrior', 'mage', 'archer'] } }],
    });
    const resources = createParser(spec).parse();
    const roleField = resources.find((r) => r.name === 'character')!.customCreateActions![0].fields.find((f: any) => f.name === 'role');
    expect(roleField!.enumValues).toEqual(['warrior', 'mage', 'archer']);
    expect(computeZodType(roleField!)).toBe('z.enum(["warrior", "mage", "archer"])');
  });

  it('optional enum param produces z.enum().optional()', () => {
    const spec = buildCharacterSpec({
      queryParams: [{ name: 'role', required: false, schema: { type: 'string', enum: ['warrior', 'mage', 'archer'] } }],
    });
    const resources = createParser(spec).parse();
    const roleField = resources.find((r) => r.name === 'character')!.customCreateActions![0].fields.find((f: any) => f.name === 'role');
    expect(computeZodType(roleField!)).toBe('z.enum(["warrior", "mage", "archer"]).optional()');
    expect(roleField!.isRequired).toBe(false);
  });

  it('date-time format in queryParam produces type "date"', () => {
    const spec = buildCharacterSpec({
      queryParams: [{ name: 'created_at', required: true, schema: { type: 'string', format: 'date-time' } }],
    });
    const resources = createParser(spec).parse();
    const field = resources.find((r) => r.name === 'character')!.customCreateActions![0].fields.find((f: any) => f.name === 'created_at');
    expect(field!.type).toBe('date');
    expect(computeZodType(field!)).toBe('z.union([z.string(), z.date()])');
  });

  it('enum + non-enum mixed params all handled correctly', () => {
    const spec = buildCharacterSpec({
      queryParams: [
        { name: 'name', required: true, schema: { type: 'string' } },
        { name: 'role', required: true, schema: { type: 'string', enum: ['warrior', 'mage'] } },
        { name: 'level', required: false, schema: { type: 'integer' } },
      ],
    });
    const resources = createParser(spec).parse();
    const action = resources.find((r) => r.name === 'character')!.customCreateActions![0];
    expect(action.fields.length).toBe(3);
    const nameField = action.fields.find((f: any) => f.name === 'name')!;
    expect(nameField.type).toBe('string');
    expect(nameField.enumValues).toBeUndefined();
    expect(computeZodType(nameField)).toBe('z.string()');
    const roleField = action.fields.find((f: any) => f.name === 'role')!;
    expect(roleField.enumValues).toEqual(['warrior', 'mage']);
    expect(computeZodType(roleField)).toBe('z.enum(["warrior", "mage"])');
    const levelField = action.fields.find((f: any) => f.name === 'level')!;
    expect(levelField.enumValues).toBeUndefined();
    expect(computeZodType(levelField)).toBe('z.number().int().optional()');
  });
});

// ============================================================================
// inlineBodyParam with object-type schema — expand sub-fields
// ============================================================================
describe('inlineBodyParam with object-type schema — should expand sub-fields', () => {
  function buildObjectInlineBodyParamSpec() {
    return {
      info: { title: 'Test', version: '1.0' },
      paths: {
        '/character': { post: { requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/Character' } } } } } },
        '/character/{id}': { get: {} },
      },
      'x-autocrud-custom-create-actions': {
        character: [{
          path: '/character/action', label: 'Create with Config', operationId: 'create_with_config',
          inlineBodyParams: [
            { name: 'config', required: true, schema: { $ref: '#/components/schemas/CharacterConfig' } },
            { name: 'name', required: true, schema: { type: 'string' } },
          ],
        }],
      },
      components: {
        schemas: {
          Character: { type: 'object', properties: { name: { type: 'string' } }, required: ['name'] },
          CharacterConfig: {
            type: 'object',
            properties: { strength: { type: 'integer' }, dexterity: { type: 'integer' } },
            required: ['strength', 'dexterity'],
          },
        },
      },
    };
  }

  it('expands $ref object inlineBodyParam into dot-notation sub-fields', () => {
    const resources = createParser(buildObjectInlineBodyParamSpec()).parse();
    const action = resources.find((r) => r.name === 'character')!.customCreateActions![0];
    expect(action.fields.find((f: any) => f.name === 'config')).toBeUndefined();
    expect(action.fields.find((f: any) => f.name === 'config.strength')).toBeDefined();
    expect(action.fields.find((f: any) => f.name === 'config.strength')!.type).toBe('integer');
    expect(action.fields.find((f: any) => f.name === 'config.dexterity')).toBeDefined();
    expect(action.fields.find((f: any) => f.name === 'name')!.type).toBe('string');
  });

  it('expands inline object (non-$ref) inlineBodyParam into dot-notation sub-fields', () => {
    const spec = buildObjectInlineBodyParamSpec();
    spec['x-autocrud-custom-create-actions'].character[0].inlineBodyParams[0].schema = {
      type: 'object',
      properties: { strength: { type: 'integer' }, dexterity: { type: 'integer' } },
      required: ['strength', 'dexterity'],
    };
    const resources = createParser(spec).parse();
    const action = resources.find((r) => r.name === 'character')!.customCreateActions![0];
    expect(action.fields.find((f: any) => f.name === 'config')).toBeUndefined();
    expect(action.fields.find((f: any) => f.name === 'config.strength')!.type).toBe('integer');
  });

  it('expands nullable $ref object inlineBodyParam (anyOf + null)', () => {
    const spec = buildObjectInlineBodyParamSpec();
    spec['x-autocrud-custom-create-actions'].character[0].inlineBodyParams[0].schema = {
      anyOf: [{ $ref: '#/components/schemas/CharacterConfig' }, { type: 'null' }],
    };
    const resources = createParser(spec).parse();
    const action = resources.find((r) => r.name === 'character')!.customCreateActions![0];
    expect(action.fields.find((f: any) => f.name === 'config')).toBeUndefined();
    expect(action.fields.find((f: any) => f.name === 'config.strength')).toBeDefined();
  });

  it('does NOT expand simple-type inlineBodyParams (string, number)', () => {
    const spec = buildCharacterSpec({
      inlineBodyParams: [
        { name: 'name', required: true, schema: { type: 'string' } },
        { name: 'age', required: false, schema: { type: 'integer' } },
      ],
    });
    const resources = createParser(spec).parse();
    const action = resources.find((r) => r.name === 'character')!.customCreateActions![0];
    expect(action.fields.length).toBe(2);
    expect(action.fields[0].name).toBe('name');
    expect(action.fields[1].name).toBe('age');
  });
});

// ============================================================================
// bodySchema mixed with other params
// ============================================================================
describe('extractCustomCreateActions — bodySchema mixed with other params (prefix)', () => {
  function buildMixedBodySchemaCharacterSpec(extraOverrides: Record<string, any> = {}) {
    const base = buildCharacterSpec({
      bodySchema: 'Skill', bodySchemaParamName: 'f',
      queryParams: [{ name: 'x', required: true, schema: { type: 'integer' } }, { name: 'y', required: true, schema: { type: 'string' } }],
      inlineBodyParams: [{ name: 'name', required: true, schema: { type: 'string' } }],
      fileParams: [{ name: 'z', required: true, schema: { type: 'string', format: 'binary' } }],
      ...extraOverrides,
    });
    (base.components.schemas as any).Skill = {
      type: 'object',
      properties: { skname: { type: 'string' }, description: { type: 'string' }, required_level: { type: 'integer' } },
      required: ['skname'],
    };
    return base;
  }

  it('prefixes bodySchema fields with bodySchemaParamName when mixed with other params', () => {
    const resources = createParser(buildMixedBodySchemaCharacterSpec()).parse();
    const action = resources.find((r) => r.name === 'character')!.customCreateActions![0];
    const bodyFields = action.fields.filter((f: any) => f.name.startsWith('f.'));
    expect(bodyFields.length).toBe(3);
    expect(bodyFields.map((f: any) => f.name).sort()).toEqual(['f.description', 'f.required_level', 'f.skname']);
  });

  it('non-body fields remain unprefixed', () => {
    const resources = createParser(buildMixedBodySchemaCharacterSpec()).parse();
    const action = resources.find((r) => r.name === 'character')!.customCreateActions![0];
    expect(action.fields.find((f: any) => f.name === 'x')).toBeDefined();
    expect(action.fields.find((f: any) => f.name === 'y')).toBeDefined();
    expect(action.fields.find((f: any) => f.name === 'name')).toBeDefined();
    expect(action.fields.find((f: any) => f.name === 'z')).toBeDefined();
  });

  it('does NOT prefix bodySchema fields when pure bodySchema (no other params)', () => {
    const spec = buildCharacterSpec({ bodySchema: 'Skill', bodySchemaParamName: 'f' });
    (spec.components.schemas as any).Skill = {
      type: 'object',
      properties: { skname: { type: 'string' }, description: { type: 'string' } },
      required: ['skname'],
    };
    const resources = createParser(spec).parse();
    const action = resources.find((r) => r.name === 'character')!.customCreateActions![0];
    expect(action.fields.find((f: any) => f.name === 'skname')).toBeDefined();
    expect(action.fields.find((f: any) => f.name.startsWith('f.'))).toBeUndefined();
  });

  it('total field count includes all param types', () => {
    const resources = createParser(buildMixedBodySchemaCharacterSpec()).parse();
    const action = resources.find((r) => r.name === 'character')!.customCreateActions![0];
    expect(action.fields.length).toBe(7);
  });
});

// ============================================================================
// parseField — constValue for tagged struct discriminators
// ============================================================================
describe('parseField — constValue for tagged struct discriminators', () => {
  it('parseField detects prop.const and returns constValue', () => {
    const spec = buildSimpleSpec();
    const parser = createParser(spec);
    const field = parser.parseField('type', { const: 'Apple' }, true);
    expect(field).toBeDefined();
    expect(field!.constValue).toBe('Apple');
    expect(field!.type).toBe('string');
    expect(computeZodType(field!)).toBe("z.literal('Apple')");
  });

  it('parseField detects single-element enum and returns constValue', () => {
    const spec = buildSimpleSpec();
    const parser = createParser(spec);
    const field = parser.parseField('type', { type: 'string', enum: ['Carrot'] }, true);
    expect(field).toBeDefined();
    expect(field!.constValue).toBe('Carrot');
    expect(computeZodType(field!)).toBe("z.literal('Carrot')");
  });

  it('parseField does NOT set constValue for multi-element enum', () => {
    const spec = buildSimpleSpec();
    const parser = createParser(spec);
    const field = parser.parseField('role', { type: 'string', enum: ['warrior', 'mage'] }, true);
    expect(field).toBeDefined();
    expect(field!.constValue).toBeUndefined();
    expect(field!.enumValues).toEqual(['warrior', 'mage']);
  });

  it('extractFields expands tagged struct and produces constValue on discriminator field', () => {
    const spec = {
      info: { title: 'Test', version: '1.0' },
      paths: {},
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
    const parser = createParser(spec);
    const carrotFields = parser.extractFields(spec.components.schemas.Carrot, 'carrot', 1, 2);
    const typeField = carrotFields.find((f: any) => f.name === 'carrot.type');
    expect(typeField).toBeDefined();
    expect(typeField!.constValue).toBe('Carrot');
  });
});

// ============================================================================
// Job resource — defaultHiddenFields
// ============================================================================
describe('Job resource — defaultHiddenFields', () => {
  function buildJobSpec() {
    return {
      info: { title: 'Test', version: '1.0' },
      paths: {
        '/game-event': {
          post: { requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/GameEvent' } } } } },
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
    const resources = createParser(buildJobSpec()).parse();
    const r = resources[0];
    expect(r.isJob).toBe(true);
    expect(r.maxFormDepth).toBe(1);
  });

  it('computes maxFormDepth from nested payload struct fields', () => {
    const spec = {
      info: { title: 'Test', version: '1.0' },
      paths: {
        '/my-job': { post: { requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/MyJob' } } } } } },
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
            properties: { event_type: { type: 'string' }, description: { type: 'string' } },
            required: ['event_type'],
          },
        },
      },
    };
    const resources = createParser(spec).parse();
    expect(resources[0].isJob).toBe(true);
    expect(resources[0].maxFormDepth).toBe(2);
  });
});

// ============================================================================
// extractFields — nullable $ref struct expansion
// ============================================================================
describe('extractFields — nullable $ref struct expansion', () => {
  function buildNullableRefSpec() {
    return {
      info: { title: 'Test', version: '1.0' },
      paths: {
        '/game-event': { post: { requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/GameEventPayload' } } } } } },
        '/game-event/{id}': { get: {} },
      },
      components: {
        schemas: {
          EventBodyX: {
            type: 'object',
            properties: { type: { type: 'string', enum: ['EventBodyX'] }, good: { type: 'string' }, great: { type: 'integer' } },
            required: ['type', 'good', 'great'],
          },
          GameEventPayload: {
            type: 'object',
            properties: {
              name: { type: 'string' },
              event_x2: { $ref: '#/components/schemas/EventBodyX' },
              event_x: { anyOf: [{ $ref: '#/components/schemas/EventBodyX' }, { type: 'null' }] },
            },
            required: ['name', 'event_x2'],
          },
        },
      },
    };
  }

  it('expands non-nullable $ref struct into dot-notation sub-fields', () => {
    const parser = createParser(buildNullableRefSpec());
    const fields = parser.extractFields(buildNullableRefSpec().components.schemas.GameEventPayload, '', 1, 2);
    const x2Fields = fields.filter((f: any) => f.name.startsWith('event_x2.'));
    expect(x2Fields.length).toBe(3);
    expect(x2Fields.map((f: any) => f.name).sort()).toEqual(['event_x2.good', 'event_x2.great', 'event_x2.type']);
  });

  it('expands nullable $ref struct (anyOf [$ref, null]) into dot-notation sub-fields', () => {
    const parser = createParser(buildNullableRefSpec());
    const fields = parser.extractFields(buildNullableRefSpec().components.schemas.GameEventPayload, '', 1, 2);
    const xFields = fields.filter((f: any) => f.name.startsWith('event_x.'));
    expect(xFields.length).toBe(3);
    expect(xFields.map((f: any) => f.name).sort()).toEqual(['event_x.good', 'event_x.great', 'event_x.type']);
  });

  it('does NOT expand nullable $ref struct when depth exceeds maxDepth', () => {
    const parser = createParser(buildNullableRefSpec());
    const fields = parser.extractFields(buildNullableRefSpec().components.schemas.GameEventPayload, '', 1, 1);
    const xDotFields = fields.filter((f: any) => f.name.startsWith('event_x.'));
    expect(xDotFields.length).toBe(0);
    const xField = fields.find((f: any) => f.name === 'event_x');
    expect(xField).toBeDefined();
  });

  it('does NOT expand nullable $ref when resolved schema has no properties (not a struct)', () => {
    const spec = buildNullableRefSpec();
    spec.components.schemas.GameEventPayload.properties.status = {
      anyOf: [{ $ref: '#/components/schemas/MyEnum' }, { type: 'null' }],
    } as any;
    (spec.components.schemas as any).MyEnum = { type: 'string', enum: ['active', 'inactive'] };
    const parser = createParser(spec);
    const fields = parser.extractFields(spec.components.schemas.GameEventPayload, '', 1, 2);
    expect(fields.filter((f: any) => f.name.startsWith('status.')).length).toBe(0);
    expect(fields.find((f: any) => f.name === 'status')).toBeDefined();
  });
});

// ============================================================================
// parseField — structural union
// ============================================================================
describe('parseField — structural union', () => {
  function buildStructuralUnionSpec() {
    return {
      info: { title: 'Test', version: '1.0' },
      paths: {
        '/payload': { post: { requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/Payload' } } } } } },
        '/payload/{id}': { get: {} },
      },
      components: {
        schemas: {
          EventBodyX: {
            type: 'object',
            properties: { type: { type: 'string', enum: ['EventBodyX'], const: 'EventBodyX' }, good: { type: 'string' }, great: { type: 'integer' } },
            required: ['type', 'good', 'great'],
          },
          EventBodyA: {
            type: 'object',
            properties: { type: { type: 'string', enum: ['EventBodyA'], const: 'EventBodyA' }, extra_info_a: { type: 'string' }, extra_value_a: { type: 'integer' } },
            required: ['type', 'extra_info_a', 'extra_value_a'],
          },
          Payload: { type: 'object', properties: { name: { type: 'string' } }, required: ['name'] },
        },
      },
    };
  }

  it('parses list[A] | A as structural union with 2 variants', () => {
    const prop = {
      anyOf: [
        { type: 'array', items: { $ref: '#/components/schemas/EventBodyX' } },
        { $ref: '#/components/schemas/EventBodyX' },
      ],
    };
    const parser = createParser(buildStructuralUnionSpec());
    const field = parser.parseField('event_x3', prop, true);
    expect(field).toBeDefined();
    expect(field!.type).toBe('union');
    expect(field!.isArray).toBe(false);
    expect(field!.unionMeta!.discriminatorField).toBe('__variant');
    expect(field!.unionMeta!.variants).toHaveLength(2);
  });

  it('list[A] | A: array variant has isArray=true and correct fields', () => {
    const prop = {
      anyOf: [
        { type: 'array', items: { $ref: '#/components/schemas/EventBodyX' } },
        { $ref: '#/components/schemas/EventBodyX' },
      ],
    };
    const parser = createParser(buildStructuralUnionSpec());
    const field = parser.parseField('event_x3', prop, true);
    const arrayVariant = field!.unionMeta!.variants.find((v: any) => v.isArray);
    expect(arrayVariant).toBeDefined();
    expect(arrayVariant!.label).toContain('[]');
    expect(arrayVariant!.fields!.map((f: any) => f.name)).toContain('good');
  });

  it('parses list[A] | B as structural union with 2 variants', () => {
    const prop = {
      anyOf: [
        { type: 'array', items: { $ref: '#/components/schemas/EventBodyX' } },
        { $ref: '#/components/schemas/EventBodyA' },
      ],
    };
    const parser = createParser(buildStructuralUnionSpec());
    const field = parser.parseField('mixed', prop, true);
    expect(field!.type).toBe('union');
    expect(field!.unionMeta!.variants).toHaveLength(2);
    expect(field!.unionMeta!.variants.find((v: any) => v.isArray)!.fields!.map((f: any) => f.name)).toContain('good');
    expect(field!.unionMeta!.variants.find((v: any) => !v.isArray)!.schemaName).toBe('EventBodyA');
  });

  it('parses list[A] | A | null as nullable structural union', () => {
    const prop = {
      anyOf: [
        { type: 'array', items: { $ref: '#/components/schemas/EventBodyX' } },
        { $ref: '#/components/schemas/EventBodyX' },
        { type: 'null' },
      ],
    };
    const parser = createParser(buildStructuralUnionSpec());
    const field = parser.parseField('event_x3', prop, false);
    expect(field!.type).toBe('union');
    expect(field!.isNullable).toBe(true);
    expect(field!.unionMeta!.variants).toHaveLength(3);
    const nullVariant = field!.unionMeta!.variants.find((v: any) => v.type === 'null');
    expect(nullVariant).toBeDefined();
    expect(nullVariant!.tag).toBe('null');
    expect(nullVariant!.label).toBe('None');
  });

  it('parses A | B (two $ref, no discriminator) as structural union', () => {
    const prop = { anyOf: [{ $ref: '#/components/schemas/EventBodyX' }, { $ref: '#/components/schemas/EventBodyA' }] };
    const parser = createParser(buildStructuralUnionSpec());
    const field = parser.parseField('mixed_obj', prop, true);
    expect(field!.type).toBe('union');
    expect(field!.unionMeta!.discriminatorField).toBe('__variant');
    expect(field!.unionMeta!.variants).toHaveLength(2);
  });

  it('parses list[A] | list[B] as structural union with 2 array variants', () => {
    const prop = {
      anyOf: [
        { type: 'array', items: { $ref: '#/components/schemas/EventBodyX' } },
        { type: 'array', items: { $ref: '#/components/schemas/EventBodyA' } },
      ],
    };
    const parser = createParser(buildStructuralUnionSpec());
    const field = parser.parseField('lists', prop, true);
    expect(field!.type).toBe('union');
    expect(field!.unionMeta!.variants).toHaveLength(2);
    for (const v of field!.unionMeta!.variants) {
      expect(v.isArray).toBe(true);
    }
  });

  it('parses $ref | string as structural union with object + primitive variants', () => {
    const prop = { anyOf: [{ $ref: '#/components/schemas/EventBodyX' }, { type: 'string' }] };
    const parser = createParser(buildStructuralUnionSpec());
    const field = parser.parseField('mixed_prim', prop, true);
    expect(field!.type).toBe('union');
    expect(field!.unionMeta!.variants).toHaveLength(2);
    expect(field!.unionMeta!.variants.find((v: any) => v.schemaName === 'EventBodyX')).toBeDefined();
    expect(field!.unionMeta!.variants.find((v: any) => v.type === 'string')).toBeDefined();
  });

  it('parses null as a selectable variant in structural union', () => {
    const prop = {
      anyOf: [
        { type: 'array', items: { $ref: '#/components/schemas/EventBodyA' } },
        { type: 'null' },
        { $ref: '#/components/schemas/EventBodyX' },
      ],
    };
    const parser = createParser(buildStructuralUnionSpec());
    const field = parser.parseField('event_x6', prop, false);
    expect(field!.type).toBe('union');
    expect(field!.unionMeta!.variants).toHaveLength(3);
    expect(field!.isNullable).toBe(true);
  });

  it('parses dict (additionalProperties) as a variant in structural union', () => {
    const prop = {
      anyOf: [
        { type: 'array', items: { $ref: '#/components/schemas/EventBodyA' } },
        { type: 'object', additionalProperties: { $ref: '#/components/schemas/EventBodyX' } },
      ],
    };
    const parser = createParser(buildStructuralUnionSpec());
    const field = parser.parseField('event_x7', prop, true);
    expect(field!.type).toBe('union');
    expect(field!.unionMeta!.variants).toHaveLength(2);
    const dictVariant = field!.unionMeta!.variants.find((v: any) => v.isDict);
    expect(dictVariant).toBeDefined();
    expect(dictVariant!.dictValueFields).toBeDefined();
    expect(dictVariant!.dictValueFields!.map((f: any) => f.name)).toContain('good');
  });

  it('parses list[DiscriminatedUnion] | SingleRef as structural union with itemUnionMeta', () => {
    const spec = buildStructuralUnionSpec();
    spec.components.schemas.EventBodyB = {
      type: 'object',
      properties: { type: { type: 'string', enum: ['EventBodyB'], const: 'EventBodyB' }, beta_info: { type: 'string' } },
      required: ['type', 'beta_info'],
    } as any;
    const prop = {
      anyOf: [
        {
          type: 'array',
          items: {
            anyOf: [{ $ref: '#/components/schemas/EventBodyX' }, { $ref: '#/components/schemas/EventBodyB' }, { $ref: '#/components/schemas/EventBodyA' }],
            discriminator: { propertyName: 'type', mapping: { EventBodyX: '#/components/schemas/EventBodyX', EventBodyB: '#/components/schemas/EventBodyB', EventBodyA: '#/components/schemas/EventBodyA' } },
          },
        },
        { $ref: '#/components/schemas/EventBodyX' },
        { $ref: '#/components/schemas/EventBodyB' },
      ],
    };
    const parser = createParser(spec);
    const field = parser.parseField('event_x3', prop, true);
    expect(field!.unionMeta!.variants).toHaveLength(3);
    const arrayVariant = field!.unionMeta!.variants.find((v: any) => v.isArray);
    expect(arrayVariant!.itemUnionMeta).toBeDefined();
    expect(arrayVariant!.itemUnionMeta!.variants).toHaveLength(3);
  });
});

// ============================================================================
// parseField — nested arrays
// ============================================================================
describe('parseField — nested arrays', () => {
  function buildNestedArraySpec() {
    return {
      info: { title: 'Test', version: '1.0' },
      paths: {
        '/payload': { post: { requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/Payload' } } } } } },
        '/payload/{id}': { get: {} },
      },
      components: {
        schemas: {
          EventBodyX: { type: 'object', properties: { type: { type: 'string', enum: ['EventBodyX'], const: 'EventBodyX' }, good: { type: 'string' }, great: { type: 'integer' } }, required: ['type', 'good', 'great'] },
          EventBodyA: { type: 'object', properties: { type: { type: 'string', enum: ['EventBodyA'], const: 'EventBodyA' }, extra_info_a: { type: 'string' }, extra_value_a: { type: 'integer' } }, required: ['type', 'extra_info_a', 'extra_value_a'] },
          EventBodyB: { type: 'object', properties: { type: { type: 'string', enum: ['EventBodyB'], const: 'EventBodyB' }, some_field: { type: 'string' }, cooldown_seconds: { type: 'integer' } }, required: ['type', 'some_field', 'cooldown_seconds'] },
          Payload: { type: 'object', properties: { name: { type: 'string' } }, required: ['name'] },
        },
      },
    };
  }

  it('parses list[list[string]] as JSON fallback with correct tsType/zodType', () => {
    const prop = { type: 'array', items: { type: 'array', items: { type: 'string' } } };
    const parser = createParser(buildNestedArraySpec());
    const field = parser.parseField('nested_strings', prop, true);
    expect(field).toBeDefined();
    expect(computeTsType(field!)).toBe('string[][]');
    expect(computeZodType(field!)).toBe('z.array(z.array(z.string()))');
    expect(field!.type).toBe('object');
    expect(field!.isArray).toBe(false);
  });

  it('parses list[list[int]] as JSON fallback with correct tsType/zodType', () => {
    const prop = { type: 'array', items: { type: 'array', items: { type: 'integer' } } };
    const parser = createParser(buildNestedArraySpec());
    const field = parser.parseField('matrix', prop, true);
    expect(computeTsType(field!)).toBe('number[][]');
    expect(computeZodType(field!)).toBe('z.array(z.array(z.number().int()))');
    expect(field!.type).toBe('object');
  });

  it('parses list[list[list[string]]] as JSON fallback', () => {
    const prop = { type: 'array', items: { type: 'array', items: { type: 'array', items: { type: 'string' } } } };
    const parser = createParser(buildNestedArraySpec());
    const field = parser.parseField('cube', prop, true);
    expect(computeTsType(field!)).toBe('string[][][]');
    expect(computeZodType(field!)).toBe('z.array(z.array(z.array(z.string())))');
  });

  it('parses list[list[X | Y]] as JSON fallback with correct tsType', () => {
    const prop = {
      type: 'array',
      items: {
        type: 'array',
        items: {
          anyOf: [{ $ref: '#/components/schemas/EventBodyX' }, { $ref: '#/components/schemas/EventBodyB' }],
          discriminator: { propertyName: 'type', mapping: { EventBodyX: '#/components/schemas/EventBodyX', EventBodyB: '#/components/schemas/EventBodyB' } },
        },
      },
    };
    const parser = createParser(buildNestedArraySpec());
    const field = parser.parseField('nested_union', prop, true);
    expect(field!.type).toBe('object');
    expect(field!.isArray).toBe(false);
    expect(computeTsType(field!)).toContain('[][]');
    expect(computeTsType(field!)).not.toBe('string[]');
  });

  it('parses event_x8: list[list[list[X|B] | B | A]] as JSON fallback', () => {
    const prop = {
      type: 'array',
      items: {
        type: 'array',
        items: {
          anyOf: [
            { type: 'array', items: { anyOf: [{ $ref: '#/components/schemas/EventBodyX' }, { $ref: '#/components/schemas/EventBodyB' }], discriminator: { propertyName: 'type', mapping: { EventBodyX: '#/components/schemas/EventBodyX', EventBodyB: '#/components/schemas/EventBodyB' } } } },
            { anyOf: [{ $ref: '#/components/schemas/EventBodyB' }, { $ref: '#/components/schemas/EventBodyA' }], discriminator: { propertyName: 'type', mapping: { EventBodyB: '#/components/schemas/EventBodyB', EventBodyA: '#/components/schemas/EventBodyA' } } },
          ],
        },
      },
    };
    const parser = createParser(buildNestedArraySpec());
    const field = parser.parseField('event_x8', prop, true);
    expect(field).toBeDefined();
    expect(computeTsType(field!)).not.toBe('string[]');
    expect(computeTsType(field!)).not.toBe('string[][]');
    expect(field!.type).toBe('object');
    expect(computeTsType(field!)).toContain('[][]');
  });

  it('parses list[list[$ref]] as JSON fallback with correct tsType', () => {
    const prop = { type: 'array', items: { type: 'array', items: { $ref: '#/components/schemas/EventBodyX' } } };
    const parser = createParser(buildNestedArraySpec());
    const field = parser.parseField('nested_objects', prop, true);
    expect(field!.type).toBe('object');
    expect(computeTsType(field!)).toContain('[][]');
    expect(computeTsType(field!)).not.toBe('string[]');
  });

  it('list[X | Y] (single-depth anyOf) still becomes union array', () => {
    const prop = {
      type: 'array',
      items: { anyOf: [{ $ref: '#/components/schemas/EventBodyX' }, { $ref: '#/components/schemas/EventBodyA' }] },
    };
    const parser = createParser(buildNestedArraySpec());
    const field = parser.parseField('single_depth', prop, true);
    expect(field!.isArray).toBe(true);
    expect(field!.type).toBe('union');
    expect(field!.unionMeta!.discriminatorField).toBe('__variant');
    expect(field!.unionMeta!.variants).toHaveLength(2);
  });

  it('falls back to object for unrecognized schema type', () => {
    const prop = { type: 'foobar' as any };
    const parser = createParser(buildNestedArraySpec());
    const field = parser.parseField('unknown_field', prop, true);
    expect(field).toBeDefined();
    expect(field!.type).toBe('object');
    expect(computeTsType(field!)).toBe('Record<string, any>');
    expect(computeZodType(field!)).toBe('z.record(z.string(), z.any())');
  });
});

// ============================================================================
// Async Create Action
// ============================================================================
describe('extractCustomCreateActions — asyncMode', () => {
  function buildAsyncCreateActionSpec() {
    return {
      paths: {
        '/article': { post: { requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/Article' } } } } } },
        '/article/generate-article': { post: { requestBody: { content: { 'application/json': { schema: { type: 'object', properties: { prompt: { type: 'string' }, title: { type: 'string' } }, required: ['prompt', 'title'], title: 'ArticleRequest' } } } } } },
        '/generate-article-job': { get: {} },
        '/generate-article-job/{id}': { get: {} },
      },
      'x-autocrud-custom-create-actions': {
        article: [{ path: '/article/generate-article', label: 'Generate', operationId: 'generate_article', bodySchema: 'ArticleRequest', asyncMode: 'job', jobResourceName: 'generate-article-job' }],
      },
      'x-autocrud-async-create-jobs': { 'generate-article-job': 'article' },
      components: {
        schemas: {
          Article: { type: 'object', properties: { title: { type: 'string' }, content: { type: 'string' } }, required: ['title', 'content'] },
          ArticleRequest: { type: 'object', properties: { prompt: { type: 'string' }, title: { type: 'string' } }, required: ['prompt', 'title'] },
        },
      },
    };
  }

  it('parses asyncMode and jobResourceName from OpenAPI extension', () => {
    const resources = createParser(buildAsyncCreateActionSpec()).parse();
    const action = resources.find((r) => r.name === 'article')!.customCreateActions![0];
    expect(action.asyncMode).toBe('job');
    expect(action.jobResourceName).toBe('generate-article-job');
  });

  it('sync actions have no asyncMode or jobResourceName', () => {
    const resources = createParser(buildCustomActionSpec()).parse();
    const action = resources.find((r) => r.name === 'article')!.customCreateActions![0];
    expect(action.asyncMode).toBeUndefined();
    expect(action.jobResourceName).toBeUndefined();
  });
});

// ============================================================================
// Enum field references (tsType via computeTsType)
// ============================================================================
describe('parseField — enum field references', () => {
  it('preserves enumSchemaName for $ref enum fields', () => {
    const spec = {
      info: { title: 'Test', version: '1.0' },
      paths: {
        '/foo': { post: { requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/Foo' } } } } } },
      },
      components: {
        schemas: {
          FooType: { type: 'string', enum: ['foo', 'bar'], title: 'FooType' },
          Foo: { type: 'object', properties: { foo_type: { $ref: '#/components/schemas/FooType' }, name: { type: 'string' } }, required: ['foo_type', 'name'] },
        },
      },
    };
    const resources = createParser(spec).parse();
    const fooTypeField = resources.find((r) => r.name === 'foo')!.fields.find((f) => f.name === 'foo_type')!;
    expect(fooTypeField.enumValues).toEqual(['foo', 'bar']);
    expect(computeTsType(fooTypeField)).toBe('FooType');
  });
});

// ============================================================================
// Tagged struct literal type
// ============================================================================
describe('parseField — tagged struct literal type', () => {
  it('parseField returns constValue and literal tsType for const field', () => {
    const spec = buildSimpleSpec();
    const parser = createParser(spec);
    const field = parser.parseField('type', { const: 'Equipment', type: 'string' }, true);
    expect(field!.constValue).toBe('Equipment');
    expect(computeTsType(field!)).toBe("'Equipment'");
  });

  it('parseField returns constValue and literal tsType for single-element enum', () => {
    const spec = buildSimpleSpec();
    const parser = createParser(spec);
    const field = parser.parseField('type', { enum: ['Consumable'], type: 'string' }, true);
    expect(field!.constValue).toBe('Consumable');
    expect(computeTsType(field!)).toBe("'Consumable'");
  });
});
