/**
 * MetadataSection - Shared metadata display component
 * 
 * Shows resource metadata including ID, revision, timestamps, and authors
 */

import { Paper, Stack, Group, Text, Badge } from '@mantine/core';
import { TimeDisplay } from './TimeDisplay';
import { ResourceIdCell } from './resource-table/ResourceIdCell';
import { RevisionIdCell } from './resource-table/RevisionIdCell';

export interface MetadataSectionProps {
  meta: {
    resource_id: string;
    current_revision_id: string;
    revision_status?: string;
    total_revision_count?: number;
    created_time: string;
    updated_time: string;
    created_by: string;
    updated_by: string;
  };
  revisionInfo?: {
    updated_time: string;
    updated_by: string;
  };
  variant?: 'compact' | 'full';
}

/**
 * Displays resource metadata in a consistent format
 * 
 * @param meta - Resource metadata object
 * @param variant - Display style ('compact' or 'full')
 */
export function MetadataSection({ meta, revisionInfo, variant = 'full' }: MetadataSectionProps) {
  return (
    <Paper p="md" withBorder>
      <Stack gap="md">
        <Text fw={600} size="lg">
          Metadata
        </Text>
        
        <Group grow>
          <div>
            <Text size="sm" c="dimmed">
              Resource ID
            </Text>
            <ResourceIdCell rid={meta.resource_id} />
          </div>
          <div>
            <Text size="sm" c="dimmed">
              Revision {meta.revision_status && <Badge size="xs" variant="light" ml="xs">{meta.revision_status}</Badge>}
            </Text>
            <RevisionIdCell revisionId={meta.current_revision_id} resourceId={meta.resource_id} />
          </div>
        </Group>

        {variant === 'full' && meta.total_revision_count !== undefined && (
          <Group>
            <Text size="sm" c="dimmed">
              Total Revisions
            </Text>
            <Badge>{meta.total_revision_count}</Badge>
          </Group>
        )}

        <Group grow>
          <div>
            <Text size="sm" c="dimmed">
              Created
            </Text>
            <TimeDisplay time={meta.created_time} variant="full" />
            <Text size="xs" c="dimmed">
              by {meta.created_by}
            </Text>
          </div>
          <div>
            <Text size="sm" c="dimmed">
              Updated
            </Text>
            <TimeDisplay time={revisionInfo?.updated_time ?? meta.updated_time} variant="full" />
            <Text size="xs" c="dimmed">
              by {revisionInfo?.updated_by ?? meta.updated_by}
            </Text>
          </div>
        </Group>
      </Stack>
    </Paper>
  );
}
