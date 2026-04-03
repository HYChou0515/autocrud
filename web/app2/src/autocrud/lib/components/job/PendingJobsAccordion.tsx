/**
 * PendingJobsAccordion — Shows an accordion above the resource list table
 * when the resource has pending async-create jobs.
 *
 * Automatically queries all child async-create-job resources for items
 * with `status ∈ ['pending', 'processing']`.  If none are found the
 * component renders nothing.  When there *are* pending jobs the accordion
 * is shown (collapsed by default) with a summary badge and a
 * MultiResourceTable inside.
 *
 * This is a standard autocrud-admin feature — any resource with
 * async-create custom actions will automatically display this section.
 */

import { useMemo, useState, useTransition } from 'react';
import { Accordion, Badge, Center, Group, Loader, Text } from '@mantine/core';
import { IconLoader2 } from '@tabler/icons-react';
import { getAsyncCreateJobChildren, getResource, type ResourceConfig } from '../../resources';
import type { UseResourceListParams } from '../../hooks/useResourceList';
import { useMultiResourceList } from '../../hooks/useMultiResourceList';
import { MultiResourceTable } from '../table/MultiResourceTable';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface PendingJobsAccordionProps {
  /** The parent resource name (e.g. 'character'). */
  parentResourceName: string;
}

// ---------------------------------------------------------------------------
// Shared query params — only fetch pending / processing jobs
// ---------------------------------------------------------------------------

const PENDING_PARAMS: UseResourceListParams = {
  data_conditions: JSON.stringify([
    { field_path: 'status', operator: 'in', value: ['pending', 'processing'] },
  ]),
  limit: 100,
};

// ---------------------------------------------------------------------------
// Job-specific column overrides (status badge, payload preview, etc.)
// ---------------------------------------------------------------------------

const STATUS_COLORS: Record<string, string> = {
  pending: 'gray',
  processing: 'blue',
  completed: 'green',
  failed: 'red',
};

const JOB_COLUMN_OPTIONS = {
  order: ['_source', 'status', 'resource_id', 'retries', 'created_time', 'updated_time'],
  overrides: {
    status: {
      label: 'Status',
      render: (value: unknown) => {
        const status = String(value || 'pending');
        return (
          <Badge color={STATUS_COLORS[status] || 'gray'} variant="filled" size="sm">
            {status.toUpperCase()}
          </Badge>
        );
      },
    },
    // Hide payload to avoid rendering large blob data that can freeze the UI
    payload: { hidden: true },
    retries: { label: 'Retries' },
    created_time: { label: 'Created' },
    updated_time: { label: 'Updated' },
  },
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function PendingJobsAccordion({ parentResourceName }: PendingJobsAccordionProps) {
  // ── Resolve child job configs ──
  const jobConfigs = useMemo(() => {
    const names = getAsyncCreateJobChildren(parentResourceName);
    return names.map((n) => getResource(n)).filter((c): c is ResourceConfig => !!c);
  }, [parentResourceName]);

  // ── Fetch pending/processing jobs ──
  const entries = useMemo(() => jobConfigs.map((config) => ({ config })), [jobConfigs]);

  const { totalCount, loading } = useMultiResourceList(entries, PENDING_PARAMS);

  // ── Deferred rendering: only mount the heavy MultiResourceTable after
  //    the accordion has been opened at least once, using startTransition
  //    so the expand animation is not blocked by the table mount. ──
  const [hasOpened, setHasOpened] = useState(false);
  const [, startTransition] = useTransition();

  const handleAccordionChange = (value: string | null) => {
    if (value && !hasOpened) {
      startTransition(() => setHasOpened(true));
    }
  };

  // ── Render nothing when no child jobs or no pending items ──
  if (jobConfigs.length === 0) return null;
  if (!loading && totalCount === 0) return null;

  return (
    <Accordion variant="contained" onChange={handleAccordionChange}>
      <Accordion.Item value="pending-jobs">
        <Accordion.Control>
          <Group gap="sm">
            {loading && <IconLoader2 size={16} className="mantine-loader-spin" />}
            <Text fw={500} size="sm">
              Creating in progress
            </Text>
            <Badge size="sm" variant="filled" color="blue">
              {loading ? '…' : totalCount}
            </Badge>
          </Group>
        </Accordion.Control>
        <Accordion.Panel>
          {hasOpened ? (
            <MultiResourceTable
              configs={jobConfigs}
              params={PENDING_PARAMS}
              columns={JOB_COLUMN_OPTIONS}
              emptyMessage={null}
            />
          ) : (
            <Center py="md">
              <Loader size="sm" />
            </Center>
          )}
        </Accordion.Panel>
      </Accordion.Item>
    </Accordion>
  );
}
