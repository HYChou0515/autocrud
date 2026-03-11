/**
 * Tests for codegen/ts-type.ts — TypeScript type generation from IR Fields.
 *
 * Covers: computeTsType(), genTypes() with enum references, tagged struct literals.
 */
import { describe, it, expect } from 'vitest';
import { OpenAPIParser } from '../openapi-parser.js';
import { computeTsType, genTypes } from './ts-type.js';

// ─── Helpers ────────────────────────────────────────────────────────────────

function parse(spec: any, basePath = ''): ReturnType<OpenAPIParser['parse']> {
  return new OpenAPIParser(spec, basePath).parse();
}

function parseFieldOf(spec: any, basePath = ''): OpenAPIParser['parseField'] {
  return new OpenAPIParser(spec, basePath).parseField.bind(new OpenAPIParser(spec, basePath));
}

// ============================================================================
// genTypes — enum field references
// ============================================================================
describe('genTypes — enum field references', () => {
  function buildEnumSpec() {
    return {
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
  }

  it('generates enum type reference instead of string for $ref enum fields', () => {
    const spec = buildEnumSpec();
    const parser = new OpenAPIParser(spec, '');
    const resources = parser.parse();
    const types = genTypes(spec, resources, (n, p, r) => parser.parseField(n, p, r));

    expect(types).toContain('export enum FooType {');
    expect(types).toContain('foo_type: FooType;');
    expect(types).not.toMatch(/foo_type: string;/);
  });

  it('generates nullable enum type reference for optional enum via anyOf', () => {
    const spec = {
      info: { title: 'Test', version: '1.0' },
      paths: {
        '/bar': { post: { requestBody: { content: { 'application/json': { schema: { $ref: '#/components/schemas/Bar' } } } } } },
      },
      components: {
        schemas: {
          BarType: { type: 'string', enum: ['x', 'y', 'z'], title: 'BarType' },
          Bar: {
            type: 'object',
            properties: { bar_type: { anyOf: [{ $ref: '#/components/schemas/BarType' }, { type: 'null' }] }, name: { type: 'string' } },
            required: ['name'],
          },
        },
      },
    };
    const parser = new OpenAPIParser(spec, '');
    const resources = parser.parse();
    const types = genTypes(spec, resources, (n, p, r) => parser.parseField(n, p, r));

    expect(types).toContain('export enum BarType {');
    expect(types).toContain('bar_type?: BarType | null;');
    expect(types).not.toMatch(/bar_type\??: string/);
  });

  it('preserves enumSchemaName on resource field metadata', () => {
    const spec = buildEnumSpec();
    const resources = parse(spec);
    const fooTypeField = resources.find((r) => r.name === 'foo')!.fields.find((f) => f.name === 'foo_type')!;
    expect(fooTypeField.enumValues).toEqual(['foo', 'bar']);
    expect(computeTsType(fooTypeField)).toBe('FooType');
  });
});

// ============================================================================
// genTypes — tagged struct literal type
// ============================================================================
describe('genTypes — tagged struct literal type', () => {
  function buildTaggedStructSpec() {
    return {
      info: { title: 'Test', version: '1.0' },
      paths: {
        '/item': {
          post: {
            requestBody: {
              content: {
                'application/json': {
                  schema: {
                    anyOf: [{ $ref: '#/components/schemas/Equipment' }, { $ref: '#/components/schemas/Consumable' }],
                    discriminator: {
                      propertyName: 'type',
                      mapping: { Equipment: '#/components/schemas/Equipment', Consumable: '#/components/schemas/Consumable' },
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
          Equipment: {
            type: 'object',
            properties: { type: { const: 'Equipment', type: 'string' }, name: { type: 'string' }, attack_bonus: { type: 'integer' } },
            required: ['type', 'name'],
          },
          Consumable: {
            type: 'object',
            properties: { type: { enum: ['Consumable'], type: 'string' }, name: { type: 'string' }, heal_amount: { type: 'integer' } },
            required: ['type', 'name'],
          },
        },
      },
    };
  }

  it('generates literal type for const discriminator field (prop.const)', () => {
    const spec = buildTaggedStructSpec();
    const parser = new OpenAPIParser(spec, '');
    const resources = parser.parse();
    const types = genTypes(spec, resources, (n, p, r) => parser.parseField(n, p, r));

    expect(types).toContain("type: 'Equipment';");
    expect(types).not.toMatch(/interface Equipment[\s\S]*?type: string;/);
  });

  it('generates literal type for single-element enum discriminator field', () => {
    const spec = buildTaggedStructSpec();
    const parser = new OpenAPIParser(spec, '');
    const resources = parser.parse();
    const types = genTypes(spec, resources, (n, p, r) => parser.parseField(n, p, r));

    expect(types).toContain("type: 'Consumable';");
    expect(types).not.toMatch(/interface Consumable[\s\S]*?type: string;/);
  });
});

// ============================================================================
// genTypes — union type definitions
// ============================================================================
describe('genTypes — union types', () => {
  function buildUnionSpec() {
    return {
      info: { title: 'Test', version: '1.0' },
      paths: {
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
        '/cat-or-dog/{id}': { get: {} },
      },
      components: {
        schemas: {
          Cat: { type: 'object', properties: { type: { type: 'string', enum: ['Cat'] }, name: { type: 'string' }, color: { type: 'string' } }, required: ['type', 'name', 'color'] },
          Dog: { type: 'object', properties: { type: { type: 'string', enum: ['Dog'] }, name: { type: 'string' }, breed: { type: 'string' } }, required: ['type', 'name', 'breed'] },
        },
      },
    };
  }

  it('generates variant interfaces and union type', () => {
    const spec = buildUnionSpec();
    const parser = new OpenAPIParser(spec, '');
    const resources = parser.parse();
    const types = genTypes(spec, resources, (n, p, r) => parser.parseField(n, p, r));

    expect(types).toContain('export interface Cat');
    expect(types).toContain('export interface Dog');
    expect(types).toContain('export type CatOrDog = Cat | Dog;');
  });
});
