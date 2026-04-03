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
  Fieldset,
  Progress,
} from '@mantine/core';
import { IconLayersSubtract, IconX } from '@tabler/icons-react';
import type { ResourceConfig } from '../../resources';
import {
  getByPath,
  collapseFieldToJson,
  groupFieldsByParent,
} from '@/autocrud/lib/utils/formUtils';
import { useResourceForm } from './useResourceForm';
import { FieldRenderer } from '../field/FormFieldRenderer';
import { formatBytes, formatDuration } from '../../hooks/useBlobUpload';

export interface ResourceFormProps<T> {
  config: ResourceConfig<T>;
  initialValues?: Partial<T>;
  onSubmit: (values: T) => void | Promise<void>;
  onCancel?: () => void;
  submitLabel?: string;
  /** Whether a mutation is currently in-flight — shows loading on the submit button. */
  submitting?: boolean;
  /** Ref exposing form methods for external error handling (e.g. 409 unique conflict) */
  formRef?: React.MutableRefObject<ResourceFormHandle | null>;
}

/** Handle exposed by ResourceForm via formRef for external error handling */
export interface ResourceFormHandle {
  setFieldError: (field: string, message: string) => void;
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
  submitting,
  formRef,
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
    blobUploadState,
    cancelBlobUpload,
  } = useResourceForm({ config, initialValues, onSubmit });

  const isUploadingBlobs = blobUploadState.isUploading;

  // Expose form handle for external error setting (e.g. 409 unique constraint)
  if (formRef) {
    formRef.current = {
      setFieldError: (field: string, message: string) => {
        form.setFieldError(field, message);
      },
    };
  }

  /** Render a collapsed group as a JSON textarea */
  const renderCollapsedGroup = (group: { path: string; label: string }) => {
    const rawVal = getByPath(form.getValues() as Record<string, any>, group.path);
    const field = config.fields.find((f) => f.name === group.path);
    const strVal = collapseFieldToJson(rawVal, field ?? { name: group.path, label: group.label });
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
            {(() => {
              const fieldGroups = groupFieldsByParent(visibleFields);

              // Partition collapsed groups: those that belong inside a visible
              // fieldset vs. top-level ones rendered at the bottom.
              const nestedCollapsedPaths = new Set<string>();
              const getChildCollapsed = (parentPath: string | null) => {
                if (parentPath == null) return [];
                return collapsedGroups.filter((cg) => {
                  const lastDot = cg.path.lastIndexOf('.');
                  const cgParent = lastDot > 0 ? cg.path.substring(0, lastDot) : null;
                  if (cgParent === parentPath) {
                    nestedCollapsedPaths.add(cg.path);
                    return true;
                  }
                  return false;
                });
              };

              const renderGroup = (group: (typeof fieldGroups)[number]): React.ReactNode => {
                const renderedFields = group.fields.map((field) => (
                  <FieldRenderer
                    key={field.name}
                    field={field}
                    form={form}
                    simpleUnionTypes={simpleUnionTypes}
                    setSimpleUnionTypes={setSimpleUnionTypes}
                  />
                ));
                const renderedChildren = group.children.map((child) => renderGroup(child));
                const childCollapsed = getChildCollapsed(group.parentPath);
                const renderedCollapsed = childCollapsed.map(renderCollapsedGroup);

                if (group.parentPath != null) {
                  return (
                    <Fieldset
                      key={`group-${group.parentPath}`}
                      legend={group.parentLabel ?? group.parentPath}
                    >
                      <Stack gap="md">
                        {renderedFields}
                        {renderedChildren}
                        {renderedCollapsed}
                      </Stack>
                    </Fieldset>
                  );
                }
                // Top-level fields: render directly as a flat list (no wrapper needed)
                return [...renderedFields, ...renderedChildren, ...renderedCollapsed];
              };

              // Render field groups first (this also populates nestedCollapsedPaths)
              const renderedGroups = fieldGroups.flatMap((group) => renderGroup(group));
              // Then render remaining top-level collapsed groups
              const topLevelCollapsed = collapsedGroups
                .filter((cg) => !nestedCollapsedPaths.has(cg.path))
                .map(renderCollapsedGroup);

              return [...renderedGroups, ...topLevelCollapsed];
            })()}
            {/* ── Blob upload progress (shown during deferred uploads at submit time) ── */}
            {isUploadingBlobs && (
              <Alert variant="light" color="blue" p="sm">
                <Stack gap={4}>
                  <Group justify="space-between" align="center">
                    <Text size="sm" fw={500}>
                      Uploading files ({blobUploadState.completedFiles}/{blobUploadState.totalFiles}
                      )
                    </Text>
                    <Tooltip label="Cancel upload">
                      <Button
                        variant="subtle"
                        color="red"
                        size="compact-xs"
                        onClick={cancelBlobUpload}
                        leftSection={<IconX size={14} />}
                      >
                        Cancel
                      </Button>
                    </Tooltip>
                  </Group>
                  <Progress value={blobUploadState.progress.percent} size="sm" animated />
                  <Group justify="space-between">
                    <Text size="xs" c="dimmed">
                      {blobUploadState.currentFileName && (
                        <>Uploading: {blobUploadState.currentFileName} — </>
                      )}
                      {formatBytes(blobUploadState.progress.loaded)} /{' '}
                      {formatBytes(blobUploadState.progress.total)} (
                      {blobUploadState.progress.percent}%)
                    </Text>
                    <Text size="xs" c="dimmed">
                      Elapsed: {formatDuration(blobUploadState.progress.elapsed)}
                      {blobUploadState.progress.eta != null && (
                        <> — ETA: {formatDuration(blobUploadState.progress.eta)}</>
                      )}
                    </Text>
                  </Group>
                </Stack>
              </Alert>
            )}
            {blobUploadState.error && !isUploadingBlobs && (
              <Alert color="red" variant="light">
                Upload failed: {blobUploadState.error}
              </Alert>
            )}
            <Group justify="flex-end" mt="md">
              {onCancel && (
                <Button variant="subtle" onClick={onCancel}>
                  Cancel
                </Button>
              )}
              <Button type="submit" loading={submitting || isUploadingBlobs}>
                {submitLabel}
              </Button>
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
            <Button onClick={handleJsonSubmit} loading={submitting || isUploadingBlobs}>
              {submitLabel}
            </Button>
          </Group>
        </Stack>
      )}
    </Stack>
  );
}
