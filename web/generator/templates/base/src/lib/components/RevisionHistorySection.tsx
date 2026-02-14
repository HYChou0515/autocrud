/**
 * RevisionHistorySection - Shared revision history display component
 *
 * Shows timeline of resource revisions with timestamps and authors
 * Supports clicking on revisions to view historical data
 */

import { Paper, Stack, Group, Text, Badge, Timeline, ActionIcon, Button } from '@mantine/core';
import { IconClock, IconEye, IconSortAscending, IconSortDescending } from '@tabler/icons-react';
import { useState } from 'react';
import { TimeDisplay } from './TimeDisplay';
import { RevisionIdCell } from './resource-table/RevisionIdCell';

export interface Revision {
  revision_id?: string;
  uid?: string;
  revision_status?: string;
  status?: string;
  created_time?: string;
  updated_time?: string;
  created_by?: string;
  updated_by?: string;
}

export interface RevisionHistorySectionProps {
  revisions: Revision[];
  currentRevisionId?: string;
  selectedRevisionId?: string;
  onRevisionSelect?: (revisionId: string) => void;
  resourceId?: string;
}

/**
 * Displays revision history in a timeline format
 *
 * @param revisions - Array of revision objects
 * @param currentRevisionId - ID of the currently active revision
 * @param selectedRevisionId - ID of the revision being viewed
 * @param onRevisionSelect - Callback when a revision is clicked
 */
export function RevisionHistorySection({
  revisions,
  currentRevisionId,
  selectedRevisionId,
  onRevisionSelect,
  resourceId,
}: RevisionHistorySectionProps) {
  const [sortOrder, setSortOrder] = useState<'desc' | 'asc'>('desc'); // Default: newest first

  if (!revisions || revisions.length === 0) {
    return null;
  }

  // Sort revisions based on sortOrder
  const sortedRevisions = [...revisions].sort((a, b) => {
    const timeA = a.created_time || a.updated_time || '';
    const timeB = b.created_time || b.updated_time || '';
    return sortOrder === 'desc'
      ? timeB.localeCompare(timeA) // Newest first
      : timeA.localeCompare(timeB); // Oldest first
  });

  return (
    <Paper p="md" withBorder>
      <Stack gap="md">
        <Group justify="space-between">
          <Group gap="xs">
            <Text fw={600} size="lg">
              Revision History
            </Text>
            <Badge>{revisions.length} revisions</Badge>
          </Group>
          <Button
            variant="light"
            size="xs"
            leftSection={
              sortOrder === 'desc' ? (
                <IconSortDescending size={14} />
              ) : (
                <IconSortAscending size={14} />
              )
            }
            onClick={() => setSortOrder(sortOrder === 'desc' ? 'asc' : 'desc')}
          >
            {sortOrder === 'desc' ? '新到舊' : '舊到新'}
          </Button>
        </Group>

        <Timeline active={-1} bulletSize={24} lineWidth={2}>
          {sortedRevisions.map((rev, idx) => {
            const revId = rev.revision_id || rev.uid;
            const status = rev.revision_status || rev.status;
            const time = rev.created_time || rev.updated_time;
            const author = rev.created_by || rev.updated_by;
            const isCurrent = currentRevisionId && revId === currentRevisionId;
            const isSelected = selectedRevisionId && revId === selectedRevisionId;

            return (
              <Timeline.Item
                key={revId || idx}
                bullet={<IconClock size={12} />}
                title={
                  <Group gap="xs" justify="space-between">
                    <Group gap="xs">
                      {revId ? (
                        <RevisionIdCell
                          revisionId={revId}
                          resourceId={resourceId}
                          showCopy={false}
                        />
                      ) : (
                        <Text size="sm" fw={500}>
                          Revision {sortedRevisions.length - idx}
                        </Text>
                      )}
                      {status && (
                        <Badge size="xs" variant="light">
                          {status}
                        </Badge>
                      )}
                      {isCurrent && (
                        <Badge size="xs" color="blue">
                          Current
                        </Badge>
                      )}
                      {isSelected && (
                        <Badge size="xs" color="green">
                          Viewing
                        </Badge>
                      )}
                    </Group>
                    {onRevisionSelect && revId && (
                      <ActionIcon
                        size="sm"
                        variant="subtle"
                        color={isSelected ? 'green' : 'blue'}
                        onClick={() => onRevisionSelect(revId)}
                        title={isSelected ? 'Return to current' : 'View this revision'}
                      >
                        <IconEye size={14} />
                      </ActionIcon>
                    )}
                  </Group>
                }
              >
                {time && (
                  <Text size="xs" c="dimmed">
                    <TimeDisplay time={time} format="full" />
                  </Text>
                )}
                {author && (
                  <Text size="xs" c="dimmed">
                    by {author}
                  </Text>
                )}
              </Timeline.Item>
            );
          })}
        </Timeline>
      </Stack>
    </Paper>
  );
}
