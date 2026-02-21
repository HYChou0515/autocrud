import { describe, it, expect } from "vitest";
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
  generateSubStructDefinitions,
  generateAppSetup,
  generateReadme,
  computeDependencies,
  toSnakeCase,
} from "./generateProject";
import type {
  WizardState,
  ModelDefinition,
  FieldDefinition,
} from "@/types/wizard";
import { DEFAULT_WIZARD_STATE, createEmptyModel } from "@/types/wizard";

// ─── Helper ────────────────────────────────────────────────────

function makeState(overrides: Partial<WizardState> = {}): WizardState {
  return { ...DEFAULT_WIZARD_STATE, ...overrides };
}

function makeField(overrides: Partial<FieldDefinition> = {}): FieldDefinition {
  return {
    name: "test_field",
    type: "str",
    optional: false,
    default: "",
    isIndexed: false,
    isDisplayName: false,
    isList: false,
    ref: null,
    refRevision: null,
    dictKeyType: null,
    dictValueType: null,
    structName: null,
    unionMembers: null,
    ...overrides,
  };
}

function makeModel(overrides: Partial<ModelDefinition> = {}): ModelDefinition {
  return {
    ...createEmptyModel(),
    name: "TestModel",
    ...overrides,
  };
}

// ─── generateProject ───────────────────────────────────────────

describe("generateProject", () => {
  it("produces exactly 4 files", () => {
    const files = generateProject(DEFAULT_WIZARD_STATE);
    expect(files).toHaveLength(4);
    const names = files.map((f) => f.filename);
    expect(names).toContain("pyproject.toml");
    expect(names).toContain("main.py");
    expect(names).toContain("README.md");
    expect(names).toContain(".python-version");
  });

  it(".python-version matches state", () => {
    const files = generateProject(makeState({ pythonVersion: "3.13" }));
    const pv = files.find((f) => f.filename === ".python-version")!;
    expect(pv.content).toBe("3.13\n");
  });
});

// ─── computeDependencies ───────────────────────────────────────

describe("computeDependencies", () => {
  it("memory storage → autocrud[graphql] + uvicorn (graphql default on)", () => {
    const deps = computeDependencies(makeState({ storage: "memory" }));
    expect(deps).toContain("autocrud[graphql]>=0.8.0");
    expect(deps).toContain("uvicorn>=0.30.0");
    expect(deps).toHaveLength(2);
  });

  it("memory storage with graphql off → base autocrud only", () => {
    const deps = computeDependencies(
      makeState({ storage: "memory", enableGraphql: false }),
    );
    expect(deps).toContain("autocrud>=0.8.0");
    expect(deps).toHaveLength(2);
  });

  it("disk storage → autocrud[graphql] (no s3)", () => {
    const deps = computeDependencies(makeState({ storage: "disk" }));
    expect(deps).toContain("autocrud[graphql]>=0.8.0");
    expect(deps).not.toContain("magic");
  });

  it("s3 storage → extras include s3 + magic + graphql", () => {
    const deps = computeDependencies(makeState({ storage: "s3" }));
    expect(deps[0]).toContain("s3");
    expect(deps[0]).toContain("magic");
    expect(deps[0]).toContain("graphql");
    expect(deps).toHaveLength(2);
  });

  it("postgresql → extras include graphql,magic,postgresql,s3", () => {
    const deps = computeDependencies(makeState({ storage: "postgresql" }));
    expect(deps[0]).toContain("postgresql");
    expect(deps[0]).toContain("s3");
    expect(deps[0]).toContain("magic");
    expect(deps[0]).toContain("graphql");
    expect(deps).not.toContain("psycopg2-binary");
  });

  it("extras are sorted alphabetically", () => {
    const deps = computeDependencies(makeState({ storage: "postgresql" }));
    // graphql, magic, postgresql, s3
    expect(deps[0]).toBe("autocrud[graphql,magic,postgresql,s3]>=0.8.0");
  });

  it("s3 with graphql off → s3 + magic only", () => {
    const deps = computeDependencies(
      makeState({ storage: "s3", enableGraphql: false }),
    );
    expect(deps[0]).toBe("autocrud[magic,s3]>=0.8.0");
  });
});

// ─── pyproject.toml ────────────────────────────────────────────

describe("generatePyprojectToml", () => {
  it("contains project name", () => {
    const toml = generatePyprojectToml(
      makeState({ projectName: "my-cool-api" }),
    );
    expect(toml).toContain('name = "my-cool-api"');
  });

  it("contains python version requirement", () => {
    const toml = generatePyprojectToml(makeState({ pythonVersion: "3.11" }));
    expect(toml).toContain('requires-python = ">=3.11"');
  });

  it("contains hatchling build system", () => {
    const toml = generatePyprojectToml(makeState());
    expect(toml).toContain("hatchling");
  });
});

// ─── imports ───────────────────────────────────────────────────

describe("generateImports", () => {
  it("always imports crud and Schema", () => {
    const imports = generateImports(makeState());
    expect(imports).toContain("from autocrud import");
    expect(imports).toContain("Schema");
    expect(imports).toContain("crud");
  });

  it("imports Struct for struct style", () => {
    const imports = generateImports(makeState({ modelStyle: "struct" }));
    expect(imports).toContain("from msgspec import Struct");
  });

  it("imports BaseModel for pydantic style", () => {
    const imports = generateImports(makeState({ modelStyle: "pydantic" }));
    expect(imports).toContain("from pydantic import BaseModel");
  });

  it("imports DisplayName when a field uses it", () => {
    const model = makeModel({
      fields: [makeField({ isDisplayName: true })],
    });
    const imports = generateImports(makeState({ models: [model] }));
    expect(imports).toContain("DisplayName");
    expect(imports).toContain("Annotated");
  });

  it("imports Ref and OnDelete when a Ref field exists", () => {
    const model = makeModel({
      fields: [
        makeField({
          type: "Ref",
          ref: { resource: "other", onDelete: "dangling" },
        }),
      ],
    });
    const imports = generateImports(makeState({ models: [model] }));
    expect(imports).toContain("Ref");
    expect(imports).toContain("OnDelete");
  });

  it("imports Binary from autocrud.types", () => {
    const model = makeModel({
      fields: [makeField({ type: "Binary" })],
    });
    const imports = generateImports(makeState({ models: [model] }));
    expect(imports).toContain("from autocrud.types import Binary");
  });

  it("imports RefRevision from autocrud.types", () => {
    const model = makeModel({
      fields: [
        makeField({
          type: "RefRevision",
          refRevision: { resource: "char" },
        }),
      ],
    });
    const imports = generateImports(makeState({ models: [model] }));
    expect(imports).toContain("RefRevision");
  });

  it("imports DiskStorageFactory for disk storage", () => {
    const imports = generateImports(makeState({ storage: "disk" }));
    expect(imports).toContain("DiskStorageFactory");
  });

  it("imports S3StorageFactory for s3 storage", () => {
    const imports = generateImports(makeState({ storage: "s3" }));
    expect(imports).toContain("S3StorageFactory");
  });

  it("imports PostgreSQLStorageFactory for postgresql storage", () => {
    const imports = generateImports(makeState({ storage: "postgresql" }));
    expect(imports).toContain("PostgreSQLStorageFactory");
  });

  it("does not import storage factory for memory", () => {
    const imports = generateImports(makeState({ storage: "memory" }));
    expect(imports).not.toContain("StorageFactory");
  });

  it("imports CORSMiddleware when CORS is enabled", () => {
    const imports = generateImports(makeState({ enableCORS: true }));
    expect(imports).toContain("CORSMiddleware");
  });

  it("does not import CORSMiddleware when disabled", () => {
    const imports = generateImports(makeState({ enableCORS: false }));
    expect(imports).not.toContain("CORSMiddleware");
  });

  it("imports datetime when a datetime field exists", () => {
    const model = makeModel({
      fields: [makeField({ type: "datetime" })],
    });
    const imports = generateImports(makeState({ models: [model] }));
    expect(imports).toContain("import datetime as dt");
  });

  it("imports Enum when an enum field exists", () => {
    const model = makeModel({
      enums: [{ name: "Color", values: [{ key: "RED", label: "red" }] }],
      fields: [makeField({ type: "Enum" })],
    });
    const imports = generateImports(makeState({ models: [model] }));
    expect(imports).toContain("from enum import Enum");
  });

  it("scans code-mode rawCode for imports", () => {
    const model = makeModel({
      inputMode: "code",
      rawCode:
        'class Evt(Job[Payload]):\n    icon: Binary\n    ref: Annotated[str, Ref("other")]',
    });
    const imports = generateImports(makeState({ models: [model] }));
    expect(imports).toContain("Job");
    expect(imports).toContain("Binary");
    expect(imports).toContain("Ref");
    expect(imports).toContain("OnDelete");
    expect(imports).toContain("Annotated");
  });
});

// ─── resolveFieldType ──────────────────────────────────────────

describe("resolveFieldType", () => {
  it("str → str", () => {
    expect(resolveFieldType(makeField({ type: "str" }))).toBe("str");
  });

  it("str + DisplayName → Annotated[str, DisplayName()]", () => {
    expect(
      resolveFieldType(makeField({ type: "str", isDisplayName: true })),
    ).toBe("Annotated[str, DisplayName()]");
  });

  it("str + optional → Optional[str]", () => {
    expect(resolveFieldType(makeField({ type: "str", optional: true }))).toBe(
      "Optional[str]",
    );
  });

  it("int → int", () => {
    expect(resolveFieldType(makeField({ type: "int" }))).toBe("int");
  });

  it("datetime → dt.datetime", () => {
    expect(resolveFieldType(makeField({ type: "datetime" }))).toBe(
      "dt.datetime",
    );
  });

  it("Binary → Optional[Binary]", () => {
    expect(resolveFieldType(makeField({ type: "Binary" }))).toBe(
      "Optional[Binary]",
    );
  });

  it("Ref with set_null → Annotated with OnDelete", () => {
    const result = resolveFieldType(
      makeField({
        type: "Ref",
        optional: true,
        ref: { resource: "guild", onDelete: "set_null" },
      }),
    );
    expect(result).toContain('Ref("guild"');
    expect(result).toContain("OnDelete.set_null");
    expect(result).toContain("str | None");
  });

  it("Ref with dangling → no on_delete param", () => {
    const result = resolveFieldType(
      makeField({
        type: "Ref",
        ref: { resource: "zone", onDelete: "dangling" },
      }),
    );
    expect(result).toContain('Ref("zone")');
    expect(result).not.toContain("OnDelete");
  });

  it("Ref as list → list[Annotated[...]]", () => {
    const result = resolveFieldType(
      makeField({
        type: "Ref",
        isList: true,
        ref: { resource: "skill", onDelete: "dangling" },
      }),
    );
    expect(result).toMatch(/^list\[Annotated\[/);
  });

  it("RefRevision → Annotated with RefRevision", () => {
    const result = resolveFieldType(
      makeField({
        type: "RefRevision",
        optional: true,
        refRevision: { resource: "character" },
      }),
    );
    expect(result).toContain('RefRevision("character")');
    expect(result).toContain("Optional[str]");
  });

  it("list[str] → list[str]", () => {
    expect(resolveFieldType(makeField({ type: "str", isList: true }))).toBe(
      "list[str]",
    );
  });

  it("list[int] → list[int]", () => {
    expect(resolveFieldType(makeField({ type: "int", isList: true }))).toBe(
      "list[int]",
    );
  });

  it("list[float] → list[float]", () => {
    expect(resolveFieldType(makeField({ type: "float", isList: true }))).toBe(
      "list[float]",
    );
  });

  it("list[Struct] → list[StructName]", () => {
    expect(
      resolveFieldType(
        makeField({ type: "Struct", isList: true, structName: "Equipment" }),
      ),
    ).toBe("list[Equipment]");
  });
});

// ─── generateFieldLine ─────────────────────────────────────────

describe("generateFieldLine", () => {
  it("required field → no default", () => {
    const line = generateFieldLine(makeField({ name: "title", type: "str" }));
    expect(line).toBe("title: str");
  });

  it("field with default → appends default", () => {
    const line = generateFieldLine(
      makeField({ name: "count", type: "int", default: "0" }),
    );
    expect(line).toBe("count: int = 0");
  });

  it("optional field → appends = None", () => {
    const line = generateFieldLine(
      makeField({ name: "tag", type: "str", optional: true }),
    );
    expect(line).toBe("tag: Optional[str] = None");
  });
});

// ─── generateFormModel ─────────────────────────────────────────

describe("generateFormModel", () => {
  it("generates Struct class", () => {
    const model = makeModel({
      name: "Todo",
      fields: [
        makeField({ name: "title", type: "str", isDisplayName: true }),
        makeField({ name: "done", type: "bool", default: "False" }),
      ],
    });
    const code = generateFormModel(model, "struct");
    expect(code).toContain("class Todo(Struct):");
    expect(code).toContain("title: Annotated[str, DisplayName()]");
    expect(code).toContain("done: bool = False");
  });

  it("generates BaseModel class", () => {
    const model = makeModel({
      name: "User",
      fields: [makeField({ name: "email", type: "str" })],
    });
    const code = generateFormModel(model, "pydantic");
    expect(code).toContain("class User(BaseModel):");
  });

  it("puts required fields before defaulted fields", () => {
    const model = makeModel({
      name: "Item",
      fields: [
        makeField({ name: "price", type: "int", default: "100" }),
        makeField({ name: "name", type: "str" }),
      ],
    });
    const code = generateFormModel(model, "struct");
    const nameIdx = code.indexOf("name: str");
    const priceIdx = code.indexOf("price: int = 100");
    expect(nameIdx).toBeLessThan(priceIdx);
  });

  it("empty fields → pass", () => {
    const model = makeModel({ name: "Empty", fields: [] });
    const code = generateFormModel(model, "struct");
    expect(code).toContain("pass");
  });
});

// ─── generateEnumDefinitions ───────────────────────────────────

describe("generateEnumDefinitions", () => {
  it("returns empty string when no enums", () => {
    expect(generateEnumDefinitions(makeState())).toBe("");
  });

  it("generates enum class", () => {
    const model = makeModel({
      enums: [
        {
          name: "Color",
          values: [
            { key: "RED", label: "Red" },
            { key: "BLUE", label: "Blue" },
          ],
        },
      ],
    });
    const result = generateEnumDefinitions(makeState({ models: [model] }));
    expect(result).toContain("class Color(Enum):");
    expect(result).toContain('RED = "Red"');
    expect(result).toContain('BLUE = "Blue"');
  });

  it("ignores code-mode models", () => {
    const model = makeModel({
      inputMode: "code",
      enums: [{ name: "X", values: [{ key: "A", label: "a" }] }],
    });
    const result = generateEnumDefinitions(makeState({ models: [model] }));
    expect(result).toBe("");
  });
});

// ─── generateValidators ────────────────────────────────────────

describe("generateValidators", () => {
  it("returns empty string when no validators enabled", () => {
    expect(generateValidators(makeState())).toBe("");
  });

  it("generates validator function", () => {
    const model = makeModel({
      name: "User",
      enableValidator: true,
      fields: [makeField({ name: "email", type: "str" })],
    });
    const result = generateValidators(makeState({ models: [model] }));
    expect(result).toContain("def validate_user(data: User) -> None:");
    expect(result).toContain("errors = []");
    expect(result).toContain("raise ValueError");
  });

  it("generates sample validation for string fields", () => {
    const model = makeModel({
      name: "Post",
      enableValidator: true,
      fields: [
        makeField({ name: "title", type: "str" }),
        makeField({ name: "body", type: "str" }),
      ],
    });
    const result = generateValidators(makeState({ models: [model] }));
    expect(result).toContain("data.title.strip()");
    expect(result).toContain("data.body.strip()");
  });

  it("code-mode with enableValidator → generates scaffold", () => {
    const model = makeModel({
      inputMode: "code",
      enableValidator: true,
    });
    const result = generateValidators(makeState({ models: [model] }));
    expect(result).toContain("def validate_test_model");
    expect(result).toContain("pass");
  });
});

// ─── generateConfigureCall ─────────────────────────────────────

describe("generateConfigureCall", () => {
  it("memory + defaults → crud.configure()", () => {
    const result = generateConfigureCall(makeState());
    expect(result).toBe("crud.configure()");
  });

  it("disk storage → DiskStorageFactory", () => {
    const result = generateConfigureCall(
      makeState({
        storage: "disk",
        storageConfig: { rootdir: "./mydata" },
      }),
    );
    expect(result).toContain("DiskStorageFactory");
    expect(result).toContain("./mydata");
  });

  it("s3 storage → S3StorageFactory with args", () => {
    const result = generateConfigureCall(
      makeState({
        storage: "s3",
        storageConfig: { bucket: "my-bucket", endpointUrl: "http://s3:9000" },
      }),
    );
    expect(result).toContain("S3StorageFactory");
    expect(result).toContain("my-bucket");
    expect(result).toContain("http://s3:9000");
  });

  it("s3 storage defaults → always emits all params", () => {
    const result = generateConfigureCall(
      makeState({
        storage: "s3",
        storageConfig: {},
      }),
    );
    expect(result).toContain('bucket="autocrud"');
    expect(result).toContain('endpoint_url="http://localhost:9000"');
    expect(result).toContain('access_key_id="minioadmin"');
    expect(result).toContain('secret_access_key="minioadmin"');
    expect(result).toContain('region_name="us-east-1"');
  });

  it("postgresql → PostgreSQLStorageFactory", () => {
    const result = generateConfigureCall(
      makeState({
        storage: "postgresql",
        storageConfig: {
          connectionString: "postgresql://user:pass@host/db",
          s3Bucket: "data",
        },
      }),
    );
    expect(result).toContain("PostgreSQLStorageFactory");
    expect(result).toContain("postgresql://user:pass@host/db");
  });

  it("postgresql with no user input → emits connection_string and s3_bucket fallback defaults", () => {
    const result = generateConfigureCall(
      makeState({
        storage: "postgresql",
        storageConfig: {},
      }),
    );
    expect(result).toContain("PostgreSQLStorageFactory");
    expect(result).toContain("connection_string=");
    expect(result).toContain("s3_bucket=");
    expect(result).toContain("blob_bucket=");
  });

  it("non-default naming → includes model_naming", () => {
    const result = generateConfigureCall(makeState({ naming: "snake" }));
    expect(result).toContain('model_naming="snake"');
  });

  it("default naming (kebab) → no model_naming arg", () => {
    const result = generateConfigureCall(makeState({ naming: "kebab" }));
    expect(result).not.toContain("model_naming");
  });

  it("msgpack encoding → includes encoding", () => {
    const result = generateConfigureCall(makeState({ encoding: "msgpack" }));
    expect(result).toContain("Encoding.msgpack");
  });
});

// ─── generateAddModelCall ──────────────────────────────────────

describe("generateAddModelCall", () => {
  it("uses Schema wrapper", () => {
    const model = makeModel({ name: "Todo", schemaVersion: "v1" });
    const result = generateAddModelCall(model);
    expect(result).toContain('Schema(Todo, "v1")');
  });

  it("includes validator in Schema when enabled", () => {
    const model = makeModel({
      name: "User",
      schemaVersion: "v2",
      enableValidator: true,
    });
    const result = generateAddModelCall(model);
    expect(result).toContain('Schema(User, "v2", validator=validate_user)');
  });

  it("includes indexed_fields", () => {
    const model = makeModel({
      name: "Character",
      fields: [
        makeField({ name: "level", type: "int", isIndexed: true }),
        makeField({ name: "name", type: "str", isIndexed: true }),
        makeField({ name: "bio", type: "str", isIndexed: false }),
      ],
    });
    const result = generateAddModelCall(model);
    expect(result).toContain("indexed_fields=");
    expect(result).toContain('("level", int)');
    expect(result).toContain('("name", str)');
    expect(result).not.toContain('"bio"');
  });

  it("no indexed fields → simple one-liner", () => {
    const model = makeModel({
      name: "Config",
      fields: [makeField({ name: "key", type: "str" })],
    });
    const result = generateAddModelCall(model);
    expect(result).toBe('crud.add_model(Schema(Config, "v1"))');
  });

  it("code-mode model → no indexed_fields", () => {
    const model = makeModel({
      name: "Custom",
      inputMode: "code",
      rawCode: "class Custom(Struct):\n    x: int",
    });
    const result = generateAddModelCall(model);
    expect(result).toBe('crud.add_model(Schema(Custom, "v1"))');
  });
});

// ─── generateMainPy (integration) ─────────────────────────────

describe("generateMainPy", () => {
  it("generates valid structure for default state", () => {
    const code = generateMainPy(DEFAULT_WIZARD_STATE);
    expect(code).toContain("from autocrud import");
    expect(code).toContain("class Todo");
    expect(code).toContain("crud.configure()");
    expect(code).toContain("crud.add_model(");
    expect(code).toContain("Schema(Todo,");
    expect(code).toContain("crud.apply(app)");
    expect(code).toContain("crud.openapi(app)");
    expect(code).toContain("uvicorn.run");
  });

  it("does not contain IValidator", () => {
    const code = generateMainPy(DEFAULT_WIZARD_STATE);
    expect(code).not.toContain("IValidator");
  });

  it("contains commented-out migration snippet with Schema.step API", () => {
    const code = generateMainPy(DEFAULT_WIZARD_STATE);
    // Migration is now always present as a comment using Schema.step() API
    expect(code).toContain("# ===== Migration (uncomment to enable) =====");
    expect(code).not.toContain("IMigration");
  });

  it("includes CORS middleware when enabled", () => {
    const code = generateMainPy(makeState({ enableCORS: true }));
    expect(code).toContain("CORSMiddleware");
    expect(code).toContain("allow_origins");
  });

  it("excludes CORS when disabled", () => {
    const code = generateMainPy(makeState({ enableCORS: false }));
    expect(code).not.toContain("CORSMiddleware");
  });

  it("uses correct port", () => {
    const code = generateMainPy(makeState({ port: 3000 }));
    expect(code).toContain("port=3000");
  });

  it("handles multiple models", () => {
    const state = makeState({
      models: [
        makeModel({ name: "User", schemaVersion: "v1" }),
        makeModel({ name: "Post", schemaVersion: "v1" }),
      ],
    });
    const code = generateMainPy(state);
    expect(code).toContain("class User");
    expect(code).toContain("class Post");
    expect(code).toContain("Schema(User,");
    expect(code).toContain("Schema(Post,");
  });

  it("handles code-mode model with raw code", () => {
    const state = makeState({
      models: [
        makeModel({
          name: "Custom",
          inputMode: "code",
          rawCode: "class Custom(Struct):\n    value: int = 42",
        }),
      ],
    });
    const code = generateMainPy(state);
    expect(code).toContain("class Custom(Struct):");
    expect(code).toContain("value: int = 42");
  });

  it("disk storage includes DiskStorageFactory", () => {
    const state = makeState({
      storage: "disk",
      storageConfig: { rootdir: "./data" },
    });
    const code = generateMainPy(state);
    expect(code).toContain("DiskStorageFactory");
    expect(code).toContain("./data");
  });

  it("postgresql storage includes PostgreSQLStorageFactory", () => {
    const state = makeState({
      storage: "postgresql",
      storageConfig: {
        connectionString: "postgresql://u:p@h/db",
        s3Bucket: "b",
      },
    });
    const code = generateMainPy(state);
    expect(code).toContain("PostgreSQLStorageFactory");
    expect(code).toContain("postgresql://u:p@h/db");
  });

  it("includes Ref imports when model uses Ref field", () => {
    const model = makeModel({
      name: "Monster",
      fields: [
        makeField({
          name: "zone_id",
          type: "Ref",
          ref: { resource: "zone", onDelete: "cascade" },
        }),
      ],
    });
    const code = generateMainPy(makeState({ models: [model] }));
    expect(code).toContain("Ref");
    expect(code).toContain("OnDelete");
    expect(code).toContain('Ref("zone"');
    expect(code).toContain("OnDelete.cascade");
  });
});

// ─── generateReadme ────────────────────────────────────────────

describe("generateReadme", () => {
  it("contains project name", () => {
    const md = generateReadme(makeState({ projectName: "awesome-api" }));
    expect(md).toContain("# awesome-api");
  });

  it("contains port in quick start", () => {
    const md = generateReadme(makeState({ port: 9090 }));
    expect(md).toContain("http://localhost:9090/docs");
  });

  it("lists all models", () => {
    const state = makeState({
      models: [
        makeModel({ name: "Alpha", schemaVersion: "v1" }),
        makeModel({ name: "Beta", schemaVersion: "v2" }),
      ],
    });
    const md = generateReadme(state);
    expect(md).toContain("**Alpha**");
    expect(md).toContain("**Beta**");
  });

  it("describes storage backend", () => {
    expect(generateReadme(makeState({ storage: "memory" }))).toContain(
      "in-memory",
    );
    expect(
      generateReadme(
        makeState({ storage: "disk", storageConfig: { rootdir: "./db" } }),
      ),
    ).toContain("disk");
    expect(generateReadme(makeState({ storage: "s3" }))).toContain("S3");
    expect(generateReadme(makeState({ storage: "postgresql" }))).toContain(
      "PostgreSQL",
    );
  });
});

// ─── toSnakeCase ───────────────────────────────────────────────

describe("toSnakeCase", () => {
  it("converts PascalCase", () => {
    expect(toSnakeCase("UserProfile")).toBe("user_profile");
  });

  it("converts simple name", () => {
    expect(toSnakeCase("Todo")).toBe("todo");
  });

  it("handles already snake_case", () => {
    expect(toSnakeCase("already_snake")).toBe("already_snake");
  });
});

// ─── Phase 1: DisplayName 互斥 (generator protection) ─────────

describe("DisplayName edge cases", () => {
  it("multiple isDisplayName fields → all get Annotated", () => {
    // Generator faithfully generates what it's given — UI should enforce exclusivity
    const model = makeModel({
      name: "Multi",
      fields: [
        makeField({ name: "a", type: "str", isDisplayName: true }),
        makeField({ name: "b", type: "str", isDisplayName: true }),
      ],
    });
    const code = generateFormModel(model, "struct");
    expect(code).toContain("a: Annotated[str, DisplayName()]");
    expect(code).toContain("b: Annotated[str, DisplayName()]");
  });

  it("isDisplayName on non-str field → ignored", () => {
    const result = resolveFieldType(
      makeField({ type: "int", isDisplayName: true }),
    );
    expect(result).toBe("int");
    expect(result).not.toContain("DisplayName");
  });
});

// ─── Phase 2: Dict ─────────────────────────────────────────────

describe("dict field type", () => {
  it("bare dict → dict", () => {
    expect(resolveFieldType(makeField({ type: "dict" }))).toBe("dict");
  });

  it("typed dict → dict[str, int]", () => {
    expect(
      resolveFieldType(
        makeField({ type: "dict", dictKeyType: "str", dictValueType: "int" }),
      ),
    ).toBe("dict[str, int]");
  });

  it("optional dict → Optional[dict]", () => {
    expect(resolveFieldType(makeField({ type: "dict", optional: true }))).toBe(
      "Optional[dict]",
    );
  });

  it("list of dict → list[dict]", () => {
    expect(resolveFieldType(makeField({ type: "dict", isList: true }))).toBe(
      "list[dict]",
    );
  });

  it("optional typed dict → Optional[dict[str, Any]]", () => {
    expect(
      resolveFieldType(
        makeField({
          type: "dict",
          optional: true,
          dictKeyType: "str",
          dictValueType: "Any",
        }),
      ),
    ).toBe("Optional[dict[str, Any]]");
  });

  it("dict[str, Any] → dict[str, Any]", () => {
    expect(
      resolveFieldType(
        makeField({
          type: "dict",
          dictKeyType: "str",
          dictValueType: "Any",
        }),
      ),
    ).toBe("dict[str, Any]");
  });

  it("dict[str, str] → dict[str, str]", () => {
    expect(
      resolveFieldType(
        makeField({
          type: "dict",
          dictKeyType: "str",
          dictValueType: "str",
        }),
      ),
    ).toBe("dict[str, str]");
  });

  it("dict field line with default", () => {
    const line = generateFieldLine(
      makeField({ name: "extra", type: "dict", default: "{}" }),
    );
    expect(line).toBe("extra: dict = {}");
  });

  it("dict imports Any when used in typed dict", () => {
    const model = makeModel({
      fields: [
        makeField({ type: "dict", dictKeyType: "str", dictValueType: "Any" }),
      ],
    });
    const imports = generateImports(makeState({ models: [model] }));
    expect(imports).toContain("Any");
  });
});

// ─── Phase 3: Sub-struct / Nested Class ────────────────────────

describe("Struct field type", () => {
  it("Struct → struct name", () => {
    expect(
      resolveFieldType(makeField({ type: "Struct", structName: "Equipment" })),
    ).toBe("Equipment");
  });

  it("list[Struct] → list[Equipment]", () => {
    expect(
      resolveFieldType(
        makeField({ type: "Struct", structName: "Equipment", isList: true }),
      ),
    ).toBe("list[Equipment]");
  });

  it("optional Struct → Optional[Equipment]", () => {
    expect(
      resolveFieldType(
        makeField({ type: "Struct", structName: "Equipment", optional: true }),
      ),
    ).toBe("Optional[Equipment]");
  });

  it("Struct without structName → fallback to str", () => {
    expect(resolveFieldType(makeField({ type: "Struct" }))).toBe("str");
  });
});

describe("generateSubStructDefinitions", () => {
  it("returns empty string when no sub-structs", () => {
    expect(generateSubStructDefinitions(makeState())).toBe("");
  });

  it("generates sub-struct class", () => {
    const model = makeModel({
      subStructs: [
        {
          name: "Equipment",
          tag: "",
          fields: [
            makeField({ name: "slot", type: "str" }),
            makeField({ name: "level", type: "int", default: "1" }),
          ],
        },
      ],
    });
    const result = generateSubStructDefinitions(makeState({ models: [model] }));
    expect(result).toContain("class Equipment(Struct):");
    expect(result).toContain("slot: str");
    expect(result).toContain("level: int = 1");
  });

  it("generates tagged sub-struct", () => {
    const model = makeModel({
      subStructs: [
        {
          name: "ActiveSkill",
          tag: "active",
          fields: [makeField({ name: "damage", type: "int" })],
        },
      ],
    });
    const result = generateSubStructDefinitions(makeState({ models: [model] }));
    expect(result).toContain('class ActiveSkill(Struct, tag="active"):');
  });

  it("ignores code-mode models", () => {
    const model = makeModel({
      inputMode: "code",
      subStructs: [
        {
          name: "Foo",
          tag: "",
          fields: [makeField({ name: "x", type: "int" })],
        },
      ],
    });
    const result = generateSubStructDefinitions(makeState({ models: [model] }));
    expect(result).toBe("");
  });

  it("generates multiple sub-structs across models", () => {
    const m1 = makeModel({
      name: "A",
      subStructs: [
        {
          name: "Sub1",
          tag: "",
          fields: [makeField({ name: "x", type: "int" })],
        },
      ],
    });
    const m2 = makeModel({
      name: "B",
      subStructs: [
        {
          name: "Sub2",
          tag: "two",
          fields: [makeField({ name: "y", type: "str" })],
        },
      ],
    });
    const result = generateSubStructDefinitions(
      makeState({ models: [m1, m2] }),
    );
    expect(result).toContain("class Sub1(Struct):");
    expect(result).toContain('class Sub2(Struct, tag="two"):');
  });

  it("generates auto-tagged sub-struct (tag=True)", () => {
    const model = makeModel({
      subStructs: [
        {
          name: "Warrior",
          tag: true,
          fields: [makeField({ name: "strength", type: "int" })],
        },
      ],
    });
    const result = generateSubStructDefinitions(makeState({ models: [model] }));
    expect(result).toContain("class Warrior(Struct, tag=True):");
    expect(result).not.toContain('tag="True"');
    expect(result).not.toContain('tag="true"');
  });
});

// ─── Phase 4: Union ────────────────────────────────────────────

describe("Union field type", () => {
  it("simple union → str | int", () => {
    expect(
      resolveFieldType(
        makeField({ type: "Union", unionMembers: ["str", "int"] }),
      ),
    ).toBe("str | int");
  });

  it("struct union → A | B | C", () => {
    expect(
      resolveFieldType(
        makeField({
          type: "Union",
          unionMembers: ["ActiveSkill", "PassiveSkill", "UltimateSkill"],
        }),
      ),
    ).toBe("ActiveSkill | PassiveSkill | UltimateSkill");
  });

  it("optional union → Optional[str | int]", () => {
    expect(
      resolveFieldType(
        makeField({
          type: "Union",
          unionMembers: ["str", "int"],
          optional: true,
        }),
      ),
    ).toBe("Optional[str | int]");
  });

  it("list of union → list[str | int]", () => {
    expect(
      resolveFieldType(
        makeField({
          type: "Union",
          unionMembers: ["str", "int"],
          isList: true,
        }),
      ),
    ).toBe("list[str | int]");
  });

  it("Union without members → fallback to str", () => {
    expect(resolveFieldType(makeField({ type: "Union" }))).toBe("str");
    expect(
      resolveFieldType(makeField({ type: "Union", unionMembers: [] })),
    ).toBe("str");
  });
});

// ─── Integration: main.py with new types ───────────────────────

describe("generateMainPy with new types", () => {
  it("sub-struct definitions appear before model definitions", () => {
    const model = makeModel({
      name: "Character",
      subStructs: [
        {
          name: "Equipment",
          tag: "",
          fields: [makeField({ name: "slot", type: "str" })],
        },
      ],
      fields: [
        makeField({
          name: "equipments",
          type: "Struct",
          structName: "Equipment",
          isList: true,
          default: "[]",
        }),
      ],
    });
    const code = generateMainPy(makeState({ models: [model] }));
    const subStructIdx = code.indexOf("class Equipment(Struct):");
    const modelIdx = code.indexOf("class Character(Struct):");
    expect(subStructIdx).toBeGreaterThan(-1);
    expect(modelIdx).toBeGreaterThan(-1);
    expect(subStructIdx).toBeLessThan(modelIdx);
    expect(code).toContain("equipments: list[Equipment] = []");
  });

  it("dict field generates correct code", () => {
    const model = makeModel({
      name: "Event",
      fields: [
        makeField({
          name: "extra_data",
          type: "dict",
          default: "{}",
        }),
      ],
    });
    const code = generateMainPy(makeState({ models: [model] }));
    expect(code).toContain("extra_data: dict = {}");
  });

  it("union field generates correct code", () => {
    const model = makeModel({
      name: "Skill",
      subStructs: [
        {
          name: "Active",
          tag: "active",
          fields: [makeField({ name: "dmg", type: "int" })],
        },
        {
          name: "Passive",
          tag: "passive",
          fields: [makeField({ name: "buff", type: "str" })],
        },
      ],
      fields: [
        makeField({
          name: "detail",
          type: "Union",
          unionMembers: ["Active", "Passive"],
        }),
      ],
    });
    const code = generateMainPy(makeState({ models: [model] }));
    expect(code).toContain('class Active(Struct, tag="active"):');
    expect(code).toContain('class Passive(Struct, tag="passive"):');
    expect(code).toContain("detail: Active | Passive");
  });

  it("auto-tagged sub-struct generates tag=True", () => {
    const model = makeModel({
      name: "Hero",
      subStructs: [
        {
          name: "MeleeClass",
          tag: true,
          fields: [makeField({ name: "atk", type: "int" })],
        },
        {
          name: "RangedClass",
          tag: true,
          fields: [makeField({ name: "range", type: "int" })],
        },
      ],
      fields: [
        makeField({
          name: "spec",
          type: "Union",
          unionMembers: ["MeleeClass", "RangedClass"],
        }),
      ],
    });
    const code = generateMainPy(makeState({ models: [model] }));
    expect(code).toContain("class MeleeClass(Struct, tag=True):");
    expect(code).toContain("class RangedClass(Struct, tag=True):");
    expect(code).toContain("spec: MeleeClass | RangedClass");
  });
});

// ─── F1: PostgreSQL+S3 full params ─────────────────────────────

describe("F1: PostgreSQL+S3 full params", () => {
  it("postgresql with all params emits every arg", () => {
    const result = generateConfigureCall(
      makeState({
        storage: "postgresql",
        storageConfig: {
          connectionString: "postgresql://u:p@h/db",
          s3Bucket: "data",
          s3EndpointUrl: "http://s3:9000",
          s3Region: "us-east-1",
          s3AccessKeyId: "AKID",
          s3SecretAccessKey: "SECRET",
          tablePrefix: "pf_",
          blobBucket: "blobs",
          blobPrefix: "bp_",
        },
      }),
    );
    expect(result).toContain("PostgreSQLStorageFactory");
    expect(result).toContain('connection_string="postgresql://u:p@h/db"');
    expect(result).toContain('s3_bucket="data"');
    expect(result).toContain('s3_endpoint_url="http://s3:9000"');
    expect(result).toContain('s3_region="us-east-1"');
    expect(result).toContain('s3_access_key_id="AKID"');
    expect(result).toContain('s3_secret_access_key="SECRET"');
    expect(result).toContain('table_prefix="pf_"');
    expect(result).toContain('blob_bucket="blobs"');
    expect(result).toContain('blob_prefix="bp_"');
  });

  it("postgresql default → always emits all params with defaults", () => {
    const result = generateConfigureCall(
      makeState({
        storage: "postgresql",
        storageConfig: { connectionString: "pg://host/db" },
      }),
    );
    expect(result).toContain('connection_string="pg://host/db"');
    // All params are always emitted with defaults
    expect(result).toContain('s3_region="us-east-1"');
    expect(result).toContain('s3_access_key_id="minioadmin"');
    expect(result).toContain('s3_secret_access_key="minioadmin"');
    expect(result).toContain('s3_endpoint_url="http://localhost:9000"');
    expect(result).toContain('table_prefix=""');
    expect(result).toContain('blob_prefix="blobs/"');
    // blob_bucket always emitted, fallback to s3_bucket or 'autocrud'
    expect(result).toContain('blob_bucket="autocrud"');
  });
});

// ─── F2: Custom SimpleStorage ──────────────────────────────────

describe("F2: Custom SimpleStorage", () => {
  it("custom storage → SimpleStorage import", () => {
    const result = generateImports(
      makeState({
        storage: "custom",
        storageConfig: {
          customMetaStore: "memory",
          customResourceStore: "memory",
        },
      }),
    );
    expect(result).toContain("SimpleStorage");
  });

  it("custom with MemoryMetaStore + DiskResourceStore", () => {
    const result = generateConfigureCall(
      makeState({
        storage: "custom",
        storageConfig: {
          customMetaStore: "memory",
          customResourceStore: "disk",
          resRootdir: "./res",
        },
      }),
    );
    expect(result).toContain("SimpleStorage");
    expect(result).toContain("MemoryMetaStore");
    expect(result).toContain("DiskResourceStore");
    expect(result).toContain("./res");
  });

  it("custom with postgres meta + s3 resource", () => {
    const result = generateConfigureCall(
      makeState({
        storage: "custom",
        storageConfig: {
          customMetaStore: "postgres",
          customResourceStore: "s3",
          metaPostgresDsn: "pg://h/db",
          resBucket: "mybucket",
        },
      }),
    );
    expect(result).toContain("PostgresMetaStore");
    expect(result).toContain("S3ResourceStore");
    expect(result).toContain("pg://h/db");
    expect(result).toContain("mybucket");
  });

  it("custom with redis meta → imports redis store", () => {
    const result = generateImports(
      makeState({
        storage: "custom",
        storageConfig: {
          customMetaStore: "redis",
          customResourceStore: "memory",
        },
      }),
    );
    expect(result).toContain("RedisMetaStore");
  });

  it("custom with file-sqlite meta → imports file sqlite store", () => {
    const result = generateImports(
      makeState({
        storage: "custom",
        storageConfig: {
          customMetaStore: "file-sqlite",
          customResourceStore: "memory",
        },
      }),
    );
    expect(result).toContain("FileSqliteMetaStore");
  });

  it("custom with cached-s3 resource → imports CachedS3ResourceStore", () => {
    const result = generateImports(
      makeState({
        storage: "custom",
        storageConfig: {
          customMetaStore: "memory",
          customResourceStore: "cached-s3",
        },
      }),
    );
    expect(result).toContain("CachedS3ResourceStore");
  });

  it("custom storage → computeDependencies includes extras", () => {
    const deps = computeDependencies(
      makeState({
        storage: "custom",
        storageConfig: {
          customMetaStore: "redis",
          customResourceStore: "s3",
        },
      }),
    );
    expect(deps[0]).toContain("s3");
    expect(deps[0]).toContain("redis");
    expect(deps[0]).toContain("magic");
    expect(deps).not.toContain("redis"); // no bare redis
  });

  it("custom storage memory+memory → autocrud[graphql] only", () => {
    const deps = computeDependencies(
      makeState({
        storage: "custom",
        storageConfig: {
          customMetaStore: "memory",
          customResourceStore: "memory",
        },
      }),
    );
    expect(deps[0]).toBe("autocrud[graphql]>=0.8.0");
  });

  it("custom storage memory+memory graphql off → base autocrud", () => {
    const deps = computeDependencies(
      makeState({
        storage: "custom",
        enableGraphql: false,
        storageConfig: {
          customMetaStore: "memory",
          customResourceStore: "memory",
        },
      }),
    );
    expect(deps[0]).toBe("autocrud>=0.8.0");
  });

  it("custom storage README description", () => {
    const readme = generateReadme(
      makeState({
        storage: "custom",
        storageConfig: {
          customMetaStore: "postgres",
          customResourceStore: "s3",
        },
      }),
    );
    expect(readme).toContain("custom");
  });

  it("custom with disk meta + all params", () => {
    const result = generateConfigureCall(
      makeState({
        storage: "custom",
        storageConfig: {
          customMetaStore: "disk",
          customResourceStore: "memory",
          metaRootdir: "./meta",
        },
      }),
    );
    expect(result).toContain("DiskMetaStore");
    expect(result).toContain("./meta");
  });

  it("custom with redis meta + params", () => {
    const result = generateConfigureCall(
      makeState({
        storage: "custom",
        storageConfig: {
          customMetaStore: "redis",
          customResourceStore: "memory",
          metaRedisUrl: "redis://localhost",
          metaRedisPrefix: "ac_",
        },
      }),
    );
    expect(result).toContain("RedisMetaStore");
    expect(result).toContain("redis://localhost");
    expect(result).toContain("ac_");
  });

  it("custom with redis meta defaults → always emits all params", () => {
    const result = generateConfigureCall(
      makeState({
        storage: "custom",
        storageConfig: {
          customMetaStore: "redis",
          customResourceStore: "memory",
        },
      }),
    );
    expect(result).toContain(
      'RedisMetaStore(redis_url="redis://localhost:6379", prefix=f"{model_name}:")',
    );
  });

  it("custom with sqlalchemy meta", () => {
    const result = generateConfigureCall(
      makeState({
        storage: "custom",
        storageConfig: {
          customMetaStore: "sqlalchemy",
          customResourceStore: "memory",
          metaSqlalchemyUrl: "sqlite:///test.db",
          metaSqlalchemyTable: "meta_tbl",
        },
      }),
    );
    expect(result).toContain("SQLAlchemyMetaStore");
    expect(result).toContain("sqlite:///test.db");
    expect(result).toContain("meta_tbl");
  });

  it("custom with file-sqlite meta", () => {
    const result = generateConfigureCall(
      makeState({
        storage: "custom",
        storageConfig: {
          customMetaStore: "file-sqlite",
          customResourceStore: "memory",
          metaSqliteFilepath: "./db.sqlite",
        },
      }),
    );
    expect(result).toContain("FileSqliteMetaStore");
    expect(result).toContain("./db.sqlite");
  });

  it("custom with s3-sqlite meta + params", () => {
    const result = generateConfigureCall(
      makeState({
        storage: "custom",
        storageConfig: {
          customMetaStore: "s3-sqlite",
          customResourceStore: "memory",
          metaS3Bucket: "mybucket",
          metaS3Key: "meta.db",
          metaS3EndpointUrl: "http://minio:9000",
        },
      }),
    );
    expect(result).toContain("S3SqliteMetaStore");
    expect(result).toContain("mybucket");
    expect(result).toContain("meta.db");
  });

  it("custom with disk resource", () => {
    const result = generateConfigureCall(
      makeState({
        storage: "custom",
        storageConfig: {
          customMetaStore: "memory",
          customResourceStore: "disk",
          resRootdir: "./resources",
        },
      }),
    );
    expect(result).toContain("DiskResourceStore");
    expect(result).toContain("./resources");
  });

  it("custom with s3 resource defaults → always emits all params", () => {
    const result = generateConfigureCall(
      makeState({
        storage: "custom",
        storageConfig: {
          customMetaStore: "memory",
          customResourceStore: "s3",
        },
      }),
    );
    expect(result).toContain(
      'S3ResourceStore(bucket="autocrud", prefix=f"{model_name}/"',
    );
    expect(result).toContain('access_key_id="minioadmin"');
    expect(result).toContain('region_name="us-east-1"');
  });

  it("custom with etag-cached-s3 resource", () => {
    const result = generateConfigureCall(
      makeState({
        storage: "custom",
        storageConfig: {
          customMetaStore: "memory",
          customResourceStore: "etag-cached-s3",
          resBucket: "res",
          resPrefix: "data/",
        },
      }),
    );
    expect(result).toContain("ETagCachedS3ResourceStore");
    expect(result).toContain("res");
  });

  it("custom with mq-cached-s3 resource + amqp args", () => {
    const result = generateConfigureCall(
      makeState({
        storage: "custom",
        storageConfig: {
          customMetaStore: "memory",
          customResourceStore: "mq-cached-s3",
          resBucket: "res",
          resAmqpUrl: "amqp://localhost",
          resQueuePrefix: "q_",
        },
      }),
    );
    expect(result).toContain("MQCachedS3ResourceStore");
    expect(result).toContain("amqp://localhost");
    expect(result).toContain("q_");
  });

  it("custom with memory-sqlite meta → no special args", () => {
    const result = generateConfigureCall(
      makeState({
        storage: "custom",
        storageConfig: {
          customMetaStore: "memory-sqlite",
          customResourceStore: "memory",
        },
      }),
    );
    expect(result).toContain("MemorySqliteMetaStore()");
  });

  it("custom with sqlalchemy → extras include sqlalchemy", () => {
    const deps = computeDependencies(
      makeState({
        storage: "custom",
        storageConfig: {
          customMetaStore: "sqlalchemy",
          customResourceStore: "memory",
        },
      }),
    );
    expect(deps[0]).toContain("sqlalchemy");
    expect(deps).not.toContain("sqlalchemy"); // no bare sqlalchemy
  });

  it("custom with postgres → extras include postgresql", () => {
    const deps = computeDependencies(
      makeState({
        storage: "custom",
        storageConfig: {
          customMetaStore: "postgres",
          customResourceStore: "memory",
        },
      }),
    );
    expect(deps[0]).toContain("postgresql");
    expect(deps).not.toContain("psycopg2-binary"); // no bare psycopg2
  });

  it("custom with s3-sqlite meta → extras include s3 + magic", () => {
    const deps = computeDependencies(
      makeState({
        storage: "custom",
        storageConfig: {
          customMetaStore: "s3-sqlite",
          customResourceStore: "memory",
        },
      }),
    );
    expect(deps[0]).toContain("s3");
    expect(deps[0]).toContain("magic");
  });

  it("custom with mq-cached-s3 → extras include mq + s3 + magic", () => {
    const deps = computeDependencies(
      makeState({
        storage: "custom",
        storageConfig: {
          customMetaStore: "memory",
          customResourceStore: "mq-cached-s3",
        },
      }),
    );
    expect(deps[0]).toContain("mq");
    expect(deps[0]).toContain("s3");
    expect(deps[0]).toContain("magic");
  });
});

// ─── FastSlowMetaStore ────────────────────────────────────────

describe("FastSlowMetaStore", () => {
  it("fast-slow → nested FastSlowMetaStore generation", () => {
    const result = generateConfigureCall(
      makeState({
        storage: "custom",
        storageConfig: {
          customMetaStore: "fast-slow",
          customResourceStore: "memory",
          metaFastStore: "memory",
          metaSlowStore: "file-sqlite",
          metaSqliteFilepath: "./meta.db",
          metaSyncInterval: 5,
        },
      }),
    );
    expect(result).toContain("FastSlowMetaStore(");
    expect(result).toContain("fast_store=MemoryMetaStore()");
    expect(result).toContain(
      'slow_store=FileSqliteMetaStore(filepath=f"./meta.db_{model_name}.db")',
    );
    expect(result).toContain("sync_interval=5");
  });

  it("fast-slow with redis fast + postgres slow", () => {
    const result = generateConfigureCall(
      makeState({
        storage: "custom",
        storageConfig: {
          customMetaStore: "fast-slow",
          customResourceStore: "memory",
          metaFastStore: "redis",
          metaSlowStore: "postgres",
          metaRedisUrl: "redis://myhost:6379",
          metaRedisPrefix: "ac:",
          metaPostgresDsn: "pg://h/db",
          metaPostgresTable: "meta_tbl",
        },
      }),
    );
    expect(result).toContain(
      'fast_store=RedisMetaStore(redis_url="redis://myhost:6379", prefix=f"ac:{model_name}:")',
    );
    expect(result).toContain(
      'slow_store=PostgresMetaStore(pg_dsn="pg://h/db", table_name=f"meta_tbl_{model_name}")',
    );
  });

  it("fast-slow defaults → memory fast + file-sqlite slow + sync_interval=1", () => {
    const result = generateConfigureCall(
      makeState({
        storage: "custom",
        storageConfig: {
          customMetaStore: "fast-slow",
          customResourceStore: "memory",
        },
      }),
    );
    expect(result).toContain("fast_store=MemoryMetaStore()");
    expect(result).toContain(
      'slow_store=FileSqliteMetaStore(filepath=f"./meta_{model_name}.db")',
    );
    expect(result).toContain("sync_interval=1");
  });

  it("fast-slow imports both FastSlowMetaStore and sub-store classes", () => {
    const imports = generateImports(
      makeState({
        storage: "custom",
        storageConfig: {
          customMetaStore: "fast-slow",
          customResourceStore: "memory",
          metaFastStore: "redis",
          metaSlowStore: "postgres",
        },
      }),
    );
    expect(imports).toContain("FastSlowMetaStore");
    expect(imports).toContain("RedisMetaStore");
    expect(imports).toContain("PostgresMetaStore");
  });

  it("fast-slow with redis fast → extras include redis", () => {
    const deps = computeDependencies(
      makeState({
        storage: "custom",
        storageConfig: {
          customMetaStore: "fast-slow",
          customResourceStore: "memory",
          metaFastStore: "redis",
          metaSlowStore: "file-sqlite",
        },
      }),
    );
    expect(deps[0]).toContain("redis");
    expect(deps).not.toContain("redis"); // no bare redis
  });

  it("fast-slow with s3-sqlite slow → extras include s3 + magic", () => {
    const deps = computeDependencies(
      makeState({
        storage: "custom",
        storageConfig: {
          customMetaStore: "fast-slow",
          customResourceStore: "memory",
          metaFastStore: "memory",
          metaSlowStore: "s3-sqlite",
        },
      }),
    );
    expect(deps[0]).toContain("s3");
    expect(deps[0]).toContain("magic");
  });

  it("fast-slow with disk fast + s3-sqlite slow with params", () => {
    const result = generateConfigureCall(
      makeState({
        storage: "custom",
        storageConfig: {
          customMetaStore: "fast-slow",
          customResourceStore: "memory",
          metaFastStore: "disk",
          metaRootdir: "./fast",
          metaSlowStore: "s3-sqlite",
          metaS3Bucket: "slow-bucket",
          metaS3Key: "slow.db",
          metaSyncInterval: 10,
        },
      }),
    );
    expect(result).toContain(
      'fast_store=DiskMetaStore(rootdir=f"./fast/{model_name}")',
    );
    expect(result).toContain(
      'slow_store=S3SqliteMetaStore(bucket="slow-bucket", key=f"slow.db/{model_name}.db"',
    );
    expect(result).toContain("sync_interval=10");
  });
});

// ─── P0-1: build_blob_store for S3 resource stores ────────────

describe("P0-1: build_blob_store", () => {
  const S3_RESOURCE_STORES = [
    "s3",
    "cached-s3",
    "etag-cached-s3",
    "mq-cached-s3",
  ] as const;

  for (const resStore of S3_RESOURCE_STORES) {
    it(`custom + ${resStore} → generateConfigureCall includes build_blob_store`, () => {
      const result = generateConfigureCall(
        makeState({
          storage: "custom",
          storageConfig: {
            customMetaStore: "memory",
            customResourceStore: resStore,
            resBucket: "mybucket",
            resEndpointUrl: "http://localhost:9000",
            resAccessKeyId: "minioadmin",
            resSecretAccessKey: "minioadmin",
            resRegionName: "us-east-1",
            ...(resStore === "mq-cached-s3"
              ? { resAmqpUrl: "amqp://localhost" }
              : {}),
          },
        }),
      );
      expect(result).toContain("build_blob_store");
      expect(result).toContain("S3BlobStore");
      expect(result).toContain("IBlobStore");
      expect(result).toContain('prefix="blobs/"');
    });
  }

  it("custom + memory resource → no build_blob_store", () => {
    const result = generateConfigureCall(
      makeState({
        storage: "custom",
        storageConfig: {
          customMetaStore: "memory",
          customResourceStore: "memory",
        },
      }),
    );
    expect(result).not.toContain("build_blob_store");
    expect(result).not.toContain("S3BlobStore");
  });

  it("custom + disk resource → no build_blob_store", () => {
    const result = generateConfigureCall(
      makeState({
        storage: "custom",
        storageConfig: {
          customMetaStore: "memory",
          customResourceStore: "disk",
          resRootdir: "./res",
        },
      }),
    );
    expect(result).not.toContain("build_blob_store");
    expect(result).not.toContain("S3BlobStore");
  });

  it("custom + s3 resource → imports include S3BlobStore + IBlobStore", () => {
    const result = generateImports(
      makeState({
        storage: "custom",
        storageConfig: {
          customMetaStore: "memory",
          customResourceStore: "s3",
        },
      }),
    );
    expect(result).toContain("S3BlobStore");
    expect(result).toContain("IBlobStore");
  });

  it("custom + memory resource → no S3BlobStore import", () => {
    const result = generateImports(
      makeState({
        storage: "custom",
        storageConfig: {
          customMetaStore: "memory",
          customResourceStore: "memory",
        },
      }),
    );
    expect(result).not.toContain("S3BlobStore");
  });

  it("build_blob_store uses same S3 connection params as resource store", () => {
    const result = generateConfigureCall(
      makeState({
        storage: "custom",
        storageConfig: {
          customMetaStore: "memory",
          customResourceStore: "cached-s3",
          resBucket: "my-bucket",
          resEndpointUrl: "http://minio:9000",
          resAccessKeyId: "mykey",
          resSecretAccessKey: "mysecret",
          resRegionName: "eu-west-1",
        },
      }),
    );
    // blob store should use same connection params
    expect(result).toContain('bucket="my-bucket"');
    expect(result).toContain('endpoint_url="http://minio:9000"');
    expect(result).toContain('access_key_id="mykey"');
    expect(result).toContain('secret_access_key="mysecret"');
    expect(result).toContain('region_name="eu-west-1"');
    expect(result).toContain('prefix="blobs/"');
  });
});

// ─── P0-2: encoding passthrough for custom factory ────────────

describe("P0-2: encoding passthrough", () => {
  it("custom + msgpack → factory __init__ accepts encoding", () => {
    const result = generateConfigureCall(
      makeState({
        storage: "custom",
        encoding: "msgpack",
        storageConfig: {
          customMetaStore: "memory",
          customResourceStore: "memory",
        },
      }),
    );
    expect(result).toContain("def __init__(self, encoding=Encoding.json):");
    expect(result).toContain("self.encoding = encoding");
    expect(result).toContain(
      "_CustomStorageFactory(encoding=Encoding.msgpack)",
    );
  });

  it("custom + json → no __init__ / no encoding param", () => {
    const result = generateConfigureCall(
      makeState({
        storage: "custom",
        encoding: "json",
        storageConfig: {
          customMetaStore: "memory",
          customResourceStore: "memory",
        },
      }),
    );
    expect(result).not.toContain("def __init__");
    expect(result).not.toContain("self.encoding");
    expect(result).toContain("_CustomStorageFactory()");
  });

  it("custom + msgpack → imports Encoding", () => {
    const imports = generateImports(
      makeState({
        storage: "custom",
        encoding: "msgpack",
        storageConfig: {
          customMetaStore: "memory",
          customResourceStore: "memory",
        },
      }),
    );
    expect(imports).toContain("Encoding");
  });

  it("custom + msgpack + s3 resource → encoding passed in factory instantiation", () => {
    const result = generateConfigureCall(
      makeState({
        storage: "custom",
        encoding: "msgpack",
        storageConfig: {
          customMetaStore: "postgres",
          customResourceStore: "s3",
          metaPostgresDsn: "pg://h/db",
          resBucket: "mybucket",
        },
      }),
    );
    expect(result).toContain(
      "_CustomStorageFactory(encoding=Encoding.msgpack)",
    );
    expect(result).toContain("self.encoding = encoding");
    // encoding should be passed to stores that support it
    expect(result).toContain("encoding=self.encoding");
  });
});

// ─── F3: defaultUser / defaultNow ──────────────────────────────

describe("F3: defaultNow", () => {
  it("defaultNow UTC → default_now=dt.datetime.utcnow", () => {
    const result = generateConfigureCall(makeState({ defaultNow: "UTC" }));
    expect(result).toContain("default_now");
    expect(result).toContain("dt.datetime.utcnow");
  });

  it("defaultNow Asia/Taipei → ZoneInfo lambda", () => {
    const result = generateConfigureCall(
      makeState({ defaultNow: "Asia/Taipei" }),
    );
    expect(result).toContain(
      'default_now=lambda: dt.datetime.now(ZoneInfo("Asia/Taipei"))',
    );
  });

  it("empty defaultNow → no default_now param", () => {
    const result = generateConfigureCall(makeState({ defaultNow: "" }));
    expect(result).not.toContain("default_now");
  });

  it("defaultNow UTC → imports datetime", () => {
    const result = generateImports(makeState({ defaultNow: "UTC" }));
    expect(result).toContain("import datetime as dt");
    expect(result).not.toContain("ZoneInfo");
  });

  it("defaultNow timezone → imports datetime + ZoneInfo", () => {
    const result = generateImports(makeState({ defaultNow: "Asia/Tokyo" }));
    expect(result).toContain("import datetime as dt");
    expect(result).toContain("from zoneinfo import ZoneInfo");
  });

  it("no datetime fields + no defaultNow → no datetime import", () => {
    const result = generateImports(makeState({ defaultNow: "" }));
    expect(result).not.toContain("datetime");
  });
});

// ─── F4: Migration comment snippet ────────────────────────────

describe("F4: Migration comment snippet", () => {
  it("generateAppSetup includes migration comment using first model name", () => {
    const result = generateAppSetup(makeState());
    expect(result).toContain("# ===== Migration (uncomment to enable) =====");
    // Uses first model name (default: Todo) in function and Schema
    expect(result).toContain(
      'Schema(Todo, "v2").step("v1", migrate_todo_v1_to_v2)',
    );
    expect(result).toContain(
      "def migrate_todo_v1_to_v2(raw: IO[bytes]) -> Todo:",
    );
    expect(result).toContain("msgspec.json.decode(raw.read(), type=Todo)");
    expect(result).toContain('data.new_field = "default_value"');
    // Should NOT contain old IMigration dict pattern
    expect(result).not.toContain("IMigration");
  });

  it("migration comment uses custom first model name", () => {
    const model = makeModel({ name: "UserProfile" });
    const result = generateAppSetup(makeState({ models: [model] }));
    expect(result).toContain(
      "def migrate_user_profile_v1_to_v2(raw: IO[bytes]) -> UserProfile:",
    );
    expect(result).toContain(
      'Schema(UserProfile, "v2").step("v1", migrate_user_profile_v1_to_v2)',
    );
  });

  it("migration comment appears after first add_model, not at end", () => {
    const model1 = makeModel({ name: "Alpha" });
    const model2 = makeModel({ name: "Beta" });
    const result = generateAppSetup(makeState({ models: [model1, model2] }));
    const migIdx = result.indexOf("# ===== Migration");
    const addAlphaIdx = result.indexOf("crud.add_model(Schema(Alpha");
    const addBetaIdx = result.indexOf("crud.add_model(Schema(Beta");
    // Migration is after first model but before second model
    expect(addAlphaIdx).toBeGreaterThanOrEqual(0);
    expect(addBetaIdx).toBeGreaterThanOrEqual(0);
    expect(migIdx).toBeGreaterThan(addAlphaIdx);
    expect(migIdx).toBeLessThan(addBetaIdx);
  });

  it("migration comment is commented out (not active code)", () => {
    const result = generateAppSetup(makeState());
    // Filter only migration-specific lines (exclude real add_model calls)
    const migLines = result
      .split("\n")
      .filter(
        (l: string) =>
          l.includes("migrate_todo_v1_to_v2") ||
          l.includes("msgspec.json.decode"),
      );
    expect(migLines.length).toBeGreaterThan(0);
    for (const line of migLines) {
      expect(line.trimStart().startsWith("#")).toBe(true);
    }
  });

  it("generateMainPy includes commented migration snippet", () => {
    const code = generateMainPy(DEFAULT_WIZARD_STATE);
    expect(code).toContain("# ===== Migration (uncomment to enable) =====");
  });
});

// ─── F5: Editable validators ──────────────────────────────────

describe("F5: Editable validators", () => {
  it("code-mode model with enableValidator + validatorCode → emits code", () => {
    const model = makeModel({
      name: "Item",
      inputMode: "code",
      rawCode: "class Item(Struct):\n    price: int",
      enableValidator: true,
      validatorCode:
        'def validate_item(data: Item) -> None:\n    if data.price < 0:\n        raise ValueError("price must be >= 0")',
    });
    const result = generateValidators(makeState({ models: [model] }));
    expect(result).toContain("def validate_item(data: Item) -> None:");
    expect(result).toContain("price must be >= 0");
  });

  it("code-mode with enableValidator but empty validatorCode → scaffold", () => {
    const model = makeModel({
      name: "Thing",
      inputMode: "code",
      rawCode: "class Thing(Struct):\n    x: int",
      enableValidator: true,
      validatorCode: "",
    });
    const result = generateValidators(makeState({ models: [model] }));
    expect(result).toContain("def validate_thing(data: Thing) -> None:");
  });

  it("form-mode with validatorCode → uses validatorCode", () => {
    const model = makeModel({
      name: "User",
      inputMode: "form",
      enableValidator: true,
      validatorCode: "def validate_user(data: User) -> None:\n    pass",
      fields: [makeField({ name: "email", type: "str" })],
    });
    const result = generateValidators(makeState({ models: [model] }));
    expect(result).toContain("def validate_user(data: User) -> None:");
    expect(result).toContain("pass");
    // Should use custom code, not auto-generated
    expect(result).not.toContain("errors = []");
  });

  it("form-mode with enableValidator but no validatorCode → auto scaffold", () => {
    const model = makeModel({
      name: "Product",
      inputMode: "form",
      enableValidator: true,
      validatorCode: "",
      fields: [makeField({ name: "title", type: "str" })],
    });
    const result = generateValidators(makeState({ models: [model] }));
    expect(result).toContain("def validate_product(data: Product) -> None:");
    expect(result).toContain("errors = []");
  });

  it("code-mode with enableValidator → adds_model includes validator", () => {
    const model = makeModel({
      name: "Widget",
      inputMode: "code",
      rawCode: "class Widget(Struct):\n    w: int",
      enableValidator: true,
      validatorCode: "def validate_widget(data: Widget) -> None:\n    pass",
    });
    const result = generateAddModelCall(model);
    expect(result).toContain("validator=validate_widget");
  });

  it("imports IValidator when any model has validator", () => {
    const model = makeModel({
      name: "Gadget",
      inputMode: "code",
      rawCode: "class Gadget(Struct):\n    g: int",
      enableValidator: true,
      validatorCode: "def validate_gadget(data: Gadget) -> None:\n    pass",
    });
    const result = generateImports(makeState({ models: [model] }));
    expect(result).toContain("IValidator");
  });
});
