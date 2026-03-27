import {
  TextInput,
  Stack,
  Group,
  FileInput,
  SegmentedControl,
  Text,
  Tooltip,
  ActionIcon,
  Progress,
} from '@mantine/core';
import { IconLink, IconUpload, IconX } from '@tabler/icons-react';
import type { BinaryFormValue } from '@/autocrud/lib/utils/formUtils';
import { getBlobUrl } from '../../../client';
import { useBlobUpload } from '../../../hooks/useBlobUpload';

/** Binary field editor — file upload (with chunked upload + progress bar) or URL input */
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
  const { upload, cancel, progress, status, error, reset } = useBlobUpload();

  const isUploading = status === 'uploading' || status === 'finalizing';

  const handleModeChange = (m: string) => {
    if (isUploading) return;
    if (m === 'file') onChange({ _mode: 'file', file: null });
    else onChange({ _mode: 'url', url: '' });
  };

  const handleFileChange = async (file: File | null) => {
    if (!file) {
      onChange({ _mode: 'file', file: null });
      return;
    }

    // Start eager upload immediately
    onChange({ _mode: 'file', file });
    const result = await upload(file);

    if (result) {
      // Upload complete — switch to 'existing' mode with the file_id
      onChange({
        _mode: 'existing',
        file_id: result.file_id,
        content_type: result.content_type,
        size: result.size,
      });
    }
  };

  const handleUrlChange = (url: string) => {
    onChange({ _mode: 'url', url });
  };

  const handleClear = () => {
    if (isUploading) {
      cancel();
    }
    reset();
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
            {value?.size != null && `, ${(value.size / 1024).toFixed(1)} KB`})
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
          disabled={isUploading}
        />
        {(mode !== 'empty' || isUploading) && (
          <Tooltip label={isUploading ? 'Cancel upload' : 'Clear'}>
            <ActionIcon
              variant="subtle"
              color={isUploading ? 'red' : 'gray'}
              size="sm"
              onClick={handleClear}
            >
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
            disabled={isUploading}
            leftSection={isUploading ? <IconUpload size={14} /> : undefined}
          />
          {isUploading && (
            <Stack gap={2}>
              <Progress
                value={progress.percent}
                size="sm"
                animated
                color={status === 'finalizing' ? 'yellow' : 'blue'}
              />
              <Text size="xs" c="dimmed">
                {status === 'finalizing'
                  ? 'Finalizing...'
                  : `Uploading... ${formatBytes(progress.loaded)} / ${formatBytes(progress.total)} (${progress.percent}%)`}
              </Text>
            </Stack>
          )}
          {status === 'done' && (
            <Text size="xs" c="green">
              Upload complete ✓
            </Text>
          )}
          {status === 'error' && (
            <Text size="xs" c="red">
              Upload failed: {error}
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

/** Format bytes into human-readable string */
function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
}
