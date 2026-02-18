import {
  NumberInput,
  Textarea,
  Button,
  Stack,
  Group,
  SegmentedControl,
  Alert,
  Text,
  Tooltip,
} from '@mantine/core';
import { IconLayersSubtract } from '@tabler/icons-react';
import type { ResourceConfig } from '../resources';
import { safeGetJsonString } from '@/lib/utils/formUtils';
import { useResourceForm } from './useResourceForm';
import { FieldRenderer } from './FieldRenderer';

export interface ResourceFormProps<T> {
  config: ResourceConfig<T>;
  initialValues?: Partial<T>;
  onSubmit: (values: T) => void | Promise<void>;
  onCancel?: () => void;
  submitLabel?: string;
}

/**
 * Generic resource form with auto-generated fields based on config.
 * All logic delegated to useResourceForm hook; rendering to FieldRenderer.
 */
export function ResourceForm<T extends Record<string, any>>({
  config,
  initialValues = {},
  onSubmit,
  onCancel,
  submitLabel = 'Submit',
}: ResourceFormProps<T>) {
  const {
    form,
    editMode,
    jsonText,
    setJsonText,
    jsonError,
    setJsonError,
    handleSwitchToJson,
    handleSwitchToForm,
    handleJsonSubmit,
    maxAvailableDepth,
    formDepth,
    setFormDepth,
    visibleFields,
    collapsedGroups,
    simpleUnionTypes,
    setSimpleUnionTypes,
    handleSubmit,
  } = useResourceForm({ config, initialValues, onSubmit });

  /** Render a collapsed group as a JSON textarea */
  const renderCollapsedGroup = (group: { path: string; label: string }) => {
    const rawVal = (form.getValues() as Record<string, any>)[group.path];
    const strVal = safeGetJsonString(rawVal);
    return (
      <Textarea
        key={`collapsed-${group.path}`}
        label={group.label}
        placeholder="{}"
        minRows={4}
        autosize
        styles={{ input: { fontFamily: 'monospace', fontSize: '13px' } }}
        {...form.getInputProps(group.path)}
        value={strVal}
      />
    );
  };

  return (
    <Stack gap="md">
      <Group justify="space-between" align="center">
        <SegmentedControl
          size="xs"
          value={editMode}
          onChange={(value) => {
            if (value === 'json') handleSwitchToJson();
            else handleSwitchToForm();
          }}
          data={[
            { label: 'Form', value: 'form' },
            { label: 'JSON', value: 'json' },
          ]}
        />
        {editMode === 'form' && maxAvailableDepth > 1 && (
          <Tooltip
            label="Form field expansion depth: lower values collapse nested objects into JSON editors"
            withArrow
          >
            <Group gap={4}>
              <IconLayersSubtract size={16} />
              <Text size="xs" c="dimmed">
                Depth
              </Text>
              <NumberInput
                size="xs"
                value={formDepth}
                onChange={(val) => setFormDepth(typeof val === 'number' ? val : 1)}
                min={1}
                max={maxAvailableDepth}
                step={1}
                w={60}
                styles={{ input: { textAlign: 'center' } }}
              />
            </Group>
          </Tooltip>
        )}
      </Group>

      {editMode === 'form' && (
        <form onSubmit={form.onSubmit(handleSubmit)}>
          <Stack gap="md">
            {visibleFields.map((field) => (
              <FieldRenderer
                key={field.name}
                field={field}
                form={form}
                simpleUnionTypes={simpleUnionTypes}
                setSimpleUnionTypes={setSimpleUnionTypes}
              />
            ))}
            {collapsedGroups.map(renderCollapsedGroup)}
            <Group justify="flex-end" mt="md">
              {onCancel && (
                <Button variant="subtle" onClick={onCancel}>
                  Cancel
                </Button>
              )}
              <Button type="submit">{submitLabel}</Button>
            </Group>
          </Stack>
        </form>
      )}

      {editMode === 'json' && (
        <Stack gap="md">
          {jsonError && (
            <Alert color="red" variant="light">
              {jsonError}
            </Alert>
          )}
          <Textarea
            placeholder='{"field": "value"}'
            value={jsonText}
            onChange={(e) => {
              setJsonText(e.currentTarget.value);
              setJsonError(null);
            }}
            minRows={10}
            autosize
            styles={{ input: { fontFamily: 'monospace', fontSize: '13px' } }}
          />
          <Group justify="flex-end" mt="md">
            {onCancel && (
              <Button variant="subtle" onClick={onCancel}>
                Cancel
              </Button>
            )}
            <Button onClick={handleJsonSubmit}>{submitLabel}</Button>
          </Group>
        </Stack>
      )}
    </Stack>
  );
}
