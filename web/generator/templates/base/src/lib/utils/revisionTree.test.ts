import { describe, expect, it } from 'vitest';
import { buildRevisionTreeLayout, getMissingParentMarkers } from './revisionTree';

const rev = (id: string, parentId: string | null, time: string) => ({
  revision_id: id,
  parent_revision_id: parentId,
  created_time: time,
});

describe('buildRevisionTreeLayout', () => {
  it('assigns a single lane for a linear chain', () => {
    const layout = buildRevisionTreeLayout(
      [
        rev('r1', null, '2024-01-01T00:00:00Z'),
        rev('r2', 'r1', '2024-01-02T00:00:00Z'),
        rev('r3', 'r2', '2024-01-03T00:00:00Z'),
      ],
      'asc',
    );

    expect(layout.laneCount).toBe(1);
    const lanes = layout.nodes.map((node) => node.lane);
    expect(lanes).toEqual([0, 0, 0]);
  });

  it('creates a new lane for a branch', () => {
    const layout = buildRevisionTreeLayout(
      [
        rev('root', null, '2024-01-01T00:00:00Z'),
        rev('child-a', 'root', '2024-01-02T00:00:00Z'),
        rev('child-b', 'root', '2024-01-03T00:00:00Z'),
      ],
      'asc',
    );

    const laneById = Object.fromEntries(layout.nodes.map((node) => [node.id, node.lane]));
    expect(laneById.root).toBe(0);
    expect(laneById['child-a']).toBe(0);
    expect(laneById['child-b']).toBe(1);
    expect(layout.laneCount).toBe(2);
  });

  it('marks revisions with missing parents', () => {
    const layout = buildRevisionTreeLayout(
      [rev('orphan', 'missing-parent', '2024-02-01T00:00:00Z')],
      'asc',
    );

    expect(layout.missingParentIds.has('missing-parent')).toBe(true);
    expect(layout.nodes[0].isMissingParent).toBe(true);
  });

  it('builds missing parent markers per lane', () => {
    const layout = buildRevisionTreeLayout(
      [
        rev('orphan-a', 'missing-parent', '2024-02-01T00:00:00Z'),
        rev('orphan-b', 'missing-parent', '2024-02-02T00:00:00Z'),
        rev('orphan-c', 'missing-other', '2024-02-03T00:00:00Z'),
      ],
      'asc',
    );

    const markers = getMissingParentMarkers(layout.nodes);
    const markerKeys = markers.map((marker) => `${marker.parentId}-${marker.lane}`);

    expect(markerKeys).toEqual(['missing-parent-0', 'missing-parent-1', 'missing-other-2']);
  });

  it('respects descending sort order for rows', () => {
    const layout = buildRevisionTreeLayout(
      [rev('first', null, '2024-01-01T00:00:00Z'), rev('second', 'first', '2024-01-02T00:00:00Z')],
      'desc',
    );

    expect(layout.nodes[0].id).toBe('second');
    expect(layout.nodes[1].id).toBe('first');
  });
});
