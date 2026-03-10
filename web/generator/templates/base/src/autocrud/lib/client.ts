import axios from 'axios';

const baseURL = import.meta.env.VITE_API_URL || '/api';
console.log('🔧 Axios baseURL:', baseURL);

export const client = axios.create({
  baseURL,
});

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
 * Build the full URL for downloading / displaying a blob by its file ID.
 *
 * Use this everywhere you need a blob `<img src>`, `<a href>`, or
 * fetch URL instead of manually concatenating the base URL.
 */
export function getBlobUrl(fileId: string): string {
  return `${baseURL}/blobs/${fileId}`;
}

// Response interceptor for error handling
client.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error('[API Error]', error.response?.status, error.response?.data);
    return Promise.reject(error);
  },
);
