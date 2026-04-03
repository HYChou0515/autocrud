/**
 * JsonEditor — Monaco-based JSON editor for object/nested-array fields.
 *
 * Provides syntax highlighting, auto-formatting, and validation feedback.
 * Uses @monaco-editor/react (already a project dependency).
 */
import { useState, useCallback } from 'react';
import { Stack, Text, Group, ActionIcon, Tooltip } from '@mantine/core';
import { IconArrowsMaximize, IconArrowsMinimize } from '@tabler/icons-react';
import Editor from '@monaco-editor/react';

export interface JsonEditorProps {
  /** Field label */
  label: string;
  /** Whether the field is required */
  required?: boolean;
  /** Current value — may be a string (raw JSON) or an object (will be serialised) */
  value: unknown;
  /** Change handler — emits the raw string so the form can store it as-is */
  onChange: (value: string) => void;
  /** Editor height in px (default: 200) */
  height?: number;
  /** Error message from form validation */
  error?: string;
}

/**
 * Normalise any incoming value to a pretty-printed JSON string.
 * If the value is already a string we try to re-format it; if it's
 * an object/array we serialise it.  On failure we return the raw string
 * representation so the user can still edit it.
 */
function toJsonString(value: unknown): string {
  if (value === undefined || value === null || value === '') return '';
  if (typeof value === 'string') {
    try {
      return JSON.stringify(JSON.parse(value), null, 2);
    } catch {
      return value;
    }
  }
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export function JsonEditor({
  label,
  required,
  value,
  onChange,
  height = 200,
  error,
}: JsonEditorProps) {
  const [expanded, setExpanded] = useState(false);
  const displayHeight = expanded ? Math.max(height, 400) : height;

  const handleChange = useCallback(
    (val: string | undefined) => {
      onChange(val ?? '');
    },
    [onChange],
  );

  return (
    <Stack gap={4}>
      <Group justify="space-between" align="center">
        <Text size="sm" fw={500}>
          {label}
          {required && <span style={{ color: 'var(--mantine-color-red-6)' }}> *</span>}
        </Text>
        <Tooltip label={expanded ? 'Collapse' : 'Expand'}>
          <ActionIcon variant="subtle" size="sm" onClick={() => setExpanded((v) => !v)}>
            {expanded ? <IconArrowsMinimize size={16} /> : <IconArrowsMaximize size={16} />}
          </ActionIcon>
        </Tooltip>
      </Group>

      <div
        style={{
          border: error
            ? '1px solid var(--mantine-color-red-6)'
            : '1px solid var(--mantine-color-default-border)',
          borderRadius: 'var(--mantine-radius-sm)',
          overflow: 'hidden',
        }}
      >
        <Editor
          height={displayHeight}
          language="json"
          value={toJsonString(value)}
          onChange={handleChange}
          options={{
            minimap: { enabled: false },
            lineNumbers: 'on',
            wordWrap: 'on',
            scrollBeyondLastLine: false,
            fontSize: 13,
            tabSize: 2,
            formatOnPaste: true,
            automaticLayout: true,
            padding: { top: 8, bottom: 8 },
          }}
        />
      </div>

      {error && (
        <Text size="xs" c="red">
          {error}
        </Text>
      )}
    </Stack>
  );
}
