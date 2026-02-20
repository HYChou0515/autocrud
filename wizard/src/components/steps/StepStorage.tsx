import {
  Stack,
  Title,
  Text,
  SegmentedControl,
  TextInput,
  Group,
  Paper,
} from '@mantine/core';
import type {
  WizardState,
  StorageType,
  NamingConvention,
  EncodingType,
  ModelStyle,
  StorageConfig,
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
  }
}

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
            <TextInput
              label="Table Prefix"
              description="PostgreSQL 表名前綴（選填）"
              placeholder="autocrud_"
              value={state.storageConfig.tablePrefix || ''}
              onChange={(e) =>
                updateStorageConfig({ tablePrefix: e.currentTarget.value })
              }
            />
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
    </Stack>
  );
}
