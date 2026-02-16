import type { Revision } from '../types/revision';

export interface RevisionTreeNode {
  id: string;
  parentId: string | null;
  lane: number;
  row: number;
  parentLane: number | null;
  isMissingParent: boolean;
  time: string;
  status?: string;
  author?: string;
  raw: Revision;
}

export interface RevisionTreeLayout {
  nodes: RevisionTreeNode[];
  laneCount: number;
  missingParentIds: Set<string>;
}

export interface MissingParentMarker {
  parentId: string;
  lane: number;
}

interface RevisionItem {
  id: string;
  parentId: string | null;
  time: string;
  raw: Revision;
}

function getRevisionId(rev: Revision, index: number): string {
  return rev.revision_id ?? rev.uid ?? `idx-${index}`;
}

function getRevisionTime(rev: Revision): string {
  return rev.created_time ?? rev.updated_time ?? '';
}

function getRevisionStatus(rev: Revision): string | undefined {
  return rev.revision_status ?? rev.status;
}

function getRevisionAuthor(rev: Revision): string | undefined {
  return rev.created_by ?? rev.updated_by;
}

function sortByTimeAsc(a: RevisionItem, b: RevisionItem): number {
  return a.time.localeCompare(b.time);
}

export function getMissingParentMarkers(nodes: RevisionTreeNode[]): MissingParentMarker[] {
  const markers: MissingParentMarker[] = [];
  for (const node of nodes) {
    if (!node.isMissingParent || !node.parentId) {
      continue;
    }
    const hasMarker = markers.some(
      (marker) => marker.parentId === node.parentId && marker.lane === node.lane,
    );
    if (!hasMarker) {
      markers.push({ parentId: node.parentId, lane: node.lane });
    }
  }
  return markers;
}

export function buildRevisionTreeLayout(
  revisions: Revision[],
  sortOrder: 'asc' | 'desc',
): RevisionTreeLayout {
  const items: RevisionItem[] = revisions.map((rev, index) => ({
    id: getRevisionId(rev, index),
    parentId: rev.parent_revision_id ?? null,
    time: getRevisionTime(rev),
    raw: rev,
  }));

  const byId = new Map<string, RevisionItem>();
  for (const item of items) {
    byId.set(item.id, item);
  }

  const missingParentIds = new Set<string>();
  const childrenMap = new Map<string, string[]>();
  for (const item of items) {
    if (!item.parentId) {
      continue;
    }
    if (!byId.has(item.parentId)) {
      missingParentIds.add(item.parentId);
      continue;
    }
    const children = childrenMap.get(item.parentId) ?? [];
    children.push(item.id);
    childrenMap.set(item.parentId, children);
  }

  const roots = items
    .filter((item) => !item.parentId || missingParentIds.has(item.parentId))
    .sort(sortByTimeAsc);

  const laneMap = new Map<string, number>();
  let nextLane = 0;
  const assignLane = (id: string, preferredLane?: number): number => {
    if (laneMap.has(id)) {
      return laneMap.get(id)!;
    }
    const lane = preferredLane ?? nextLane;
    laneMap.set(id, lane);
    if (lane === nextLane) {
      nextLane += 1;
    }
    return lane;
  };

  for (const root of roots) {
    assignLane(root.id);
  }

  const itemsAsc = [...items].sort(sortByTimeAsc);
  for (const item of itemsAsc) {
    if (!laneMap.has(item.id)) {
      assignLane(item.id);
    }
    const children = childrenMap.get(item.id) ?? [];
    if (children.length === 0) {
      continue;
    }
    const sortedChildren = [...children].sort((left, right) => {
      const leftItem = byId.get(left);
      const rightItem = byId.get(right);
      if (!leftItem || !rightItem) {
        return 0;
      }
      return leftItem.time.localeCompare(rightItem.time);
    });

    const parentLane = laneMap.get(item.id) ?? assignLane(item.id);
    const [firstChild, ...restChildren] = sortedChildren;
    if (firstChild) {
      assignLane(firstChild, parentLane);
    }
    for (const childId of restChildren) {
      assignLane(childId);
    }
  }

  const displayItems = [...items].sort((a, b) => {
    const order = a.time.localeCompare(b.time);
    return sortOrder === 'desc' ? -order : order;
  });

  const nodes: RevisionTreeNode[] = displayItems.map((item, index) => {
    const lane = laneMap.get(item.id) ?? assignLane(item.id);
    const parentLane = item.parentId ? (laneMap.get(item.parentId) ?? null) : null;
    return {
      id: item.id,
      parentId: item.parentId,
      lane,
      row: index,
      parentLane,
      isMissingParent: !!item.parentId && missingParentIds.has(item.parentId),
      time: item.time,
      status: getRevisionStatus(item.raw),
      author: getRevisionAuthor(item.raw),
      raw: item.raw,
    };
  });

  return {
    nodes,
    laneCount: Math.max(nextLane, 1),
    missingParentIds,
  };
}
