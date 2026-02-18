/**
 * FieldRenderer — Renders a single field based on its type and variant.
 * Also renders arrays of typed objects (itemFields) and delegates union
 * fields to UnionFieldRenderer.
 */

import {
  TextInput,
  NumberInput,
  Textarea,
  Checkbox,
  Select,
  Button,
  Stack,
  Group,
  Switch,
  Text,
  ActionIcon,
  Paper,
} from '@mantine/core';
import { DateTimePicker } from '@mantine/dates';
import { IconTrash, IconPlus } from '@tabler/icons-react';
import type { UseFormReturnType } from '@mantine/form';
import type { ResourceField, FieldVariant } from '../../resources';
import { RefSelect, RefMultiSelect, RefRevisionSelect, RefRevisionMultiSelect } from '../RefSelect';
import { MarkdownEditor } from '../MarkdownEditor';
import { BinaryFieldEditor } from './BinaryFieldEditor';
import { UnionFieldRenderer } from './UnionFieldRenderer';
import {
  getByPath,
  getDefaultVariant,
  safeGetArrayItems,
  createEmptyItem,
  type BinaryFormValue,
} from '@/lib/utils/formUtils';

interface FieldRendererProps {
  field: ResourceField;
  form: UseFormReturnType<any>;
  simpleUnionTypes: Record<string, string>;
  setSimpleUnionTypes: React.Dispatch<React.SetStateAction<Record<string, string>>>;
}

export function FieldRenderer({
  field,
  form,
  simpleUnionTypes,
  setSimpleUnionTypes,
}: FieldRendererProps) {
  const { name, label, type, isRequired, isArray, variant } = field;
  const key = name;

  // Array of typed objects — render as repeatable list with sub-fields
  if (field.itemFields && field.itemFields.length > 0) {
    const rawItems = (form.getValues() as Record<string, any>)[name];
    const items = safeGetArrayItems(rawItems);
    const emptyItemFactory = () => createEmptyItem(field.itemFields!);

    return (
      <Stack key={key} gap="xs">
        <Group justify="space-between" align="center">
          <Text fw={500} size="sm">
            {label}
          </Text>
          <Button
            size="compact-xs"
            variant="light"
            leftSection={<IconPlus size={14} />}
            onClick={() => form.insertListItem(name, emptyItemFactory())}
          >
            Add
          </Button>
        </Group>
        {items.length === 0 && (
          <Text size="sm" c="dimmed" fs="italic">
            No items yet
          </Text>
        )}
        {items.map((_: any, index: number) => (
          <Paper key={index} withBorder p="sm" radius="sm">
            <Group justify="space-between" mb="xs">
              <Text size="xs" c="dimmed" fw={500}>
                #{index + 1}
              </Text>
              <ActionIcon
                size="sm"
                color="red"
                variant="subtle"
                onClick={() => form.removeListItem(name, index)}
              >
                <IconTrash size={14} />
              </ActionIcon>
            </Group>
            <Stack gap="xs">
              {field.itemFields!.map((sf) => {
                const itemPath = `${name}.${index}.${sf.name}`;
                const _subVariant = sf.variant || getDefaultVariant(sf);

                if (sf.enumValues && sf.enumValues.length > 0) {
                  return (
                    <Select
                      key={itemPath}
                      label={sf.label}
                      required={sf.isRequired}
                      data={sf.enumValues.map((v) => ({ value: v, label: v }))}
                      clearable={sf.isNullable}
                      {...form.getInputProps(itemPath)}
                    />
                  );
                }
                if (sf.type === 'object') {
                  return (
                    <Textarea
                      key={itemPath}
                      label={sf.label}
                      required={sf.isRequired}
                      placeholder="{}"
                      minRows={2}
                      styles={{ input: { fontFamily: 'monospace', fontSize: '13px' } }}
                      {...form.getInputProps(itemPath)}
                    />
                  );
                }
                if (sf.type === 'binary') {
                  const itemApiUrl =
                    (typeof window !== 'undefined' && (import.meta as any).env?.VITE_API_URL) || '';
                  const itemBv = getByPath(
                    form.getValues() as Record<string, any>,
                    itemPath,
                  ) as BinaryFormValue | null;
                  return (
                    <BinaryFieldEditor
                      key={itemPath}
                      label={sf.label}
                      required={sf.isRequired}
                      value={itemBv}
                      onChange={(val) => form.setFieldValue(itemPath as any, val as any)}
                      apiUrl={itemApiUrl}
                    />
                  );
                }
                if (sf.type === 'boolean') {
                  return (
                    <Switch
                      key={itemPath}
                      label={sf.label}
                      {...form.getInputProps(itemPath, { type: 'checkbox' })}
                    />
                  );
                }
                if (sf.type === 'number') {
                  return (
                    <NumberInput
                      key={itemPath}
                      label={sf.label}
                      required={sf.isRequired}
                      {...form.getInputProps(itemPath)}
                    />
                  );
                }
                if (sf.isArray && sf.type === 'string') {
                  return (
                    <TextInput
                      key={itemPath}
                      label={`${sf.label} (comma-separated)`}
                      required={sf.isRequired}
                      placeholder="value1, value2, value3"
                      {...form.getInputProps(itemPath)}
                    />
                  );
                }
                return (
                  <TextInput
                    key={itemPath}
                    label={sf.label}
                    required={sf.isRequired}
                    {...form.getInputProps(itemPath)}
                  />
                );
              })}
            </Stack>
          </Paper>
        ))}
      </Stack>
    );
  }

  const effectiveVariant = variant || getDefaultVariant(field);

  // Union
  if (type === 'union' && field.unionMeta) {
    return (
      <UnionFieldRenderer
        field={field}
        unionMeta={field.unionMeta}
        form={form}
        simpleUnionTypes={simpleUnionTypes}
        setSimpleUnionTypes={setSimpleUnionTypes}
      />
    );
  }

  // Binary
  if (type === 'binary') {
    const apiUrl = (typeof window !== 'undefined' && (import.meta as any).env?.VITE_API_URL) || '';
    const binaryVal = form.getValues()[name as string] as unknown as BinaryFormValue | null;
    return (
      <BinaryFieldEditor
        key={key}
        label={label}
        required={isRequired}
        value={binaryVal}
        onChange={(val) => form.setFieldValue(name as any, val as any)}
        apiUrl={apiUrl}
      />
    );
  }

  // JSON / Object
  if (effectiveVariant.type === 'json' || type === 'object') {
    const jsonVariant = effectiveVariant as Extract<FieldVariant, { type: 'json' }>;
    return (
      <Textarea
        key={key}
        label={label}
        required={isRequired}
        placeholder="JSON object"
        minRows={3}
        maxRows={jsonVariant.height ? jsonVariant.height / 24 : undefined}
        {...form.getInputProps(name)}
      />
    );
  }

  // Markdown
  if (effectiveVariant.type === 'markdown') {
    const markdownVariant = effectiveVariant as Extract<FieldVariant, { type: 'markdown' }>;
    const inputProps = form.getInputProps(name);
    return (
      <MarkdownEditor
        key={key}
        label={label}
        required={isRequired}
        value={inputProps.value ?? ''}
        onChange={(val) => form.setFieldValue(name as any, val as any)}
        height={markdownVariant.height ?? 300}
        error={inputProps.error as string | undefined}
      />
    );
  }

  // Array text (comma-separated)
  if (isArray && type === 'string' && !(field.ref && field.ref.type === 'resource_id')) {
    return (
      <TextInput
        key={key}
        label={`${label} (comma-separated)`}
        required={isRequired}
        placeholder="value1, value2, value3"
        {...form.getInputProps(name)}
      />
    );
  }

  // Tags
  if (effectiveVariant.type === 'tags') {
    return (
      <TextInput
        key={key}
        label={label}
        required={isRequired}
        placeholder="tag1, tag2, tag3"
        {...form.getInputProps(name)}
      />
    );
  }

  // Select
  if (effectiveVariant.type === 'select') {
    const selectVariant = effectiveVariant as Extract<FieldVariant, { type: 'select' }>;
    const inputProps = form.getInputProps(name);
    return (
      <Select
        key={key}
        label={label}
        required={isRequired}
        data={selectVariant.options || []}
        clearable={field.isNullable}
        {...inputProps}
        onChange={(val) => form.setFieldValue(name as any, (val ?? null) as any)}
      />
    );
  }

  // Boolean - Checkbox
  if (type === 'boolean' && effectiveVariant.type === 'checkbox') {
    return <Checkbox key={key} label={label} {...form.getInputProps(name, { type: 'checkbox' })} />;
  }

  // Boolean - Switch
  if (type === 'boolean') {
    return <Switch key={key} label={label} {...form.getInputProps(name, { type: 'checkbox' })} />;
  }

  // Date
  if (type === 'date' || effectiveVariant.type === 'date') {
    return (
      <DateTimePicker
        key={key}
        label={label}
        required={isRequired}
        valueFormat="YYYY-MM-DD HH:mm:ss"
        clearable
        {...form.getInputProps(name)}
      />
    );
  }

  // Number - Slider
  if (type === 'number' && effectiveVariant.type === 'slider') {
    const sliderVariant = effectiveVariant as Extract<FieldVariant, { type: 'slider' }>;
    return (
      <NumberInput
        key={key}
        label={label}
        required={isRequired}
        min={sliderVariant.sliderMin}
        max={sliderVariant.sliderMax}
        step={sliderVariant.step}
        {...form.getInputProps(name)}
      />
    );
  }

  // Number
  if (type === 'number') {
    const numberVariant = effectiveVariant as Extract<FieldVariant, { type: 'number' }>;
    return (
      <NumberInput
        key={key}
        label={label}
        required={isRequired}
        min={numberVariant.min}
        max={numberVariant.max}
        step={numberVariant.step}
        {...form.getInputProps(name)}
      />
    );
  }

  // Textarea
  if (effectiveVariant.type === 'textarea') {
    const textareaVariant = effectiveVariant as Extract<FieldVariant, { type: 'textarea' }>;
    return (
      <Textarea
        key={key}
        label={label}
        required={isRequired}
        rows={textareaVariant.rows || 3}
        {...form.getInputProps(name)}
      />
    );
  }

  // Ref resource_id
  if (field.ref && field.ref.type === 'resource_id') {
    if (field.isArray) {
      return (
        <RefMultiSelect
          key={key}
          label={label}
          required={isRequired}
          fieldRef={field.ref}
          value={(form.getValues()[name as string] as string[] | undefined) ?? []}
          onChange={(val) => form.setFieldValue(name as any, val as any)}
          error={form.errors[name as string] as string | undefined}
        />
      );
    }
    return (
      <RefSelect
        key={key}
        label={label}
        required={isRequired}
        fieldRef={field.ref}
        value={form.getValues()[name as string] as string | null}
        onChange={(val) => form.setFieldValue(name as any, val as any)}
        error={form.errors[name as string] as string | undefined}
        clearable={field.isNullable}
      />
    );
  }

  // Ref revision_id
  if (field.ref && field.ref.type === 'revision_id') {
    if (field.isArray) {
      return (
        <RefRevisionMultiSelect
          key={key}
          label={label}
          required={isRequired}
          fieldRef={field.ref}
          value={(form.getValues()[name as string] as string[] | undefined) ?? []}
          onChange={(val) => form.setFieldValue(name as any, val as any)}
          error={form.errors[name as string] as string | undefined}
        />
      );
    }
    return (
      <RefRevisionSelect
        key={key}
        label={label}
        required={isRequired}
        fieldRef={field.ref}
        value={form.getValues()[name as string] as string | null}
        onChange={(val) => form.setFieldValue(name as any, val as any)}
        error={form.errors[name as string] as string | undefined}
        clearable={field.isNullable}
      />
    );
  }

  // Default: text
  return <TextInput key={key} label={label} required={isRequired} {...form.getInputProps(name)} />;
}
