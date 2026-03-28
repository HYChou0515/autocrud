import {
  TextInput,
  Stack,
  Group,
  FileInput,
  SegmentedControl,
  Text,
  Tooltip,
  ActionIcon,
} from '@mantine/core';
import { IconLink, IconX } from '@tabler/icons-react';
import type { BinaryFormValue } from '@/autocrud/lib/utils/formUtils';
import { getBlobUrl } from '../../../client';
import { formatBytes } from '../../../hooks/useBlobUpload';

/**
 * Binary field editor — deferred file upload or URL input.
 *
 * Files are NOT uploaded eagerly. Instead, the selected File object is
 * stored in form state and uploaded in bulk when the form is submitted.
 * This provides a better UX: users can fill out the entire form before
 * any network activity begins.
 */
export function BinaryFieldEditor({
  label,
  required,
  value,
  onChange,
}: {
  label: string;
  required?: boolean;
  value: BinaryFormValue | null;
  onChange: (val: BinaryFormValue) => void;
}) {
  const mode = value?._mode ?? 'empty';
  const activeMode = mode === 'existing' || mode === 'empty' ? 'file' : mode;

  const handleModeChange = (m: string) => {
    if (m === 'file') onChange({ _mode: 'file', file: null });
    else onChange({ _mode: 'url', url: '' });
  };

  const handleFileChange = (file: File | null) => {
    if (!file) {
      onChange({ _mode: 'file', file: null });
      return;
    }
    // Store the File object — upload happens at form submit time
    onChange({ _mode: 'file', file });
  };

  const handleUrlChange = (url: string) => {
    onChange({ _mode: 'url', url });
  };

  const handleClear = () => {
    onChange({ _mode: 'empty' });
  };

  const blobUrl = value?.file_id ? getBlobUrl(value.file_id) : null;

  return (
    <Stack gap={4}>
      <Group gap="xs" align="flex-end">
        <Text size="sm" fw={500}>
          {label}
          {required && <span style={{ color: 'var(--mantine-color-red-6)' }}> *</span>}
        </Text>
        {mode === 'existing' && blobUrl && (
          <Text size="xs" c="dimmed">
            (current:{' '}
            <a href={blobUrl} target="_blank" rel="noreferrer">
              {value?.content_type}
            </a>
            {value?.size != null && `, ${formatBytes(value.size)}`})
          </Text>
        )}
      </Group>
      <Group gap="xs">
        <SegmentedControl
          size="xs"
          value={activeMode}
          onChange={handleModeChange}
          data={[
            { label: 'Upload', value: 'file' },
            { label: 'URL', value: 'url' },
          ]}
        />
        {mode !== 'empty' && (
          <Tooltip label="Clear">
            <ActionIcon variant="subtle" color="gray" size="sm" onClick={handleClear}>
              <IconX size={14} />
            </ActionIcon>
          </Tooltip>
        )}
      </Group>
      {activeMode === 'file' ? (
        <>
          <FileInput
            placeholder="Choose file..."
            value={value?._mode === 'file' ? (value.file ?? null) : null}
            onChange={handleFileChange}
            clearable
          />
          {value?._mode === 'file' && value.file && (
            <Text size="xs" c="dimmed">
              Selected: {value.file.name} ({formatBytes(value.file.size)}) — will upload on submit
            </Text>
          )}
        </>
      ) : (
        <TextInput
          placeholder="https://example.com/image.png"
          leftSection={<IconLink size={14} />}
          value={value?._mode === 'url' ? (value.url ?? '') : ''}
          onChange={(e) => handleUrlChange(e.currentTarget.value)}
        />
      )}
    </Stack>
  );
}
