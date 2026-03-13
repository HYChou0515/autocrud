import axios from 'axios';

const baseURL = import.meta.env.VITE_API_URL || '/api';
console.log('🔧 Axios baseURL:', baseURL);

export const client = axios.create({
  baseURL,
});

/**
 * API base path set by the generated resources module.
 *
 * This is the path prefix under which all AutoCRUD endpoints live
 * (e.g. '/v1/autocrud').  It is injected at startup via
 * `setApiBasePath()` so that blob URLs and other non-Axios URL
 * constructions include the correct prefix.
 */
let apiBasePath = '';

/**
 * Set the API base path prefix.
 *
 * Called by the generated `resources.ts` module at import time so that
 * `getBlobUrl()` and `getBlobUploadPath()` produce correct URLs that
 * include the base path (e.g. '/v1/autocrud/blobs/...').
 */
export function setApiBasePath(path: string): void {
  apiBasePath = path;
}

/**
 * Resolve the API base URL.
 *
 * This is the **single source of truth** for the API base URL.
 * All URL construction MUST go through `getBaseUrl()` or `getBlobUrl()`
 * rather than reading `import.meta.env.VITE_API_URL` directly.
 *
 * An ESLint `no-restricted-syntax` rule enforces this — only this file
 * is allowed to access `VITE_API_URL`.
 */
export function getBaseUrl(): string {
  return baseURL;
}

/**
 * Get the current API base path.
 *
 * Returns the path prefix set via `setApiBasePath()` (e.g. '/v1/autocrud').
 */
export function getApiBasePath(): string {
  return apiBasePath;
}

/**
 * Build the full URL for downloading / displaying a blob by its file ID.
 *
 * Use this everywhere you need a blob `<img src>`, `<a href>`, or
 * fetch URL instead of manually concatenating the base URL.
 */
export function getBlobUrl(fileId: string): string {
  return `${baseURL}${apiBasePath}/blobs/${fileId}`;
}

/**
 * Get the blob upload path (relative to Axios baseURL).
 *
 * Use this for `client.post()` calls to the blob upload endpoint
 * so the request includes the correct base path prefix.
 */
export function getBlobUploadPath(): string {
  return `${apiBasePath}/blobs/upload`;
}

// Response interceptor for error handling
client.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error('[API Error]', error.response?.status, error.response?.data);
    return Promise.reject(error);
  },
);
