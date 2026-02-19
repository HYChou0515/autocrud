/**
 * JobStatusSection — Displays Job-specific status fields in a bordered Paper.
 *
 * Extracted from ResourceDetail to keep the generic component focused
 * on resource-agnostic display logic.
 */

import { Badge, Code, Group, Paper, Progress, Stack, Table, Text } from '@mantine/core';

export const JOB_STATUS_COLORS: Record<string, string> = {
  pending: 'gray',
  processing: 'blue',
  completed: 'green',
  failed: 'red',
};

/** Set of field names owned by JobStatusSection — used to filter them from the data section */
export const JOB_STATUS_FIELDS = new Set([
  'status',
  'retries',
  'errmsg',
  'periodic_interval_seconds',
  'periodic_max_runs',
  'periodic_runs',
  'periodic_initial_delay_seconds',
]);

const NA = (
  <Text c="dimmed" size="sm">
    N/A
  </Text>
);

function optionalSeconds(v: unknown): React.ReactNode {
  return v != null ? `${v}s` : NA;
}

export interface JobStatusSectionProps {
  data: Record<string, any>;
}

export function JobStatusSection({ data }: JobStatusSectionProps) {
  const status: string = data.status || 'unknown';
  const color = JOB_STATUS_COLORS[status] || 'gray';
  const retries: number = data.retries || 0;
  const errmsg: string | null = data.errmsg || null;
  const isPeriodic = data.periodic_interval_seconds != null;
  const periodicRuns: number = data.periodic_runs || 0;
  const periodicMaxRuns: number = data.periodic_max_runs || 0;

  const rows: { label: string; value: React.ReactNode }[] = [
    {
      label: 'Status',
      value: (
        <Badge color={color} variant="light">
          {status.toUpperCase()}
        </Badge>
      ),
    },
    { label: 'Retries', value: retries },
    {
      label: 'Error Message',
      value: errmsg ? (
        <Code block color="red">
          {errmsg}
        </Code>
      ) : (
        NA
      ),
    },
    {
      label: 'Periodic Interval (seconds)',
      value: optionalSeconds(data.periodic_interval_seconds),
    },
    {
      label: 'Periodic Max Runs',
      value:
        data.periodic_max_runs != null
          ? data.periodic_max_runs === 0
            ? 'Unlimited'
            : data.periodic_max_runs
          : NA,
    },
    {
      label: 'Periodic Runs',
      value: (
        <>
          {periodicRuns}
          {isPeriodic && periodicMaxRuns > 0 && (
            <>
              {' / '}
              {periodicMaxRuns}
              <Progress value={(periodicRuns / periodicMaxRuns) * 100} size="sm" mt="xs" />
            </>
          )}
        </>
      ),
    },
    {
      label: 'Periodic Initial Delay (seconds)',
      value: optionalSeconds(data.periodic_initial_delay_seconds),
    },
  ];

  return (
    <Paper p="md" withBorder>
      <Stack gap="md">
        <Group justify="space-between">
          <Text fw={600} size="lg">
            Job Status
          </Text>
          <Badge color={color} variant="filled" size="lg">
            {status.toUpperCase()}
          </Badge>
        </Group>
        <Table>
          <Table.Tbody>
            {rows.map((row) => (
              <Table.Tr key={row.label}>
                <Table.Td style={{ fontWeight: 500, width: '30%' }}>{row.label}</Table.Td>
                <Table.Td>{row.value}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Stack>
    </Paper>
  );
}
