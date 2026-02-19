/**
 * CellFieldRenderer/helpers — Unit tests for pure helper functions.
 */

import { describe, it, expect } from 'vitest';
import {
  formatBinarySize,
  isImageContentType,
  getBlobUrl,
  getContentTypeIcon,
  renderBinaryCell,
  renderObjectPreview,
  INLINE_IMAGE_MAX_SIZE,
} from './helpers';

describe('formatBinarySize', () => {
  it('formats bytes', () => {
    expect(formatBinarySize(0)).toBe('0 B');
    expect(formatBinarySize(512)).toBe('512 B');
    expect(formatBinarySize(1023)).toBe('1023 B');
  });

  it('formats kilobytes', () => {
    expect(formatBinarySize(1024)).toBe('1.0 KB');
    expect(formatBinarySize(1536)).toBe('1.5 KB');
    expect(formatBinarySize(1024 * 100)).toBe('100.0 KB');
  });

  it('formats megabytes', () => {
    expect(formatBinarySize(1024 * 1024)).toBe('1.0 MB');
    expect(formatBinarySize(1024 * 1024 * 2.5)).toBe('2.5 MB');
  });
});

describe('isImageContentType', () => {
  it('returns true for image/* types', () => {
    expect(isImageContentType('image/png')).toBe(true);
    expect(isImageContentType('image/jpeg')).toBe(true);
    expect(isImageContentType('image/svg+xml')).toBe(true);
  });

  it('returns false for non-image types', () => {
    expect(isImageContentType('text/plain')).toBe(false);
    expect(isImageContentType('application/json')).toBe(false);
    expect(isImageContentType(undefined)).toBe(false);
    expect(isImageContentType('')).toBe(false);
  });
});

describe('getBlobUrl', () => {
  it('builds URL with file id', () => {
    const url = getBlobUrl('abc123');
    expect(url).toContain('/blobs/abc123');
  });
});

describe('getContentTypeIcon', () => {
  it('returns icon for undefined content type', () => {
    const icon = getContentTypeIcon(undefined);
    expect(icon).toBeTruthy();
  });

  it('returns icon for image/*', () => {
    expect(getContentTypeIcon('image/png')).toBeTruthy();
  });

  it('returns icon for video/*', () => {
    expect(getContentTypeIcon('video/mp4')).toBeTruthy();
  });

  it('returns icon for audio/*', () => {
    expect(getContentTypeIcon('audio/mpeg')).toBeTruthy();
  });

  it('returns icon for text/*', () => {
    expect(getContentTypeIcon('text/plain')).toBeTruthy();
  });

  it('returns icon for pdf', () => {
    expect(getContentTypeIcon('application/pdf')).toBeTruthy();
  });

  it('returns icon for zip/tar/gzip/compressed', () => {
    expect(getContentTypeIcon('application/zip')).toBeTruthy();
    expect(getContentTypeIcon('application/x-tar')).toBeTruthy();
    expect(getContentTypeIcon('application/gzip')).toBeTruthy();
    expect(getContentTypeIcon('application/x-compressed')).toBeTruthy();
  });

  it('returns icon for json/xml/javascript', () => {
    expect(getContentTypeIcon('application/json')).toBeTruthy();
    expect(getContentTypeIcon('application/xml')).toBeTruthy();
    expect(getContentTypeIcon('application/javascript')).toBeTruthy();
  });

  it('returns fallback icon for unknown types', () => {
    expect(getContentTypeIcon('application/octet-stream')).toBeTruthy();
  });

  it('accepts custom size', () => {
    const icon = getContentTypeIcon('image/png', 24);
    expect(icon).toBeTruthy();
  });
});

describe('renderBinaryCell', () => {
  it('renders image thumbnail for small images with file_id', () => {
    const result = renderBinaryCell({
      file_id: 'abc',
      content_type: 'image/png',
      size: 1024,
    });
    expect(result).toBeTruthy();
  });

  it('renders icon for large images', () => {
    const result = renderBinaryCell({
      file_id: 'abc',
      content_type: 'image/png',
      size: INLINE_IMAGE_MAX_SIZE + 1,
    });
    expect(result).toBeTruthy();
  });

  it('renders icon for non-image files', () => {
    const result = renderBinaryCell({
      file_id: 'abc',
      content_type: 'application/pdf',
      size: 2048,
    });
    expect(result).toBeTruthy();
  });

  it('renders without file_id', () => {
    const result = renderBinaryCell({
      content_type: 'text/plain',
      size: 100,
    });
    expect(result).toBeTruthy();
  });

  it('renders with missing content_type', () => {
    const result = renderBinaryCell({
      file_id: 'abc',
      size: 100,
    });
    expect(result).toBeTruthy();
  });
});

describe('renderObjectPreview', () => {
  it('renders empty object as {}', () => {
    const result = renderObjectPreview({});
    expect(result).toBeTruthy();
  });

  it('renders single key object', () => {
    const result = renderObjectPreview({ name: 'Alice' });
    expect(result).toBeTruthy();
  });

  it('renders multi-key object with +N more', () => {
    const result = renderObjectPreview({ a: 1, b: 2, c: 3 });
    expect(result).toBeTruthy();
  });

  it('truncates long preview text', () => {
    const result = renderObjectPreview({
      very_long_key_name: 'very long value that should get truncated because it exceeds 40 chars',
    });
    expect(result).toBeTruthy();
  });
});
