// ─── Wizard State ──────────────────────────────────────────────

export interface WizardState {
  // Step 1: Project settings
  projectName: string;
  fastapiTitle: string;
  pythonVersion: '3.11' | '3.12' | '3.13';
  port: number;
  enableCORS: boolean;

  // Step 2: Storage & config
  storage: StorageType;
  storageConfig: StorageConfig;
  naming: NamingConvention;
  encoding: EncodingType;
  modelStyle: ModelStyle;

  // Step 3: Model definitions
  models: ModelDefinition[];
}

export type StorageType = 'memory' | 'disk' | 's3' | 'postgresql';
export type NamingConvention = 'same' | 'pascal' | 'camel' | 'snake' | 'kebab';
export type EncodingType = 'json' | 'msgpack';
export type ModelStyle = 'struct' | 'pydantic';

export interface StorageConfig {
  // Disk
  rootdir?: string;
  // S3
  bucket?: string;
  endpointUrl?: string;
  accessKeyId?: string;
  secretAccessKey?: string;
  regionName?: string;
  // PostgreSQL
  connectionString?: string;
  s3Bucket?: string;
  s3EndpointUrl?: string;
  tablePrefix?: string;
}

// ─── Model Definition ──────────────────────────────────────────

export interface ModelDefinition {
  name: string;
  inputMode: 'form' | 'code';
  schemaVersion: string;

  // Form mode
  fields: FieldDefinition[];
  enums: EnumDefinition[];

  // Code mode
  rawCode: string;

  // Shared settings
  enableValidator: boolean;
}

export interface FieldDefinition {
  name: string;
  type: FieldType;
  optional: boolean;
  default: string;
  isIndexed: boolean;
  isDisplayName: boolean;
  isList: boolean;

  // Ref configuration
  ref: RefConfig | null;
  refRevision: RefRevisionConfig | null;
}

export type FieldType =
  | 'str'
  | 'int'
  | 'float'
  | 'bool'
  | 'datetime'
  | 'Binary'
  | 'Ref'
  | 'RefRevision'
  | 'Enum';

export interface RefConfig {
  resource: string;
  onDelete: 'dangling' | 'set_null' | 'cascade';
}

export interface RefRevisionConfig {
  resource: string;
}

export interface EnumDefinition {
  name: string;
  values: EnumValue[];
}

export interface EnumValue {
  key: string;
  label: string;
}

// ─── Built-in Type Info (for the palette) ──────────────────────

export interface BuiltinTypeInfo {
  name: string;
  icon: string;
  description: string;
  detailedDescription: string;
  importStatement: string;
  codeSnippet: string;
  formFieldType?: FieldType;
}

// ─── Defaults ──────────────────────────────────────────────────

export const DEFAULT_WIZARD_STATE: WizardState = {
  projectName: 'my-autocrud-app',
  fastapiTitle: 'My AutoCRUD API',
  pythonVersion: '3.12',
  port: 8000,
  enableCORS: true,

  storage: 'memory',
  storageConfig: {},
  naming: 'kebab',
  encoding: 'json',
  modelStyle: 'struct',

  models: [createDefaultModel()],
};

export function createDefaultModel(): ModelDefinition {
  return {
    name: 'Todo',
    inputMode: 'form',
    schemaVersion: 'v1',
    fields: [
      {
        name: 'title',
        type: 'str',
        optional: false,
        default: '',
        isIndexed: true,
        isDisplayName: true,
        isList: false,
        ref: null,
        refRevision: null,
      },
      {
        name: 'description',
        type: 'str',
        optional: false,
        default: '""',
        isIndexed: false,
        isDisplayName: false,
        isList: false,
        ref: null,
        refRevision: null,
      },
      {
        name: 'done',
        type: 'bool',
        optional: false,
        default: 'False',
        isIndexed: false,
        isDisplayName: false,
        isList: false,
        ref: null,
        refRevision: null,
      },
    ],
    enums: [],
    rawCode: `class Todo(Struct):
    title: Annotated[str, DisplayName()]
    description: str = ""
    done: bool = False`,
    enableValidator: false,
  };
}

export function createEmptyField(): FieldDefinition {
  return {
    name: '',
    type: 'str',
    optional: false,
    default: '',
    isIndexed: false,
    isDisplayName: false,
    isList: false,
    ref: null,
    refRevision: null,
  };
}

export function createEmptyEnum(): EnumDefinition {
  return {
    name: '',
    values: [{ key: '', label: '' }],
  };
}

export function createEmptyModel(): ModelDefinition {
  return {
    name: '',
    inputMode: 'form',
    schemaVersion: 'v1',
    fields: [
      {
        name: 'name',
        type: 'str',
        optional: false,
        default: '',
        isIndexed: false,
        isDisplayName: true,
        isList: false,
        ref: null,
        refRevision: null,
      },
    ],
    enums: [],
    rawCode: '',
    enableValidator: false,
  };
}

// ─── Built-in Type Palette Data ────────────────────────────────

export const BUILTIN_TYPES: BuiltinTypeInfo[] = [
  {
    name: 'DisplayName',
    icon: '⭐',
    description: '標記此欄位為 resource 的顯示名稱',
    detailedDescription:
      '標記哪個 str 欄位作為 resource 的顯示名稱。AutoCRUD 會在 OpenAPI schema 注入 x-display-name-field，讓前端可以顯示友善名稱而非 resource ID。',
    importStatement: 'from autocrud import DisplayName',
    codeSnippet: 'name: Annotated[str, DisplayName()]',
    formFieldType: 'str',
  },
  {
    name: 'Ref',
    icon: '🔗',
    description: '建立到其他 resource 的外鍵關聯',
    detailedDescription:
      '宣告一個欄位參照到另一個 resource 的 resource_id，建立 1:N 或 N:N 關係。Ref 欄位會自動建立索引。支援三種刪除策略：dangling（預設）、set_null（需 Optional）、cascade。',
    importStatement: 'from autocrud import Ref, OnDelete',
    codeSnippet:
      'guild_id: Annotated[str | None, Ref("guild", on_delete=OnDelete.set_null)] = None',
    formFieldType: 'Ref',
  },
  {
    name: 'RefRevision',
    icon: '📌',
    description: '參照特定 resource 的某個 revision',
    detailedDescription:
      '宣告一個欄位參照到另一個 resource 的 revision_id（而非 resource_id）。適用於需要追蹤特定版本的場景。',
    importStatement: 'from autocrud.types import RefRevision',
    codeSnippet:
      'character_id: Annotated[Optional[str], RefRevision("character")]',
    formFieldType: 'RefRevision',
  },
  {
    name: 'Binary',
    icon: '📎',
    description: '二進制檔案欄位，自動存入 blob store',
    detailedDescription:
      '包裝二進制資料（檔案、圖片等）。建立 resource 時填入 data 欄位，系統自動將內容提取到 blob store，用 content hash 作為 file_id（去重），並填入 size。',
    importStatement: 'from autocrud.types import Binary',
    codeSnippet: 'icon: Optional[Binary] = None',
    formFieldType: 'Binary',
  },
  {
    name: 'Job[T]',
    icon: '⚡',
    description: '背景任務 wrapper，自動支援 MQ 處理',
    detailedDescription:
      '泛型 Struct，用於 message queue 系統。繼承 Job[PayloadStruct] 讓 model 自動支援 MQ 處理、重試、狀態追蹤。需搭配 job_handler 使用。',
    importStatement: 'from autocrud.types import Job',
    codeSnippet: `class MyPayload(Struct):
    event_type: str
    description: str = ""

class MyTask(Job[MyPayload]):
    pass`,
  },
];
