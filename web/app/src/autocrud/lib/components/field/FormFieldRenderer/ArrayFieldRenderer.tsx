/**
 * ArrayFieldRenderer — Renders an array of typed objects as
 * a repeatable list with per-item sub-fields.
 *
 * Extracted from FieldRenderer to keep each renderer focused.
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
  ActionIcon,
  Paper,
  TagsInput,
} from '@mantine/core';
import { DateTimePicker } from '@mantine/dates';
import { IconTrash, IconPlus } from '@tabler/icons-react';
import { useState } from 'react';
import type { UseFormReturnType } from '@mantine/form';
import type { ResourceField } from '../../../resources';
import { BinaryFieldEditor } from './BinaryFieldEditor';
import { UnionFieldRenderer } from './UnionFieldRenderer';
import {
  getByPath,
  getDefaultVariant,
  safeGetArrayItems,
  createEmptyItem,
  type BinaryFormValue,
} from '@/autocrud/lib/utils/formUtils';

interface ArrayFieldRendererProps {
  field: ResourceField;
  form: UseFormReturnType<any>;
}

/**
 * Wrapper component for rendering a nested union sub-field inside an array item.
 * Manages its own simpleUnionTypes state (needed for simple unions).
 */
function NestedUnionField({
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

export function ArrayFieldRenderer({ field, form }: ArrayFieldRendererProps) {
  const { name, label } = field;
  const rawItems = getByPath(form.getValues() as Record<string, any>, name);
  const items = safeGetArrayItems(rawItems);
  const emptyItemFactory = () => createEmptyItem(field.itemFields!);

  return (
    <Stack key={name} gap="xs">
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
                  <TagsInput
                    key={itemPath}
                    label={sf.label}
                    required={sf.isRequired}
                    placeholder="Type and press Enter"
                    clearable
                    {...form.getInputProps(itemPath)}
                  />
                );
              }
              // Date sub-field
              if (sf.type === 'date') {
                return (
                  <DateTimePicker
                    key={itemPath}
                    label={sf.label}
                    required={sf.isRequired}
                    valueFormat="YYYY-MM-DD HH:mm:ss"
                    clearable
                    {...form.getInputProps(itemPath)}
                  />
                );
              }
              // Nested union sub-field (recursive)
              if (sf.type === 'union' && sf.unionMeta) {
                return <NestedUnionField key={itemPath} field={sf} path={itemPath} form={form} />;
              }
              // Nested array of typed objects (recursive)
              if (sf.itemFields && sf.itemFields.length > 0) {
                return (
                  <ArrayFieldRenderer
                    key={itemPath}
                    field={{ ...sf, name: itemPath }}
                    form={form}
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
