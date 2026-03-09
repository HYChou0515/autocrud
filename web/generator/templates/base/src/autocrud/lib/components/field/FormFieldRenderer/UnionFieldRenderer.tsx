/**
 * UnionFieldRenderer — Renders discriminated, structural, and simple union fields.
 *
 * Three rendering modes:
 * 1. **Structural** (`discriminatorField === '__variant'`): anyOf without discriminator.
 *    Radio.Card selection between named variants; each variant gets its own fieldset.
 *    Array variants use __items sub-path; object variants render inline sub-fields;
 *    primitive variants render a single input.
 * 2. **Discriminated** (real discriminator field): Radio.Card with sub-fields.
 * 3. **Simple** (`discriminatorField === '__type'`): Radio.Group for primitive types.
 */

import {
  TextInput,
  NumberInput,
  Textarea,
  Select,
  Button,
  Stack,
  Group,
  Switch,
  Text,
  Paper,
  Radio,
  ActionIcon,
  TagsInput,
} from '@mantine/core';
import { DateTimePicker } from '@mantine/dates';
import { IconTrash, IconPlus } from '@tabler/icons-react';
import { useRef, useState } from 'react';
import type { UseFormReturnType } from '@mantine/form';
import type { ResourceField, UnionMeta, UnionVariant } from '../../../resources';
import { BinaryFieldEditor } from './BinaryFieldEditor';
import { ArrayFieldRenderer } from './ArrayFieldRenderer';
import {
  getByPath,
  createEmptyItem,
  getEmptyValue,
  type BinaryFormValue,
} from '@/autocrud/lib/utils/formUtils';

interface UnionFieldRendererProps {
  field: ResourceField;
  unionMeta: UnionMeta;
  form: UseFormReturnType<any>;
  simpleUnionTypes: Record<string, string>;
  setSimpleUnionTypes: React.Dispatch<React.SetStateAction<Record<string, string>>>;
}

// ---------------------------------------------------------------------------
// Shared sub-field renderers
// ---------------------------------------------------------------------------

/** Render a single sub-field at the given form path. */
function renderSubField(sf: ResourceField, subPath: string, form: UseFormReturnType<any>) {
  if (sf.enumValues && sf.enumValues.length > 0) {
    return (
      <Select
        key={subPath}
        label={sf.label}
        required={sf.isRequired && !sf.isNullable}
        data={sf.enumValues.map((v) => ({ value: v, label: v }))}
        clearable={sf.isNullable}
        {...form.getInputProps(subPath)}
      />
    );
  }
  if (sf.type === 'binary') {
    const apiUrl = (typeof window !== 'undefined' && (import.meta as any).env?.VITE_API_URL) || '';
    const binaryVal = getByPath(
      form.getValues() as Record<string, any>,
      subPath,
    ) as unknown as BinaryFormValue | null;
    return (
      <BinaryFieldEditor
        key={subPath}
        label={sf.label}
        required={sf.isRequired && !sf.isNullable}
        value={binaryVal}
        onChange={(val) => form.setFieldValue(subPath as any, val as any)}
        apiUrl={apiUrl}
      />
    );
  }
  if (sf.type === 'boolean') {
    return (
      <Switch
        key={subPath}
        label={sf.label}
        {...form.getInputProps(subPath, { type: 'checkbox' })}
      />
    );
  }
  if (sf.type === 'number') {
    return (
      <NumberInput
        key={subPath}
        label={sf.label}
        required={sf.isRequired && !sf.isNullable}
        {...form.getInputProps(subPath)}
      />
    );
  }
  if (sf.type === 'object') {
    return (
      <Textarea
        key={subPath}
        label={sf.label}
        required={sf.isRequired && !sf.isNullable}
        placeholder="{}"
        minRows={2}
        styles={{ input: { fontFamily: 'monospace', fontSize: '13px' } }}
        {...form.getInputProps(subPath)}
      />
    );
  }
  if (sf.isArray && sf.type === 'string') {
    return (
      <TagsInput
        key={subPath}
        label={sf.label}
        required={sf.isRequired && !sf.isNullable}
        placeholder="Type and press Enter"
        clearable
        {...form.getInputProps(subPath)}
      />
    );
  }
  // Date sub-field
  if (sf.type === 'date') {
    return (
      <DateTimePicker
        key={subPath}
        label={sf.label}
        required={sf.isRequired && !sf.isNullable}
        valueFormat="YYYY-MM-DD HH:mm:ss"
        clearable
        {...form.getInputProps(subPath)}
      />
    );
  }
  // Nested union sub-field (recursive)
  if (sf.type === 'union' && sf.unionMeta) {
    return <NestedUnionWrapper key={subPath} field={sf} path={subPath} form={form} />;
  }
  // Nested array of typed objects
  if (sf.itemFields && sf.itemFields.length > 0) {
    return <ArrayFieldRenderer key={subPath} field={{ ...sf, name: subPath }} form={form} />;
  }
  return (
    <TextInput
      key={subPath}
      label={sf.label}
      required={sf.isRequired && !sf.isNullable}
      {...form.getInputProps(subPath)}
    />
  );
}

// ---------------------------------------------------------------------------
// Helper: empty value for a sub-field based on its type
// ---------------------------------------------------------------------------

/** Return an appropriate empty/default value for a sub-field within a union variant. */
function emptyValueForSubField(sf: ResourceField): any {
  if (sf.constValue !== undefined) return sf.constValue;
  if (sf.type === 'binary') return { _mode: 'empty' };
  if (sf.type === 'boolean') return false;
  if (sf.type === 'union' && sf.unionMeta) return getEmptyValue(sf);
  if (sf.itemFields && sf.itemFields.length > 0) return [];
  if (sf.type === 'number') return '';
  if (sf.isArray) return [];
  return '';
}

/**
 * Wrapper component for rendering a nested union sub-field.
 * Manages its own simpleUnionTypes state (needed for simple unions).
 */
function NestedUnionWrapper({
  field,
  path,
  form,
}: {
  field: ResourceField;
  path: string;
  form: UseFormReturnType<any>;
}) {
  const [sut, setSut] = useState<Record<string, string>>({});
  return (
    <UnionFieldRenderer
      field={{ ...field, name: path }}
      unionMeta={field.unionMeta!}
      form={form}
      simpleUnionTypes={sut}
      setSimpleUnionTypes={setSut}
    />
  );
}

// ---------------------------------------------------------------------------
// Discriminated union array body
// ---------------------------------------------------------------------------

/**
 * Render an array whose items are discriminated union variants.
 * Each item has a variant-type selector (Select) + corresponding sub-fields.
 * The "Add" button remembers the last selected variant type.
 */
function DiscriminatedArrayBody({
  itemsPath,
  items,
  itemUnionMeta,
  form,
}: {
  itemsPath: string;
  items: any[];
  itemUnionMeta: UnionMeta;
  form: UseFormReturnType<any>;
}) {
  const { discriminatorField, variants } = itemUnionMeta;
  const lastVariantRef = useRef(variants[0]?.tag ?? '');

  const createEmptyItemForVariant = (tag: string): Record<string, any> => {
    const variant = variants.find((v) => v.tag === tag);
    const item: Record<string, any> = { [discriminatorField]: tag };
    if (variant?.fields) {
      for (const sf of variant.fields) {
        item[sf.name] = emptyValueForSubField(sf);
      }
    }
    return item;
  };

  const selectData = variants.map((v) => ({ value: v.tag, label: v.label }));

  return (
    <Paper withBorder p="sm" radius="sm">
      <Stack gap="xs">
        <Group justify="space-between" align="center">
          <Text size="xs" c="dimmed" fw={500}>
            Items ({items.length})
          </Text>
          <Button
            size="compact-xs"
            variant="light"
            leftSection={<IconPlus size={14} />}
            onClick={() => {
              const tag = lastVariantRef.current || variants[0]?.tag;
              if (tag) form.insertListItem(itemsPath, createEmptyItemForVariant(tag));
            }}
          >
            Add
          </Button>
        </Group>
        {items.length === 0 && (
          <Text size="sm" c="dimmed" fs="italic">
            No items yet
          </Text>
        )}
        {items.map((item: any, index: number) => {
          const currentTag = item?.[discriminatorField] ?? variants[0]?.tag ?? '';
          const currentVariant = variants.find((v) => v.tag === currentTag);
          const itemPath = `${itemsPath}.${index}`;

          return (
            <Paper key={index} withBorder p="sm" radius="sm">
              <Group justify="space-between" mb="xs">
                <Text size="xs" c="dimmed" fw={500}>
                  #{index + 1}
                </Text>
                <ActionIcon
                  size="sm"
                  color="red"
                  variant="subtle"
                  onClick={() => form.removeListItem(itemsPath, index)}
                >
                  <IconTrash size={14} />
                </ActionIcon>
              </Group>
              <Stack gap="xs">
                <Select
                  size="xs"
                  label="Type"
                  data={selectData}
                  value={currentTag}
                  onChange={(tag) => {
                    if (!tag) return;
                    lastVariantRef.current = tag;
                    // Replace the whole item with empty fields for the new variant
                    form.setFieldValue(`${itemPath}` as any, createEmptyItemForVariant(tag) as any);
                  }}
                  allowDeselect={false}
                />
                {currentVariant?.fields?.map((sf) =>
                  renderSubField(sf, `${itemPath}.${sf.name}`, form),
                )}
              </Stack>
            </Paper>
          );
        })}
      </Stack>
    </Paper>
  );
}

// ---------------------------------------------------------------------------
// Structural union variant body
// ---------------------------------------------------------------------------

/** Render the body for the currently-selected structural union variant. */
function StructuralVariantBody({
  variant,
  name,
  form,
}: {
  variant: UnionVariant;
  name: string;
  form: UseFormReturnType<any>;
}) {
  // ── Null variant: no body needed ──
  if (variant.type === 'null') {
    return (
      <Text size="sm" c="dimmed" fs="italic">
        This field will be set to null
      </Text>
    );
  }

  // ── Array variant: repeatable list via __items ──
  if (variant.isArray) {
    const itemsPath = `${name}.__items`;
    const rawItems = getByPath(form.getValues() as Record<string, any>, itemsPath);
    const items: any[] = Array.isArray(rawItems) ? rawItems : [];

    // Discriminated union array items (itemUnionMeta present)
    if (variant.itemUnionMeta) {
      return (
        <DiscriminatedArrayBody
          itemsPath={itemsPath}
          items={items}
          itemUnionMeta={variant.itemUnionMeta}
          form={form}
        />
      );
    }

    // Regular (non-union) array items
    const hasFields = variant.fields && variant.fields.length > 0;
    const emptyItem = hasFields ? createEmptyItem(variant.fields!) : '';

    return (
      <Paper withBorder p="sm" radius="sm">
        <Stack gap="xs">
          <Group justify="space-between" align="center">
            <Text size="xs" c="dimmed" fw={500}>
              Items ({items.length})
            </Text>
            <Button
              size="compact-xs"
              variant="light"
              leftSection={<IconPlus size={14} />}
              onClick={() => form.insertListItem(itemsPath, emptyItem)}
            >
              Add
            </Button>
          </Group>
          {items.length === 0 && (
            <Text size="sm" c="dimmed" fs="italic">
              No items yet
            </Text>
          )}
          {items.map((_: any, index: number) => {
            if (!hasFields) {
              // Primitive array items (e.g., list[str])
              const primItemPath = `${itemsPath}.${index}`;
              return (
                <Group key={index} gap="xs" align="flex-end">
                  <TextInput
                    style={{ flex: 1 }}
                    label={`#${index + 1}`}
                    {...form.getInputProps(primItemPath)}
                  />
                  <ActionIcon
                    size="sm"
                    color="red"
                    variant="subtle"
                    onClick={() => form.removeListItem(itemsPath, index)}
                  >
                    <IconTrash size={14} />
                  </ActionIcon>
                </Group>
              );
            }
            // Object-typed array items
            return (
              <Paper key={index} withBorder p="sm" radius="sm">
                <Group justify="space-between" mb="xs">
                  <Text size="xs" c="dimmed" fw={500}>
                    #{index + 1}
                  </Text>
                  <ActionIcon
                    size="sm"
                    color="red"
                    variant="subtle"
                    onClick={() => form.removeListItem(itemsPath, index)}
                  >
                    <IconTrash size={14} />
                  </ActionIcon>
                </Group>
                <Stack gap="xs">
                  {variant.fields!.map((sf) =>
                    renderSubField(sf, `${itemsPath}.${index}.${sf.name}`, form),
                  )}
                </Stack>
              </Paper>
            );
          })}
        </Stack>
      </Paper>
    );
  }

  // ── Dict variant: key-value map editor via __entries ──
  if (variant.isDict) {
    const entriesPath = `${name}.__entries`;
    const rawEntries = getByPath(form.getValues() as Record<string, any>, entriesPath);
    const entries: any[] = Array.isArray(rawEntries) ? rawEntries : [];
    const hasValueFields = variant.dictValueFields && variant.dictValueFields.length > 0;
    const emptyEntry: Record<string, any> = { __key: '' };
    if (hasValueFields) {
      for (const sf of variant.dictValueFields!) {
        emptyEntry[sf.name] = emptyValueForSubField(sf);
      }
    } else {
      emptyEntry.__value = '';
    }

    return (
      <Paper withBorder p="sm" radius="sm">
        <Stack gap="xs">
          <Group justify="space-between" align="center">
            <Text size="xs" c="dimmed" fw={500}>
              Entries ({entries.length})
            </Text>
            <Button
              size="compact-xs"
              variant="light"
              leftSection={<IconPlus size={14} />}
              onClick={() => form.insertListItem(entriesPath, emptyEntry)}
            >
              Add
            </Button>
          </Group>
          {entries.length === 0 && (
            <Text size="sm" c="dimmed" fs="italic">
              No entries yet
            </Text>
          )}
          {entries.map((_: any, index: number) => (
            <Paper key={index} withBorder p="sm" radius="sm">
              <Group justify="space-between" mb="xs">
                <Text size="xs" c="dimmed" fw={500}>
                  #{index + 1}
                </Text>
                <ActionIcon
                  size="sm"
                  color="red"
                  variant="subtle"
                  onClick={() => form.removeListItem(entriesPath, index)}
                >
                  <IconTrash size={14} />
                </ActionIcon>
              </Group>
              <Stack gap="xs">
                <TextInput
                  label="Key"
                  required
                  {...form.getInputProps(`${entriesPath}.${index}.__key`)}
                />
                {hasValueFields ? (
                  variant.dictValueFields!.map((sf) =>
                    renderSubField(sf, `${entriesPath}.${index}.${sf.name}`, form),
                  )
                ) : (
                  <TextInput
                    label="Value"
                    {...form.getInputProps(`${entriesPath}.${index}.__value`)}
                  />
                )}
              </Stack>
            </Paper>
          ))}
        </Stack>
      </Paper>
    );
  }

  // ── Object variant: inline sub-fields (skip constValue fields — auto-injected) ──
  if (variant.fields && variant.fields.length > 0) {
    const editableFields = variant.fields.filter((sf) => sf.constValue === undefined);
    return (
      <Paper withBorder p="sm" radius="sm">
        <Stack gap="xs">
          {editableFields.map((sf) => renderSubField(sf, `${name}.${sf.name}`, form))}
        </Stack>
      </Paper>
    );
  }

  // ── Primitive variant: single value input ──
  const valuePath = `${name}.value`;
  if (variant.type === 'number' || variant.type === 'integer') {
    return <NumberInput label="Value" {...form.getInputProps(valuePath)} />;
  }
  if (variant.type === 'boolean') {
    return <Switch label="Value" {...form.getInputProps(valuePath, { type: 'checkbox' })} />;
  }
  if (variant.type === 'string') {
    return <TextInput label="Value" {...form.getInputProps(valuePath)} />;
  }
  // Fallback: JSON textarea for complex/unknown types
  return (
    <Textarea
      label="Value (JSON)"
      autosize
      minRows={3}
      placeholder='{"key": "value"}'
      {...form.getInputProps(valuePath)}
    />
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function UnionFieldRenderer({
  field,
  unionMeta,
  form,
  simpleUnionTypes,
  setSimpleUnionTypes,
}: UnionFieldRendererProps) {
  const { name, label, isRequired } = field;
  const currentValue = getByPath(form.getValues() as Record<string, any>, name);

  // ── Structural union (__variant mode) ──
  if (unionMeta.discriminatorField === '__variant') {
    const selectedTag = currentValue?.__variant ?? unionMeta.variants[0]?.tag ?? '';
    const selectedVariant = unionMeta.variants.find((v) => v.tag === selectedTag);

    const handleVariantChange = (tag: string) => {
      const variant = unionMeta.variants.find((v) => v.tag === tag);
      if (!variant) return;

      // Null variant — no body needed
      if (variant.type === 'null') {
        form.setFieldValue(name as any, { __variant: tag } as any);
        return;
      }
      if (variant.isArray) {
        form.setFieldValue(name as any, { __variant: tag, __items: [] } as any);
        return;
      }
      if (variant.isDict) {
        form.setFieldValue(name as any, { __variant: tag, __entries: [] } as any);
        return;
      }
      if (variant.fields && variant.fields.length > 0) {
        const newValue: Record<string, any> = { __variant: tag };
        for (const sf of variant.fields) {
          newValue[sf.name] = emptyValueForSubField(sf);
        }
        form.setFieldValue(name as any, newValue as any);
        return;
      }
      // Primitive
      form.setFieldValue(name as any, { __variant: tag, value: '' } as any);
    };

    return (
      <Stack key={name} gap="xs">
        <Radio.Group
          label={label}
          required={isRequired && !field.isNullable}
          value={selectedTag}
          onChange={handleVariantChange}
        >
          <Stack gap="xs" mt="xs">
            {unionMeta.variants.map((v) => (
              <Radio.Card key={v.tag} value={v.tag} radius="md" withBorder p="md">
                <Group wrap="nowrap" align="flex-start">
                  <Radio.Indicator />
                  <div>
                    <Text fw={500} size="sm">
                      {v.label}
                    </Text>
                    {v.schemaName && (
                      <Text size="xs" c="dimmed">
                        {v.schemaName}
                      </Text>
                    )}
                    {v.isArray && (
                      <Text size="xs" c="dimmed">
                        (array)
                      </Text>
                    )}
                    {v.isDict && (
                      <Text size="xs" c="dimmed">
                        (dict)
                      </Text>
                    )}
                    {v.type === 'null' && (
                      <Text size="xs" c="dimmed">
                        (null)
                      </Text>
                    )}
                  </div>
                </Group>
              </Radio.Card>
            ))}
          </Stack>
        </Radio.Group>

        {selectedVariant && (
          <StructuralVariantBody variant={selectedVariant} name={name} form={form} />
        )}
      </Stack>
    );
  }

  // ── Discriminated union ──
  const isDiscriminated = unionMeta.discriminatorField !== '__type';

  if (isDiscriminated) {
    // Array of discriminated union items — render DiscriminatedArrayBody directly
    if (field.isArray) {
      const items = Array.isArray(currentValue) ? currentValue : [];
      return (
        <Stack key={name} gap="xs">
          <Text fw={500} size="sm">
            {label}
          </Text>
          <DiscriminatedArrayBody
            itemsPath={name}
            items={items}
            itemUnionMeta={unionMeta}
            form={form}
          />
        </Stack>
      );
    }

    const discField = unionMeta.discriminatorField;
    const isValueNull = currentValue === null || currentValue === undefined;
    const selectedTag =
      isValueNull && field.isNullable ? '__none__' : (currentValue?.[discField] ?? '');
    const selectedVariant = unionMeta.variants.find((v) => v.tag === selectedTag);

    const handleVariantChange = (tag: string) => {
      // Handle None option for nullable discriminated unions
      if (tag === '__none__') {
        form.setFieldValue(name as any, null as any);
        return;
      }
      const variant = unionMeta.variants.find((v) => v.tag === tag);
      if (!variant) return;
      const newValue: Record<string, any> = { [discField]: tag };
      if (variant.fields) {
        for (const sf of variant.fields) {
          newValue[sf.name] = emptyValueForSubField(sf);
        }
      }
      form.setFieldValue(name as any, newValue as any);
    };

    return (
      <Stack key={name} gap="xs">
        <Radio.Group
          label={label}
          required={isRequired && !field.isNullable}
          value={selectedTag}
          onChange={handleVariantChange}
        >
          <Stack gap="xs" mt="xs">
            {field.isNullable && (
              <Radio.Card key="__none__" value="__none__" radius="md" withBorder p="md">
                <Group wrap="nowrap" align="flex-start">
                  <Radio.Indicator />
                  <div>
                    <Text fw={500} size="sm">
                      None
                    </Text>
                    <Text size="xs" c="dimmed">
                      (null)
                    </Text>
                  </div>
                </Group>
              </Radio.Card>
            )}
            {unionMeta.variants.map((v) => (
              <Radio.Card key={v.tag} value={v.tag} radius="md" withBorder p="md">
                <Group wrap="nowrap" align="flex-start">
                  <Radio.Indicator />
                  <div>
                    <Text fw={500} size="sm">
                      {v.label}
                    </Text>
                    {v.schemaName && (
                      <Text size="xs" c="dimmed">
                        {v.schemaName}
                      </Text>
                    )}
                  </div>
                </Group>
              </Radio.Card>
            ))}
          </Stack>
        </Radio.Group>

        {selectedTag === '__none__' && (
          <Text size="sm" c="dimmed" fs="italic">
            This field will be set to null
          </Text>
        )}

        {selectedVariant?.fields && selectedVariant.fields.length > 0 && (
          <Paper withBorder p="sm" radius="sm">
            <Stack gap="xs">
              {selectedVariant.fields.map((sf) => renderSubField(sf, `${name}.${sf.name}`, form))}
            </Stack>
          </Paper>
        )}
      </Stack>
    );
  }

  // ── Simple union ──
  const inferType = (): string => {
    if (currentValue === null || currentValue === undefined || currentValue === '') {
      return simpleUnionTypes[name] || unionMeta.variants[0]?.tag || '';
    }
    if (typeof currentValue === 'number') return 'number';
    if (typeof currentValue === 'boolean') return 'boolean';
    return 'string';
  };
  const selectedType = inferType();

  const handleTypeChange = (tag: string) => {
    setSimpleUnionTypes((prev) => ({ ...prev, [name]: tag }));
    const variant = unionMeta.variants.find((v) => v.tag === tag);
    if (!variant) return;
    if (variant.type === 'number' || variant.type === 'integer') {
      form.setFieldValue(name as any, '' as any);
    } else if (variant.type === 'boolean') {
      form.setFieldValue(name as any, false as any);
    } else {
      form.setFieldValue(name as any, '' as any);
    }
  };

  const renderSimpleInput = () => {
    const variant = unionMeta.variants.find((v) => v.tag === selectedType);
    if (!variant) return null;
    if (variant.type === 'boolean') {
      return (
        <Switch label={`${label} value`} {...form.getInputProps(name, { type: 'checkbox' })} />
      );
    }
    if (variant.type === 'number' || variant.type === 'integer') {
      return (
        <NumberInput
          label={`${label} value`}
          required={isRequired && !field.isNullable}
          {...form.getInputProps(name)}
        />
      );
    }
    return (
      <TextInput
        label={`${label} value`}
        required={isRequired && !field.isNullable}
        {...form.getInputProps(name)}
      />
    );
  };

  return (
    <Stack key={name} gap="xs">
      <Radio.Group
        label={label}
        required={isRequired && !field.isNullable}
        value={selectedType}
        onChange={(val) => handleTypeChange(val)}
      >
        <Group mt="xs">
          {unionMeta.variants.map((v) => (
            <Radio key={v.tag} value={v.tag} label={v.label} />
          ))}
        </Group>
      </Radio.Group>
      {renderSimpleInput()}
    </Stack>
  );
}
