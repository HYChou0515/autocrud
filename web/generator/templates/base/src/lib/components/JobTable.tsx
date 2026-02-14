/**
 * JobTable - Job-specific resource table
 *
 * Wraps ResourceTable with Job-specific column configurations
 */

import { useMemo } from 'react';
import { Badge, Code, Tooltip, Group, Text } from '@mantine/core';
import { IconFileCode } from '@tabler/icons-react';
import type { ResourceConfig } from '../resources';
import { ResourceTable } from './resource-table';

export interface JobTableProps<T> {
  config: ResourceConfig<T>;
  basePath: string;
}

const statusColors: Record<string, string> = {
  pending: 'gray',
  processing: 'blue',
  completed: 'green',
  failed: 'red',
};

/**
 * Render payload object with hover preview
 */
function renderPayload(value: unknown) {
  if (!value || typeof value !== 'object') {
    return (
      <Text c="dimmed" size="sm">
        N/A
      </Text>
    );
  }

  const obj = value as Record<string, unknown>;
  const keys = Object.keys(obj);

  if (keys.length === 0) {
    return (
      <Text c="dimmed" size="sm">
        {'{}'}
      </Text>
    );
  }

  // Show first key-value pair as preview
  const firstKey = keys[0];
  const firstValue = obj[firstKey];
  const previewText =
    keys.length === 1
      ? `${firstKey}: ${JSON.stringify(firstValue)}`
      : `${firstKey}: ${JSON.stringify(firstValue)}, +${keys.length - 1} more`;

  const shortPreview = previewText.length > 40 ? previewText.slice(0, 37) + '...' : previewText;

  return (
    <Tooltip
      label={
        <Code block style={{ maxWidth: '400px', maxHeight: '300px', overflow: 'auto' }}>
          {JSON.stringify(obj, null, 2)}
        </Code>
      }
      position="bottom-start"
      withArrow
      withinPortal
    >
      <Group gap={4} wrap="nowrap" style={{ cursor: 'help' }}>
        <IconFileCode size={14} />
        <Text size="sm" style={{ fontFamily: 'monospace' }}>
          {shortPreview}
        </Text>
      </Group>
    </Tooltip>
  );
}

/**
 * Job-specific table with preconfigured columns and search fields
 */
export function JobTable<T extends Record<string, any>>({ config, basePath }: JobTableProps<T>) {
  // Job-specific column configuration
  const columns = useMemo(
    () => ({
      order: [
        'status',
        'resource_id',
        'payload',
        'retries',
        'created_time',
        'updated_time',
        'errmsg',
      ],
      overrides: {
        // Status column with Badge
        status: {
          label: 'Status',
          render: (value: unknown) => {
            const status = String(value || 'pending');
            return (
              <Badge color={statusColors[status] || 'gray'} variant="filled">
                {status.toUpperCase()}
              </Badge>
            );
          },
        },
        // Payload column with JSON preview
        payload: {
          label: 'Payload',
          render: renderPayload,
        },
        // Retries column
        retries: {
          label: 'Retries',
          variant: 'auto' as const,
        },
        // Error message column (hidden by default)
        errmsg: {
          label: 'Error',
          variant: 'string' as const,
          hidden: true,
        },
        // Periodic job fields (hidden by default)
        periodic_interval_seconds: {
          label: 'Interval (s)',
          variant: 'auto' as const,
          hidden: true,
        },
        periodic_max_runs: {
          label: 'Max Runs',
          variant: 'auto' as const,
          hidden: true,
        },
        periodic_runs: {
          label: 'Runs',
          variant: 'auto' as const,
          hidden: true,
        },
        periodic_initial_delay_seconds: {
          label: 'Initial Delay (s)',
          variant: 'auto' as const,
          hidden: true,
        },
        // Override default time columns to use relative-time
        created_time: {
          label: 'Created',
          variant: 'relative-time' as const,
        },
        updated_time: {
          label: 'Updated',
          variant: 'relative-time' as const,
        },
      },
    }),
    [],
  );

  return <ResourceTable config={config} basePath={basePath} columns={columns} />;
}
