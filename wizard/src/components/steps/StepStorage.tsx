import {
  Stack,
  Title,
  Text,
  SegmentedControl,
  TextInput,
  Group,
  Paper,
  Select,
  NumberInput,
  Divider,
} from '@mantine/core';
import type {
  WizardState,
  StorageType,
  NamingConvention,
  EncodingType,
  ModelStyle,
  StorageConfig,
  MetaStoreType,
  ResourceStoreType,
} from '@/types/wizard';

interface Props {
  state: WizardState;
  onChange: (patch: Partial<WizardState>) => void;
}

const STORAGE_OPTIONS = [
  { value: 'memory', label: 'Memory' },
  { value: 'disk', label: 'Disk' },
  { value: 's3', label: 'S3' },
  { value: 'postgresql', label: 'PostgreSQL' },
  { value: 'custom', label: '自訂組合' },
];

const NAMING_OPTIONS = [
  { value: 'same', label: '不轉換' },
  { value: 'pascal', label: 'PascalCase' },
  { value: 'camel', label: 'camelCase' },
  { value: 'snake', label: 'snake_case' },
  { value: 'kebab', label: 'kebab-case' },
];

const ENCODING_OPTIONS = [
  { value: 'json', label: 'JSON' },
  { value: 'msgpack', label: 'MsgPack' },
];

const MODEL_STYLE_OPTIONS = [
  { value: 'struct', label: 'msgspec Struct' },
  { value: 'pydantic', label: 'Pydantic BaseModel' },
];

function storageDescription(t: StorageType): string {
  switch (t) {
    case 'memory':
      return '資料存在記憶體中，重啟後消失。適合開發與測試。';
    case 'disk':
      return '資料以檔案形式存在本地磁碟。適合小型專案。';
    case 's3':
      return '使用 S3 相容 object storage。適合生產環境。';
    case 'postgresql':
      return '使用 PostgreSQL + S3 混合儲存（metadata 存 PG，blob 存 S3）。適合大型生產環境。';
    case 'custom':
      return '自由組合 MetaStore 與 ResourceStore。進階使用者專用。';
  }
}

const META_STORE_OPTIONS = [
  { value: 'memory', label: 'MemoryMetaStore', description: '記憶體（預設）' },
  { value: 'disk', label: 'DiskMetaStore', description: '磁碟' },
  { value: 'memory-sqlite', label: 'MemorySqliteMetaStore', description: 'SQLite 記憶體模式' },
  { value: 'file-sqlite', label: 'FileSqliteMetaStore', description: 'SQLite 檔案模式' },
  { value: 's3-sqlite', label: 'S3SqliteMetaStore', description: 'SQLite on S3' },
  { value: 'postgres', label: 'PostgresMetaStore', description: 'PostgreSQL' },
  { value: 'sqlalchemy', label: 'SqlAlchemyMetaStore', description: 'SQLAlchemy (any DB)' },
  { value: 'redis', label: 'RedisMetaStore', description: 'Redis' },
  { value: 'fast-slow', label: 'FastSlowMetaStore', description: '快慢雙層快取' },
];

const RESOURCE_STORE_OPTIONS = [
  { value: 'memory', label: 'MemoryResourceStore', description: '記憶體（預設）' },
  { value: 'disk', label: 'DiskResourceStore', description: '磁碟' },
  { value: 's3', label: 'S3ResourceStore', description: 'S3' },
  { value: 'cached-s3', label: 'CachedS3ResourceStore', description: 'S3 + 本地快取' },
  { value: 'etag-cached-s3', label: 'ETagCachedS3ResourceStore', description: 'S3 + ETag 快取' },
  { value: 'mq-cached-s3', label: 'MQCachedS3ResourceStore', description: 'S3 + MQ 快取' },
];

const DEFAULT_NOW_OPTIONS = [
  { value: '', label: '不設定' },
  { value: 'utcnow', label: 'dt.datetime.utcnow' },
  { value: 'now', label: 'dt.datetime.now' },
];

export function StepStorage({ state, onChange }: Props) {
  const updateStorageConfig = (patch: Partial<StorageConfig>) => {
    onChange({ storageConfig: { ...state.storageConfig, ...patch } });
  };

  return (
    <Stack gap="lg">
      <div>
        <Title order={3}>儲存 &amp; 設定</Title>
        <Text size="sm" c="dimmed">
          選擇儲存後端、命名慣例與編碼格式
        </Text>
      </div>

      {/* Storage Backend */}
      <div>
        <Text fw={500} size="sm" mb={4}>
          Storage Backend
        </Text>
        <SegmentedControl
          fullWidth
          data={STORAGE_OPTIONS}
          value={state.storage}
          onChange={(v) => onChange({ storage: v as StorageType })}
        />
        <Text size="xs" c="dimmed" mt={4}>
          {storageDescription(state.storage)}
        </Text>
      </div>

      {/* Conditional Storage Config */}
      {state.storage === 'disk' && (
        <Paper p="md" withBorder>
          <TextInput
            label="Root Directory"
            description="磁碟儲存的根目錄路徑"
            placeholder="./data"
            value={state.storageConfig.rootdir || ''}
            onChange={(e) =>
              updateStorageConfig({ rootdir: e.currentTarget.value })
            }
          />
        </Paper>
      )}

      {state.storage === 's3' && (
        <Paper p="md" withBorder>
          <Stack gap="sm">
            <TextInput
              label="Bucket"
              placeholder="my-bucket"
              value={state.storageConfig.bucket || ''}
              onChange={(e) =>
                updateStorageConfig({ bucket: e.currentTarget.value })
              }
            />
            <TextInput
              label="Endpoint URL"
              description="S3 相容的 endpoint URL（如 MinIO）"
              placeholder="http://localhost:9000"
              value={state.storageConfig.endpointUrl || ''}
              onChange={(e) =>
                updateStorageConfig({ endpointUrl: e.currentTarget.value })
              }
            />
            <Group grow>
              <TextInput
                label="Access Key ID"
                placeholder="minioadmin"
                value={state.storageConfig.accessKeyId || ''}
                onChange={(e) =>
                  updateStorageConfig({ accessKeyId: e.currentTarget.value })
                }
              />
              <TextInput
                label="Secret Access Key"
                placeholder="minioadmin"
                value={state.storageConfig.secretAccessKey || ''}
                onChange={(e) =>
                  updateStorageConfig({
                    secretAccessKey: e.currentTarget.value,
                  })
                }
              />
            </Group>
            <TextInput
              label="Region"
              placeholder="us-east-1"
              value={state.storageConfig.regionName || ''}
              onChange={(e) =>
                updateStorageConfig({ regionName: e.currentTarget.value })
              }
            />
          </Stack>
        </Paper>
      )}

      {state.storage === 'postgresql' && (
        <Paper p="md" withBorder>
          <Stack gap="sm">
            <TextInput
              label="PostgreSQL Connection String"
              placeholder="postgresql://user:pass@localhost:5432/mydb"
              value={state.storageConfig.connectionString || ''}
              onChange={(e) =>
                updateStorageConfig({ connectionString: e.currentTarget.value })
              }
            />
            <TextInput
              label="S3 Bucket (for blobs)"
              placeholder="my-blob-bucket"
              value={state.storageConfig.s3Bucket || ''}
              onChange={(e) =>
                updateStorageConfig({ s3Bucket: e.currentTarget.value })
              }
            />
            <TextInput
              label="S3 Endpoint URL"
              placeholder="http://localhost:9000"
              value={state.storageConfig.s3EndpointUrl || ''}
              onChange={(e) =>
                updateStorageConfig({ s3EndpointUrl: e.currentTarget.value })
              }
            />
            <Group grow>
              <TextInput
                label="S3 Access Key ID"
                placeholder="minioadmin"
                value={state.storageConfig.s3AccessKeyId || ''}
                onChange={(e) =>
                  updateStorageConfig({ s3AccessKeyId: e.currentTarget.value })
                }
              />
              <TextInput
                label="S3 Secret Access Key"
                placeholder="minioadmin"
                value={state.storageConfig.s3SecretAccessKey || ''}
                onChange={(e) =>
                  updateStorageConfig({ s3SecretAccessKey: e.currentTarget.value })
                }
              />
            </Group>
            <TextInput
              label="S3 Region"
              placeholder="us-east-1"
              value={state.storageConfig.s3Region || ''}
              onChange={(e) =>
                updateStorageConfig({ s3Region: e.currentTarget.value })
              }
            />
            <Group grow>
              <TextInput
                label="Table Prefix"
                description="PostgreSQL 表名前綴（選填）"
                placeholder="autocrud_"
                value={state.storageConfig.tablePrefix || ''}
                onChange={(e) =>
                  updateStorageConfig({ tablePrefix: e.currentTarget.value })
                }
              />
              <TextInput
                label="Blob Bucket"
                description="Blob 專用 S3 bucket（選填）"
                placeholder=""
                value={state.storageConfig.blobBucket || ''}
                onChange={(e) =>
                  updateStorageConfig({ blobBucket: e.currentTarget.value })
                }
              />
            </Group>
            <TextInput
              label="Blob Prefix"
              description="Blob key 前綴（選填）"
              placeholder=""
              value={state.storageConfig.blobPrefix || ''}
              onChange={(e) =>
                updateStorageConfig({ blobPrefix: e.currentTarget.value })
              }
            />
          </Stack>
        </Paper>
      )}

      {state.storage === 'custom' && (
        <Paper p="md" withBorder>
          <Stack gap="sm">
            <Text fw={500} size="sm">自訂儲存組合 (SimpleStorage)</Text>
            <Group grow>
              <Select
                label="MetaStore"
                description="儲存 metadata / index 的後端"
                data={META_STORE_OPTIONS}
                value={state.storageConfig.customMetaStore || 'memory'}
                onChange={(v) =>
                  updateStorageConfig({ customMetaStore: (v || 'memory') as MetaStoreType })
                }
              />
              <Select
                label="ResourceStore"
                description="儲存 resource payload 的後端"
                data={RESOURCE_STORE_OPTIONS}
                value={state.storageConfig.customResourceStore || 'memory'}
                onChange={(v) =>
                  updateStorageConfig({ customResourceStore: (v || 'memory') as ResourceStoreType })
                }
              />
            </Group>

            {/* MetaStore params */}
            {state.storageConfig.customMetaStore === 'disk' && (
              <TextInput
                label="Meta Rootdir"
                placeholder="./meta"
                value={state.storageConfig.metaRootdir || ''}
                onChange={(e) => updateStorageConfig({ metaRootdir: e.currentTarget.value })}
              />
            )}
            {state.storageConfig.customMetaStore === 'redis' && (
              <>
                <TextInput
                  label="Redis URL"
                  placeholder="redis://localhost:6379"
                  value={state.storageConfig.metaRedisUrl || ''}
                  onChange={(e) => updateStorageConfig({ metaRedisUrl: e.currentTarget.value })}
                />
                <TextInput
                  label="Redis Key Prefix"
                  placeholder="autocrud:"
                  value={state.storageConfig.metaRedisPrefix || ''}
                  onChange={(e) => updateStorageConfig({ metaRedisPrefix: e.currentTarget.value })}
                />
              </>
            )}
            {state.storageConfig.customMetaStore === 'postgres' && (
              <>
                <TextInput
                  label="PostgreSQL DSN"
                  placeholder="postgresql://user:pass@host/db"
                  value={state.storageConfig.metaPostgresDsn || ''}
                  onChange={(e) => updateStorageConfig({ metaPostgresDsn: e.currentTarget.value })}
                />
                <TextInput
                  label="Table Name"
                  placeholder="autocrud_meta"
                  value={state.storageConfig.metaPostgresTable || ''}
                  onChange={(e) => updateStorageConfig({ metaPostgresTable: e.currentTarget.value })}
                />
              </>
            )}
            {state.storageConfig.customMetaStore === 'sqlalchemy' && (
              <>
                <TextInput
                  label="SQLAlchemy URL"
                  placeholder="sqlite:///data.db"
                  value={state.storageConfig.metaSqlalchemyUrl || ''}
                  onChange={(e) => updateStorageConfig({ metaSqlalchemyUrl: e.currentTarget.value })}
                />
                <TextInput
                  label="Table Name"
                  placeholder="autocrud_meta"
                  value={state.storageConfig.metaSqlalchemyTable || ''}
                  onChange={(e) => updateStorageConfig({ metaSqlalchemyTable: e.currentTarget.value })}
                />
              </>
            )}
            {state.storageConfig.customMetaStore === 'file-sqlite' && (
              <TextInput
                label="SQLite File Path"
                placeholder="./meta.db"
                value={state.storageConfig.metaSqliteFilepath || ''}
                onChange={(e) => updateStorageConfig({ metaSqliteFilepath: e.currentTarget.value })}
              />
            )}
            {state.storageConfig.customMetaStore === 's3-sqlite' && (
              <>
                <Group grow>
                  <TextInput
                    label="S3 Bucket"
                    placeholder="meta-bucket"
                    value={state.storageConfig.metaS3Bucket || ''}
                    onChange={(e) => updateStorageConfig({ metaS3Bucket: e.currentTarget.value })}
                  />
                  <TextInput
                    label="S3 Key"
                    placeholder="meta.db"
                    value={state.storageConfig.metaS3Key || ''}
                    onChange={(e) => updateStorageConfig({ metaS3Key: e.currentTarget.value })}
                  />
                </Group>
                <TextInput
                  label="S3 Endpoint URL"
                  placeholder="http://localhost:9000"
                  value={state.storageConfig.metaS3EndpointUrl || ''}
                  onChange={(e) => updateStorageConfig({ metaS3EndpointUrl: e.currentTarget.value })}
                />
              </>
            )}

            {/* ResourceStore params */}
            {state.storageConfig.customResourceStore === 'disk' && (
              <TextInput
                label="Resource Rootdir"
                placeholder="./resources"
                value={state.storageConfig.resRootdir || ''}
                onChange={(e) => updateStorageConfig({ resRootdir: e.currentTarget.value })}
              />
            )}
            {['s3', 'cached-s3', 'etag-cached-s3', 'mq-cached-s3'].includes(
              state.storageConfig.customResourceStore || '',
            ) && (
              <>
                <Group grow>
                  <TextInput
                    label="Resource S3 Bucket"
                    placeholder="resource-bucket"
                    value={state.storageConfig.resBucket || ''}
                    onChange={(e) => updateStorageConfig({ resBucket: e.currentTarget.value })}
                  />
                  <TextInput
                    label="Resource S3 Prefix"
                    placeholder="data/"
                    value={state.storageConfig.resPrefix || ''}
                    onChange={(e) => updateStorageConfig({ resPrefix: e.currentTarget.value })}
                  />
                </Group>
                <TextInput
                  label="Resource S3 Endpoint URL"
                  placeholder="http://localhost:9000"
                  value={state.storageConfig.resEndpointUrl || ''}
                  onChange={(e) => updateStorageConfig({ resEndpointUrl: e.currentTarget.value })}
                />
              </>
            )}
            {state.storageConfig.customResourceStore === 'mq-cached-s3' && (
              <Group grow>
                <TextInput
                  label="AMQP URL"
                  placeholder="amqp://localhost"
                  value={state.storageConfig.resAmqpUrl || ''}
                  onChange={(e) => updateStorageConfig({ resAmqpUrl: e.currentTarget.value })}
                />
                <TextInput
                  label="Queue Prefix"
                  placeholder="autocrud_"
                  value={state.storageConfig.resQueuePrefix || ''}
                  onChange={(e) => updateStorageConfig({ resQueuePrefix: e.currentTarget.value })}
                />
              </Group>
            )}
          </Stack>
        </Paper>
      )}

      {/* Naming Convention */}
      <div>
        <Text fw={500} size="sm" mb={4}>
          Naming Convention
        </Text>
        <SegmentedControl
          fullWidth
          data={NAMING_OPTIONS}
          value={state.naming}
          onChange={(v) => onChange({ naming: v as NamingConvention })}
        />
        <Text size="xs" c="dimmed" mt={4}>
          API URL 中 model 名稱的轉換規則，例如 MyModel → my-model (kebab-case)
        </Text>
      </div>

      {/* Encoding */}
      <div>
        <Text fw={500} size="sm" mb={4}>
          Encoding
        </Text>
        <SegmentedControl
          fullWidth
          data={ENCODING_OPTIONS}
          value={state.encoding}
          onChange={(v) => onChange({ encoding: v as EncodingType })}
        />
        <Text size="xs" c="dimmed" mt={4}>
          {state.encoding === 'json'
            ? 'JSON 格式，人類可讀，適合調試。'
            : 'MsgPack 二進制格式，更快更小，適合高效能場景。'}
        </Text>
      </div>

      {/* Model Style */}
      <div>
        <Text fw={500} size="sm" mb={4}>
          Model Style
        </Text>
        <SegmentedControl
          fullWidth
          data={MODEL_STYLE_OPTIONS}
          value={state.modelStyle}
          onChange={(v) => onChange({ modelStyle: v as ModelStyle })}
        />
        <Text size="xs" c="dimmed" mt={4}>
          {state.modelStyle === 'struct'
            ? 'msgspec.Struct 高效能序列化，AutoCRUD 原生支援。'
            : 'Pydantic BaseModel，自動轉換為 Struct，支援 field_validator。'}
        </Text>
      </div>

      {/* Advanced Configuration */}
      <Divider my="xs" />
      <div>
        <Title order={4}>進階設定</Title>
        <Text size="xs" c="dimmed" mb="sm">
          configure() 的額外選項
        </Text>
      </div>

      <Group grow>
        <TextInput
          label="Default User (admin)"
          description="crud.configure(admin=...) — 預設操作者名稱"
          placeholder="留空不設定"
          value={state.defaultUser}
          onChange={(e) => onChange({ defaultUser: e.currentTarget.value })}
        />
        <Select
          label="Default Now"
          description="crud.configure(default_now=...) — 時間戳函式"
          data={DEFAULT_NOW_OPTIONS}
          value={state.defaultNow}
          onChange={(v) =>
            onChange({ defaultNow: (v || '') as '' | 'utcnow' | 'now' })
          }
        />
      </Group>
    </Stack>
  );
}
