import { describe, it, expect } from 'vitest';
import {
  generateProject,
  generatePyprojectToml,
  generateMainPy,
  generateImports,
  generateConfigureCall,
  generateAddModelCall,
  generateFormModel,
  generateFieldLine,
  resolveFieldType,
  generateValidators,
  generateEnumDefinitions,
  generateReadme,
  computeDependencies,
  toSnakeCase,
} from './generateProject';
import type {
  WizardState,
  ModelDefinition,
  FieldDefinition,
} from '@/types/wizard';
import {
  DEFAULT_WIZARD_STATE,
  createDefaultModel,
  createEmptyModel,
} from '@/types/wizard';

// ─── Helper ────────────────────────────────────────────────────

function makeState(overrides: Partial<WizardState> = {}): WizardState {
  return { ...DEFAULT_WIZARD_STATE, ...overrides };
}

function makeField(overrides: Partial<FieldDefinition> = {}): FieldDefinition {
  return {
    name: 'test_field',
    type: 'str',
    optional: false,
    default: '',
    isIndexed: false,
    isDisplayName: false,
    isList: false,
    ref: null,
    refRevision: null,
    ...overrides,
  };
}

function makeModel(overrides: Partial<ModelDefinition> = {}): ModelDefinition {
  return {
    ...createEmptyModel(),
    name: 'TestModel',
    ...overrides,
  };
}

// ─── generateProject ───────────────────────────────────────────

describe('generateProject', () => {
  it('produces exactly 4 files', () => {
    const files = generateProject(DEFAULT_WIZARD_STATE);
    expect(files).toHaveLength(4);
    const names = files.map((f) => f.filename);
    expect(names).toContain('pyproject.toml');
    expect(names).toContain('main.py');
    expect(names).toContain('README.md');
    expect(names).toContain('.python-version');
  });

  it('.python-version matches state', () => {
    const files = generateProject(makeState({ pythonVersion: '3.13' }));
    const pv = files.find((f) => f.filename === '.python-version')!;
    expect(pv.content).toBe('3.13\n');
  });
});

// ─── computeDependencies ───────────────────────────────────────

describe('computeDependencies', () => {
  it('memory storage → autocrud + uvicorn only', () => {
    const deps = computeDependencies(makeState({ storage: 'memory' }));
    expect(deps).toContain('autocrud>=0.8.0');
    expect(deps).toContain('uvicorn>=0.30.0');
    expect(deps).toHaveLength(2);
  });

  it('disk storage → autocrud + uvicorn only', () => {
    const deps = computeDependencies(makeState({ storage: 'disk' }));
    expect(deps).toContain('autocrud>=0.8.0');
    expect(deps).not.toContain('autocrud[s3]>=0.8.0');
  });

  it('s3 storage → autocrud[s3]', () => {
    const deps = computeDependencies(makeState({ storage: 's3' }));
    expect(deps).toContain('autocrud[s3]>=0.8.0');
    expect(deps).not.toContain('autocrud>=0.8.0');
  });

  it('postgresql → autocrud[s3] + psycopg2-binary', () => {
    const deps = computeDependencies(makeState({ storage: 'postgresql' }));
    expect(deps).toContain('autocrud[s3]>=0.8.0');
    expect(deps).toContain('psycopg2-binary');
  });
});

// ─── pyproject.toml ────────────────────────────────────────────

describe('generatePyprojectToml', () => {
  it('contains project name', () => {
    const toml = generatePyprojectToml(
      makeState({ projectName: 'my-cool-api' }),
    );
    expect(toml).toContain('name = "my-cool-api"');
  });

  it('contains python version requirement', () => {
    const toml = generatePyprojectToml(makeState({ pythonVersion: '3.11' }));
    expect(toml).toContain('requires-python = ">=3.11"');
  });

  it('contains hatchling build system', () => {
    const toml = generatePyprojectToml(makeState());
    expect(toml).toContain('hatchling');
  });
});

// ─── imports ───────────────────────────────────────────────────

describe('generateImports', () => {
  it('always imports crud and Schema', () => {
    const imports = generateImports(makeState());
    expect(imports).toContain('from autocrud import');
    expect(imports).toContain('Schema');
    expect(imports).toContain('crud');
  });

  it('imports Struct for struct style', () => {
    const imports = generateImports(makeState({ modelStyle: 'struct' }));
    expect(imports).toContain('from msgspec import Struct');
  });

  it('imports BaseModel for pydantic style', () => {
    const imports = generateImports(makeState({ modelStyle: 'pydantic' }));
    expect(imports).toContain('from pydantic import BaseModel');
  });

  it('imports DisplayName when a field uses it', () => {
    const model = makeModel({
      fields: [makeField({ isDisplayName: true })],
    });
    const imports = generateImports(makeState({ models: [model] }));
    expect(imports).toContain('DisplayName');
    expect(imports).toContain('Annotated');
  });

  it('imports Ref and OnDelete when a Ref field exists', () => {
    const model = makeModel({
      fields: [
        makeField({
          type: 'Ref',
          ref: { resource: 'other', onDelete: 'dangling' },
        }),
      ],
    });
    const imports = generateImports(makeState({ models: [model] }));
    expect(imports).toContain('Ref');
    expect(imports).toContain('OnDelete');
  });

  it('imports Binary from autocrud.types', () => {
    const model = makeModel({
      fields: [makeField({ type: 'Binary' })],
    });
    const imports = generateImports(makeState({ models: [model] }));
    expect(imports).toContain('from autocrud.types import Binary');
  });

  it('imports RefRevision from autocrud.types', () => {
    const model = makeModel({
      fields: [
        makeField({
          type: 'RefRevision',
          refRevision: { resource: 'char' },
        }),
      ],
    });
    const imports = generateImports(makeState({ models: [model] }));
    expect(imports).toContain('RefRevision');
  });

  it('imports DiskStorageFactory for disk storage', () => {
    const imports = generateImports(makeState({ storage: 'disk' }));
    expect(imports).toContain('DiskStorageFactory');
  });

  it('imports S3StorageFactory for s3 storage', () => {
    const imports = generateImports(makeState({ storage: 's3' }));
    expect(imports).toContain('S3StorageFactory');
  });

  it('imports PostgreSQLStorageFactory for postgresql storage', () => {
    const imports = generateImports(makeState({ storage: 'postgresql' }));
    expect(imports).toContain('PostgreSQLStorageFactory');
  });

  it('does not import storage factory for memory', () => {
    const imports = generateImports(makeState({ storage: 'memory' }));
    expect(imports).not.toContain('StorageFactory');
  });

  it('imports CORSMiddleware when CORS is enabled', () => {
    const imports = generateImports(makeState({ enableCORS: true }));
    expect(imports).toContain('CORSMiddleware');
  });

  it('does not import CORSMiddleware when disabled', () => {
    const imports = generateImports(makeState({ enableCORS: false }));
    expect(imports).not.toContain('CORSMiddleware');
  });

  it('imports datetime when a datetime field exists', () => {
    const model = makeModel({
      fields: [makeField({ type: 'datetime' })],
    });
    const imports = generateImports(makeState({ models: [model] }));
    expect(imports).toContain('import datetime as dt');
  });

  it('imports Enum when an enum field exists', () => {
    const model = makeModel({
      enums: [{ name: 'Color', values: [{ key: 'RED', label: 'red' }] }],
      fields: [makeField({ type: 'Enum' })],
    });
    const imports = generateImports(makeState({ models: [model] }));
    expect(imports).toContain('from enum import Enum');
  });

  it('scans code-mode rawCode for imports', () => {
    const model = makeModel({
      inputMode: 'code',
      rawCode:
        'class Evt(Job[Payload]):\n    icon: Binary\n    ref: Annotated[str, Ref("other")]',
    });
    const imports = generateImports(makeState({ models: [model] }));
    expect(imports).toContain('Job');
    expect(imports).toContain('Binary');
    expect(imports).toContain('Ref');
    expect(imports).toContain('OnDelete');
    expect(imports).toContain('Annotated');
  });
});

// ─── resolveFieldType ──────────────────────────────────────────

describe('resolveFieldType', () => {
  it('str → str', () => {
    expect(resolveFieldType(makeField({ type: 'str' }))).toBe('str');
  });

  it('str + DisplayName → Annotated[str, DisplayName()]', () => {
    expect(
      resolveFieldType(makeField({ type: 'str', isDisplayName: true })),
    ).toBe('Annotated[str, DisplayName()]');
  });

  it('str + optional → Optional[str]', () => {
    expect(resolveFieldType(makeField({ type: 'str', optional: true }))).toBe(
      'Optional[str]',
    );
  });

  it('int → int', () => {
    expect(resolveFieldType(makeField({ type: 'int' }))).toBe('int');
  });

  it('datetime → dt.datetime', () => {
    expect(resolveFieldType(makeField({ type: 'datetime' }))).toBe(
      'dt.datetime',
    );
  });

  it('Binary → Optional[Binary]', () => {
    expect(resolveFieldType(makeField({ type: 'Binary' }))).toBe(
      'Optional[Binary]',
    );
  });

  it('Ref with set_null → Annotated with OnDelete', () => {
    const result = resolveFieldType(
      makeField({
        type: 'Ref',
        optional: true,
        ref: { resource: 'guild', onDelete: 'set_null' },
      }),
    );
    expect(result).toContain('Ref("guild"');
    expect(result).toContain('OnDelete.set_null');
    expect(result).toContain('str | None');
  });

  it('Ref with dangling → no on_delete param', () => {
    const result = resolveFieldType(
      makeField({
        type: 'Ref',
        ref: { resource: 'zone', onDelete: 'dangling' },
      }),
    );
    expect(result).toContain('Ref("zone")');
    expect(result).not.toContain('OnDelete');
  });

  it('Ref as list → list[Annotated[...]]', () => {
    const result = resolveFieldType(
      makeField({
        type: 'Ref',
        isList: true,
        ref: { resource: 'skill', onDelete: 'dangling' },
      }),
    );
    expect(result).toMatch(/^list\[Annotated\[/);
  });

  it('RefRevision → Annotated with RefRevision', () => {
    const result = resolveFieldType(
      makeField({
        type: 'RefRevision',
        optional: true,
        refRevision: { resource: 'character' },
      }),
    );
    expect(result).toContain('RefRevision("character")');
    expect(result).toContain('Optional[str]');
  });

  it('list[str] → list[str]', () => {
    expect(
      resolveFieldType(makeField({ type: 'str', isList: true })),
    ).toBe('list[str]');
  });
});

// ─── generateFieldLine ─────────────────────────────────────────

describe('generateFieldLine', () => {
  it('required field → no default', () => {
    const line = generateFieldLine(makeField({ name: 'title', type: 'str' }));
    expect(line).toBe('title: str');
  });

  it('field with default → appends default', () => {
    const line = generateFieldLine(
      makeField({ name: 'count', type: 'int', default: '0' }),
    );
    expect(line).toBe('count: int = 0');
  });

  it('optional field → appends = None', () => {
    const line = generateFieldLine(
      makeField({ name: 'tag', type: 'str', optional: true }),
    );
    expect(line).toBe('tag: Optional[str] = None');
  });
});

// ─── generateFormModel ─────────────────────────────────────────

describe('generateFormModel', () => {
  it('generates Struct class', () => {
    const model = makeModel({
      name: 'Todo',
      fields: [
        makeField({ name: 'title', type: 'str', isDisplayName: true }),
        makeField({ name: 'done', type: 'bool', default: 'False' }),
      ],
    });
    const code = generateFormModel(model, 'struct');
    expect(code).toContain('class Todo(Struct):');
    expect(code).toContain('title: Annotated[str, DisplayName()]');
    expect(code).toContain('done: bool = False');
  });

  it('generates BaseModel class', () => {
    const model = makeModel({
      name: 'User',
      fields: [makeField({ name: 'email', type: 'str' })],
    });
    const code = generateFormModel(model, 'pydantic');
    expect(code).toContain('class User(BaseModel):');
  });

  it('puts required fields before defaulted fields', () => {
    const model = makeModel({
      name: 'Item',
      fields: [
        makeField({ name: 'price', type: 'int', default: '100' }),
        makeField({ name: 'name', type: 'str' }),
      ],
    });
    const code = generateFormModel(model, 'struct');
    const nameIdx = code.indexOf('name: str');
    const priceIdx = code.indexOf('price: int = 100');
    expect(nameIdx).toBeLessThan(priceIdx);
  });

  it('empty fields → pass', () => {
    const model = makeModel({ name: 'Empty', fields: [] });
    const code = generateFormModel(model, 'struct');
    expect(code).toContain('pass');
  });
});

// ─── generateEnumDefinitions ───────────────────────────────────

describe('generateEnumDefinitions', () => {
  it('returns empty string when no enums', () => {
    expect(generateEnumDefinitions(makeState())).toBe('');
  });

  it('generates enum class', () => {
    const model = makeModel({
      enums: [
        {
          name: 'Color',
          values: [
            { key: 'RED', label: 'Red' },
            { key: 'BLUE', label: 'Blue' },
          ],
        },
      ],
    });
    const result = generateEnumDefinitions(makeState({ models: [model] }));
    expect(result).toContain('class Color(Enum):');
    expect(result).toContain('RED = "Red"');
    expect(result).toContain('BLUE = "Blue"');
  });

  it('ignores code-mode models', () => {
    const model = makeModel({
      inputMode: 'code',
      enums: [
        { name: 'X', values: [{ key: 'A', label: 'a' }] },
      ],
    });
    const result = generateEnumDefinitions(makeState({ models: [model] }));
    expect(result).toBe('');
  });
});

// ─── generateValidators ────────────────────────────────────────

describe('generateValidators', () => {
  it('returns empty string when no validators enabled', () => {
    expect(generateValidators(makeState())).toBe('');
  });

  it('generates validator function', () => {
    const model = makeModel({
      name: 'User',
      enableValidator: true,
      fields: [makeField({ name: 'email', type: 'str' })],
    });
    const result = generateValidators(makeState({ models: [model] }));
    expect(result).toContain('def validate_user(data: User) -> None:');
    expect(result).toContain('errors = []');
    expect(result).toContain('raise ValueError');
  });

  it('generates sample validation for string fields', () => {
    const model = makeModel({
      name: 'Post',
      enableValidator: true,
      fields: [
        makeField({ name: 'title', type: 'str' }),
        makeField({ name: 'body', type: 'str' }),
      ],
    });
    const result = generateValidators(makeState({ models: [model] }));
    expect(result).toContain('data.title.strip()');
    expect(result).toContain('data.body.strip()');
  });

  it('skips code-mode models', () => {
    const model = makeModel({
      inputMode: 'code',
      enableValidator: true,
    });
    const result = generateValidators(makeState({ models: [model] }));
    expect(result).toBe('');
  });
});

// ─── generateConfigureCall ─────────────────────────────────────

describe('generateConfigureCall', () => {
  it('memory + defaults → crud.configure()', () => {
    const result = generateConfigureCall(makeState());
    expect(result).toBe('crud.configure()');
  });

  it('disk storage → DiskStorageFactory', () => {
    const result = generateConfigureCall(
      makeState({
        storage: 'disk',
        storageConfig: { rootdir: './mydata' },
      }),
    );
    expect(result).toContain('DiskStorageFactory');
    expect(result).toContain('./mydata');
  });

  it('s3 storage → S3StorageFactory with args', () => {
    const result = generateConfigureCall(
      makeState({
        storage: 's3',
        storageConfig: { bucket: 'my-bucket', endpointUrl: 'http://s3:9000' },
      }),
    );
    expect(result).toContain('S3StorageFactory');
    expect(result).toContain('my-bucket');
    expect(result).toContain('http://s3:9000');
  });

  it('postgresql → PostgreSQLStorageFactory', () => {
    const result = generateConfigureCall(
      makeState({
        storage: 'postgresql',
        storageConfig: {
          connectionString: 'postgresql://user:pass@host/db',
          s3Bucket: 'data',
        },
      }),
    );
    expect(result).toContain('PostgreSQLStorageFactory');
    expect(result).toContain('postgresql://user:pass@host/db');
  });

  it('non-default naming → includes model_naming', () => {
    const result = generateConfigureCall(makeState({ naming: 'snake' }));
    expect(result).toContain('model_naming="snake"');
  });

  it('default naming (kebab) → no model_naming arg', () => {
    const result = generateConfigureCall(makeState({ naming: 'kebab' }));
    expect(result).not.toContain('model_naming');
  });

  it('msgpack encoding → includes encoding', () => {
    const result = generateConfigureCall(makeState({ encoding: 'msgpack' }));
    expect(result).toContain('Encoding.msgpack');
  });
});

// ─── generateAddModelCall ──────────────────────────────────────

describe('generateAddModelCall', () => {
  it('uses Schema wrapper', () => {
    const model = makeModel({ name: 'Todo', schemaVersion: 'v1' });
    const result = generateAddModelCall(model, makeState());
    expect(result).toContain('Schema(Todo, "v1")');
  });

  it('includes validator in Schema when enabled', () => {
    const model = makeModel({
      name: 'User',
      schemaVersion: 'v2',
      enableValidator: true,
    });
    const result = generateAddModelCall(model, makeState());
    expect(result).toContain(
      'Schema(User, "v2", validator=validate_user)',
    );
  });

  it('includes indexed_fields', () => {
    const model = makeModel({
      name: 'Character',
      fields: [
        makeField({ name: 'level', type: 'int', isIndexed: true }),
        makeField({ name: 'name', type: 'str', isIndexed: true }),
        makeField({ name: 'bio', type: 'str', isIndexed: false }),
      ],
    });
    const result = generateAddModelCall(model, makeState());
    expect(result).toContain('indexed_fields=');
    expect(result).toContain('("level", int)');
    expect(result).toContain('("name", str)');
    expect(result).not.toContain('"bio"');
  });

  it('no indexed fields → simple one-liner', () => {
    const model = makeModel({
      name: 'Config',
      fields: [makeField({ name: 'key', type: 'str' })],
    });
    const result = generateAddModelCall(model, makeState());
    expect(result).toBe('crud.add_model(Schema(Config, "v1"))');
  });

  it('code-mode model → no indexed_fields', () => {
    const model = makeModel({
      name: 'Custom',
      inputMode: 'code',
      rawCode: 'class Custom(Struct):\n    x: int',
    });
    const result = generateAddModelCall(model, makeState());
    expect(result).toBe('crud.add_model(Schema(Custom, "v1"))');
  });
});

// ─── generateMainPy (integration) ─────────────────────────────

describe('generateMainPy', () => {
  it('generates valid structure for default state', () => {
    const code = generateMainPy(DEFAULT_WIZARD_STATE);
    expect(code).toContain('from autocrud import');
    expect(code).toContain('class Todo');
    expect(code).toContain('crud.configure()');
    expect(code).toContain('crud.add_model(');
    expect(code).toContain('Schema(Todo,');
    expect(code).toContain('crud.apply(app)');
    expect(code).toContain('crud.openapi(app)');
    expect(code).toContain('uvicorn.run');
  });

  it('does not contain IValidator', () => {
    const code = generateMainPy(DEFAULT_WIZARD_STATE);
    expect(code).not.toContain('IValidator');
  });

  it('does not contain IMigration', () => {
    const code = generateMainPy(DEFAULT_WIZARD_STATE);
    expect(code).not.toContain('IMigration');
  });

  it('includes CORS middleware when enabled', () => {
    const code = generateMainPy(makeState({ enableCORS: true }));
    expect(code).toContain('CORSMiddleware');
    expect(code).toContain('allow_origins');
  });

  it('excludes CORS when disabled', () => {
    const code = generateMainPy(makeState({ enableCORS: false }));
    expect(code).not.toContain('CORSMiddleware');
  });

  it('uses correct port', () => {
    const code = generateMainPy(makeState({ port: 3000 }));
    expect(code).toContain('port=3000');
  });

  it('handles multiple models', () => {
    const state = makeState({
      models: [
        makeModel({ name: 'User', schemaVersion: 'v1' }),
        makeModel({ name: 'Post', schemaVersion: 'v1' }),
      ],
    });
    const code = generateMainPy(state);
    expect(code).toContain('class User');
    expect(code).toContain('class Post');
    expect(code).toContain('Schema(User,');
    expect(code).toContain('Schema(Post,');
  });

  it('handles code-mode model with raw code', () => {
    const state = makeState({
      models: [
        makeModel({
          name: 'Custom',
          inputMode: 'code',
          rawCode: 'class Custom(Struct):\n    value: int = 42',
        }),
      ],
    });
    const code = generateMainPy(state);
    expect(code).toContain('class Custom(Struct):');
    expect(code).toContain('value: int = 42');
  });

  it('disk storage includes DiskStorageFactory', () => {
    const state = makeState({
      storage: 'disk',
      storageConfig: { rootdir: './data' },
    });
    const code = generateMainPy(state);
    expect(code).toContain('DiskStorageFactory');
    expect(code).toContain('./data');
  });

  it('postgresql storage includes PostgreSQLStorageFactory', () => {
    const state = makeState({
      storage: 'postgresql',
      storageConfig: {
        connectionString: 'postgresql://u:p@h/db',
        s3Bucket: 'b',
      },
    });
    const code = generateMainPy(state);
    expect(code).toContain('PostgreSQLStorageFactory');
    expect(code).toContain('psycopg2' === 'never' ? '' : 'postgresql://u:p@h/db');
  });

  it('includes Ref imports when model uses Ref field', () => {
    const model = makeModel({
      name: 'Monster',
      fields: [
        makeField({
          name: 'zone_id',
          type: 'Ref',
          ref: { resource: 'zone', onDelete: 'cascade' },
        }),
      ],
    });
    const code = generateMainPy(makeState({ models: [model] }));
    expect(code).toContain('Ref');
    expect(code).toContain('OnDelete');
    expect(code).toContain('Ref("zone"');
    expect(code).toContain('OnDelete.cascade');
  });
});

// ─── generateReadme ────────────────────────────────────────────

describe('generateReadme', () => {
  it('contains project name', () => {
    const md = generateReadme(
      makeState({ projectName: 'awesome-api' }),
    );
    expect(md).toContain('# awesome-api');
  });

  it('contains port in quick start', () => {
    const md = generateReadme(makeState({ port: 9090 }));
    expect(md).toContain('http://localhost:9090/docs');
  });

  it('lists all models', () => {
    const state = makeState({
      models: [
        makeModel({ name: 'Alpha', schemaVersion: 'v1' }),
        makeModel({ name: 'Beta', schemaVersion: 'v2' }),
      ],
    });
    const md = generateReadme(state);
    expect(md).toContain('**Alpha**');
    expect(md).toContain('**Beta**');
  });

  it('describes storage backend', () => {
    expect(generateReadme(makeState({ storage: 'memory' }))).toContain(
      'in-memory',
    );
    expect(
      generateReadme(
        makeState({ storage: 'disk', storageConfig: { rootdir: './db' } }),
      ),
    ).toContain('disk');
    expect(generateReadme(makeState({ storage: 's3' }))).toContain('S3');
    expect(generateReadme(makeState({ storage: 'postgresql' }))).toContain(
      'PostgreSQL',
    );
  });
});

// ─── toSnakeCase ───────────────────────────────────────────────

describe('toSnakeCase', () => {
  it('converts PascalCase', () => {
    expect(toSnakeCase('UserProfile')).toBe('user_profile');
  });

  it('converts simple name', () => {
    expect(toSnakeCase('Todo')).toBe('todo');
  });

  it('handles already snake_case', () => {
    expect(toSnakeCase('already_snake')).toBe('already_snake');
  });
});
