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
import type { BinaryFormValue } from '@/lib/utils/formUtils';

/** Binary field editor — file upload or URL input */
export function BinaryFieldEditor({
  label,
  required,
  value,
  onChange,
  apiUrl,
}: {
  label: string;
  required?: boolean;
  value: BinaryFormValue | null;
  onChange: (val: BinaryFormValue) => void;
  apiUrl?: string;
}) {
  const mode = value?._mode ?? 'empty';
  const activeMode = mode === 'existing' || mode === 'empty' ? 'file' : mode;

  const handleModeChange = (m: string) => {
    if (m === 'file') onChange({ _mode: 'file', file: null });
    else onChange({ _mode: 'url', url: '' });
  };

  const handleFileChange = (file: File | null) => {
    onChange({ _mode: 'file', file });
  };

  const handleUrlChange = (url: string) => {
    onChange({ _mode: 'url', url });
  };

  const handleClear = () => {
    onChange({ _mode: 'empty' });
  };

  const blobUrl = value?.file_id && apiUrl ? `${apiUrl}/blobs/${value.file_id}` : null;

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
        <FileInput
          placeholder="Choose file..."
          value={value?._mode === 'file' ? (value.file ?? null) : null}
          onChange={handleFileChange}
          clearable
        />
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
