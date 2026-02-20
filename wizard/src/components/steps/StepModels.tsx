import { useState, useCallback, useRef, useEffect } from 'react';
import {
  Stack,
  Title,
  Text,
  Group,
  TextInput,
  Select,
  MultiSelect,
  TagsInput,
  Switch,
  ActionIcon,
  Paper,
  Tabs,
  Button,
  Accordion,
  Badge,
  Tooltip,
  Table,
  Checkbox,
  Code,
  Divider,
  ScrollArea,
  Textarea,
} from '@mantine/core';
import type { ComboboxLikeRenderOptionInput } from '@mantine/core';
import {
  IconPlus,
  IconTrash,
  IconCode,
  IconForms,
  IconCopy,
} from '@tabler/icons-react';
import type {
  WizardState,
  ModelDefinition,
  FieldDefinition,
  FieldType,
  EnumDefinition,
  SubStructDefinition,
} from '@/types/wizard';
import {
  createEmptyField,
  createEmptyModel,
  createEmptyEnum,
  createEmptySubStruct,
  BUILTIN_TYPES,
} from '@/types/wizard';

interface Props {
  state: WizardState;
  onChange: (patch: Partial<WizardState>) => void;
}

const FIELD_TYPE_OPTIONS: {
  value: FieldType;
  label: string;
  description?: string;
}[] = [
  { value: 'str', label: 'str' },
  { value: 'int', label: 'int' },
  { value: 'float', label: 'float' },
  { value: 'bool', label: 'bool' },
  { value: 'datetime', label: 'datetime' },
  {
    value: 'dict',
    label: 'dict',
    description: '字典型別，可選 dict 或 dict[K, V]',
  },
  {
    value: 'Binary',
    label: 'Binary',
    description: '二進位資料，自動存入 blob store',
  },
  {
    value: 'Ref',
    label: 'Ref',
    description: '外鍵，關聯到另一個 resource',
  },
  {
    value: 'RefRevision',
    label: 'RefRevision',
    description: '參照特定 resource 的某個 revision',
  },
  {
    value: 'Enum',
    label: 'Enum',
    description: '列舉型別，需先在下方定義 Enum',
  },
  {
    value: 'Struct',
    label: 'Struct',
    description: '巢狀結構，需先在下方定義 Sub-struct',
  },
  {
    value: 'Union',
    label: 'Union',
    description: '聯合型別，如 str | int 或 tagged union',
  },
];

const ON_DELETE_OPTIONS = [
  { value: 'dangling', label: 'dangling（預設）' },
  { value: 'set_null', label: 'set_null（設為 null）' },
  { value: 'cascade', label: 'cascade（連帶刪除）' },
];

// Description lookup for field type options
const TYPE_DESCRIPTION_MAP = Object.fromEntries(
  FIELD_TYPE_OPTIONS.filter((o) => o.description).map((o) => [
    o.value,
    o.description,
  ]),
);

function renderTypeOption({
  option,
}: ComboboxLikeRenderOptionInput<{ value: string; label: string }>) {
  const desc = TYPE_DESCRIPTION_MAP[option.value];
  if (!desc) return option.label;
  return (
    <div>
      <Text size="sm">{option.label}</Text>
      <Text size="xs" c="dimmed">
        {desc}
      </Text>
    </div>
  );
}

const TAG_MODE_OPTIONS = [
  { value: '', label: '無' },
  { value: '__auto__', label: '自動 (tag=True)' },
  { value: '__custom__', label: '自訂 tag 值' },
];

export function StepModels({ state, onChange }: Props) {
  const [activeModel, setActiveModel] = useState(0);

  const updateModels = useCallback(
    (models: ModelDefinition[]) => {
      onChange({ models });
    },
    [onChange]
  );

  const updateModel = useCallback(
    (index: number, patch: Partial<ModelDefinition>) => {
      const models = [...state.models];
      models[index] = { ...models[index], ...patch };
      updateModels(models);
    },
    [state.models, updateModels]
  );

  const addModel = useCallback(() => {
    const models = [...state.models, createEmptyModel()];
    updateModels(models);
    setActiveModel(models.length - 1);
  }, [state.models, updateModels]);

  const removeModel = useCallback(
    (index: number) => {
      if (state.models.length <= 1) return;
      const models = state.models.filter((_, i) => i !== index);
      updateModels(models);
      if (activeModel >= models.length) {
        setActiveModel(models.length - 1);
      }
    },
    [state.models, activeModel, updateModels]
  );

  const model = state.models[activeModel];
  if (!model) return null;

  return (
    <Stack gap="lg">
      <div>
        <Title order={3}>Model 定義</Title>
        <Text size="sm" c="dimmed">
          定義你的 resource models，可用表單或直接寫 Python code
        </Text>
      </div>

      {/* Model list tabs */}
      <Group gap="xs" wrap="wrap">
        {state.models.map((m, i) => (
          <Button
            key={i}
            size="xs"
            variant={i === activeModel ? 'filled' : 'outline'}
            onClick={() => setActiveModel(i)}
            rightSection={
              state.models.length > 1 ? (
                <ActionIcon
                  size="xs"
                  variant="transparent"
                  c={i === activeModel ? 'white' : 'red'}
                  onClick={(e) => {
                    e.stopPropagation();
                    removeModel(i);
                  }}
                >
                  <IconTrash size={12} />
                </ActionIcon>
              ) : undefined
            }
          >
            {m.name || `Model ${i + 1}`}
          </Button>
        ))}
        <Button
          size="xs"
          variant="light"
          leftSection={<IconPlus size={14} />}
          onClick={addModel}
        >
          新增 Model
        </Button>
      </Group>

      {/* Active model editor */}
      <Paper p="md" withBorder>
        <Stack gap="md">
          {/* Model name & version */}
          <Group grow>
            <TextInput
              label="Model 名稱"
              placeholder="MyModel"
              value={model.name}
              onChange={(e) =>
                updateModel(activeModel, { name: e.currentTarget.value })
              }
            />
            <TextInput
              label="Schema Version"
              description="用於 Schema(Model, version)"
              placeholder="v1"
              value={model.schemaVersion}
              onChange={(e) =>
                updateModel(activeModel, {
                  schemaVersion: e.currentTarget.value,
                })
              }
            />
          </Group>

          <Switch
            label="啟用 Validator"
            description="生成一個 validate 函式模板供你填寫驗證邏輯"
            checked={model.enableValidator}
            onChange={(e) =>
              updateModel(activeModel, {
                enableValidator: e.currentTarget.checked,
              })
            }
          />

          {model.enableValidator && (
            <Textarea
              label="Validator 程式碼（選填）"
              description="自訂驗證函式。留空則自動生成基本模板。"
              placeholder={`def validate_${model.name.replace(/([A-Z])/g, '_$1').toLowerCase().replace(/^_/, '')}(data: ${model.name}) -> None:\n    pass`}
              minRows={4}
              autosize
              value={model.validatorCode}
              onChange={(e) =>
                updateModel(activeModel, {
                  validatorCode: e.currentTarget.value,
                })
              }
              styles={{ input: { fontFamily: 'monospace', fontSize: '13px' } }}
            />
          )}

          {/* Input mode toggle */}
          <Tabs
            value={model.inputMode}
            onChange={(v) =>
              updateModel(activeModel, {
                inputMode: (v as 'form' | 'code') || 'form',
              })
            }
          >
            <Tabs.List>
              <Tabs.Tab
                value="form"
                leftSection={<IconForms size={16} />}
              >
                表單模式
              </Tabs.Tab>
              <Tabs.Tab
                value="code"
                leftSection={<IconCode size={16} />}
              >
                Code 模式
              </Tabs.Tab>
            </Tabs.List>

            <Tabs.Panel value="form" pt="md">
              <FormModeEditor
                model={model}
                modelIndex={activeModel}
                state={state}
                updateModel={updateModel}
              />
            </Tabs.Panel>

            <Tabs.Panel value="code" pt="md">
              <CodeModeEditor
                model={model}
                modelIndex={activeModel}
                updateModel={updateModel}
                modelStyle={state.modelStyle}
              />
            </Tabs.Panel>
          </Tabs>
        </Stack>
      </Paper>

      {/* Built-in type palette */}
      <BuiltinTypePalette
        model={model}
        modelIndex={activeModel}
        updateModel={updateModel}
      />
    </Stack>
  );
}

// ─── Form Mode Editor ──────────────────────────────────────────

interface FormEditorProps {
  model: ModelDefinition;
  modelIndex: number;
  state: WizardState;
  updateModel: (index: number, patch: Partial<ModelDefinition>) => void;
}

function FormModeEditor({
  model,
  modelIndex,
  state,
  updateModel,
}: FormEditorProps) {
  const updateField = (fieldIndex: number, patch: Partial<FieldDefinition>) => {
    const fields = [...model.fields];
    fields[fieldIndex] = { ...fields[fieldIndex], ...patch };
    updateModel(modelIndex, { fields });
  };

  const setDisplayName = (fieldIndex: number, checked: boolean) => {
    // Radio semantics: only one field can be DisplayName per model
    if (checked) {
      const fields = model.fields.map((f, i) => ({
        ...f,
        isDisplayName: i === fieldIndex,
      }));
      updateModel(modelIndex, { fields });
    } else {
      updateField(fieldIndex, { isDisplayName: false });
    }
  };

  const addField = () => {
    updateModel(modelIndex, { fields: [...model.fields, createEmptyField()] });
  };

  const removeField = (fieldIndex: number) => {
    updateModel(modelIndex, {
      fields: model.fields.filter((_, i) => i !== fieldIndex),
    });
  };

  // Enum helpers
  const addEnum = () => {
    updateModel(modelIndex, { enums: [...model.enums, createEmptyEnum()] });
  };

  const updateEnum = (enumIndex: number, patch: Partial<EnumDefinition>) => {
    const enums = [...model.enums];
    enums[enumIndex] = { ...enums[enumIndex], ...patch };
    updateModel(modelIndex, { enums });
  };

  const removeEnum = (enumIndex: number) => {
    updateModel(modelIndex, {
      enums: model.enums.filter((_, i) => i !== enumIndex),
    });
  };

  // Sub-struct helpers
  const addSubStruct = () => {
    updateModel(modelIndex, {
      subStructs: [...(model.subStructs || []), createEmptySubStruct()],
    });
  };

  const updateSubStruct = (
    ssIndex: number,
    patch: Partial<SubStructDefinition>,
  ) => {
    const subStructs = [...(model.subStructs || [])];
    subStructs[ssIndex] = { ...subStructs[ssIndex], ...patch };
    updateModel(modelIndex, { subStructs });
  };

  const removeSubStruct = (ssIndex: number) => {
    updateModel(modelIndex, {
      subStructs: (model.subStructs || []).filter((_, i) => i !== ssIndex),
    });
  };

  const modelNames = state.models.map((m) => m.name).filter(Boolean);
  const enumNames = model.enums.map((e) => e.name).filter(Boolean);
  const subStructNames = (model.subStructs || [])
    .map((s) => s.name)
    .filter(Boolean);

  return (
    <Stack gap="md">
      {/* Fields Table */}
      <Text fw={500} size="sm">
        欄位定義
      </Text>
      <ScrollArea>
        <Table withTableBorder withColumnBorders>
          <Table.Thead>
            <Table.Tr>
              <Table.Th w={150}>名稱</Table.Th>
              <Table.Th w={120}>類型</Table.Th>
              <Table.Th w={60}>Optional</Table.Th>
              <Table.Th w={60}>List</Table.Th>
              <Table.Th w={120}>預設值</Table.Th>
              <Table.Th w={60}>Indexed</Table.Th>
              <Table.Th w={80}>Display</Table.Th>
              <Table.Th w={50}></Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {model.fields.map((field, fi) => (
              <FieldRow
                key={fi}
                field={field}
                fieldIndex={fi}
                updateField={updateField}
                setDisplayName={setDisplayName}
                removeField={removeField}
                modelNames={modelNames}
                enumNames={enumNames}
                subStructNames={subStructNames}
              />
            ))}
          </Table.Tbody>
        </Table>
      </ScrollArea>

      <Button
        size="xs"
        variant="light"
        leftSection={<IconPlus size={14} />}
        onClick={addField}
      >
        新增欄位
      </Button>

      {/* Sub-struct definitions */}
      {(model.subStructs || []).length > 0 && (
        <Divider label="Sub-struct 定義" />
      )}
      {(model.subStructs || []).map((ss, si) => (
        <SubStructEditor
          key={si}
          subStruct={ss}
          ssIndex={si}
          updateSubStruct={updateSubStruct}
          removeSubStruct={removeSubStruct}
        />
      ))}
      <Button
        size="xs"
        variant="light"
        leftSection={<IconPlus size={14} />}
        onClick={addSubStruct}
      >
        新增 Sub-struct
      </Button>

      {/* Enum definitions */}
      {model.enums.length > 0 && <Divider label="Enum 定義" />}
      {model.enums.map((enumDef, ei) => (
        <EnumEditor
          key={ei}
          enumDef={enumDef}
          enumIndex={ei}
          updateEnum={updateEnum}
          removeEnum={removeEnum}
        />
      ))}
      <Button
        size="xs"
        variant="light"
        leftSection={<IconPlus size={14} />}
        onClick={addEnum}
      >
        新增 Enum
      </Button>
    </Stack>
  );
}

// ─── Single Field Row ──────────────────────────────────────────

interface FieldRowProps {
  field: FieldDefinition;
  fieldIndex: number;
  updateField: (index: number, patch: Partial<FieldDefinition>) => void;
  setDisplayName: (fieldIndex: number, checked: boolean) => void;
  removeField: (index: number) => void;
  modelNames: string[];
  enumNames: string[];
  subStructNames: string[];
}

function FieldRow({
  field,
  fieldIndex,
  updateField,
  setDisplayName,
  removeField,
  modelNames,
  enumNames,
  subStructNames,
}: FieldRowProps) {
  return (
    <>
      <Table.Tr>
        <Table.Td>
          <TextInput
            size="xs"
            placeholder="field_name"
            value={field.name}
            onChange={(e) =>
              updateField(fieldIndex, { name: e.currentTarget.value })
            }
          />
        </Table.Td>
        <Table.Td>
          <Select
            size="xs"
            data={FIELD_TYPE_OPTIONS}
            value={field.type}
            renderOption={renderTypeOption}
            onChange={(v) =>
              updateField(fieldIndex, { type: (v as FieldType) || 'str' })
            }
          />
        </Table.Td>
        <Table.Td>
          <Checkbox
            size="xs"
            checked={field.optional}
            onChange={(e) =>
              updateField(fieldIndex, { optional: e.currentTarget.checked })
            }
          />
        </Table.Td>
        <Table.Td>
          <Checkbox
            size="xs"
            checked={field.isList}
            onChange={(e) =>
              updateField(fieldIndex, { isList: e.currentTarget.checked })
            }
          />
        </Table.Td>
        <Table.Td>
          <TextInput
            size="xs"
            placeholder='""'
            value={field.default}
            onChange={(e) =>
              updateField(fieldIndex, { default: e.currentTarget.value })
            }
          />
        </Table.Td>
        <Table.Td>
          <Checkbox
            size="xs"
            checked={field.isIndexed}
            onChange={(e) =>
              updateField(fieldIndex, { isIndexed: e.currentTarget.checked })
            }
          />
        </Table.Td>
        <Table.Td>
          <Checkbox
            size="xs"
            checked={field.isDisplayName}
            disabled={field.type !== 'str'}
            onChange={(e) =>
              setDisplayName(fieldIndex, e.currentTarget.checked)
            }
          />
        </Table.Td>
        <Table.Td>
          <ActionIcon
            size="xs"
            color="red"
            variant="subtle"
            onClick={() => removeField(fieldIndex)}
          >
            <IconTrash size={12} />
          </ActionIcon>
        </Table.Td>
      </Table.Tr>

      {/* Extra config rows for Ref/RefRevision/Enum */}
      {field.type === 'Ref' && (
        <Table.Tr>
          <Table.Td colSpan={8}>
            <Group gap="sm" ml="md">
              <Select
                size="xs"
                label="Ref → Resource"
                data={modelNames}
                value={field.ref?.resource || ''}
                onChange={(v) =>
                  updateField(fieldIndex, {
                    ref: {
                      resource: v || '',
                      onDelete: field.ref?.onDelete || 'dangling',
                    },
                  })
                }
                w={200}
              />
              <Select
                size="xs"
                label="On Delete"
                data={ON_DELETE_OPTIONS}
                value={field.ref?.onDelete || 'dangling'}
                onChange={(v) =>
                  updateField(fieldIndex, {
                    ref: {
                      resource: field.ref?.resource || '',
                      onDelete:
                        (v as 'dangling' | 'set_null' | 'cascade') ||
                        'dangling',
                    },
                  })
                }
                w={200}
              />
            </Group>
          </Table.Td>
        </Table.Tr>
      )}

      {field.type === 'RefRevision' && (
        <Table.Tr>
          <Table.Td colSpan={8}>
            <Group gap="sm" ml="md">
              <Select
                size="xs"
                label="RefRevision → Resource"
                data={modelNames}
                value={field.refRevision?.resource || ''}
                onChange={(v) =>
                  updateField(fieldIndex, {
                    refRevision: { resource: v || '' },
                  })
                }
                w={200}
              />
            </Group>
          </Table.Td>
        </Table.Tr>
      )}

      {field.type === 'Enum' && (
        <Table.Tr>
          <Table.Td colSpan={8}>
            <Group gap="sm" ml="md">
              <Select
                size="xs"
                label="Enum Type"
                description="選擇已定義的 Enum"
                data={enumNames}
                value={field.default || ''}
                onChange={(v) =>
                  updateField(fieldIndex, { default: v || '' })
                }
                w={200}
              />
              <Text size="xs" c="dimmed" mt={20}>
                在下方 Enum 定義區域新增 Enum
              </Text>
            </Group>
          </Table.Td>
        </Table.Tr>
      )}

      {/* Dict config: optional key/value type */}
      {field.type === 'dict' && (
        <Table.Tr>
          <Table.Td colSpan={8}>
            <Group gap="sm" ml="md">
              <TextInput
                size="xs"
                label="Key Type（可選）"
                placeholder="str"
                value={field.dictKeyType || ''}
                onChange={(e) =>
                  updateField(fieldIndex, {
                    dictKeyType: e.currentTarget.value || null,
                  })
                }
                w={150}
              />
              <TextInput
                size="xs"
                label="Value Type（可選）"
                placeholder="Any"
                value={field.dictValueType || ''}
                onChange={(e) =>
                  updateField(fieldIndex, {
                    dictValueType: e.currentTarget.value || null,
                  })
                }
                w={150}
              />
              <Text size="xs" c="dimmed" mt={20}>
                留空則產生 bare dict
              </Text>
            </Group>
          </Table.Td>
        </Table.Tr>
      )}

      {/* Struct config: select sub-struct name */}
      {field.type === 'Struct' && (
        <Table.Tr>
          <Table.Td colSpan={8}>
            <Group gap="sm" ml="md">
              <Select
                size="xs"
                label="Sub-struct"
                description="選擇已定義的 Sub-struct"
                data={subStructNames}
                value={field.structName || ''}
                onChange={(v) =>
                  updateField(fieldIndex, { structName: v || null })
                }
                w={200}
              />
              <Text size="xs" c="dimmed" mt={20}>
                在下方 Sub-struct 定義區域新增
              </Text>
            </Group>
          </Table.Td>
        </Table.Tr>
      )}

      {/* Union config: pick member types */}
      {field.type === 'Union' && (
        <Table.Tr>
          <Table.Td colSpan={8}>
            <Group gap="sm" ml="md">
              <TagsInput
                size="xs"
                label="Union 成員"
                description="輸入類型名稱或選擇已有類型"
                data={[
                  'str',
                  'int',
                  'float',
                  'bool',
                  ...subStructNames,
                  ...modelNames,
                ]}
                value={field.unionMembers || []}
                onChange={(v) =>
                  updateField(fieldIndex, { unionMembers: v.length ? v : null })
                }
                w={400}
              />
            </Group>
          </Table.Td>
        </Table.Tr>
      )}
    </>
  );
}

// ─── Enum Editor ───────────────────────────────────────────────

interface EnumEditorProps {
  enumDef: EnumDefinition;
  enumIndex: number;
  updateEnum: (index: number, patch: Partial<EnumDefinition>) => void;
  removeEnum: (index: number) => void;
}

function EnumEditor({
  enumDef,
  enumIndex,
  updateEnum,
  removeEnum,
}: EnumEditorProps) {
  return (
    <Paper p="sm" withBorder>
      <Group justify="space-between" mb="xs">
        <TextInput
          size="xs"
          label="Enum 名稱"
          placeholder="MyEnum"
          value={enumDef.name}
          onChange={(e) =>
            updateEnum(enumIndex, { name: e.currentTarget.value })
          }
          w={200}
        />
        <ActionIcon
          color="red"
          variant="subtle"
          onClick={() => removeEnum(enumIndex)}
        >
          <IconTrash size={16} />
        </ActionIcon>
      </Group>

      {enumDef.values.map((v, vi) => (
        <Group key={vi} gap="xs" mb={4}>
          <TextInput
            size="xs"
            placeholder="key"
            value={v.key}
            onChange={(e) => {
              const values = [...enumDef.values];
              values[vi] = { ...values[vi], key: e.currentTarget.value };
              updateEnum(enumIndex, { values });
            }}
            w={120}
          />
          <TextInput
            size="xs"
            placeholder="label"
            value={v.label}
            onChange={(e) => {
              const values = [...enumDef.values];
              values[vi] = { ...values[vi], label: e.currentTarget.value };
              updateEnum(enumIndex, { values });
            }}
            w={150}
          />
          <ActionIcon
            size="xs"
            color="red"
            variant="subtle"
            onClick={() => {
              const values = enumDef.values.filter((_, i) => i !== vi);
              updateEnum(enumIndex, {
                values: values.length ? values : [{ key: '', label: '' }],
              });
            }}
          >
            <IconTrash size={12} />
          </ActionIcon>
        </Group>
      ))}
      <Button
        size="xs"
        variant="subtle"
        leftSection={<IconPlus size={12} />}
        onClick={() =>
          updateEnum(enumIndex, {
            values: [...enumDef.values, { key: '', label: '' }],
          })
        }
      >
        新增值
      </Button>
    </Paper>
  );
}

// ─── Sub-struct Editor ─────────────────────────────────────────

interface SubStructEditorProps {
  subStruct: SubStructDefinition;
  ssIndex: number;
  updateSubStruct: (index: number, patch: Partial<SubStructDefinition>) => void;
  removeSubStruct: (index: number) => void;
}

function SubStructEditor({
  subStruct,
  ssIndex,
  updateSubStruct,
  removeSubStruct,
}: SubStructEditorProps) {
  const addField = () => {
    updateSubStruct(ssIndex, {
      fields: [...subStruct.fields, createEmptyField()],
    });
  };

  const removeField = (fieldIndex: number) => {
    updateSubStruct(ssIndex, {
      fields: subStruct.fields.filter((_, i) => i !== fieldIndex),
    });
  };

  const tagMode =
    subStruct.tag === true
      ? '__auto__'
      : subStruct.tag
        ? '__custom__'
        : '';

  return (
    <Paper p="sm" withBorder>
      <Group justify="space-between" mb="xs">
        <Group gap="sm">
          <TextInput
            size="xs"
            label="Sub-struct 名稱"
            placeholder="MySubStruct"
            value={subStruct.name}
            onChange={(e) =>
              updateSubStruct(ssIndex, { name: e.currentTarget.value })
            }
            w={200}
          />
          <Select
            size="xs"
            label="Tag 模式"
            description="用於 tagged union 識別"
            data={TAG_MODE_OPTIONS}
            value={tagMode}
            onChange={(v) => {
              if (v === '__auto__') {
                updateSubStruct(ssIndex, { tag: true });
              } else if (v === '__custom__') {
                updateSubStruct(ssIndex, { tag: 'my_tag' });
              } else {
                updateSubStruct(ssIndex, { tag: '' });
              }
            }}
            w={160}
          />
          {tagMode === '__custom__' && (
            <TextInput
              size="xs"
              label="Tag 值"
              placeholder='e.g. "warrior"'
              value={typeof subStruct.tag === 'string' ? subStruct.tag : ''}
              onChange={(e) =>
                updateSubStruct(ssIndex, { tag: e.currentTarget.value })
              }
              w={150}
            />
          )}
        </Group>
        <ActionIcon
          color="red"
          variant="subtle"
          onClick={() => removeSubStruct(ssIndex)}
        >
          <IconTrash size={16} />
        </ActionIcon>
      </Group>

      {subStruct.fields.map((field, fi) => (
        <Group key={fi} gap="xs" mb={4}>
          <TextInput
            size="xs"
            placeholder="field_name"
            value={field.name}
            onChange={(e) => {
              const fields = [...subStruct.fields];
              fields[fi] = { ...fields[fi], name: e.currentTarget.value };
              updateSubStruct(ssIndex, { fields });
            }}
            w={120}
          />
          <Select
            size="xs"
            data={FIELD_TYPE_OPTIONS.filter(
              (o) => !['Ref', 'RefRevision', 'Struct', 'Union'].includes(o.value),
            )}
            value={field.type}
            renderOption={renderTypeOption}
            onChange={(v) => {
              const fields = [...subStruct.fields];
              fields[fi] = {
                ...fields[fi],
                type: (v as FieldType) || 'str',
              };
              updateSubStruct(ssIndex, { fields });
            }}
            w={120}
          />
          <Checkbox
            size="xs"
            label="Optional"
            checked={field.optional}
            onChange={(e) => {
              const fields = [...subStruct.fields];
              fields[fi] = {
                ...fields[fi],
                optional: e.currentTarget.checked,
              };
              updateSubStruct(ssIndex, { fields });
            }}
          />
          <TextInput
            size="xs"
            placeholder="預設值"
            value={field.default}
            onChange={(e) => {
              const fields = [...subStruct.fields];
              fields[fi] = {
                ...fields[fi],
                default: e.currentTarget.value,
              };
              updateSubStruct(ssIndex, { fields });
            }}
            w={100}
          />
          <ActionIcon
            size="xs"
            color="red"
            variant="subtle"
            onClick={() => removeField(fi)}
          >
            <IconTrash size={12} />
          </ActionIcon>
        </Group>
      ))}
      <Button
        size="xs"
        variant="subtle"
        leftSection={<IconPlus size={12} />}
        onClick={addField}
      >
        新增欄位
      </Button>
    </Paper>
  );
}

// ─── Code Mode Editor ──────────────────────────────────────────

interface CodeEditorProps {
  model: ModelDefinition;
  modelIndex: number;
  updateModel: (index: number, patch: Partial<ModelDefinition>) => void;
  modelStyle: WizardState['modelStyle'];
}

function CodeModeEditor({
  model,
  modelIndex,
  updateModel,
  modelStyle,
}: CodeEditorProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const placeholder =
    modelStyle === 'struct'
      ? `class ${model.name || 'MyModel'}(Struct):
    name: Annotated[str, DisplayName()]
    description: str = ""
    done: bool = False`
      : `class ${model.name || 'MyModel'}(BaseModel):
    name: str
    description: str = ""
    done: bool = False`;

  // Auto-resize textarea
  useEffect(() => {
    const ta = textareaRef.current;
    if (ta) {
      ta.style.height = 'auto';
      ta.style.height = Math.max(200, ta.scrollHeight) + 'px';
    }
  }, [model.rawCode]);

  return (
    <Stack gap="sm">
      <Text size="xs" c="dimmed">
        直接寫 Python class 定義。支援 Annotated、DisplayName、Ref、RefRevision、Binary
        等所有 AutoCRUD 型別。import 會自動從 code 中偵測。
      </Text>

      <textarea
        ref={textareaRef}
        value={model.rawCode}
        placeholder={placeholder}
        onChange={(e) =>
          updateModel(modelIndex, { rawCode: e.target.value })
        }
        style={{
          fontFamily: 'ui-monospace, "Cascadia Code", "Source Code Pro", Menlo, monospace',
          fontSize: '13px',
          lineHeight: '1.5',
          padding: '12px',
          borderRadius: '8px',
          border: '1px solid var(--mantine-color-default-border)',
          backgroundColor: 'var(--mantine-color-body)',
          color: 'var(--mantine-color-text)',
          resize: 'vertical',
          minHeight: '200px',
          width: '100%',
          outline: 'none',
          tabSize: 4,
        }}
        spellCheck={false}
      />

      <Text size="xs" c="dimmed">
        提示: 你也可以從下方的「Built-in Type 一覽」複製程式碼片段到這裡。
      </Text>
    </Stack>
  );
}

// ─── Built-in Type Palette ─────────────────────────────────────

interface PaletteProps {
  model: ModelDefinition;
  modelIndex: number;
  updateModel: (index: number, patch: Partial<ModelDefinition>) => void;
}

function BuiltinTypePalette({ model, modelIndex, updateModel }: PaletteProps) {
  const [copied, setCopied] = useState<string | null>(null);

  const copySnippet = useCallback(
    (name: string, snippet: string) => {
      navigator.clipboard.writeText(snippet).then(() => {
        setCopied(name);
        setTimeout(() => setCopied(null), 1500);
      });
    },
    []
  );

  const insertToCode = useCallback(
    (snippet: string) => {
      if (model.inputMode === 'code') {
        const code = model.rawCode
          ? model.rawCode + '\n    ' + snippet
          : snippet;
        updateModel(modelIndex, { rawCode: code });
      }
    },
    [model, modelIndex, updateModel]
  );

  return (
    <Accordion variant="separated">
      <Accordion.Item value="builtin-types">
        <Accordion.Control>
          <Group>
            <Text fw={500} size="sm">
              Built-in Type 一覽
            </Text>
            <Badge size="sm" variant="light">
              {BUILTIN_TYPES.length} 種
            </Badge>
          </Group>
        </Accordion.Control>
        <Accordion.Panel>
          <Stack gap="sm">
            {BUILTIN_TYPES.map((bt) => (
              <Paper key={bt.name} p="sm" withBorder>
                <Group justify="space-between" mb="xs">
                  <Group gap="xs">
                    <Text size="lg">{bt.icon}</Text>
                    <Text fw={600} size="sm">
                      {bt.name}
                    </Text>
                  </Group>
                  <Group gap="xs">
                    <Tooltip
                      label={copied === bt.name ? '已複製！' : '複製程式碼'}
                    >
                      <ActionIcon
                        size="sm"
                        variant="subtle"
                        onClick={() =>
                          copySnippet(bt.name, bt.codeSnippet)
                        }
                      >
                        <IconCopy size={14} />
                      </ActionIcon>
                    </Tooltip>
                    {model.inputMode === 'code' && (
                      <Button
                        size="xs"
                        variant="light"
                        onClick={() => insertToCode(bt.codeSnippet)}
                      >
                        插入到 Code
                      </Button>
                    )}
                  </Group>
                </Group>
                <Text size="xs" mb="xs">
                  {bt.description}
                </Text>
                <Text size="xs" c="dimmed" mb="xs">
                  {bt.detailedDescription}
                </Text>
                <Code block>{bt.importStatement + '\n\n' + bt.codeSnippet}</Code>
              </Paper>
            ))}
          </Stack>
        </Accordion.Panel>
      </Accordion.Item>
    </Accordion>
  );
}
