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
  trunkIds: Set<string>;
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
  currentRevisionId?: string,
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

  // --- Trunk detection ---
  const trunkIds = new Set<string>();
  if (currentRevisionId && byId.has(currentRevisionId)) {
    let cur: string | null = currentRevisionId;
    while (cur) {
      trunkIds.add(cur);
      const item = byId.get(cur);
      if (!item || !item.parentId || !byId.has(item.parentId)) {
        break;
      }
      cur = item.parentId;
    }
  }

  const laneMap = new Map<string, number>();
  let nextLane = 0;
  const assignLane = (id: string, preferredLane?: number): number => {
    if (laneMap.has(id)) {
      return laneMap.get(id)!;
    }
    const lane = preferredLane ?? nextLane;
    laneMap.set(id, lane);
    if (lane >= nextLane) {
      nextLane = lane + 1;
    }
    return lane;
  };

  const hasTrunk = trunkIds.size > 0;

  if (hasTrunk) {
    // --- Phase A: Assign all trunk nodes to lane 0 ---
    for (const id of trunkIds) {
      assignLane(id, 0);
    }

    // --- Phase B: Assign branches from trunk (latest fork first → inner lane) ---
    // Collect trunk nodes sorted by time descending (latest first)
    const trunkNodesDesc = [...trunkIds]
      .map((id) => byId.get(id)!)
      .sort((a, b) => b.time.localeCompare(a.time));

    for (const trunkNode of trunkNodesDesc) {
      const children = childrenMap.get(trunkNode.id) ?? [];
      // Non-trunk children, sorted by time ascending
      const branchRoots = children
        .filter((childId) => !trunkIds.has(childId))
        .map((childId) => byId.get(childId)!)
        .filter(Boolean)
        .sort(sortByTimeAsc);

      for (const branchRoot of branchRoots) {
        // DFS: first child inherits parent lane, rest get new lanes
        dfsAssignLanes(branchRoot.id, assignLane(branchRoot.id), childrenMap, byId, laneMap, assignLane);
      }
    }

    // --- Phase C: Non-trunk roots and orphans ---
    for (const root of roots) {
      if (!trunkIds.has(root.id) && !laneMap.has(root.id)) {
        dfsAssignLanes(root.id, assignLane(root.id), childrenMap, byId, laneMap, assignLane);
      }
    }
  } else {
    // --- Fallback: no currentRevisionId provided ---
    // First root gets lane 0, others get new lanes
    for (const root of roots) {
      assignLane(root.id);
    }
  }

  // Assign any remaining unassigned nodes via DFS from roots (handles fallback and edge cases)
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

    const parentLane = laneMap.get(item.id)!;
    const [firstChild, ...restChildren] = sortedChildren;
    if (firstChild && !laneMap.has(firstChild)) {
      assignLane(firstChild, parentLane);
    }
    for (const childId of restChildren) {
      if (!laneMap.has(childId)) {
        assignLane(childId);
      }
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
    trunkIds,
  };
}

/** DFS helper: assign lanes for a subtree. First child inherits parent lane, rest get new lanes. */
function dfsAssignLanes(
  nodeId: string,
  lane: number,
  childrenMap: Map<string, string[]>,
  byId: Map<string, RevisionItem>,
  laneMap: Map<string, number>,
  assignLane: (id: string, preferredLane?: number) => number,
): void {
  if (!laneMap.has(nodeId)) {
    assignLane(nodeId, lane);
  }
  const children = childrenMap.get(nodeId) ?? [];
  if (children.length === 0) {
    return;
  }
  const sortedChildren = [...children]
    .map((id) => byId.get(id)!)
    .filter(Boolean)
    .sort(sortByTimeAsc);

  const [firstChild, ...restChildren] = sortedChildren;
  if (firstChild && !laneMap.has(firstChild.id)) {
    dfsAssignLanes(firstChild.id, lane, childrenMap, byId, laneMap, assignLane);
  }
  for (const child of restChildren) {
    if (!laneMap.has(child.id)) {
      const newLane = assignLane(child.id);
      dfsAssignLanes(child.id, newLane, childrenMap, byId, laneMap, assignLane);
    }
  }
}
