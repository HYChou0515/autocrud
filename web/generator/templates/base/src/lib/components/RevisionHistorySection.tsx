/**
 * RevisionHistorySection - Shared revision history display component
 *
 * Shows timeline of resource revisions with timestamps and authors
 * Supports clicking on revisions to view historical data
 */

import {
  Paper,
  Stack,
  Group,
  Text,
  Badge,
  Box,
  Timeline,
  ActionIcon,
  Button,
  Loader,
  Center,
  SegmentedControl,
} from '@mantine/core';
import { useViewportSize } from '@mantine/hooks';
import {
  IconClock,
  IconEye,
  IconSortAscending,
  IconSortDescending,
  IconChevronDown,
} from '@tabler/icons-react';
import { useState, useEffect, useCallback, useRef } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { TimeDisplay } from './TimeDisplay';
import { RevisionIdCell } from './resource-table/RevisionIdCell';
import type { ResourceConfig } from '../resources';
import type { Revision } from '../types/revision';
import { RevisionTreeTimeline } from './RevisionTreeTimeline';
import { getRevisionViewMode, setRevisionViewMode } from '../utils/customization';
import { getVirtualPadding } from '../utils/virtualization';
import {
  ensureRevisionInList,
  hasRevisionId,
  mergeRevisionsUnique,
  toRevisionFromInfo,
} from '../utils/revisionList';

export interface RevisionHistorySectionProps {
  config: ResourceConfig;
  resourceId: string;
  currentRevisionId?: string;
  selectedRevisionId?: string;
  onRevisionSelect?: (revisionId: string) => void;
  /** Enable timeline view toggle. When false (default), only tree view is available. */
  enableTimelineView?: boolean;
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
  enableTimelineView = false,
}: RevisionHistorySectionProps) {
  const headerHeight = 400;
  const [sortOrder, setSortOrder] = useState<'desc' | 'asc'>('desc'); // Default: newest first
  const savedViewMode = getRevisionViewMode();
  const [viewMode, setViewMode] = useState<'timeline' | 'tree'>(
    enableTimelineView ? savedViewMode : 'tree',
  );
  const [revisions, setRevisions] = useState<Revision[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [totalRevisionCount, setTotalRevisionCount] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [treeOffset, setTreeOffset] = useState(0);
  const [treeChainFrom, setTreeChainFrom] = useState<string | undefined>(undefined);
  const treeChainBase = selectedRevisionId ?? currentRevisionId;
  const timelineParentRef = useRef<HTMLDivElement | null>(null);
  const { height: vh } = useViewportSize();
  const viewportHeight = vh - headerHeight;

  useEffect(() => {
    setRevisionViewMode(viewMode);
  }, [viewMode]);

  const fetchRevisions = useCallback(
    async ({ fromRevisionId, offset }: { fromRevisionId?: string; offset?: number } = {}) => {
      if (fromRevisionId || offset !== undefined) {
        setLoadingMore(true);
      } else {
        setLoading(true);
      }
      try {
        if (viewMode === 'timeline') {
          const params: any = {
            chain_only: true,
            limit: 1000,
            sort: '-created_time',
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
          setHasMore(response.data.has_more);
          setTotalRevisionCount(response.data.total);
          return;
        }

        const chainParams: any = {
          chain_only: true,
          limit: 1000,
          sort: '-created_time',
        };
        if (fromRevisionId) {
          chainParams.from_revision_id = fromRevisionId;
        } else if (treeChainBase) {
          chainParams.from_revision_id = treeChainBase;
        }

        const listParams: any = {
          chain_only: false,
          limit: 1000,
          sort: '-created_time',
        };
        if (offset !== undefined) {
          listParams.offset = offset;
        }

        const [chainResponse, listResponse] = await Promise.all([
          config.apiClient.revisionList(resourceId, chainParams),
          config.apiClient.revisionList(resourceId, listParams),
        ]);

        const chainRevisions = fromRevisionId
          ? chainResponse.data.revisions.slice(1)
          : chainResponse.data.revisions;
        const listRevisions = listResponse.data.revisions;

        setRevisions((prev) => {
          const base = fromRevisionId || offset !== undefined ? prev : [];
          return mergeRevisionsUnique(mergeRevisionsUnique(base, chainRevisions), listRevisions);
        });

        const chainLast = chainRevisions[chainRevisions.length - 1];
        if (chainLast?.revision_id || chainLast?.uid) {
          setTreeChainFrom(chainLast.revision_id || chainLast.uid);
        }

        if (offset === undefined) {
          setTreeOffset(listRevisions.length);
        } else {
          setTreeOffset((prev) => prev + listRevisions.length);
        }
        setHasMore(chainResponse.data.has_more || listResponse.data.has_more);
        setTotalRevisionCount(listResponse.data.total);
      } catch (error) {
        console.error('Failed to fetch revisions:', error);
      } finally {
        setLoading(false);
        setLoadingMore(false);
      }
    },
    [config.apiClient, resourceId, treeChainBase, viewMode],
  );

  useEffect(() => {
    setRevisions([]);
    setHasMore(false);
    setTotalRevisionCount(null);
    setTreeOffset(0);
    setTreeChainFrom(undefined);
    fetchRevisions();
  }, [fetchRevisions, viewMode, treeChainBase]);

  useEffect(() => {
    const ids = [selectedRevisionId, currentRevisionId].filter((value): value is string => !!value);
    const missingIds = ids.filter((id) => !hasRevisionId(revisions, id));
    if (missingIds.length === 0) {
      return;
    }

    let cancelled = false;
    const ensureSelectedRevisions = async () => {
      for (const revisionId of missingIds) {
        try {
          const response = await config.apiClient.getFull(resourceId, {
            revision_id: revisionId,
          });
          if (cancelled) {
            return;
          }
          const revision = toRevisionFromInfo(response.data.revision_info);
          setRevisions((prev) => ensureRevisionInList(prev, revision));
        } catch (error) {
          console.warn('Failed to fetch selected revision info:', error);
        }
      }
    };

    ensureSelectedRevisions();

    return () => {
      cancelled = true;
    };
  }, [config.apiClient, currentRevisionId, resourceId, revisions, selectedRevisionId]);

  const handleLoadMore = () => {
    if (viewMode === 'timeline') {
      const lastRevision = revisions[revisions.length - 1];
      if (lastRevision?.revision_id || lastRevision?.uid) {
        const lastRevId = lastRevision.revision_id || lastRevision.uid;
        fetchRevisions({ fromRevisionId: lastRevId });
      }
      return;
    }

    fetchRevisions({ offset: treeOffset, fromRevisionId: treeChainFrom });
  };

  // Sort revisions based on sortOrder
  const sortedRevisions = [...revisions].sort((a, b) => {
    const timeA = a.created_time || a.updated_time || '';
    const timeB = b.created_time || b.updated_time || '';
    return sortOrder === 'desc'
      ? timeB.localeCompare(timeA) // Newest first
      : timeA.localeCompare(timeB); // Oldest first
  });

  const timelineVirtualizer = useVirtualizer({
    count: sortedRevisions.length,
    getScrollElement: () => timelineParentRef.current,
    estimateSize: () => 120,
    overscan: 6,
  });
  const timelineVirtualItems = timelineVirtualizer.getVirtualItems();
  const timelineTotalSize = timelineVirtualizer.getTotalSize();
  const { paddingTop: timelinePaddingTop, paddingBottom: timelinePaddingBottom } =
    getVirtualPadding(timelineVirtualItems, timelineTotalSize);

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

  return (
    <Paper p="md" withBorder>
      <Stack gap="md">
        <Group justify="space-between">
          <Group gap="xs">
            <Text fw={600} size="lg">
              Revision History
            </Text>
            <Badge>
              {hasMore && totalRevisionCount != null
                ? `${revisions.length}/${totalRevisionCount} revisions`
                : `${revisions.length} revisions`}
            </Badge>
          </Group>
          <Group gap="xs" wrap="nowrap">
            {enableTimelineView && (
              <SegmentedControl
                size="xs"
                value={viewMode}
                onChange={(value) => setViewMode(value as 'timeline' | 'tree')}
                data={[
                  { label: '時間軸', value: 'timeline' },
                  { label: '樹狀時間軸', value: 'tree' },
                ]}
              />
            )}
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
        </Group>

        {viewMode === 'timeline' ? (
          <Box
            ref={timelineParentRef}
            style={{ maxHeight: viewportHeight, overflowY: 'auto', paddingRight: 12 }}
          >
            <Box style={{ position: 'relative', height: timelineTotalSize }}>
              <Box
                style={{
                  position: 'absolute',
                  top: timelinePaddingTop,
                  left: 0,
                  right: 0,
                  paddingBottom: timelinePaddingBottom,
                }}
              >
                <Timeline
                  active={-1}
                  bulletSize={24}
                  lineWidth={2}
                  styles={{ itemBody: { paddingBottom: 16 } }}
                >
                  {timelineVirtualItems.map((virtualRow) => {
                    const rev = sortedRevisions[virtualRow.index];
                    if (!rev) {
                      return null;
                    }
                    const revId = rev.revision_id || rev.uid;
                    const status = rev.revision_status || rev.status;
                    const time = rev.created_time || rev.updated_time;
                    const author = rev.created_by || rev.updated_by;
                    const isCurrent = currentRevisionId && revId === currentRevisionId;
                    const isSelected = selectedRevisionId && revId === selectedRevisionId;

                    return (
                      <Box
                        key={virtualRow.key}
                        ref={timelineVirtualizer.measureElement}
                        data-index={virtualRow.index}
                      >
                        <Timeline.Item
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
                                    Revision {sortedRevisions.length - virtualRow.index}
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
                      </Box>
                    );
                  })}
                </Timeline>
              </Box>
            </Box>
          </Box>
        ) : (
          <RevisionTreeTimeline
            revisions={sortedRevisions}
            sortOrder={sortOrder}
            currentRevisionId={currentRevisionId}
            selectedRevisionId={selectedRevisionId}
            onRevisionSelect={onRevisionSelect}
            resourceId={resourceId}
            viewportHeight={viewportHeight}
          />
        )}

        {hasMore && (
          <Center mt="md">
            <Button
              variant="light"
              size="xs"
              leftSection={<IconChevronDown size={14} />}
              onClick={handleLoadMore}
              loading={loadingMore}
            >
              載入更多
            </Button>
          </Center>
        )}
      </Stack>
    </Paper>
  );
}
