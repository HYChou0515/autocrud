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

  // --- Trunk-aware tests ---

  it('trunk identification: currentRevisionId chain is all on lane 0', () => {
    // root → A → B → C(current), branch: A → X → Y
    const layout = buildRevisionTreeLayout(
      [
        rev('root', null, '2024-01-01T00:00:00Z'),
        rev('A', 'root', '2024-01-02T00:00:00Z'),
        rev('X', 'A', '2024-01-03T00:00:00Z'),
        rev('B', 'A', '2024-01-04T00:00:00Z'),
        rev('Y', 'X', '2024-01-05T00:00:00Z'),
        rev('C', 'B', '2024-01-06T00:00:00Z'),
      ],
      'asc',
      'C',
    );

    const laneById = Object.fromEntries(layout.nodes.map((n) => [n.id, n.lane]));
    expect(layout.trunkIds).toEqual(new Set(['root', 'A', 'B', 'C']));
    expect(laneById['root']).toBe(0);
    expect(laneById['A']).toBe(0);
    expect(laneById['B']).toBe(0);
    expect(laneById['C']).toBe(0);
    // X, Y should be on a different lane (> 0)
    expect(laneById['X']).toBeGreaterThan(0);
    expect(laneById['Y']).toBeGreaterThan(0);
  });

  it('later fork gets inner lane (closer to trunk)', () => {
    // root → A → B → C → D(current)
    // early branch from A: A → E1 → E2
    // late branch from C: C → L1
    const layout = buildRevisionTreeLayout(
      [
        rev('root', null, '2024-01-01T00:00:00Z'),
        rev('A', 'root', '2024-01-02T00:00:00Z'),
        rev('E1', 'A', '2024-01-03T00:00:00Z'),
        rev('B', 'A', '2024-01-04T00:00:00Z'),
        rev('E2', 'E1', '2024-01-05T00:00:00Z'),
        rev('C', 'B', '2024-01-06T00:00:00Z'),
        rev('L1', 'C', '2024-01-07T00:00:00Z'),
        rev('D', 'C', '2024-01-08T00:00:00Z'),
      ],
      'asc',
      'D',
    );

    const laneById = Object.fromEntries(layout.nodes.map((n) => [n.id, n.lane]));
    // Trunk on lane 0
    expect(laneById['root']).toBe(0);
    expect(laneById['D']).toBe(0);
    // Late fork (from C) should have smaller lane than early fork (from A)
    expect(laneById['L1']).toBeLessThan(laneById['E1']);
  });

  it('long branch crossing avoidance: late short branch does not cross early long branch', () => {
    // root → A → B → C → D(current)
    // early branch from A: A → E1 → E2 → E3 (long)
    // late branch from C: C → L1 (short)
    const layout = buildRevisionTreeLayout(
      [
        rev('root', null, '2024-01-01T00:00:00Z'),
        rev('A', 'root', '2024-01-02T00:00:00Z'),
        rev('E1', 'A', '2024-01-03T00:00:00Z'),
        rev('B', 'A', '2024-01-04T00:00:00Z'),
        rev('E2', 'E1', '2024-01-05T00:00:00Z'),
        rev('C', 'B', '2024-01-06T00:00:00Z'),
        rev('E3', 'E2', '2024-01-07T00:00:00Z'),
        rev('L1', 'C', '2024-01-08T00:00:00Z'),
        rev('D', 'C', '2024-01-09T00:00:00Z'),
      ],
      'asc',
      'D',
    );

    const laneById = Object.fromEntries(layout.nodes.map((n) => [n.id, n.lane]));
    // Late fork (L1) lane < early fork (E1) lane → no crossing
    expect(laneById['L1']).toBeLessThan(laneById['E1']);
    // E1, E2, E3 should all be on the same lane (branch continuation)
    expect(laneById['E1']).toBe(laneById['E2']);
    expect(laneById['E2']).toBe(laneById['E3']);
  });

  it('sub-branches within branches expand outward', () => {
    // root → A → B(current)
    // branch from A: A → X → X1, X → X2
    const layout = buildRevisionTreeLayout(
      [
        rev('root', null, '2024-01-01T00:00:00Z'),
        rev('A', 'root', '2024-01-02T00:00:00Z'),
        rev('X', 'A', '2024-01-03T00:00:00Z'),
        rev('B', 'A', '2024-01-04T00:00:00Z'),
        rev('X1', 'X', '2024-01-05T00:00:00Z'),
        rev('X2', 'X', '2024-01-06T00:00:00Z'),
      ],
      'asc',
      'B',
    );

    const laneById = Object.fromEntries(layout.nodes.map((n) => [n.id, n.lane]));
    // trunk on lane 0
    expect(laneById['root']).toBe(0);
    expect(laneById['A']).toBe(0);
    expect(laneById['B']).toBe(0);
    // X inherits a branch lane; X1 inherits X's lane; X2 gets a new outer lane
    expect(laneById['X']).toBeGreaterThan(0);
    expect(laneById['X1']).toBe(laneById['X']);
    expect(laneById['X2']).toBeGreaterThan(laneById['X']);
  });

  it('fallback: no currentRevisionId still works (first child inherits lane)', () => {
    const layout = buildRevisionTreeLayout(
      [
        rev('root', null, '2024-01-01T00:00:00Z'),
        rev('a', 'root', '2024-01-02T00:00:00Z'),
        rev('b', 'root', '2024-01-03T00:00:00Z'),
        rev('c', 'a', '2024-01-04T00:00:00Z'),
      ],
      'asc',
    );

    const laneById = Object.fromEntries(layout.nodes.map((n) => [n.id, n.lane]));
    expect(layout.trunkIds.size).toBe(0);
    expect(laneById['root']).toBe(0);
    // first child (a) inherits lane 0
    expect(laneById['a']).toBe(0);
    expect(laneById['c']).toBe(0);
    expect(laneById['b']).toBe(1);
  });

  it('missing parent in trunk chain: trunk is partial but correct', () => {
    // A(missing) → B → C → D(current)
    // B's parent is A which is not in the list
    const layout = buildRevisionTreeLayout(
      [
        rev('B', 'A', '2024-01-02T00:00:00Z'),
        rev('C', 'B', '2024-01-03T00:00:00Z'),
        rev('D', 'C', '2024-01-04T00:00:00Z'),
      ],
      'asc',
      'D',
    );

    const laneById = Object.fromEntries(layout.nodes.map((n) => [n.id, n.lane]));
    // B, C, D are all on trunk (B is root since A is missing)
    expect(layout.trunkIds).toEqual(new Set(['B', 'C', 'D']));
    expect(laneById['B']).toBe(0);
    expect(laneById['C']).toBe(0);
    expect(laneById['D']).toBe(0);
    expect(layout.missingParentIds.has('A')).toBe(true);
  });

  it('currentRevisionId not in list: safe fallback with empty trunk', () => {
    const layout = buildRevisionTreeLayout(
      [rev('root', null, '2024-01-01T00:00:00Z'), rev('a', 'root', '2024-01-02T00:00:00Z')],
      'asc',
      'nonexistent',
    );

    expect(layout.trunkIds.size).toBe(0);
    // Should not crash, normal behavior
    const laneById = Object.fromEntries(layout.nodes.map((n) => [n.id, n.lane]));
    expect(laneById['root']).toBe(0);
    expect(laneById['a']).toBe(0);
  });

  it('returns trunkIds in layout', () => {
    const layout = buildRevisionTreeLayout(
      [rev('r1', null, '2024-01-01T00:00:00Z'), rev('r2', 'r1', '2024-01-02T00:00:00Z')],
      'asc',
      'r2',
    );

    expect(layout.trunkIds).toEqual(new Set(['r1', 'r2']));
  });

  it('handles empty revisions list', () => {
    const layout = buildRevisionTreeLayout([], 'asc', 'anything');
    expect(layout.nodes).toEqual([]);
    expect(layout.laneCount).toBe(1);
    expect(layout.trunkIds.size).toBe(0);
  });

  it('multiple roots: trunk root on lane 0, other roots on higher lanes', () => {
    // Two roots: root1 and root2. trunk passes through root1.
    const layout = buildRevisionTreeLayout(
      [
        rev('root1', null, '2024-01-01T00:00:00Z'),
        rev('root2', null, '2024-01-02T00:00:00Z'),
        rev('a', 'root1', '2024-01-03T00:00:00Z'),
      ],
      'asc',
      'a',
    );

    const laneById = Object.fromEntries(layout.nodes.map((n) => [n.id, n.lane]));
    expect(laneById['root1']).toBe(0);
    expect(laneById['a']).toBe(0);
    expect(laneById['root2']).toBeGreaterThan(0);
  });
});
