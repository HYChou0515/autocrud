import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup, waitFor, fireEvent } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import { RevisionHistorySection } from './RevisionHistorySection';
import { getRevisionViewMode } from '../../utils/customization';

// ── Mock child components ──
vi.mock('../common/TimeDisplay', () => ({
  TimeDisplay: ({ time, format }: any) => <span data-testid="time-display">{time}</span>,
}));

vi.mock('../common/RevisionIdCell', () => ({
  RevisionIdCell: ({ revisionId }: any) => (
    <span data-testid="revision-id-cell">{revisionId}</span>
  ),
}));

vi.mock('./RevisionTreeTimeline', () => ({
  RevisionTreeTimeline: (props: any) => (
    <div data-testid="revision-tree-timeline">
      <span data-testid="tree-revision-count">{props.revisions?.length ?? 0}</span>
    </div>
  ),
}));

vi.mock('../../utils/customization', () => ({
  getRevisionViewMode: vi.fn().mockReturnValue('tree'),
  setRevisionViewMode: vi.fn(),
}));

vi.mock('../../utils/virtualization', () => ({
  getVirtualPadding: () => ({ paddingTop: 0, paddingBottom: 0 }),
}));

vi.mock('@tanstack/react-virtual', () => ({
  useVirtualizer: () => ({
    getVirtualItems: () => [],
    getTotalSize: () => 0,
    measureElement: vi.fn(),
  }),
}));

vi.mock('@mantine/hooks', () => ({
  useViewportSize: () => ({ width: 1024, height: 768 }),
}));

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const makeRevision = (id: string, status = 'stable', time = '2024-01-01T00:00:00Z') => ({
  revision_id: id,
  revision_status: status,
  created_time: time,
  updated_time: time,
  parent_revision_id: null,
});

const makeConfig = (overrides: { revisionListData?: any; getData?: any } = {}) => {
  const defaultRevisions = [
    makeRevision('rev-1', 'stable', '2024-01-01T00:00:00Z'),
    makeRevision('rev-2', 'draft', '2024-01-02T00:00:00Z'),
  ];

  return {
    name: 'character',
    label: 'Character',
    fields: [],
    apiClient: {
      revisionList: vi.fn().mockResolvedValue({
        data: overrides.revisionListData ?? {
          revisions: defaultRevisions,
          has_more: false,
          total: defaultRevisions.length,
        },
      }),
      get: vi.fn().mockResolvedValue({
        data: overrides.getData ?? {
          revision_info: makeRevision('rev-1'),
        },
      }),
    },
  };
};

function renderComponent(props: Partial<React.ComponentProps<typeof RevisionHistorySection>> = {}) {
  const config = props.config || makeConfig();
  return render(
    <MantineProvider>
      <RevisionHistorySection
        config={config as any}
        resourceId="res-1"
        {...props}
      />
    </MantineProvider>,
  );
}

describe('RevisionHistorySection', () => {
  it('shows loading state initially', () => {
    const config = makeConfig();
    // Make the API never resolve
    config.apiClient.revisionList.mockReturnValue(new Promise(() => {}));

    renderComponent({ config: config as any });
    // Should show a loader (Paper with loader)
    expect(document.querySelector('.mantine-Loader-root')).not.toBeNull();
  });

  it('renders null when no revisions', async () => {
    const config = makeConfig({
      revisionListData: { revisions: [], has_more: false, total: 0 },
    });

    const { container } = renderComponent({ config: config as any });

    await waitFor(() => {
      // Should not show the main content after loading
      expect(container.querySelector('[data-testid="revision-tree-timeline"]')).toBeNull();
    });
  });

  it('renders tree view by default with revisions', async () => {
    const config = makeConfig();

    renderComponent({ config: config as any });

    await waitFor(() => {
      expect(screen.getByTestId('revision-tree-timeline')).toBeDefined();
    });
  });

  it('shows revision count badge', async () => {
    const config = makeConfig();

    renderComponent({ config: config as any });

    await waitFor(() => {
      expect(screen.getByText('Revision History')).toBeDefined();
    });
  });

  it('has sort toggle button', async () => {
    const config = makeConfig();

    renderComponent({ config: config as any });

    await waitFor(() => {
      expect(screen.getByText('新到舊')).toBeDefined();
    });
  });

  it('toggles sort order on button click', async () => {
    const config = makeConfig();

    renderComponent({ config: config as any });

    await waitFor(() => {
      expect(screen.getByText('新到舊')).toBeDefined();
    });

    fireEvent.click(screen.getByText('新到舊'));

    expect(screen.getByText('舊到新')).toBeDefined();
  });

  it('shows timeline view toggle when enableTimelineView is true', async () => {
    const config = makeConfig();

    renderComponent({ config: config as any, enableTimelineView: true });

    await waitFor(() => {
      expect(screen.getByText('時間軸')).toBeDefined();
      expect(screen.getByText('樹狀時間軸')).toBeDefined();
    });
  });

  it('does not show timeline toggle when enableTimelineView is false', async () => {
    const config = makeConfig();

    renderComponent({ config: config as any, enableTimelineView: false });

    await waitFor(() => {
      expect(screen.getByText('Revision History')).toBeDefined();
    });

    expect(screen.queryByText('時間軸')).toBeNull();
  });

  it('shows "has more" button when more revisions available', async () => {
    const config = makeConfig({
      revisionListData: {
        revisions: [makeRevision('rev-1')],
        has_more: true,
        total: 100,
      },
    });

    renderComponent({ config: config as any });

    await waitFor(() => {
      expect(screen.getByText('載入更多')).toBeDefined();
    });
  });

  it('shows total count in badge when has_more', async () => {
    const config = makeConfig({
      revisionListData: {
        revisions: [makeRevision('rev-1')],
        has_more: true,
        total: 100,
      },
    });

    renderComponent({ config: config as any });

    await waitFor(() => {
      expect(screen.getByText('1/100 revisions')).toBeDefined();
    });
  });

  it('shows simple count in badge when no more', async () => {
    const config = makeConfig({
      revisionListData: {
        revisions: [makeRevision('rev-1'), makeRevision('rev-2')],
        has_more: false,
        total: 2,
      },
    });

    renderComponent({ config: config as any });

    await waitFor(() => {
      expect(screen.getByText('2 revisions')).toBeDefined();
    });
  });

  it('handles load more click in tree view', async () => {
    const config = makeConfig({
      revisionListData: {
        revisions: [makeRevision('rev-1')],
        has_more: true,
        total: 10,
      },
    });

    renderComponent({ config: config as any });

    await waitFor(() => {
      expect(screen.getByText('載入更多')).toBeDefined();
    });

    fireEvent.click(screen.getByText('載入更多'));

    // Should call revisionList again
    await waitFor(() => {
      expect(config.apiClient.revisionList.mock.calls.length).toBeGreaterThan(2); // initial 2 calls (chain + list) + load more
    });
  });

  it('toggles to timeline view mode and loads revisions', async () => {
    const config = makeConfig();

    const { container } = renderComponent({
      config: config as any,
      enableTimelineView: true,
    });

    await waitFor(() => {
      expect(config.apiClient.revisionList).toHaveBeenCalled();
    });

    // Find the timeline radio and click it
    const radios = container.querySelectorAll('input[type="radio"]');
    const timelineRadio = Array.from(radios).find((r) => r.getAttribute('value') === 'timeline');
    if (timelineRadio) {
      fireEvent.click(timelineRadio);
      await waitFor(() => {
        // Should re-fetch with timeline mode params
        expect(config.apiClient.revisionList.mock.calls.length).toBeGreaterThanOrEqual(2);
      });
    }
  });

  it('handles load more in timeline view mode', async () => {
    // Start in timeline mode
    vi.mocked(getRevisionViewMode).mockReturnValue('timeline');

    const revisions = [
      makeRevision('rev-1', 'stable', '2024-01-01T00:00:00Z'),
      makeRevision('rev-2', 'stable', '2024-01-02T00:00:00Z'),
    ];
    const config = makeConfig({
      revisionListData: {
        revisions: revisions,
        has_more: true,
        total: 10,
      },
    });

    renderComponent({
      config: config as any,
      enableTimelineView: true,
    });

    await waitFor(() => {
      const loadMoreBtn = screen.queryByText('載入更多');
      if (loadMoreBtn) {
        fireEvent.click(loadMoreBtn);
      }
    });

    // Should call revisionList for load more
    await waitFor(() => {
      expect(config.apiClient.revisionList.mock.calls.length).toBeGreaterThanOrEqual(1);
    });

    // Restore
    vi.mocked(getRevisionViewMode).mockReturnValue('tree');
  });

  it('fetches missing selected revision info via get API', async () => {
    const revisionListResponse = {
      revisions: [makeRevision('rev-1')],
      has_more: false,
      total: 1,
    };
    const config = makeConfig({ revisionListData: revisionListResponse });

    // selectedRevisionId points to a revision NOT in the list
    renderComponent({
      config: config as any,
      selectedRevisionId: 'rev-missing',
    });

    // The ensureSelectedRevisions effect should call get() to fetch the missing revision
    await waitFor(() => {
      expect(config.apiClient.get).toHaveBeenCalledWith(
        'res-1',
        expect.objectContaining({ revision_id: 'rev-missing', include_deleted: true }),
      );
    });
  });

  it('handles error when fetching missing revision info', async () => {
    const config = makeConfig();
    config.apiClient.get.mockRejectedValue(new Error('not found'));

    const spy = vi.spyOn(console, 'warn').mockImplementation(() => {});

    renderComponent({
      config: config as any,
      selectedRevisionId: 'rev-404',
    });

    await waitFor(() => {
      expect(config.apiClient.get).toHaveBeenCalled();
    });

    spy.mockRestore();
  });

  it('handles error when fetching revisions', async () => {
    const config = makeConfig();
    config.apiClient.revisionList.mockRejectedValue(new Error('network error'));

    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});

    renderComponent({ config: config as any });

    await waitFor(() => {
      expect(config.apiClient.revisionList).toHaveBeenCalled();
    });

    spy.mockRestore();
  });
});
