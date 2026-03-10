/**
 * Conversion utility functions for form data transformation
 */

import { client, getBlobUploadPath } from '../../client';
import type { BinaryFormValue } from './types';

/**
 * Convert snake_case or kebab-case string to Title Case label
 * @param s - String to convert (e.g., "user_name" or "user-name")
 * @returns Title Case string (e.g., "User Name")
 *
 * @example
 * toLabel('user_name') // 'User Name'
 * toLabel('first-name') // 'First Name'
 * toLabel('api_key') // 'Api Key'
 */
export function toLabel(s: string): string {
  if (!s) return '';
  return s
    .split(/[-_]+/)
    .filter(Boolean)
    .map((w) => w[0].toUpperCase() + w.slice(1))
    .join(' ');
}

/**
 * Convert a File object to base64 string (without data: prefix)
 * @param file - File object to convert
 * @returns Promise resolving to base64 string (without 'data:...;base64,' prefix)
 *
 * @example
 * const file = new File(['hello'], 'test.txt', { type: 'text/plain' });
 * const base64 = await fileToBase64(file);
 * // base64 is 'aGVsbG8=' (base64 of 'hello')
 */
export function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = reader.result as string;
      // Strip "data:...;base64," prefix
      const base64 = dataUrl.split(',')[1] || '';
      resolve(base64);
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

/**
 * Convert a BinaryFormValue to API-ready binary payload.
 *
 * For new file uploads (`_mode: 'file'`) and URL fetches (`_mode: 'url'`),
 * the file is uploaded to the blob store via `POST /blobs/upload` and the
 * returned `file_id` is used in the payload. This avoids base64 encoding
 * overhead for large files.
 *
 * @param val - Binary form value to convert
 * @returns Promise resolving to API binary object or null
 *
 * @example
 * // Existing binary (preserve file_id)
 * await binaryFormValueToApi({ _mode: 'existing', file_id: 'abc123' })
 * // Returns: { file_id: 'abc123' }
 *
 * // New file upload (uploaded via /blobs/upload)
 * const file = new File(['data'], 'file.txt', { type: 'text/plain' });
 * await binaryFormValueToApi({ _mode: 'file', file })
 * // Returns: { file_id: 'xxx', content_type: 'text/plain', size: 4 }
 *
 * // URL fetch (fetched then uploaded via /blobs/upload)
 * await binaryFormValueToApi({ _mode: 'url', url: 'https://example.com/image.png' })
 * // Returns: { file_id: 'yyy', content_type: 'image/png', size: 1024 }
 *
 * // Empty
 * await binaryFormValueToApi({ _mode: 'empty' })
 * // Returns: null
 */
export async function binaryFormValueToApi(
  val: BinaryFormValue | null | undefined,
): Promise<Record<string, any> | null> {
  if (!val || val._mode === 'empty') return null;

  if (val._mode === 'existing') {
    // Don't re-send existing binary — return object with file_id so backend keeps it
    return { file_id: val.file_id };
  }

  if (val._mode === 'file' && val.file) {
    try {
      const uploaded = await uploadBlob(val.file);
      return {
        file_id: uploaded.file_id,
        content_type: uploaded.content_type,
        size: uploaded.size,
      };
    } catch (e) {
      console.error('[binaryFormValueToApi] Failed to upload file:', e);
      throw e;
    }
  }

  if (val._mode === 'url' && val.url) {
    try {
      const resp = await fetch(val.url);
      const blob = await resp.blob();
      const file = new File([blob], 'download', { type: blob.type || 'application/octet-stream' });
      const uploaded = await uploadBlob(file);
      return {
        file_id: uploaded.file_id,
        content_type: uploaded.content_type,
        size: uploaded.size,
      };
    } catch (e) {
      console.error('[binaryFormValueToApi] Failed to fetch URL for binary field:', val.url, e);
      return null;
    }
  }

  return null;
}

/**
 * Response from the blob upload endpoint.
 */
export interface BlobUploadResult {
  file_id: string;
  size: number;
  content_type: string;
}

/**
 * Upload a file to the blob store via `POST /blobs/upload` (multipart/form-data).
 *
 * Returns the blob metadata (`file_id`, `size`, `content_type`). The returned
 * `file_id` can be used in create/update requests to reference the uploaded
 * binary without base64 encoding.
 *
 * @param file - File object to upload
 * @returns Promise resolving to blob metadata
 *
 * @example
 * const result = await uploadBlob(myFile);
 * // result = { file_id: 'abc123', size: 1024, content_type: 'image/png' }
 * // Then use in create: { avatar: { file_id: result.file_id } }
 */
export async function uploadBlob(file: File): Promise<BlobUploadResult> {
  const formData = new FormData();
  formData.append('file', file);
  const resp = await client.post<BlobUploadResult>(getBlobUploadPath(), formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return resp.data;
}
