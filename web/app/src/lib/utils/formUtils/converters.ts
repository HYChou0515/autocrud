/**
 * Conversion utility functions for form data transformation
 */

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
 * Convert a BinaryFormValue to API-ready binary payload
 * Handles different binary input modes: existing file_id, new file upload, or URL fetch
 * 
 * @param val - Binary form value to convert
 * @returns Promise resolving to API binary object or null
 * 
 * @example
 * // Existing binary (preserve file_id)
 * await binaryFormValueToApi({ _mode: 'existing', file_id: 'abc123' })
 * // Returns: { file_id: 'abc123' }
 * 
 * // New file upload
 * const file = new File(['data'], 'file.txt', { type: 'text/plain' });
 * await binaryFormValueToApi({ _mode: 'file', file })
 * // Returns: { data: 'base64...', content_type: 'text/plain' }
 * 
 * // URL fetch
 * await binaryFormValueToApi({ _mode: 'url', url: 'https://example.com/image.png' })
 * // Fetches URL, converts to base64: { data: 'base64...', content_type: 'image/png' }
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
    const base64 = await fileToBase64(val.file);
    return {
      data: base64,
      content_type: val.file.type || 'application/octet-stream',
    };
  }
  
  if (val._mode === 'url' && val.url) {
    try {
      const resp = await fetch(val.url);
      const blob = await resp.blob();
      const base64 = await fileToBase64(new File([blob], 'download', { type: blob.type }));
      return {
        data: base64,
        content_type: blob.type || 'application/octet-stream',
      };
    } catch {
      return null;
    }
  }
  
  return null;
}
