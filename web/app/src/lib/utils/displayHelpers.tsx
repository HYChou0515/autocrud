/**
 * Shared display helper functions used by DetailFieldRenderer, JobFieldsSection,
 * and other read-only value rendering contexts.
 */

import { Code, Text } from '@mantine/core';
import { TimeDisplay } from '../components/TimeDisplay';

/** Check if a string looks like an ISO datetime (e.g. "2024-01-01T00:00:00...") */
export function isISODateString(value: unknown): value is string {
  return typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/.test(value);
}

/** Check if an object looks like a blob reference (has file_id + size) */
export function isBlobObject(obj: Record<string, unknown>): boolean {
  return 'file_id' in obj && 'size' in obj;
}

/** Reusable N/A placeholder */
export const NA = (
  <Text c="dimmed" size="sm">
    N/A
  </Text>
);

/**
 * Render a value without any field-schema context.
 *
 * Handles: null → N/A, ISO dates, booleans, arrays, objects (JSON), strings.
 * Used by JobFieldsSection and as fallback in DetailFieldRenderer's `text` kind.
 */
export function renderSimpleValue(value: unknown): React.ReactNode {
  if (value == null) return NA;
  if (isISODateString(value)) return <TimeDisplay time={String(value)} format="full" />;
  if (typeof value === 'boolean') return value ? '✅ Yes' : '❌ No';
  if (Array.isArray(value)) {
    if (value.length === 0)
      return (
        <Text c="dimmed" size="sm">
          []
        </Text>
      );
    if (typeof value[0] === 'object' && value[0] !== null) {
      return <Code block>{JSON.stringify(value, null, 2)}</Code>;
    }
    return value.join(', ');
  }
  if (typeof value === 'object' && value !== null) {
    return <Code block>{JSON.stringify(value, null, 2)}</Code>;
  }
  return String(value);
}
