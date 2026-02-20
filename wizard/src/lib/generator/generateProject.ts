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
} from '@/types/wizard';

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
      filename: 'pyproject.toml',
      content: generatePyprojectToml(state),
      language: 'toml',
    },
    {
      filename: 'main.py',
      content: generateMainPy(state),
      language: 'python',
    },
    {
      filename: 'README.md',
      content: generateReadme(state),
      language: 'markdown',
    },
    {
      filename: '.python-version',
      content: state.pythonVersion + '\n',
      language: 'plaintext',
    },
  ];
}

// ─── pyproject.toml ────────────────────────────────────────────

export function generatePyprojectToml(state: WizardState): string {
  const deps = computeDependencies(state);
  const depsStr = deps.map((d) => `    "${d}",`).join('\n');

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
  const deps: string[] = [];

  switch (state.storage) {
    case 's3':
      deps.push('autocrud[s3]>=0.8.0');
      break;
    case 'postgresql':
      deps.push('autocrud[s3]>=0.8.0');
      deps.push('psycopg2-binary');
      break;
    default:
      deps.push('autocrud>=0.8.0');
  }

  deps.push('uvicorn>=0.30.0');

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

  return sections.join('\n\n') + '\n';
}

// ─── Import Generation ─────────────────────────────────────────

export function generateImports(state: WizardState): string {
  const lines: string[] = [];
  const autocrudImports = new Set<string>(['crud', 'Schema']);
  const autocrudTypesImports = new Set<string>();
  const typingImports = new Set<string>();
  let needDatetime = false;
  let needEnum = false;

  // Scan all form-mode models for what they use
  for (const model of state.models) {
    if (model.inputMode === 'form') {
      for (const field of model.fields) {
        // Check types
        if (
          field.isDisplayName ||
          field.type === 'Ref' ||
          field.type === 'RefRevision'
        ) {
          typingImports.add('Annotated');
        }
        if (field.optional || field.type === 'Binary') {
          typingImports.add('Optional');
        }
        if (field.type === 'datetime') {
          needDatetime = true;
        }
        if (field.type === 'Enum') {
          needEnum = true;
        }
        if (field.isDisplayName) {
          autocrudImports.add('DisplayName');
        }
        if (field.type === 'Ref' || field.ref) {
          autocrudImports.add('Ref');
          autocrudImports.add('OnDelete');
        }
        if (field.type === 'RefRevision' || field.refRevision) {
          autocrudTypesImports.add('RefRevision');
        }
        if (field.type === 'Binary') {
          autocrudTypesImports.add('Binary');
        }
        if (
          field.type === 'dict' &&
          field.dictKeyType &&
          field.dictValueType &&
          field.dictValueType === 'Any'
        ) {
          typingImports.add('Any');
        }
      }
      if (model.enums.length > 0) {
        needEnum = true;
      }
    } else {
      // code-mode: scan rawCode for keywords
      const code = model.rawCode;
      if (code.includes('DisplayName')) autocrudImports.add('DisplayName');
      if (code.includes('Ref(') || code.includes('Ref("')) {
        autocrudImports.add('Ref');
        autocrudImports.add('OnDelete');
      }
      if (code.includes('RefRevision'))
        autocrudTypesImports.add('RefRevision');
      if (code.includes('Binary')) autocrudTypesImports.add('Binary');
      if (code.includes('Job[')) autocrudTypesImports.add('Job');
      if (code.includes('Annotated')) typingImports.add('Annotated');
      if (code.includes('Optional')) typingImports.add('Optional');
      if (code.includes('datetime')) needDatetime = true;
      if (code.includes('Enum)') || code.includes('(Enum')) needEnum = true;
    }
  }

  // Standard library imports
  if (needDatetime) lines.push('import datetime as dt');
  if (needEnum) lines.push('from enum import Enum');
  if (typingImports.size > 0) {
    const sorted = [...typingImports].sort();
    lines.push(`from typing import ${sorted.join(', ')}`);
  }
  if (lines.length > 0) lines.push('');

  // Third-party imports
  lines.push('import uvicorn');
  lines.push('from fastapi import FastAPI');
  if (state.enableCORS) {
    lines.push(
      'from fastapi.middleware.cors import CORSMiddleware',
    );
  }
  if (
    state.modelStyle === 'struct' ||
    state.models.some((m) => m.inputMode === 'code' && m.rawCode.includes('Struct'))
  ) {
    lines.push('from msgspec import Struct');
  }
  if (
    state.modelStyle === 'pydantic' ||
    state.models.some((m) => m.inputMode === 'code' && m.rawCode.includes('BaseModel'))
  ) {
    lines.push('from pydantic import BaseModel');
  }
  lines.push('');

  // AutoCRUD imports
  const sortedAutocrud = [...autocrudImports].sort();
  lines.push(`from autocrud import ${sortedAutocrud.join(', ')}`);

  // Storage factory import
  const storageImport = getStorageImport(state.storage);
  if (storageImport) lines.push(storageImport);

  // autocrud.types imports
  if (autocrudTypesImports.size > 0) {
    const sorted = [...autocrudTypesImports].sort();
    lines.push(`from autocrud.types import ${sorted.join(', ')}`);
  }

  return lines.join('\n');
}

function getStorageImport(storage: WizardState['storage']): string | null {
  switch (storage) {
    case 'disk':
      return 'from autocrud.resource_manager.storage_factory import DiskStorageFactory';
    case 's3':
      return 'from autocrud.resource_manager.storage_factory import S3StorageFactory';
    case 'postgresql':
      return 'from autocrud.resource_manager.storage_factory import PostgreSQLStorageFactory';
    default:
      return null;
  }
}

// ─── Enum Generation ───────────────────────────────────────────

export function generateEnumDefinitions(state: WizardState): string {
  const enums: EnumDefinition[] = [];

  for (const model of state.models) {
    if (model.inputMode === 'form') {
      enums.push(...model.enums);
    }
  }

  if (enums.length === 0) return '';

  return enums.map(generateSingleEnum).join('\n\n');
}

function generateSingleEnum(en: EnumDefinition): string {
  const lines = [`class ${en.name}(Enum):`];
  if (en.values.length === 0) {
    lines.push('    pass');
  } else {
    for (const v of en.values) {
      lines.push(`    ${v.key} = "${v.label}"`);
    }
  }
  return lines.join('\n');
}

// ─── Sub-struct Generation ─────────────────────────────────────

export function generateSubStructDefinitions(state: WizardState): string {
  const subStructs: SubStructDefinition[] = [];

  for (const model of state.models) {
    if (model.inputMode === 'form' && model.subStructs) {
      subStructs.push(...model.subStructs);
    }
  }

  if (subStructs.length === 0) return '';

  return subStructs.map(generateSingleSubStruct).join('\n\n');
}

function generateSingleSubStruct(ss: SubStructDefinition): string {
  let tagSuffix = '';
  if (ss.tag === true) {
    tagSuffix = ', tag=True';
  } else if (ss.tag) {
    tagSuffix = `, tag="${ss.tag}"`;
  }
  const lines: string[] = [`class ${ss.name}(Struct${tagSuffix}):`];

  if (ss.fields.length === 0) {
    lines.push('    pass');
  } else {
    // Same field ordering logic as generateFormModel
    const requiredFields = ss.fields.filter(
      (f) => !f.optional && !f.default,
    );
    const defaultedFields = ss.fields.filter(
      (f) => f.optional || !!f.default,
    );
    const orderedFields = [...requiredFields, ...defaultedFields];

    for (const field of orderedFields) {
      lines.push('    ' + generateFieldLine(field));
    }
  }

  return lines.join('\n');
}

// ─── Model Generation ──────────────────────────────────────────

export function generateModelDefinitions(state: WizardState): string {
  const parts: string[] = [];

  for (const model of state.models) {
    if (model.inputMode === 'code') {
      parts.push(model.rawCode);
    } else {
      parts.push(generateFormModel(model, state.modelStyle));
    }
  }

  return parts.join('\n\n\n');
}

export function generateFormModel(
  model: ModelDefinition,
  style: WizardState['modelStyle'],
): string {
  const baseClass = style === 'pydantic' ? 'BaseModel' : 'Struct';
  const lines: string[] = [`class ${model.name}(${baseClass}):`];

  if (model.fields.length === 0) {
    lines.push('    pass');
    return lines.join('\n');
  }

  // Separate required fields (no default) from optional/defaulted fields
  // Required fields must come first in Struct
  const requiredFields = model.fields.filter(
    (f) => !f.optional && !f.default,
  );
  const defaultedFields = model.fields.filter(
    (f) => f.optional || !!f.default,
  );
  const orderedFields = [...requiredFields, ...defaultedFields];

  for (const field of orderedFields) {
    lines.push('    ' + generateFieldLine(field));
  }

  return lines.join('\n');
}

export function generateFieldLine(field: FieldDefinition): string {
  let typeStr = resolveFieldType(field);
  let line = `${field.name}: ${typeStr}`;

  // Add default value
  if (field.optional && !field.default) {
    line += ' = None';
  } else if (field.default) {
    line += ` = ${field.default}`;
  }

  return line;
}

export function resolveFieldType(field: FieldDefinition): string {
  let baseType: string;

  switch (field.type) {
    case 'str':
      baseType = 'str';
      break;
    case 'int':
      baseType = 'int';
      break;
    case 'float':
      baseType = 'float';
      break;
    case 'bool':
      baseType = 'bool';
      break;
    case 'datetime':
      baseType = 'dt.datetime';
      break;
    case 'Binary':
      // Binary is always Optional[Binary] = None
      return 'Optional[Binary]';
    case 'Ref': {
      const ref = field.ref;
      if (!ref) return 'str';
      const onDelete =
        ref.onDelete === 'dangling'
          ? ''
          : `, on_delete=OnDelete.${ref.onDelete}`;
      const innerType = field.optional ? 'str | None' : 'str';
      const annotated = `Annotated[${innerType}, Ref("${ref.resource}"${onDelete})]`;
      if (field.isList) return `list[${annotated}]`;
      return annotated;
    }
    case 'RefRevision': {
      const refRev = field.refRevision;
      if (!refRev) return 'str';
      const innerType = field.optional ? 'Optional[str]' : 'str';
      return `Annotated[${innerType}, RefRevision("${refRev.resource}")]`;
    }
    case 'dict': {
      if (field.dictKeyType && field.dictValueType) {
        baseType = `dict[${field.dictKeyType}, ${field.dictValueType}]`;
      } else {
        baseType = 'dict';
      }
      break;
    }
    case 'Struct': {
      if (!field.structName) return 'str';
      baseType = field.structName;
      break;
    }
    case 'Union': {
      if (!field.unionMembers || field.unionMembers.length === 0) return 'str';
      baseType = field.unionMembers.join(' | ');
      break;
    }
    case 'Enum':
      // The enum name should be set in the default or derived from context
      // For now use the field name capitalized
      return capitalizeFirst(field.name);
    default:
      baseType = 'str';
  }

  // Apply DisplayName annotation
  if (field.isDisplayName && baseType === 'str') {
    return 'Annotated[str, DisplayName()]';
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
    if (model.enableValidator && model.inputMode === 'form') {
      parts.push(generateValidatorFunction(model));
    }
  }

  if (parts.length === 0) return '';

  return '\n# ===== Validators =====\n\n' + parts.join('\n\n');
}

function generateValidatorFunction(model: ModelDefinition): string {
  const fnName = `validate_${toSnakeCase(model.name)}`;
  const lines = [
    `def ${fnName}(data: ${model.name}) -> None:`,
    '    errors = []',
    '    # Add your validation rules here',
  ];

  // Generate sample validation for string fields
  const strFields = model.fields.filter(
    (f) => f.type === 'str' && !f.optional && !f.default,
  );
  for (const field of strFields.slice(0, 3)) {
    lines.push(
      `    if not data.${field.name}.strip():`,
      `        errors.append("${field.name} must not be empty")`,
    );
  }

  lines.push(
    '    if errors:',
    '        raise ValueError("; ".join(errors))',
  );

  return lines.join('\n');
}

// ─── App Setup Generation ──────────────────────────────────────

export function generateAppSetup(state: WizardState): string {
  const lines: string[] = [];

  // configure section
  lines.push('# ===== Configure AutoCRUD =====');
  lines.push('');
  lines.push(generateConfigureCall(state));
  lines.push('');

  // add_model calls
  lines.push('# ===== Register Models =====');
  lines.push('');
  for (const model of state.models) {
    lines.push(generateAddModelCall(model, state));
    lines.push('');
  }

  // FastAPI app
  lines.push('# ===== FastAPI App =====');
  lines.push('');
  lines.push(`app = FastAPI(title="${state.fastapiTitle}", version="0.1.0")`);
  lines.push('');

  if (state.enableCORS) {
    lines.push('app.add_middleware(');
    lines.push('    CORSMiddleware,');
    lines.push('    allow_origins=["*"],');
    lines.push('    allow_credentials=True,');
    lines.push('    allow_methods=["*"],');
    lines.push('    allow_headers=["*"],');
    lines.push(')');
    lines.push('');
  }

  lines.push('crud.apply(app)');
  lines.push('crud.openapi(app)');
  lines.push('');
  lines.push('');
  lines.push('if __name__ == "__main__":');
  lines.push(
    `    uvicorn.run(app, host="0.0.0.0", port=${state.port})`,
  );

  return lines.join('\n');
}

export function generateConfigureCall(state: WizardState): string {
  const args: string[] = [];

  // Storage factory
  switch (state.storage) {
    case 'disk': {
      const rootdir = state.storageConfig.rootdir || './data';
      args.push(`storage_factory=DiskStorageFactory(rootdir="${rootdir}")`);
      break;
    }
    case 's3': {
      const sc = state.storageConfig;
      const s3Args: string[] = [];
      if (sc.bucket) s3Args.push(`bucket="${sc.bucket}"`);
      if (sc.endpointUrl)
        s3Args.push(`endpoint_url="${sc.endpointUrl}"`);
      if (sc.accessKeyId)
        s3Args.push(`access_key_id="${sc.accessKeyId}"`);
      if (sc.secretAccessKey)
        s3Args.push(`secret_access_key="${sc.secretAccessKey}"`);
      if (sc.regionName)
        s3Args.push(`region_name="${sc.regionName}"`);
      args.push(
        `storage_factory=S3StorageFactory(\n        ${s3Args.join(',\n        ')},\n    )`,
      );
      break;
    }
    case 'postgresql': {
      const sc = state.storageConfig;
      const pgArgs: string[] = [];
      if (sc.connectionString)
        pgArgs.push(`connection_string="${sc.connectionString}"`);
      if (sc.s3Bucket) pgArgs.push(`s3_bucket="${sc.s3Bucket}"`);
      if (sc.s3EndpointUrl)
        pgArgs.push(`s3_endpoint_url="${sc.s3EndpointUrl}"`);
      if (sc.tablePrefix)
        pgArgs.push(`table_prefix="${sc.tablePrefix}"`);
      args.push(
        `storage_factory=PostgreSQLStorageFactory(\n        ${pgArgs.join(',\n        ')},\n    )`,
      );
      break;
    }
    // memory: no storage_factory arg needed (it's the default)
  }

  // Naming (only if not default)
  if (state.naming !== 'kebab') {
    args.push(`model_naming="${state.naming}"`);
  }

  // Encoding (only if not default)
  if (state.encoding !== 'json') {
    args.push('encoding=Encoding.msgpack');
  }

  if (args.length === 0) {
    return 'crud.configure()';
  }

  if (args.length === 1 && !args[0].includes('\n')) {
    return `crud.configure(${args[0]})`;
  }

  return `crud.configure(\n    ${args.join(',\n    ')},\n)`;
}

export function generateAddModelCall(
  model: ModelDefinition,
  state: WizardState,
): string {
  const args: string[] = [];

  // First arg: Schema(Model, version) or Schema(Model, version, validator=fn)
  const validatorSuffix =
    model.enableValidator && model.inputMode === 'form'
      ? `, validator=validate_${toSnakeCase(model.name)}`
      : '';
  args.push(
    `Schema(${model.name}, "${model.schemaVersion}"${validatorSuffix})`,
  );

  // indexed_fields
  const indexedFields = getIndexedFields(model, state);
  if (indexedFields.length > 0) {
    const fieldStrs = indexedFields
      .map((f) => `("${f.name}", ${f.pyType})`)
      .join(', ');
    args.push(`indexed_fields=[${fieldStrs}]`);
  }

  if (args.length === 1) {
    return `crud.add_model(${args[0]})`;
  }

  return `crud.add_model(\n    ${args.join(',\n    ')},\n)`;
}

interface IndexedFieldInfo {
  name: string;
  pyType: string;
}

function getIndexedFields(
  model: ModelDefinition,
  _state: WizardState,
): IndexedFieldInfo[] {
  if (model.inputMode !== 'form') return [];

  return model.fields
    .filter((f) => f.isIndexed)
    .map((f) => ({
      name: f.name,
      pyType: fieldTypeToPythonType(f),
    }));
}

function fieldTypeToPythonType(field: FieldDefinition): string {
  switch (field.type) {
    case 'str':
      return field.optional ? 'str | None' : 'str';
    case 'int':
      return field.optional ? 'int | None' : 'int';
    case 'float':
      return field.optional ? 'float | None' : 'float';
    case 'bool':
      return 'bool';
    case 'datetime':
      return 'dt.datetime';
    case 'dict':
      return 'dict';
    case 'Struct':
      return field.structName || 'str';
    case 'Union':
      return field.unionMembers?.join(' | ') || 'str';
    case 'Enum':
      return capitalizeFirst(field.name);
    default:
      return 'str';
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

${state.models.map((m) => `- **${m.name}** (Schema version: ${m.schemaVersion})`).join('\n')}

## Storage Backend

${getStorageDescription(state)}

## Learn More

- [AutoCRUD Documentation](https://github.com/autocrud/autocrud)
- [FastAPI Documentation](https://fastapi.tiangolo.com)
`;
}

function getStorageDescription(state: WizardState): string {
  switch (state.storage) {
    case 'memory':
      return 'Using **in-memory** storage (data is lost on restart). Great for development and testing.';
    case 'disk':
      return `Using **disk** storage at \`${state.storageConfig.rootdir || './data'}\`. Data persists across restarts.`;
    case 's3':
      return 'Using **S3** storage. Data is stored in an S3-compatible object store.';
    case 'postgresql':
      return 'Using **PostgreSQL + S3** storage. Production-grade setup with database and object storage.';
  }
}

// ─── Utilities ─────────────────────────────────────────────────

export function toSnakeCase(str: string): string {
  return str
    .replace(/([A-Z])/g, '_$1')
    .toLowerCase()
    .replace(/^_/, '');
}
