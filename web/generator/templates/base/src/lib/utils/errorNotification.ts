/**
 * Error notification utilities for API error responses
 *
 * Extracts human-readable error messages from Axios error responses
 * (especially 422 validation errors) and shows Mantine notifications.
 */

import { notifications } from '@mantine/notifications';
import type { AxiosError } from 'axios';

/** FastAPI validation error detail item */
interface ValidationErrorItem {
  loc: (string | number)[];
  msg: string;
  type: string;
}

/**
 * Extract a human-readable error message from an Axios error response.
 *
 * Handles both formats:
 * - FastAPI validation: { detail: [{ loc, msg, type }] }
 * - HTTPException: { detail: "string message" }
 */
export function extractErrorMessage(error: unknown): string {
  const axiosError = error as AxiosError<{ detail?: string | ValidationErrorItem[] }>;
  const data = axiosError?.response?.data;

  if (!data?.detail) {
    // Fallback to generic message
    const status = axiosError?.response?.status;
    if (status) {
      return `Request failed with status ${status}`;
    }
    return axiosError?.message || 'An unexpected error occurred';
  }

  // String detail (HTTPException)
  if (typeof data.detail === 'string') {
    return data.detail;
  }

  // Array detail (ValidationError)
  if (Array.isArray(data.detail)) {
    return data.detail
      .map((item: ValidationErrorItem) => {
        const field = item.loc.filter((l) => l !== 'body').join(' → ') || '(root)';
        return `${field}: ${item.msg}`;
      })
      .join('\n');
  }

  return 'An unexpected error occurred';
}

/**
 * Show an error notification for an API error.
 */
export function showErrorNotification(error: unknown, title = 'Operation Failed') {
  const message = extractErrorMessage(error);

  notifications.show({
    title,
    message,
    color: 'red',
    autoClose: 8000,
    withCloseButton: true,
    style: { whiteSpace: 'pre-line' },
  });
}
