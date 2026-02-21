/**
 * AutoCRUD Starter Code Generator
 *
 * Pure functions that transform WizardState → Map<filename, content>
 * for a complete uv Python project.
 */

import type {
  WizardState,
  ModelDefinition,
  FieldDefinition,
  EnumDefinition,
  SubStructDefinition,
  MetaStoreType,
  ResourceStoreType,
} from "@/types/wizard";

// ─── Public API ────────────────────────────────────────────────

export interface GeneratedFile {
  filename: string;
  content: string;
  language: string; // for Monaco Editor syntax highlighting
}

/**
 * Generate the complete project file set from wizard state.
 */
export function generateProject(state: WizardState): GeneratedFile[] {
  return [
    {
      filename: "pyproject.toml",
      content: generatePyprojectToml(state),
      language: "toml",
    },
    {
      filename: "main.py",
      content: generateMainPy(state),
      language: "python",
    },
    {
      filename: "README.md",
      content: generateReadme(state),
      language: "markdown",
    },
    {
      filename: ".python-version",
      content: state.pythonVersion + "\n",
      language: "plaintext",
    },
  ];
}

// ─── pyproject.toml ────────────────────────────────────────────

export function generatePyprojectToml(state: WizardState): string {
  const deps = computeDependencies(state);
  const depsStr = deps.map((d) => `    "${d}",`).join("\n");

  return `[project]
name = "${state.projectName}"
version = "0.1.0"
description = "AutoCRUD-powered FastAPI application"
requires-python = ">=${state.pythonVersion}"
dependencies = [
${depsStr}
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.backends"
`;
}

export function computeDependencies(state: WizardState): string[] {
  const extras = new Set<string>();

  // ── Storage-based extras ──
  switch (state.storage) {
    case "s3":
      extras.add("s3");
      break;
    case "postgresql":
      extras.add("s3");
      extras.add("postgresql");
      break;
    case "custom": {
      const sc = state.storageConfig;
      const meta = sc.customMetaStore || "memory";
      const res = sc.customResourceStore || "memory";

      // Gather all meta store types (including fast/slow sub-stores)
      const allMetas: string[] = [meta];
      if (meta === "fast-slow") {
        allMetas.push(sc.metaFastStore || "memory");
        allMetas.push(sc.metaSlowStore || "file-sqlite");
      }

      // Resource store → extras
      if (["s3", "cached-s3", "etag-cached-s3"].includes(res)) {
        extras.add("s3");
      }
      if (res === "mq-cached-s3") {
        extras.add("s3");
        extras.add("mq");
      }

      // Meta store → extras
      if (allMetas.includes("s3-sqlite")) extras.add("s3");
      if (allMetas.includes("redis")) extras.add("redis");
      if (allMetas.includes("postgres")) extras.add("postgresql");
      if (allMetas.includes("sqlalchemy")) extras.add("sqlalchemy");
      break;
    }
  }

  // ── Feature-based extras ──
  if (state.enableGraphql) extras.add("graphql");

  // magic: auto-add when S3 is involved (blob content-type detection)
  if (extras.has("s3")) extras.add("magic");

  // ── Build final dependency list ──
  const deps: string[] = [];
  if (extras.size > 0) {
    const sorted = [...extras].sort();
    deps.push(`autocrud[${sorted.join(",")}]>=0.8.0`);
  } else {
    deps.push("autocrud>=0.8.0");
  }
  deps.push("uvicorn>=0.30.0");

  return deps;
}

// ─── main.py ───────────────────────────────────────────────────

export function generateMainPy(state: WizardState): string {
  const sections: string[] = [];

  // 1. Imports
  sections.push(generateImports(state));

  // 2. Enum definitions (from form-mode models)
  const enumDefs = generateEnumDefinitions(state);
  if (enumDefs) sections.push(enumDefs);

  // 3. Sub-struct definitions (from form-mode models)
  const subStructDefs = generateSubStructDefinitions(state);
  if (subStructDefs) sections.push(subStructDefs);

  // 4. Model definitions
  sections.push(generateModelDefinitions(state));

  // 4. Validators
  const validators = generateValidators(state);
  if (validators) sections.push(validators);

  // 5. App setup
  sections.push(generateAppSetup(state));

  return sections.join("\n\n") + "\n";
}

// ─── Import Generation ─────────────────────────────────────────

export function generateImports(state: WizardState): string {
  const lines: string[] = [];
  const autocrudImports = new Set<string>(["crud", "Schema"]);
  const autocrudTypesImports = new Set<string>();
  const typingImports = new Set<string>();
  let needDatetime = state.defaultNow !== "";
  const needZoneInfo = state.defaultNow !== "" && state.defaultNow !== "UTC";
  let needEnum = false;

  // Scan all form-mode models for what they use
  for (const model of state.models) {
    if (model.inputMode === "form") {
      for (const field of model.fields) {
        // Check types
        if (
          field.isDisplayName ||
          field.type === "Ref" ||
          field.type === "RefRevision"
        ) {
          typingImports.add("Annotated");
        }
        if (field.optional || field.type === "Binary") {
          typingImports.add("Optional");
        }
        if (field.type === "datetime") {
          needDatetime = true;
        }
        if (field.type === "Enum") {
          needEnum = true;
        }
        if (field.isDisplayName) {
          autocrudImports.add("DisplayName");
        }
        if (field.type === "Ref" || field.ref) {
          autocrudImports.add("Ref");
          autocrudImports.add("OnDelete");
        }
        if (field.type === "RefRevision" || field.refRevision) {
          autocrudTypesImports.add("RefRevision");
        }
        if (field.type === "Binary") {
          autocrudTypesImports.add("Binary");
        }
        if (
          field.type === "dict" &&
          field.dictKeyType &&
          field.dictValueType &&
          field.dictValueType === "Any"
        ) {
          typingImports.add("Any");
        }
      }
      if (model.enums.length > 0) {
        needEnum = true;
      }
    } else {
      // code-mode: scan rawCode for keywords
      const code = model.rawCode;
      if (code.includes("DisplayName")) autocrudImports.add("DisplayName");
      if (code.includes("Ref(") || code.includes('Ref("')) {
        autocrudImports.add("Ref");
        autocrudImports.add("OnDelete");
      }
      if (code.includes("RefRevision")) autocrudTypesImports.add("RefRevision");
      if (code.includes("Binary")) autocrudTypesImports.add("Binary");
      if (code.includes("Job[")) autocrudTypesImports.add("Job");
      if (code.includes("Annotated")) typingImports.add("Annotated");
      if (code.includes("Optional")) typingImports.add("Optional");
      if (code.includes("datetime")) needDatetime = true;
      if (code.includes("Enum)") || code.includes("(Enum")) needEnum = true;
    }
  }

  // Standard library imports
  if (needDatetime) lines.push("import datetime as dt");
  if (needZoneInfo) lines.push("from zoneinfo import ZoneInfo");
  if (needEnum) lines.push("from enum import Enum");
  if (typingImports.size > 0) {
    const sorted = [...typingImports].sort();
    lines.push(`from typing import ${sorted.join(", ")}`);
  }
  if (lines.length > 0) lines.push("");

  // Third-party imports
  lines.push("import uvicorn");
  lines.push("from fastapi import FastAPI");
  if (state.enableCORS) {
    lines.push("from fastapi.middleware.cors import CORSMiddleware");
  }
  if (
    state.modelStyle === "struct" ||
    state.models.some(
      (m) => m.inputMode === "code" && m.rawCode.includes("Struct"),
    ) ||
    // Sub-structs always use Struct, even when modelStyle is "pydantic"
    state.models.some(
      (m) => m.inputMode === "form" && m.subStructs && m.subStructs.length > 0,
    )
  ) {
    lines.push("from msgspec import Struct");
  }
  if (
    state.modelStyle === "pydantic" ||
    state.models.some(
      (m) => m.inputMode === "code" && m.rawCode.includes("BaseModel"),
    )
  ) {
    // Check if any form-mode model needs arbitrary_types_allowed
    const needsConfigDict =
      state.modelStyle === "pydantic" &&
      state.models.some(
        (m) =>
          m.inputMode === "form" &&
          m.fields.some(
            (f) =>
              f.type === "Struct" || f.type === "Union" || f.type === "Binary",
          ),
      );
    if (needsConfigDict) {
      lines.push("from pydantic import BaseModel, ConfigDict");
    } else {
      lines.push("from pydantic import BaseModel");
    }
  }
  lines.push("");

  // AutoCRUD imports
  const sortedAutocrud = [...autocrudImports].sort();
  lines.push(`from autocrud import ${sortedAutocrud.join(", ")}`);

  // Encoding import (needed when non-default encoding is used)
  if (state.encoding !== "json") {
    lines.push("from autocrud.resource_manager.basic import Encoding");
  }

  // Storage factory import
  const storageImport = getStorageImport(state.storage);
  if (storageImport) lines.push(storageImport);

  // Custom storage imports (SimpleStorage + individual stores)
  if (state.storage === "custom") {
    for (const imp of getCustomStorageImports(state)) {
      lines.push(imp);
    }
  }

  // autocrud.types imports
  // Add IValidator if any model has validators enabled
  if (state.models.some((m) => m.enableValidator)) {
    autocrudTypesImports.add("IValidator");
  }
  if (autocrudTypesImports.size > 0) {
    const sorted = [...autocrudTypesImports].sort();
    lines.push(`from autocrud.types import ${sorted.join(", ")}`);
  }

  return lines.join("\n");
}

function getStorageImport(storage: WizardState["storage"]): string | null {
  switch (storage) {
    case "disk":
      return "from autocrud.resource_manager.storage_factory import DiskStorageFactory";
    case "s3":
      return "from autocrud.resource_manager.storage_factory import S3StorageFactory";
    case "postgresql":
      return "from autocrud.resource_manager.storage_factory import PostgreSQLStorageFactory";
    default:
      return null;
  }
}

const S3_RESOURCE_STORES: ResourceStoreType[] = [
  "s3",
  "cached-s3",
  "etag-cached-s3",
  "mq-cached-s3",
];

function isS3ResourceStore(res: ResourceStoreType): boolean {
  return S3_RESOURCE_STORES.includes(res);
}

function getCustomStorageImports(state: WizardState): string[] {
  const imports: string[] = [];
  const sc = state.storageConfig;
  const meta = sc.customMetaStore || "memory";
  const res = sc.customResourceStore || "memory";

  imports.push("from autocrud.resource_manager.core import SimpleStorage");
  imports.push(
    "from autocrud.resource_manager.storage_factory import IStorageFactory",
  );
  imports.push("from autocrud.resource_manager.basic import IStorage");

  // Meta store import
  if (meta === "fast-slow") {
    imports.push(META_STORE_IMPORT_MAP["fast-slow"]);
    const fast = sc.metaFastStore || "memory";
    const slow = sc.metaSlowStore || "file-sqlite";
    const fastImport = META_STORE_IMPORT_MAP[fast];
    if (fastImport) imports.push(fastImport);
    const slowImport = META_STORE_IMPORT_MAP[slow];
    if (slowImport) imports.push(slowImport);
  } else {
    const metaImport = META_STORE_IMPORT_MAP[meta];
    if (metaImport) imports.push(metaImport);
  }

  // Resource store import
  const resImport = RESOURCE_STORE_IMPORT_MAP[res];
  if (resImport) imports.push(resImport);

  // S3 blob store imports (for build_blob_store)
  if (isS3ResourceStore(res)) {
    imports.push(
      "from autocrud.resource_manager.blob_store.s3 import S3BlobStore",
    );
    imports.push("from autocrud.resource_manager.basic import IBlobStore");
  }

  return imports;
}

const META_STORE_CLASS_MAP: Record<MetaStoreType, string> = {
  memory: "MemoryMetaStore",
  disk: "DiskMetaStore",
  "memory-sqlite": "MemorySqliteMetaStore",
  "file-sqlite": "FileSqliteMetaStore",
  "s3-sqlite": "S3SqliteMetaStore",
  postgres: "PostgresMetaStore",
  sqlalchemy: "SQLAlchemyMetaStore",
  redis: "RedisMetaStore",
  "fast-slow": "FastSlowMetaStore",
};

const META_STORE_IMPORT_MAP: Record<MetaStoreType, string> = {
  memory:
    "from autocrud.resource_manager.meta_store.simple import MemoryMetaStore",
  disk: "from autocrud.resource_manager.meta_store.simple import DiskMetaStore",
  "memory-sqlite":
    "from autocrud.resource_manager.meta_store.sqlite3 import MemorySqliteMetaStore",
  "file-sqlite":
    "from autocrud.resource_manager.meta_store.sqlite3 import FileSqliteMetaStore",
  "s3-sqlite":
    "from autocrud.resource_manager.meta_store.sqlite3 import S3SqliteMetaStore",
  postgres:
    "from autocrud.resource_manager.meta_store.postgres import PostgresMetaStore",
  sqlalchemy:
    "from autocrud.resource_manager.meta_store.sqlalchemy import SQLAlchemyMetaStore",
  redis:
    "from autocrud.resource_manager.meta_store.redis import RedisMetaStore",
  "fast-slow":
    "from autocrud.resource_manager.meta_store.fast_slow import FastSlowMetaStore",
};

const RESOURCE_STORE_CLASS_MAP: Record<ResourceStoreType, string> = {
  memory: "MemoryResourceStore",
  disk: "DiskResourceStore",
  s3: "S3ResourceStore",
  "cached-s3": "CachedS3ResourceStore",
  "etag-cached-s3": "ETagCachedS3ResourceStore",
  "mq-cached-s3": "MQCachedS3ResourceStore",
};

const RESOURCE_STORE_IMPORT_MAP: Record<ResourceStoreType, string> = {
  memory:
    "from autocrud.resource_manager.resource_store import MemoryResourceStore",
  disk: "from autocrud.resource_manager.resource_store import DiskResourceStore",
  s3: "from autocrud.resource_manager.resource_store import S3ResourceStore",
  "cached-s3":
    "from autocrud.resource_manager.resource_store import CachedS3ResourceStore",
  "etag-cached-s3":
    "from autocrud.resource_manager.resource_store import ETagCachedS3ResourceStore",
  "mq-cached-s3":
    "from autocrud.resource_manager.resource_store import MQCachedS3ResourceStore",
};

import type { StorageConfig } from "@/types/wizard";

/**
 * Build meta store args for use inside a factory build(model_name) method.
 * Uses f-strings to incorporate model_name into isolation-relevant args
 * (prefix, table_name, rootdir, key path).
 */
function buildMetaStoreArgsForFactory(
  sc: StorageConfig,
  meta: MetaStoreType,
): string[] {
  const args: string[] = [];
  switch (meta) {
    case "disk": {
      const rootdir = sc.metaRootdir || "./meta";
      args.push(`rootdir=f"${rootdir}/{model_name}"`);
      break;
    }
    case "redis": {
      const redisUrl = sc.metaRedisUrl || "redis://localhost:6379";
      const prefix = sc.metaRedisPrefix || "";
      args.push(`redis_url="${redisUrl}"`);
      args.push(`prefix=f"${prefix}{model_name}:"`);
      break;
    }
    case "postgres": {
      const dsn = sc.metaPostgresDsn || "postgresql://user:pass@localhost/db";
      const table = sc.metaPostgresTable || "resource_meta";
      args.push(`pg_dsn="${dsn}"`);
      args.push(`table_name=f"${table}_{model_name}"`);
      break;
    }
    case "sqlalchemy": {
      const url = sc.metaSqlalchemyUrl || "sqlite:///data.db";
      const table = sc.metaSqlalchemyTable || "resource_meta";
      args.push(`url="${url}"`);
      args.push(`table=f"${table}_{model_name}"`);
      break;
    }
    case "file-sqlite": {
      const filepath = sc.metaSqliteFilepath || "./meta";
      args.push(`filepath=f"${filepath}_{model_name}.db"`);
      break;
    }
    case "s3-sqlite": {
      const bucket = sc.metaS3Bucket || "meta-bucket";
      const key = sc.metaS3Key || "meta";
      args.push(`bucket="${bucket}"`);
      args.push(`key=f"${key}/{model_name}.db"`);
      args.push(
        `endpoint_url="${sc.metaS3EndpointUrl || "http://localhost:9000"}"`,
      );
      args.push(`access_key_id="${sc.metaS3AccessKeyId || "minioadmin"}"`);
      args.push(
        `secret_access_key="${sc.metaS3SecretAccessKey || "minioadmin"}"`,
      );
      args.push(`region_name="${sc.metaS3RegionName || "us-east-1"}"`);
      break;
    }
    // memory, memory-sqlite: no args (fresh instance per call)
  }
  return args;
}

/**
 * Build resource store args for use inside a factory build(model_name) method.
 * Uses f-strings to incorporate model_name into prefix/rootdir arguments.
 */
function buildResourceStoreArgsForFactory(
  sc: StorageConfig,
  res: ResourceStoreType,
): string[] {
  const args: string[] = [];
  switch (res) {
    case "disk": {
      const rootdir = sc.resRootdir || "./resources";
      args.push(`rootdir=f"${rootdir}/{model_name}"`);
      break;
    }
    case "s3":
    case "cached-s3":
    case "etag-cached-s3":
    case "mq-cached-s3": {
      const bucket = sc.resBucket || "autocrud";
      const prefix = sc.resPrefix || "";
      args.push(`bucket="${bucket}"`);
      args.push(`prefix=f"${prefix}{model_name}/"`);
      args.push(
        `endpoint_url="${sc.resEndpointUrl || "http://localhost:9000"}"`,
      );
      args.push(`access_key_id="${sc.resAccessKeyId || "minioadmin"}"`);
      args.push(`secret_access_key="${sc.resSecretAccessKey || "minioadmin"}"`);
      args.push(`region_name="${sc.resRegionName || "us-east-1"}"`);
      if (res === "mq-cached-s3") {
        args.push(
          `amqp_url="${sc.resAmqpUrl || "amqp://guest:guest@localhost:5672/"}"`,
        );
        args.push(
          `queue_prefix=f"${sc.resQueuePrefix || "autocrud:"}{model_name}:"`,
        );
      }
      break;
    }
    // memory: no args (fresh instance per call)
  }
  return args;
}

/**
 * Factory-aware version: uses model_name f-strings for per-model isolation.
 */
function buildFastSlowMetaStoreExprForFactory(
  sc: StorageConfig,
  needsEncoding: boolean = false,
): string {
  const fast = sc.metaFastStore || "memory";
  const slow = sc.metaSlowStore || "file-sqlite";
  const syncInterval = sc.metaSyncInterval ?? 1;

  const fastClass = META_STORE_CLASS_MAP[fast];
  const fastArgs = buildMetaStoreArgsForFactory(sc, fast);
  if (needsEncoding) fastArgs.push("encoding=self.encoding");
  const fastExpr =
    fastArgs.length > 0
      ? `${fastClass}(${fastArgs.join(", ")})`
      : `${fastClass}()`;

  const slowClass = META_STORE_CLASS_MAP[slow];
  const slowArgs = buildMetaStoreArgsForFactory(sc, slow);
  if (needsEncoding) slowArgs.push("encoding=self.encoding");
  const slowExpr =
    slowArgs.length > 0
      ? `${slowClass}(${slowArgs.join(", ")})`
      : `${slowClass}()`;

  return `FastSlowMetaStore(fast_store=${fastExpr}, slow_store=${slowExpr}, sync_interval=${syncInterval})`;
}

// ─── Enum Generation ───────────────────────────────────────────

export function generateEnumDefinitions(state: WizardState): string {
  const enums: EnumDefinition[] = [];

  for (const model of state.models) {
    if (model.inputMode === "form") {
      enums.push(...model.enums);
    }
  }

  if (enums.length === 0) return "";

  return enums.map(generateSingleEnum).join("\n\n");
}

function generateSingleEnum(en: EnumDefinition): string {
  const lines = [`class ${en.name}(Enum):`];
  if (en.values.length === 0) {
    lines.push("    pass");
  } else {
    for (const v of en.values) {
      lines.push(`    ${v.key} = "${v.label}"`);
    }
  }
  return lines.join("\n");
}

// ─── Sub-struct Generation ─────────────────────────────────────

export function generateSubStructDefinitions(state: WizardState): string {
  const subStructs: SubStructDefinition[] = [];

  for (const model of state.models) {
    if (model.inputMode === "form" && model.subStructs) {
      subStructs.push(...model.subStructs);
    }
  }

  if (subStructs.length === 0) return "";

  return subStructs.map(generateSingleSubStruct).join("\n\n");
}

function generateSingleSubStruct(ss: SubStructDefinition): string {
  let tagSuffix = "";
  if (ss.tag === true) {
    tagSuffix = ", tag=True";
  } else if (ss.tag) {
    tagSuffix = `, tag="${ss.tag}"`;
  }
  const lines: string[] = [`class ${ss.name}(Struct${tagSuffix}):`];

  if (ss.fields.length === 0) {
    lines.push("    pass");
  } else {
    // Same field ordering logic as generateFormModel
    const requiredFields = ss.fields.filter((f) => !f.optional && !f.default);
    const defaultedFields = ss.fields.filter((f) => f.optional || !!f.default);
    const orderedFields = [...requiredFields, ...defaultedFields];

    for (const field of orderedFields) {
      lines.push("    " + generateFieldLine(field));
    }
  }

  return lines.join("\n");
}

// ─── Model Generation ──────────────────────────────────────────

export function generateModelDefinitions(state: WizardState): string {
  const parts: string[] = [];

  for (const model of state.models) {
    if (model.inputMode === "code") {
      parts.push(model.rawCode);
    } else {
      parts.push(generateFormModel(model, state.modelStyle));
    }
  }

  return parts.join("\n\n\n");
}

export function generateFormModel(
  model: ModelDefinition,
  style: WizardState["modelStyle"],
): string {
  const baseClass = style === "pydantic" ? "BaseModel" : "Struct";
  const lines: string[] = [`class ${model.name}(${baseClass}):`];

  if (model.fields.length === 0) {
    lines.push("    pass");
    return lines.join("\n");
  }

  // Pydantic models need arbitrary_types_allowed when using Struct/Binary/Union fields
  if (style === "pydantic") {
    const needsArbitraryTypes = model.fields.some(
      (f) => f.type === "Struct" || f.type === "Union" || f.type === "Binary",
    );
    if (needsArbitraryTypes) {
      lines.push(
        "    model_config = ConfigDict(arbitrary_types_allowed=True)",
        "",
      );
    }
  }

  // Separate required fields (no default) from optional/defaulted fields
  // Required fields must come first in Struct
  const requiredFields = model.fields.filter((f) => !f.optional && !f.default);
  const defaultedFields = model.fields.filter((f) => f.optional || !!f.default);
  const orderedFields = [...requiredFields, ...defaultedFields];

  for (const field of orderedFields) {
    lines.push("    " + generateFieldLine(field));
  }

  return lines.join("\n");
}

export function generateFieldLine(field: FieldDefinition): string {
  const typeStr = resolveFieldType(field);
  let line = `${field.name}: ${typeStr}`;

  // Add default value
  if (field.optional && !field.default) {
    line += " = None";
  } else if (field.default) {
    line += ` = ${field.default}`;
  }

  return line;
}

export function resolveFieldType(field: FieldDefinition): string {
  let baseType: string;

  switch (field.type) {
    case "str":
      baseType = "str";
      break;
    case "int":
      baseType = "int";
      break;
    case "float":
      baseType = "float";
      break;
    case "bool":
      baseType = "bool";
      break;
    case "datetime":
      baseType = "dt.datetime";
      break;
    case "Binary":
      // Binary is always Optional[Binary] = None
      return "Optional[Binary]";
    case "Ref": {
      const ref = field.ref;
      if (!ref) return "str";
      const onDelete =
        ref.onDelete === "dangling"
          ? ""
          : `, on_delete=OnDelete.${ref.onDelete}`;
      const innerType = field.optional ? "str | None" : "str";
      const annotated = `Annotated[${innerType}, Ref("${ref.resource}"${onDelete})]`;
      if (field.isList) return `list[${annotated}]`;
      return annotated;
    }
    case "RefRevision": {
      const refRev = field.refRevision;
      if (!refRev) return "str";
      const innerType = field.optional ? "Optional[str]" : "str";
      return `Annotated[${innerType}, RefRevision("${refRev.resource}")]`;
    }
    case "dict": {
      if (field.dictKeyType && field.dictValueType) {
        baseType = `dict[${field.dictKeyType}, ${field.dictValueType}]`;
      } else {
        baseType = "dict";
      }
      break;
    }
    case "Struct": {
      if (!field.structName) return "str";
      baseType = field.structName;
      break;
    }
    case "Union": {
      if (!field.unionMembers || field.unionMembers.length === 0) return "str";
      baseType = field.unionMembers.join(" | ");
      break;
    }
    case "Enum":
      // The enum name should be set in the default or derived from context
      // For now use the field name capitalized
      return capitalizeFirst(field.name);
    default:
      baseType = "str";
  }

  // Apply DisplayName annotation
  if (field.isDisplayName && baseType === "str") {
    return "Annotated[str, DisplayName()]";
  }

  // Apply Optional wrapper
  if (field.optional) {
    return `Optional[${baseType}]`;
  }

  // Apply list wrapper
  if (field.isList) {
    return `list[${baseType}]`;
  }

  return baseType;
}

function capitalizeFirst(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

// ─── Validator Generation ──────────────────────────────────────

export function generateValidators(state: WizardState): string {
  const parts: string[] = [];

  for (const model of state.models) {
    if (model.enableValidator) {
      if (model.validatorCode) {
        // User provided custom validator code
        parts.push(model.validatorCode);
      } else if (model.inputMode === "form") {
        // Auto-generate scaffold for form-mode models
        parts.push(generateValidatorFunction(model));
      } else {
        // code-mode with no custom code: generate basic scaffold
        parts.push(generateCodeModeValidatorScaffold(model));
      }
    }
  }

  if (parts.length === 0) return "";

  return "\n# ===== Validators =====\n\n" + parts.join("\n\n");
}

export function generateCodeModeValidatorScaffold(
  model: ModelDefinition,
): string {
  const fnName = `validate_${toSnakeCase(model.name)}`;
  return [
    `def ${fnName}(data: ${model.name}) -> None:`,
    "    # Add your validation rules here",
    "    pass",
  ].join("\n");
}

export function generateValidatorFunction(model: ModelDefinition): string {
  const fnName = `validate_${toSnakeCase(model.name)}`;
  const lines = [
    `def ${fnName}(data: ${model.name}) -> None:`,
    "    errors = []",
    "    # Add your validation rules here",
  ];

  // Generate sample validation for string fields
  const strFields = model.fields.filter(
    (f) => f.type === "str" && !f.optional && !f.default,
  );
  for (const field of strFields.slice(0, 3)) {
    lines.push(
      `    if not data.${field.name}.strip():`,
      `        errors.append("${field.name} must not be empty")`,
    );
  }

  lines.push("    if errors:", '        raise ValueError("; ".join(errors))');

  return lines.join("\n");
}

// ─── App Setup Generation ──────────────────────────────────────

export function generateAppSetup(state: WizardState): string {
  const lines: string[] = [];

  // configure section
  lines.push("# ===== Configure AutoCRUD =====");
  lines.push("");
  lines.push(generateConfigureCall(state));
  lines.push("");

  // add_model calls
  lines.push("# ===== Register Models =====");
  lines.push("");
  const firstName = state.models[0]?.name || "MyModel";
  const fnName = `migrate_${toSnakeCase(firstName)}_v1_to_v2`;
  for (let i = 0; i < state.models.length; i++) {
    lines.push(generateAddModelCall(state.models[i]));
    lines.push("");
    // Place migration snippet right after first model
    if (i === 0) {
      lines.push("# ===== Migration (uncomment to enable) =====");
      lines.push("# import msgspec");
      lines.push("# from typing import IO");
      lines.push("#");
      lines.push(`# def ${fnName}(raw: IO[bytes]) -> ${firstName}:`);
      lines.push(
        `#     data = msgspec.json.decode(raw.read(), type=${firstName})  # or msgspec.msgpack.decode(...)`,
      );
      lines.push('#     data.new_field = "default_value"');
      lines.push("#     return data");
      lines.push("#");
      lines.push("# crud.add_model(");
      lines.push(`#     Schema(${firstName}, "v2").step("v1", ${fnName}),`);
      lines.push("# )");
      lines.push("");
    }
  }

  // FastAPI app
  lines.push("# ===== FastAPI App =====");
  lines.push("");
  lines.push(`app = FastAPI(title="${state.fastapiTitle}", version="0.1.0")`);
  lines.push("");

  if (state.enableCORS) {
    lines.push("app.add_middleware(");
    lines.push("    CORSMiddleware,");
    lines.push('    allow_origins=["*"],');
    lines.push("    allow_credentials=True,");
    lines.push('    allow_methods=["*"],');
    lines.push('    allow_headers=["*"],');
    lines.push(")");
    lines.push("");
  }

  lines.push("crud.apply(app)");
  lines.push("crud.openapi(app)");
  lines.push("");

  lines.push("");
  lines.push('if __name__ == "__main__":');
  lines.push(`    uvicorn.run(app, host="0.0.0.0", port=${state.port})`);

  return lines.join("\n");
}

export function generateConfigureCall(state: WizardState): string {
  const args: string[] = [];
  let customFactoryClass = "";

  // Storage factory
  switch (state.storage) {
    case "disk": {
      const rootdir = state.storageConfig.rootdir || "./data";
      args.push(`storage_factory=DiskStorageFactory(rootdir="${rootdir}")`);
      break;
    }
    case "s3": {
      const sc = state.storageConfig;
      const s3Args: string[] = [];
      s3Args.push(`bucket="${sc.bucket || "autocrud"}"`);
      s3Args.push(
        `endpoint_url="${sc.endpointUrl || "http://localhost:9000"}"`,
      );
      s3Args.push(`access_key_id="${sc.accessKeyId || "minioadmin"}"`);
      s3Args.push(`secret_access_key="${sc.secretAccessKey || "minioadmin"}"`);
      s3Args.push(`region_name="${sc.regionName || "us-east-1"}"`);
      args.push(
        `storage_factory=S3StorageFactory(\n        ${s3Args.join(",\n        ")},\n    )`,
      );
      break;
    }
    case "postgresql": {
      const sc = state.storageConfig;
      const pgArgs: string[] = [];
      pgArgs.push(
        `connection_string="${sc.connectionString || "postgresql://user:pass@localhost:5432/mydb"}"`,
      );
      pgArgs.push(`s3_bucket="${sc.s3Bucket || "autocrud"}"`);
      pgArgs.push(
        `s3_endpoint_url="${sc.s3EndpointUrl || "http://localhost:9000"}"`,
      );
      pgArgs.push(`s3_region="${sc.s3Region || "us-east-1"}"`);
      pgArgs.push(`s3_access_key_id="${sc.s3AccessKeyId || "minioadmin"}"`);
      pgArgs.push(
        `s3_secret_access_key="${sc.s3SecretAccessKey || "minioadmin"}"`,
      );
      pgArgs.push(`table_prefix="${sc.tablePrefix || ""}"`);
      pgArgs.push(`blob_prefix="${sc.blobPrefix || "blobs/"}"`);
      pgArgs.push(
        `blob_bucket="${sc.blobBucket || sc.s3Bucket || "autocrud"}"`,
      );
      args.push(
        `storage_factory=PostgreSQLStorageFactory(\n        ${pgArgs.join(",\n        ")},\n    )`,
      );
      break;
    }
    case "custom": {
      const sc = state.storageConfig;
      const meta = sc.customMetaStore || "memory";
      const res = sc.customResourceStore || "memory";
      const needsEncoding = state.encoding !== "json";

      let metaExpr: string;
      if (meta === "fast-slow") {
        metaExpr = buildFastSlowMetaStoreExprForFactory(sc, needsEncoding);
      } else {
        const metaClass = META_STORE_CLASS_MAP[meta];
        const metaArgs = buildMetaStoreArgsForFactory(sc, meta);
        if (needsEncoding) metaArgs.push("encoding=self.encoding");
        metaExpr =
          metaArgs.length > 0
            ? `${metaClass}(${metaArgs.join(", ")})`
            : `${metaClass}()`;
      }

      const resClass = RESOURCE_STORE_CLASS_MAP[res];
      const resArgs = buildResourceStoreArgsForFactory(sc, res);
      // encoding is supported by: memory, disk, s3 (cached-s3 passes it through **kwargs)
      if (
        needsEncoding &&
        ["memory", "disk", "s3", "cached-s3"].includes(res)
      ) {
        resArgs.push("encoding=self.encoding");
      }
      const resExpr =
        resArgs.length > 0
          ? `${resClass}(${resArgs.join(", ")})`
          : `${resClass}()`;

      // Build the custom factory class lines
      const factoryLines: string[] = [];
      factoryLines.push("class _CustomStorageFactory(IStorageFactory):");

      // P0-2: Add __init__ with encoding when non-json encoding is used
      if (needsEncoding) {
        factoryLines.push("    def __init__(self, encoding=Encoding.json):");
        factoryLines.push("        self.encoding = encoding");
        factoryLines.push("");
      }

      factoryLines.push("    def build(self, model_name: str) -> IStorage:");
      factoryLines.push(`        return SimpleStorage(`);
      factoryLines.push(`            meta_store=${metaExpr},`);
      factoryLines.push(`            resource_store=${resExpr},`);
      factoryLines.push(`        )`);

      // P0-1: Add build_blob_store when using S3-series resource stores
      if (isS3ResourceStore(res)) {
        factoryLines.push("");
        factoryLines.push("    def build_blob_store(self) -> IBlobStore:");
        const blobArgs: string[] = [];
        blobArgs.push(`bucket="${sc.resBucket || "autocrud"}"`);
        blobArgs.push(
          `endpoint_url="${sc.resEndpointUrl || "http://localhost:9000"}"`,
        );
        blobArgs.push(`access_key_id="${sc.resAccessKeyId || "minioadmin"}"`);
        blobArgs.push(
          `secret_access_key="${sc.resSecretAccessKey || "minioadmin"}"`,
        );
        blobArgs.push(`region_name="${sc.resRegionName || "us-east-1"}"`);
        blobArgs.push(`prefix="blobs/"`);
        factoryLines.push(`        return S3BlobStore(${blobArgs.join(", ")})`);
      }

      factoryLines.push("");
      customFactoryClass = factoryLines.join("\n");

      // P0-2: Pass encoding to factory instantiation when non-json
      if (needsEncoding) {
        args.push(
          "storage_factory=_CustomStorageFactory(encoding=Encoding.msgpack)",
        );
      } else {
        args.push("storage_factory=_CustomStorageFactory()");
      }
      break;
    }
    // memory: no storage_factory arg needed (it's the default)
  }

  // Naming (only if not default)
  if (state.naming !== "kebab") {
    args.push(`model_naming="${state.naming}"`);
  }

  // Encoding (only if not default)
  if (state.encoding !== "json") {
    args.push("encoding=Encoding.msgpack");
  }

  // Default now
  if (state.defaultNow === "UTC") {
    args.push("default_now=dt.datetime.utcnow");
  } else if (state.defaultNow) {
    args.push(
      `default_now=lambda: dt.datetime.now(ZoneInfo("${state.defaultNow}"))`,
    );
  }

  if (args.length === 0) {
    return customFactoryClass + "crud.configure()";
  }

  if (args.length === 1 && !args[0].includes("\n")) {
    return customFactoryClass + `crud.configure(${args[0]})`;
  }

  return (
    customFactoryClass + `crud.configure(\n    ${args.join(",\n    ")},\n)`
  );
}

export function generateAddModelCall(model: ModelDefinition): string {
  const args: string[] = [];

  // First arg: Schema(Model, version) or Schema(Model, version, validator=fn)
  const validatorSuffix = model.enableValidator
    ? `, validator=validate_${toSnakeCase(model.name)}`
    : "";
  args.push(
    `Schema(${model.name}, "${model.schemaVersion}"${validatorSuffix})`,
  );

  // indexed_fields
  const indexedFields = getIndexedFields(model);
  if (indexedFields.length > 0) {
    const fieldStrs = indexedFields
      .map((f) => `("${f.name}", ${f.pyType})`)
      .join(", ");
    args.push(`indexed_fields=[${fieldStrs}]`);
  }

  if (args.length === 1) {
    return `crud.add_model(${args[0]})`;
  }

  return `crud.add_model(\n    ${args.join(",\n    ")},\n)`;
}

interface IndexedFieldInfo {
  name: string;
  pyType: string;
}

function getIndexedFields(model: ModelDefinition): IndexedFieldInfo[] {
  if (model.inputMode !== "form") return [];

  return model.fields
    .filter((f) => f.isIndexed)
    .map((f) => ({
      name: f.name,
      pyType: fieldTypeToPythonType(f),
    }));
}

function fieldTypeToPythonType(field: FieldDefinition): string {
  switch (field.type) {
    case "str":
      return field.optional ? "str | None" : "str";
    case "int":
      return field.optional ? "int | None" : "int";
    case "float":
      return field.optional ? "float | None" : "float";
    case "bool":
      return "bool";
    case "datetime":
      return "dt.datetime";
    case "dict":
      return "dict";
    case "Struct":
      return field.structName || "str";
    case "Union":
      return field.unionMembers?.join(" | ") || "str";
    case "Enum":
      return capitalizeFirst(field.name);
    default:
      return "str";
  }
}

// ─── README.md ────────────────────────────────────────────────

export function generateReadme(state: WizardState): string {
  return `# ${state.projectName}

AutoCRUD-powered FastAPI application.

## Quick Start

\`\`\`bash
# Install dependencies (requires uv: https://docs.astral.sh/uv/)
uv sync

# Run the server
uv run python main.py
\`\`\`

Then open your browser:
- **API Docs (Swagger UI)**: http://localhost:${state.port}/docs
- **ReDoc**: http://localhost:${state.port}/redoc

## Generated Models

${state.models.map((m) => `- **${m.name}** (Schema version: ${m.schemaVersion})`).join("\n")}

## Storage Backend

${getStorageDescription(state)}

## Learn More

- [AutoCRUD Documentation](https://github.com/autocrud/autocrud)
- [FastAPI Documentation](https://fastapi.tiangolo.com)
`;
}

function getStorageDescription(state: WizardState): string {
  switch (state.storage) {
    case "memory":
      return "Using **in-memory** storage (data is lost on restart). Great for development and testing.";
    case "disk":
      return `Using **disk** storage at \`${state.storageConfig.rootdir || "./data"}\`. Data persists across restarts.`;
    case "s3":
      return "Using **S3** storage. Data is stored in an S3-compatible object store.";
    case "postgresql":
      return "Using **PostgreSQL + S3** storage. Production-grade setup with database and object storage.";
    case "custom": {
      const meta = state.storageConfig.customMetaStore || "memory";
      const res = state.storageConfig.customResourceStore || "memory";
      return `Using **custom** storage: ${META_STORE_CLASS_MAP[meta]} (meta) + ${RESOURCE_STORE_CLASS_MAP[res]} (resource).`;
    }
  }
}

// ─── Utilities ─────────────────────────────────────────────────

export function toSnakeCase(str: string): string {
  return str
    .replace(/([A-Z])/g, "_$1")
    .toLowerCase()
    .replace(/^_/, "");
}
