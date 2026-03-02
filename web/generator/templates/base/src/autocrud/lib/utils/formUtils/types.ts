/**
 * Type definitions for form utilities
 */

/**
 * Internal binary field value tracked in form state
 * Represents different modes of binary data input
 */
export interface BinaryFormValue {
  /** Mode of binary input: file upload, URL fetch, existing data, or empty */
  _mode: 'file' | 'url' | 'existing' | 'empty';
  /** File object when mode is 'file' */
  file?: File | null;
  /** URL string when mode is 'url' */
  url?: string;
  /** Existing binary file ID (for display only) */
  file_id?: string;
  /** Content type of existing binary */
  content_type?: string;
  /** Size of existing binary in bytes */
  size?: number;
}
