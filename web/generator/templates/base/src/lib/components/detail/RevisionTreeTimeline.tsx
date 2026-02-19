import { ActionIcon, Badge, Box, Group, Stack, Text, Tooltip } from '@mantine/core';
import { useRef, useState } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { IconEye } from '@tabler/icons-react';
import { RevisionIdCell } from '../common/RevisionIdCell';
import { TimeDisplay } from '../common/TimeDisplay';
import { buildRevisionTreeLayout, getMissingParentMarkers } from '../../utils/revisionTree';
import type { Revision } from '../../types/revision';

export interface RevisionTreeTimelineProps {
  revisions: Revision[];
  sortOrder: 'asc' | 'desc';
  currentRevisionId?: string;
  selectedRevisionId?: string;
  onRevisionSelect?: (revisionId: string) => void;
  resourceId: string;
  viewportHeight?: number;
}

const laneWidth = 48;
const dayWidth = 120;
const rowHeight = 64;
const rowGap = 10;
const titleOffset = 16;
const nodeSize = 12;
const dayAxisOffset = 24;
const missingParentRowHeight = 32;

function formatDayLabel(time: string): string | null {
  if (!time) {
    return null;
  }
  const isoDay = time.slice(0, 10);
  if (/^\d{4}-\d{2}-\d{2}$/.test(isoDay)) {
    return isoDay;
  }
  const parsed = new Date(time);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  const year = parsed.getFullYear();
  const month = String(parsed.getMonth() + 1).padStart(2, '0');
  const day = String(parsed.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export function RevisionTreeTimeline({
  revisions,
  sortOrder,
  currentRevisionId,
  selectedRevisionId,
  onRevisionSelect,
  resourceId,
  viewportHeight,
}: RevisionTreeTimelineProps) {
  const treeViewportHeight = viewportHeight ?? 520;
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const layout = buildRevisionTreeLayout(revisions, sortOrder);
  const graphWidth = layout.laneCount * laneWidth;
  const lineColor = 'var(--mantine-color-gray-4)';
  const rowStride = rowHeight + rowGap;
  const rowVirtualizer = useVirtualizer({
    count: layout.nodes.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => rowStride,
    overscan: 6,
  });
  const baseHeight = Math.max(rowVirtualizer.getTotalSize() - rowGap, 0);
  const totalHeight = baseHeight + (layout.missingParentIds.size > 0 ? missingParentRowHeight : 0);
  const missingParentRowY = totalHeight - missingParentRowHeight / 2;
  const nodesById = new Map(layout.nodes.map((node) => [node.id, node]));
  const missingParentMarkers = getMissingParentMarkers(layout.nodes);
  const virtualRows = rowVirtualizer.getVirtualItems();
  const visibleNodes = virtualRows
    .map((row) => layout.nodes[row.index])
    .filter((node): node is (typeof layout.nodes)[number] => !!node);
  const dayMarkers = visibleNodes.reduce<{ day: string; y: number }[]>((acc, node) => {
    const label = formatDayLabel(node.time);
    if (!label) {
      return acc;
    }
    if (acc.length === 0 || acc[acc.length - 1].day !== label) {
      acc.push({ day: label, y: node.row * rowStride + titleOffset });
    }
    return acc;
  }, []);

  if (layout.nodes.length === 0) {
    return null;
  }

  return (
    <Box
      ref={scrollRef}
      style={{ maxHeight: treeViewportHeight, overflowY: 'auto', paddingRight: 12 }}
    >
      <Box
        style={{
          display: 'grid',
          gridTemplateColumns: `${dayWidth}px ${graphWidth}px 1fr`,
          columnGap: 16,
          height: totalHeight,
        }}
      >
        <Box style={{ position: 'relative', width: dayWidth, height: totalHeight }}>
          <svg
            width={dayWidth}
            height={totalHeight}
            style={{ position: 'absolute', top: 0, left: 0 }}
          >
            <line
              x1={dayAxisOffset}
              y1={0}
              x2={dayAxisOffset}
              y2={totalHeight}
              stroke={lineColor}
              strokeWidth={2}
              opacity={0.4}
            />
            {dayMarkers.map((marker) => (
              <g key={`day-${marker.day}`}>
                <circle cx={dayAxisOffset} cy={marker.y} r={5} fill="var(--mantine-color-blue-6)" />
                <line
                  x1={dayAxisOffset}
                  y1={marker.y}
                  x2={dayWidth}
                  y2={marker.y}
                  stroke={lineColor}
                  strokeWidth={1}
                  opacity={0.35}
                />
              </g>
            ))}
          </svg>
          {dayMarkers.map((marker) => (
            <Text
              key={`day-label-${marker.day}`}
              size="xs"
              c="dimmed"
              style={{
                position: 'absolute',
                top: marker.y - 9,
                left: dayAxisOffset + 12,
              }}
            >
              {marker.day}
            </Text>
          ))}
        </Box>
        <Box style={{ position: 'relative', width: graphWidth, height: totalHeight }}>
          <svg
            width={graphWidth}
            height={totalHeight}
            style={{ position: 'absolute', top: 0, left: 0 }}
          >
            {Array.from({ length: layout.laneCount }).map((_, laneIndex) => {
              const x = laneIndex * laneWidth + laneWidth / 2;
              return (
                <line
                  key={`lane-${laneIndex}`}
                  x1={x}
                  y1={0}
                  x2={x}
                  y2={totalHeight}
                  stroke={lineColor}
                  strokeWidth={2}
                  opacity={0.4}
                />
              );
            })}
            {visibleNodes.map((node) => {
              if (!node.parentId) {
                return null;
              }
              const parentNode = nodesById.get(node.parentId);
              if (!parentNode) {
                const nodeX = node.lane * laneWidth + laneWidth / 2;
                const nodeY = node.row * rowStride + titleOffset;
                return (
                  <path
                    key={`missing-edge-${node.id}`}
                    d={`M ${nodeX} ${missingParentRowY} L ${nodeX} ${nodeY}`}
                    stroke="var(--mantine-color-gray-5)"
                    strokeWidth={1.5}
                    strokeDasharray="3 3"
                    fill="none"
                  />
                );
              }
              const parentX = parentNode.lane * laneWidth + laneWidth / 2;
              const parentY = parentNode.row * rowStride + titleOffset;
              const nodeX = node.lane * laneWidth + laneWidth / 2;
              const nodeY = node.row * rowStride + titleOffset;

              return (
                <path
                  key={`edge-${node.id}`}
                  d={`M ${parentX} ${parentY} L ${nodeX} ${parentY} L ${nodeX} ${nodeY}`}
                  stroke={lineColor}
                  strokeWidth={2}
                  fill="none"
                />
              );
            })}
            {missingParentMarkers.map((marker) => {
              const label = marker.parentId.split(':').pop();
              const baseLabel = label ? label : '?';
              const display = baseLabel.startsWith('rev#') ? baseLabel : `rev#${baseLabel}`;
              const markerX = marker.lane * laneWidth + laneWidth / 2;
              return (
                <g key={`missing-parent-${marker.parentId}-${marker.lane}`}>
                  <circle
                    cx={markerX}
                    cy={missingParentRowY}
                    r={5}
                    fill="var(--mantine-color-gray-1)"
                    stroke="var(--mantine-color-gray-4)"
                    strokeWidth={1.5}
                    strokeDasharray="2 2"
                  />
                  <text
                    x={markerX}
                    y={missingParentRowY + 14}
                    textAnchor="middle"
                    fontSize="11"
                    fill="var(--mantine-color-gray-6)"
                  >
                    {display}
                  </text>
                </g>
              );
            })}
          </svg>
          {visibleNodes.map((node) => {
            const revId = node.raw.revision_id || node.raw.uid || node.id;
            const isHovered = hoveredId === node.id;
            const isCurrent = currentRevisionId && revId === currentRevisionId;
            const isSelected = selectedRevisionId && revId === selectedRevisionId;
            const nodeColor = isSelected
              ? 'var(--mantine-color-green-6)'
              : isCurrent
                ? 'var(--mantine-color-blue-6)'
                : 'var(--mantine-color-gray-6)';
            const nodeBorder = '2px solid var(--mantine-color-white)';
            const nodeX = node.lane * laneWidth + laneWidth / 2;
            const nodeY = node.row * rowStride + titleOffset;
            const canSelect = !!onRevisionSelect && !!revId;

            return (
              <Tooltip key={`node-${node.id}`} label={revId} position="top" withArrow>
                <Box
                  role={canSelect ? 'button' : undefined}
                  tabIndex={canSelect ? 0 : undefined}
                  onMouseEnter={() => setHoveredId(node.id)}
                  onMouseLeave={() => setHoveredId(null)}
                  onClick={() => {
                    if (canSelect) {
                      onRevisionSelect?.(revId);
                    }
                  }}
                  onKeyDown={(event) => {
                    if (!canSelect) return;
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault();
                      onRevisionSelect?.(revId);
                    }
                  }}
                  style={{
                    position: 'absolute',
                    left: nodeX - nodeSize / 2,
                    top: nodeY - nodeSize / 2,
                    width: nodeSize,
                    height: nodeSize,
                    borderRadius: '50%',
                    background: nodeColor,
                    border: nodeBorder,
                    transform: isHovered ? 'scale(1.25)' : 'scale(1)',
                    transition: 'transform 120ms ease, box-shadow 120ms ease',
                    cursor: canSelect ? 'pointer' : 'default',
                    boxShadow: isHovered
                      ? '0 0 0 4px var(--mantine-color-blue-2)'
                      : '0 0 0 2px var(--mantine-color-white)',
                  }}
                />
              </Tooltip>
            );
          })}
        </Box>
        <Box style={{ position: 'relative', height: totalHeight }}>
          {visibleNodes.map((node) => {
            const revId = node.raw.revision_id || node.raw.uid || node.id;
            const isHovered = hoveredId === node.id;
            const isCurrent = currentRevisionId && revId === currentRevisionId;
            const isSelected = selectedRevisionId && revId === selectedRevisionId;
            const canSelect = !!onRevisionSelect && !!revId;
            const rowTop = node.row * rowStride;

            return (
              <Group
                key={`content-${node.id}`}
                wrap="nowrap"
                align="center"
                gap="md"
                onMouseEnter={() => setHoveredId(node.id)}
                onMouseLeave={() => setHoveredId(null)}
                style={{
                  position: 'absolute',
                  top: rowTop,
                  left: 0,
                  right: 0,
                  height: rowHeight,
                  paddingTop: 8,
                  borderRadius: 8,
                  background: isHovered ? 'var(--mantine-color-blue-0)' : 'transparent',
                  transition: 'background 120ms ease',
                }}
              >
                <Stack gap={2} style={{ minWidth: 0, flex: 1 }}>
                  <Group gap="xs" justify="space-between" wrap="nowrap">
                    <Group gap="xs" wrap="nowrap">
                      <RevisionIdCell revisionId={revId} resourceId={resourceId} showCopy={false} />
                      {node.status && (
                        <Badge size="xs" variant="light">
                          {node.status}
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
                    {canSelect && (
                      <ActionIcon
                        size="sm"
                        variant="subtle"
                        color={isSelected ? 'green' : 'blue'}
                        onClick={() => onRevisionSelect?.(revId)}
                        title={isSelected ? 'Return to current' : 'View this revision'}
                      >
                        <IconEye size={14} />
                      </ActionIcon>
                    )}
                  </Group>
                  {node.time && (
                    <Text size="xs" c="dimmed">
                      <TimeDisplay time={node.time} format="full" />
                    </Text>
                  )}
                  {node.author && (
                    <Text size="xs" c="dimmed">
                      by {node.author}
                    </Text>
                  )}
                </Stack>
              </Group>
            );
          })}
        </Box>
      </Box>
    </Box>
  );
}
