/**
 * BinaryArrayFieldRenderer — Renders a list of binary fields for
 * `isArray: true, type: 'binary'` fields (e.g. `List[bytes]` backend fields).
 *
 * Each array item is an independent `BinaryFieldEditor`. Files are NOT uploaded
 * eagerly — the selected File objects are stored in form state and uploaded
 * in bulk when the form is submitted.
 */

import { Stack, Group, Text, Button, ActionIcon, Paper } from '@mantine/core';
import { IconTrash, IconPlus } from '@tabler/icons-react';
import type { UseFormReturnType } from '@mantine/form';
import type { ResourceField } from '../../../resources';
import { BinaryFieldEditor } from './BinaryFieldEditor';
import { getByPath, safeGetArrayItems, type BinaryFormValue } from '@/autocrud/lib/utils/formUtils';

interface BinaryArrayFieldRendererProps {
  field: ResourceField;
  form: UseFormReturnType<any>;
}

const EMPTY_BINARY: BinaryFormValue = { _mode: 'empty' };

export function BinaryArrayFieldRenderer({ field, form }: BinaryArrayFieldRendererProps) {
  const { name, label, isRequired, isNullable } = field;
  const rawItems = getByPath(form.getValues() as Record<string, any>, name);
  const items = safeGetArrayItems(rawItems);

  return (
    <Stack gap="xs">
      <Group justify="space-between" align="center">
        <Text fw={500} size="sm">
          {label}
          {isRequired && !isNullable && (
            <span style={{ color: 'var(--mantine-color-red-6)' }}> *</span>
          )}
        </Text>
        <Button
          size="compact-xs"
          variant="light"
          leftSection={<IconPlus size={14} />}
          onClick={() => form.insertListItem(name, EMPTY_BINARY)}
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
        const itemPath = `${name}.${index}`;
        const itemBv = getByPath(
          form.getValues() as Record<string, any>,
          itemPath,
        ) as BinaryFormValue | null;

        return (
          <Paper key={index} withBorder p="sm" radius="sm">
            <Group justify="space-between" mb="xs">
              <Text size="xs" c="dimmed" fw={500}>
                #{index + 1}
              </Text>
              <ActionIcon
                aria-label="Remove"
                size="sm"
                color="red"
                variant="subtle"
                onClick={() => form.removeListItem(name, index)}
              >
                <IconTrash size={14} />
              </ActionIcon>
            </Group>
            <BinaryFieldEditor
              label={label}
              required={isRequired && !isNullable}
              value={itemBv}
              onChange={(val) => form.setFieldValue(itemPath as any, val as any)}
            />
          </Paper>
        );
      })}
    </Stack>
  );
}
