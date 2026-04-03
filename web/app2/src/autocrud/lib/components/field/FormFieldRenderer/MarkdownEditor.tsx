/**
 * MarkdownEditor — Monaco editor with live preview toggle for markdown fields.
 *
 * Uses @monaco-editor/react for editing and react-markdown + remark-gfm for preview.
 */
import { useState } from 'react';
import { Stack, Group, Text, SegmentedControl, TypographyStylesProvider } from '@mantine/core';
import Editor from '@monaco-editor/react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export interface MarkdownEditorProps {
  /** Field label */
  label: string;
  /** Whether the field is required */
  required?: boolean;
  /** Current markdown text value */
  value: string;
  /** Change handler */
  onChange: (value: string) => void;
  /** Editor height in px (default: 300) */
  height?: number;
  /** Error message from form validation */
  error?: string;
}

export function MarkdownEditor({
  label,
  required,
  value,
  onChange,
  height = 300,
  error,
}: MarkdownEditorProps) {
  const [mode, setMode] = useState<'edit' | 'preview'>('edit');

  return (
    <Stack gap={4}>
      <Group justify="space-between" align="center">
        <Text size="sm" fw={500}>
          {label}
          {required && <span style={{ color: 'var(--mantine-color-red-6)' }}> *</span>}
        </Text>
        <SegmentedControl
          size="xs"
          value={mode}
          onChange={(val) => setMode(val as 'edit' | 'preview')}
          data={[
            { label: 'Edit', value: 'edit' },
            { label: 'Preview', value: 'preview' },
          ]}
        />
      </Group>

      {mode === 'edit' ? (
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
            height={height}
            language="markdown"
            value={value ?? ''}
            onChange={(val) => onChange(val ?? '')}
            options={{
              minimap: { enabled: false },
              lineNumbers: 'off',
              wordWrap: 'on',
              scrollBeyondLastLine: false,
              fontSize: 14,
              padding: { top: 8, bottom: 8 },
            }}
          />
        </div>
      ) : (
        <TypographyStylesProvider>
          <div
            style={{
              border: '1px solid var(--mantine-color-default-border)',
              borderRadius: 'var(--mantine-radius-sm)',
              padding: '12px 16px',
              minHeight: height,
              maxHeight: height * 1.5,
              overflow: 'auto',
            }}
          >
            {value ? (
              <Markdown remarkPlugins={[remarkGfm]}>{value}</Markdown>
            ) : (
              <Text c="dimmed" fs="italic" size="sm">
                Nothing to preview
              </Text>
            )}
          </div>
        </TypographyStylesProvider>
      )}

      {error && (
        <Text size="xs" c="red">
          {error}
        </Text>
      )}
    </Stack>
  );
}
