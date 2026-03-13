/**
 * client.ts — Unit tests for getBaseUrl() and getBlobUrl().
 *
 * Verifies that the centralized URL utilities produce correct paths
 * and that all blob URL construction goes through getBlobUrl().
 */

import { describe, it, expect } from 'vitest';
import { getBaseUrl, getBlobUrl } from './client';

describe('getBaseUrl', () => {
  it('returns a string', () => {
    const url = getBaseUrl();
    expect(typeof url).toBe('string');
    expect(url.length).toBeGreaterThan(0);
  });

  it('returns /api as default fallback', () => {
    // In vitest with happy-dom, VITE_API_URL is not set → fallback to '/api'
    expect(getBaseUrl()).toBe('/api');
  });
});

describe('getBlobUrl', () => {
  it('builds URL with base path prefix', () => {
    const url = getBlobUrl('abc123');
    expect(url).toBe(`${getBaseUrl()}/blobs/abc123`);
  });

  it('starts with getBaseUrl()', () => {
    const url = getBlobUrl('file-id');
    expect(url.startsWith(getBaseUrl())).toBe(true);
  });

  it('contains /blobs/ segment followed by file id', () => {
    const url = getBlobUrl('my-file-id');
    expect(url).toContain('/blobs/my-file-id');
  });

  it('uses /api prefix (default fallback) rather than hardcoded localhost', () => {
    const url = getBlobUrl('test');
    expect(url).not.toContain('localhost');
    expect(url).toBe('/api/blobs/test');
  });
});
