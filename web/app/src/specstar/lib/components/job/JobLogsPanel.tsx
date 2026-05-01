/**
 * JobLogsPanel — Displays job execution logs in a scrollable panel.
 *
 * Fetches plain-text logs from the backend and renders them in a
 * monospace code block with an auto-refresh option.
 */

import { useEffect, useRef } from 'react';
import { Button, Code, Group, Loader, Paper, Stack, Text, Title } from '@mantine/core';
import { IconFileText, IconRefresh } from '@tabler/icons-react';

export interface JobLogsPanelProps {
  /** Fetched log text (null = not loaded, undefined = no logs) */
  logs: string | null | undefined;
  /** Whether logs are currently being fetched */
  loading: boolean;
  /** Callback to fetch/refresh logs */
  onFetch: () => void;
  /** Whether the getLogs API is available */
  available: boolean;
}

export function JobLogsPanel({ logs, loading, onFetch, available }: JobLogsPanelProps) {
  const codeRef = useRef<HTMLElement>(null);

  // Auto-scroll to bottom when logs update
  useEffect(() => {
    if (codeRef.current) {
      codeRef.current.scrollTop = codeRef.current.scrollHeight;
    }
  }, [logs]);

  if (!available) return null;

  return (
    <Paper withBorder p="md">
      <Stack gap="md">
        <Group justify="space-between">
          <Group gap="xs">
            <IconFileText size={20} />
            <Title order={4}>Execution Logs</Title>
          </Group>
          <Button
            variant="light"
            size="xs"
            leftSection={loading ? <Loader size={14} /> : <IconRefresh size={14} />}
            onClick={onFetch}
            disabled={loading}
          >
            {logs === null ? 'Load Logs' : 'Refresh'}
          </Button>
        </Group>

        {logs === null && !loading && (
          <Text c="dimmed" size="sm">
            Click "Load Logs" to fetch execution logs.
          </Text>
        )}

        {loading && logs === null && (
          <Group gap="xs">
            <Loader size="sm" />
            <Text size="sm" c="dimmed">
              Loading logs…
            </Text>
          </Group>
        )}

        {logs === undefined && !loading && (
          <Text c="dimmed" size="sm" fs="italic">
            No logs available. The job may not have started yet or no blob store is configured.
          </Text>
        )}

        {typeof logs === 'string' && (
          <Code
            block
            ref={codeRef}
            style={{
              maxHeight: '400px',
              overflow: 'auto',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-all',
              fontSize: '0.8rem',
              lineHeight: 1.5,
            }}
          >
            {logs}
          </Code>
        )}
      </Stack>
    </Paper>
  );
}
