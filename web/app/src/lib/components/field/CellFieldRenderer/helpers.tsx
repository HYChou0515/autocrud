/**
 * CellFieldRenderer helpers — shared utility functions for table cell rendering.
 *
 * These were originally inline in ResourceTable.tsx. Extracted here so the
 * CELL_RENDERERS registry stays concise and each helper can be tested independently.
 */

import { Code, Group, Image, Text, Tooltip } from '@mantine/core';
import {
  IconFile,
  IconFileCode,
  IconFileText,
  IconFileZip,
  IconMusic,
  IconPhoto,
  IconVideo,
} from '@tabler/icons-react';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Size threshold (in bytes) below which images are shown as inline thumbnails. */
export const INLINE_IMAGE_MAX_SIZE = 512 * 1024; // 512 KB

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

// ---------------------------------------------------------------------------
// Pure helpers
// ---------------------------------------------------------------------------

export function getBlobUrl(fileId: string): string {
  return `${API_BASE_URL}/blobs/${fileId}`;
}

export function isImageContentType(ct: string | undefined): boolean {
  return !!ct && ct.startsWith('image/');
}

export function formatBinarySize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// ---------------------------------------------------------------------------
// Icon helper
// ---------------------------------------------------------------------------

/** Return an appropriate icon component for a given MIME content type. */
export function getContentTypeIcon(contentType: string | undefined, size = 16) {
  if (!contentType) return <IconFile size={size} />;
  if (contentType.startsWith('image/'))
    return <IconPhoto size={size} color="var(--mantine-color-teal-6)" />;
  if (contentType.startsWith('video/'))
    return <IconVideo size={size} color="var(--mantine-color-grape-6)" />;
  if (contentType.startsWith('audio/'))
    return <IconMusic size={size} color="var(--mantine-color-orange-6)" />;
  if (contentType.startsWith('text/'))
    return <IconFileText size={size} color="var(--mantine-color-blue-6)" />;
  if (contentType.includes('pdf'))
    return <IconFileText size={size} color="var(--mantine-color-red-6)" />;
  if (
    contentType.includes('zip') ||
    contentType.includes('tar') ||
    contentType.includes('gzip') ||
    contentType.includes('compressed')
  )
    return <IconFileZip size={size} color="var(--mantine-color-yellow-6)" />;
  if (
    contentType.includes('json') ||
    contentType.includes('xml') ||
    contentType.includes('javascript')
  )
    return <IconFileCode size={size} color="var(--mantine-color-violet-6)" />;
  return <IconFile size={size} />;
}

// ---------------------------------------------------------------------------
// Cell renderers (JSX helpers)
// ---------------------------------------------------------------------------

/**
 * Render a binary field value in a table cell.
 * Shows inline image thumbnail for small images, or icon + type + size for others.
 */
export function renderBinaryCell(value: Record<string, unknown>): React.ReactNode {
  const fileId = value.file_id as string | undefined;
  const contentType = value.content_type as string | undefined;
  const size = (value.size as number) || 0;

  // For small images, show inline thumbnail
  if (fileId && isImageContentType(contentType) && size <= INLINE_IMAGE_MAX_SIZE) {
    const blobUrl = getBlobUrl(fileId);
    return (
      <Tooltip label={`${contentType} · ${formatBinarySize(size)}`} withArrow>
        <Image
          src={blobUrl}
          maw={80}
          mah={48}
          fit="contain"
          radius="sm"
          style={{ cursor: 'pointer' }}
        />
      </Tooltip>
    );
  }

  // Otherwise show icon + info
  const sizeStr = formatBinarySize(size);
  const label = contentType || 'File';

  return (
    <Tooltip
      label={fileId ? `${label} · ${sizeStr} — click to download` : `${label} · ${sizeStr}`}
      withArrow
    >
      <Group gap={4} wrap="nowrap" style={{ cursor: fileId ? 'pointer' : 'default' }}>
        {getContentTypeIcon(contentType, 16)}
        <Text size="xs" c="dimmed" truncate style={{ maxWidth: 120 }}>
          {sizeStr}
        </Text>
      </Group>
    </Tooltip>
  );
}

/**
 * Render an object value as a compact preview with hover tooltip showing full JSON.
 */
export function renderObjectPreview(value: Record<string, unknown>): React.ReactNode {
  const keys = Object.keys(value);

  if (keys.length === 0) {
    return (
      <Text c="dimmed" size="sm">
        {'{}'}
      </Text>
    );
  }

  const firstKey = keys[0];
  const firstValue = value[firstKey];
  const previewText =
    keys.length === 1
      ? `${firstKey}: ${JSON.stringify(firstValue)}`
      : `${firstKey}: ${JSON.stringify(firstValue)}, +${keys.length - 1} more`;

  const shortPreview = previewText.length > 40 ? previewText.slice(0, 37) + '...' : previewText;

  return (
    <Tooltip
      label={
        <Code block style={{ maxWidth: '400px', maxHeight: '300px', overflow: 'auto' }}>
          {JSON.stringify(value, null, 2)}
        </Code>
      }
      position="bottom-start"
      withArrow
      withinPortal
    >
      <Group gap={4} wrap="nowrap" style={{ cursor: 'help' }}>
        <IconFileCode size={14} />
        <Text size="sm" style={{ fontFamily: 'monospace' }}>
          {shortPreview}
        </Text>
      </Group>
    </Tooltip>
  );
}
