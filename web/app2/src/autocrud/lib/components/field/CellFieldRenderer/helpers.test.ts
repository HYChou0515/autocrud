/**
 * CellFieldRenderer/helpers — Unit tests for pure helper functions.
 */

import { describe, it, expect } from 'vitest';
import { isValidElement } from 'react';
import {
  formatBinarySize,
  isImageContentType,
  getBlobUrl,
  getContentTypeIcon,
  renderBinaryCell,
  renderObjectPreview,
  safeStringify,
  INLINE_IMAGE_MAX_SIZE,
} from './helpers';
import { getBaseUrl } from '../../../client';

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

  it('uses getBaseUrl() as prefix (not hardcoded localhost)', () => {
    const url = getBlobUrl('abc123');
    expect(url).toBe(`${getBaseUrl()}/blobs/abc123`);
    expect(url).not.toContain('localhost');
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

describe('safeStringify', () => {
  it('returns normal JSON for small objects', () => {
    expect(safeStringify({ a: 1, b: 2 })).toBe('{"a":1,"b":2}');
  });

  it('supports indent parameter', () => {
    expect(safeStringify({ a: 1 }, 2)).toBe('{\n  "a": 1\n}');
  });

  it('truncates output exceeding maxLen', () => {
    const huge = { data: 'x'.repeat(200_000) };
    const result = safeStringify(huge, undefined, 1000);
    expect(result.length).toBeLessThanOrEqual(1100); // small tolerance for suffix
    expect(result).toContain('…[truncated');
  });

  it('uses default MAX_SAFE_JSON_LENGTH when maxLen not provided', () => {
    // Create object with a 2 MB string value — should be truncated by default
    const huge = { blob: 'A'.repeat(2_000_000) };
    const result = safeStringify(huge);
    expect(result.length).toBeLessThan(200_000);
    expect(result).toContain('…[truncated');
  });

  it('returns full JSON when under the limit', () => {
    const small = { name: 'Alice', age: 30 };
    const result = safeStringify(small);
    expect(result).toBe(JSON.stringify(small));
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

  it('handles object with huge blob value without hanging', () => {
    // Simulate a payload containing a large base64 blob
    const hugePayload = {
      name: 'test',
      image_data: 'A'.repeat(5_000_000), // 5 MB base64 string
    };
    const start = performance.now();
    const result = renderObjectPreview(hugePayload);
    const elapsed = performance.now() - start;

    expect(result).toBeTruthy();
    // Must complete in under 500ms (would hang for seconds without fix)
    expect(elapsed).toBeLessThan(500);
  });

  it('tooltip Code block has explicit readable text color (not inherited white)', () => {
    // BUG: Mantine Tooltip default dark bg sets white text color, but the Code
    // block inside has a light background → white text on light bg = invisible.
    const result = renderObjectPreview({ name: 'Alice' });
    expect(isValidElement(result)).toBe(true);

    const tooltipEl = result as any;
    const codeEl = tooltipEl.props.label;
    expect(isValidElement(codeEl)).toBe(true);

    // The Code block must have an explicit color style to override inherited white
    const style = codeEl.props.style as Record<string, unknown>;
    expect(style).toHaveProperty('color');
    expect(style.color).toBeTruthy();
    // Must not be white / #fff / #ffffff
    const colorVal = String(style.color).toLowerCase().replace(/\s/g, '');
    expect(colorVal).not.toMatch(/^(white|#fff|#ffffff)$/);
  });
});
