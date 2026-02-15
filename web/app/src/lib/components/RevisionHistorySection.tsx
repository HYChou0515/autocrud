/**
 * RevisionHistorySection - Shared revision history display component
 *
 * Shows timeline of resource revisions with timestamps and authors
 * Supports clicking on revisions to view historical data
 */

import { Paper, Stack, Group, Text, Badge, Timeline, ActionIcon, Button, Loader, Center } from '@mantine/core';
import { IconClock, IconEye, IconSortAscending, IconSortDescending, IconChevronDown } from '@tabler/icons-react';
import { useState, useEffect, useCallback } from 'react';
import { TimeDisplay } from './TimeDisplay';
import { RevisionIdCell } from './resource-table/RevisionIdCell';
import type { ResourceConfig } from '../resources';

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
  config: ResourceConfig;
  resourceId: string;
  currentRevisionId?: string;
  selectedRevisionId?: string;
  onRevisionSelect?: (revisionId: string) => void;
}

/**
 * Displays revision history in a timeline format
 *
 * @param config - Resource configuration
 * @param resourceId - Resource ID
 * @param currentRevisionId - ID of the currently active revision
 * @param selectedRevisionId - ID of the revision being viewed
 * @param onRevisionSelect - Callback when a revision is clicked
 */
export function RevisionHistorySection({
  config,
  resourceId,
  currentRevisionId,
  selectedRevisionId,
  onRevisionSelect,
}: RevisionHistorySectionProps) {
  const [sortOrder, setSortOrder] = useState<'desc' | 'asc'>('desc'); // Default: newest first
  const [revisions, setRevisions] = useState<Revision[]>([]);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);

  const fetchRevisions = useCallback(
    async (fromRevisionId?: string) => {
      if (!fromRevisionId) {
        setLoading(true);
      } else {
        setLoadingMore(true);
      }
      try {
        const params: any = {
          chain_only: true,
          limit: 10,
        };
        if (fromRevisionId) {
          params.from_revision_id = fromRevisionId;
        }
        const response = await config.apiClient.revisionList(resourceId, params);
        
        if (!fromRevisionId) {
          // Initial load
          setRevisions(response.data.revisions);
        } else {
          // Load more - append new revisions (skip first one as it's the from_revision_id)
          setRevisions((prev) => [...prev, ...response.data.revisions.slice(1)]);
        }
        setTotal(response.data.total);
        setHasMore(response.data.has_more);
      } catch (error) {
        console.error('Failed to fetch revisions:', error);
      } finally {
        setLoading(false);
        setLoadingMore(false);
      }
    },
    [config.apiClient, resourceId],
  );

  useEffect(() => {
    fetchRevisions();
  }, [fetchRevisions]);

  const handleLoadMore = () => {
    const lastRevision = revisions[revisions.length - 1];
    if (lastRevision?.revision_id || lastRevision?.uid) {
      const lastRevId = lastRevision.revision_id || lastRevision.uid;
      fetchRevisions(lastRevId);
    }
  };

  if (loading) {
    return (
      <Paper p="md" withBorder>
        <Center py="xl">
          <Loader size="sm" />
        </Center>
      </Paper>
    );
  }

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

        {hasMore && (
          <Center mt="md">
            <Button
              variant="light"
              size="xs"
              leftSection={<IconChevronDown size={14} />}
              onClick={handleLoadMore}
              loading={loadingMore}
            >
              載入更多 (+10)
            </Button>
          </Center>
        )}
      </Stack>
    </Paper>
  );
}
