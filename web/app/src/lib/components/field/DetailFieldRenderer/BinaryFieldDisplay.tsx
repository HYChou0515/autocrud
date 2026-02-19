/**
 * BinaryFieldDisplay — Read-only display for binary/blob fields.
 *
 * Shows an image preview for image content types,
 * or a file download link with type + size badge for other types.
 */

import { Anchor, Group, Image, Stack, Text } from '@mantine/core';
import { IconDownload } from '@tabler/icons-react';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

/** Build a URL to fetch a blob by file_id */
function getBlobUrl(fileId: string): string {
  return `${API_BASE_URL}/blobs/${fileId}`;
}

/** Check if content_type is an image type */
function isImageContentType(contentType: string | undefined): boolean {
  return !!contentType && contentType.startsWith('image/');
}

/** Format byte size to human-readable string */
export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export interface BinaryFieldDisplayProps {
  value: Record<string, unknown>;
}

export function BinaryFieldDisplay({ value }: BinaryFieldDisplayProps) {
  const fileId = String(value.file_id);
  const contentType = value.content_type as string | undefined;
  const size = value.size as number;
  const blobUrl = getBlobUrl(fileId);

  if (isImageContentType(contentType)) {
    return (
      <Stack gap="xs">
        <Image
          src={blobUrl}
          alt={fileId}
          maw={400}
          mah={300}
          fit="contain"
          radius="sm"
          style={{ border: '1px solid var(--mantine-color-gray-3)' }}
        />
        <Group gap="xs">
          <Text size="xs" c="dimmed">
            {contentType} · {formatSize(size)}
          </Text>
          <Anchor href={blobUrl} target="_blank" size="xs">
            <Group gap={4}>
              <IconDownload size={12} />
              Download
            </Group>
          </Anchor>
        </Group>
      </Stack>
    );
  }

  return (
    <Group gap="xs">
      <Text size="sm">
        📎 {contentType || 'File'} ({formatSize(size)})
      </Text>
      <Anchor href={blobUrl} target="_blank" size="sm">
        <Group gap={4}>
          <IconDownload size={14} />
          Download
        </Group>
      </Anchor>
    </Group>
  );
}
