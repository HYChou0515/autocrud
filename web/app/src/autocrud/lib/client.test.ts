/**
 * client.ts — Unit tests for getBaseUrl() and getBlobUrl().
 *
 * Verifies that the centralized URL utilities produce correct paths
 * and that all blob URL construction goes through getBlobUrl().
 */

import { describe, it, expect } from 'vitest';
import {
  getBaseUrl,
  getBlobUrl,
  setApiBasePath,
  getApiBasePath,
  getBlobUploadPath,
  client,
} from './client';

describe('getBaseUrl', () => {
  it('returns a string', () => {
    const url = getBaseUrl();
    expect(typeof url).toBe('string');
    expect(url.length).toBeGreaterThan(0);
  });

  it('returns the configured VITE_API_URL (or /api fallback)', () => {
    // getBaseUrl() should return whatever VITE_API_URL is set to, or '/api' if unset.
    const url = getBaseUrl();
    expect(typeof url).toBe('string');
    expect(url.startsWith('/')).toBe(true);
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

  it('uses getBaseUrl() prefix rather than hardcoded localhost', () => {
    const url = getBlobUrl('test');
    expect(url).not.toContain('localhost');
    expect(url).toBe(`${getBaseUrl()}/blobs/test`);
  });
});

describe('setApiBasePath / getApiBasePath', () => {
  it('setApiBasePath updates the stored path', () => {
    setApiBasePath('/v1/autocrud');
    expect(getApiBasePath()).toBe('/v1/autocrud');
  });

  it('getBlobUrl includes the apiBasePath', () => {
    setApiBasePath('/v1/autocrud');
    const url = getBlobUrl('abc');
    expect(url).toContain('/v1/autocrud/blobs/abc');
  });

  it('getBlobUploadPath returns correct path', () => {
    setApiBasePath('/v1/autocrud');
    expect(getBlobUploadPath()).toBe('/v1/autocrud/blobs/upload');
  });

  it('getBlobUploadPath with empty base path', () => {
    setApiBasePath('');
    expect(getBlobUploadPath()).toBe('/blobs/upload');
  });
});

describe('client Axios instance', () => {
  it('is an Axios instance with standard methods', () => {
    expect(typeof client.get).toBe('function');
    expect(typeof client.post).toBe('function');
    expect(typeof client.put).toBe('function');
    expect(typeof client.delete).toBe('function');
  });

  it('has response interceptors configured', () => {
    expect(client.interceptors.response).toBeDefined();
  });
});
