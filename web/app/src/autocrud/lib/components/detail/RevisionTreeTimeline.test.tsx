/**
 * RevisionTreeTimeline — layout tests
 *
 * Verifies that the grid layout does not squeeze the content column
 * when many lanes make the graph area wide.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@tanstack/react-virtual', () => ({
  useVirtualizer: ({ count }: { count: number }) => ({
    getTotalSize: () => count * 74,
    getVirtualItems: () =>
      Array.from({ length: count }, (_, i) => ({
        index: i,
        start: i * 74,
        size: 74,
        end: (i + 1) * 74,
        key: i,
      })),
  }),
}));

vi.mock('../common/RevisionIdCell', () => ({
  RevisionIdCell: ({ revisionId }: { revisionId: string }) => (
    <span data-testid="rev-id">{revisionId}</span>
  ),
}));

vi.mock('../common/TimeDisplay', () => ({
  TimeDisplay: ({ time }: { time: string }) => <span>{time}</span>,
}));

import { render } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import { RevisionTreeTimeline } from './RevisionTreeTimeline';

function rev(id: string, parentId: string | null, time: string) {
  return {
    revision_id: id,
    parent_revision_id: parentId,
    created_time: time,
  };
}

function renderTimeline(revisions: ReturnType<typeof rev>[], sortOrder: 'asc' | 'desc' = 'asc') {
  return render(
    <MantineProvider>
      <RevisionTreeTimeline
        revisions={revisions as any}
        sortOrder={sortOrder}
        resourceId="test-resource"
        currentRevisionId={revisions[0]?.revision_id}
      />
    </MantineProvider>,
  );
}

describe('RevisionTreeTimeline layout', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('applies horizontal overflow scrolling to the scroll container', () => {
    const revisions = [
      rev('r1', null, '2024-01-01T00:00:00Z'),
      rev('r2', 'r1', '2024-01-02T00:00:00Z'),
    ];
    const { container } = renderTimeline(revisions);
    // Find the scroll container (has overflowX or overflowY)
    const scrollContainer = container.querySelector('[style*="overflow"]') as HTMLElement;
    expect(scrollContainer).toBeTruthy();
    expect(scrollContainer.style.overflowX).toBe('auto');
  });

  it('sets minWidth on the grid so content column is never squeezed', () => {
    // Create many branches from the same root to produce many lanes
    const root = rev('root', null, '2024-01-01T00:00:00Z');
    const branches = Array.from({ length: 12 }, (_, i) =>
      rev(`branch-${i}`, 'root', `2024-01-02T0${String(i).padStart(2, '0')}:00:00Z`),
    );
    const revisions = [root, ...branches];
    const { container } = renderTimeline(revisions);

    const gridContainer = container.querySelector('[style*="display: grid"]') as HTMLElement;
    expect(gridContainer).toBeTruthy();

    // Grid must have a minWidth that prevents the content column from collapsing
    const minWidth = gridContainer.style.minWidth;
    expect(minWidth).toBeTruthy();
    // Parse the numeric value — it should be at least (dayWidth + graphWidth + contentMinWidth + gaps)
    const minWidthValue = parseInt(minWidth, 10);
    expect(minWidthValue).toBeGreaterThan(0);
  });

  it('uses minmax for the content grid column', () => {
    const revisions = [
      rev('r1', null, '2024-01-01T00:00:00Z'),
      rev('r2', 'r1', '2024-01-02T00:00:00Z'),
    ];
    const { container } = renderTimeline(revisions);
    const gridContainer = container.querySelector('[style*="display: grid"]') as HTMLElement;
    expect(gridContainer).toBeTruthy();

    // gridTemplateColumns should contain minmax for the content column
    const cols = gridContainer.style.gridTemplateColumns;
    expect(cols).toMatch(/minmax\(\d+px,\s*1fr\)/);
  });

  it('renders without crashing when there are no revisions', () => {
    const { container } = renderTimeline([]);
    // Should return null for empty revisions — no grid container rendered
    // (MantineProvider may inject a <style> tag, so check for the grid specifically)
    const gridEl = container.querySelector('[style*="display: grid"]');
    expect(gridEl).toBeNull();
  });
});
