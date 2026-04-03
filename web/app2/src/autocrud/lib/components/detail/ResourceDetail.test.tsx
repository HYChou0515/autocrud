/**
 * ResourceDetail — unit tests for Rerun button
 *
 * Verifies that the Rerun button:
 * 1. Shows for job resources with failed status
 * 2. Shows for job resources with completed status
 * 3. Does not show for job resources with pending status
 * 4. Does not show for non-job resources
 * 5. Calls rerun on click
 * 6. Shows error notification on rerun failure
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { ResourceConfig, ResourceField } from '../../resources';
import type { UseResourceDetailResult } from '../../hooks/useResourceDetail';

// Mock return value for useResourceDetail
let mockDetailResult: UseResourceDetailResult<any>;

// Mutable mock return value for useFieldDepth
let mockFieldDepthResult = {
  maxAvailableDepth: 1,
  depth: 1,
  setDepth: vi.fn(),
  visibleFields: [] as ResourceField[],
  collapsedGroups: [] as any[],
};

vi.mock('../../hooks/useResourceDetail', () => ({
  useResourceDetail: () => mockDetailResult,
}));

vi.mock('../../hooks/useFieldDepth', () => ({
  useFieldDepth: () => mockFieldDepthResult,
}));

vi.mock('../form/ResourceForm', () => ({
  ResourceForm: (props: any) => (
    <div
      data-testid="edit-form"
      data-submitting={props.submitting ? 'true' : 'false'}
      data-submit-label={props.submitLabel}
    >
      <button data-testid="edit-submit" onClick={() => props.onSubmit?.({})}>
        {props.submitLabel}
      </button>
      <button data-testid="edit-cancel" onClick={props.onCancel}>
        Cancel
      </button>
    </div>
  ),
}));

vi.mock('./MetadataSection', () => ({
  MetadataSection: () => null,
}));

vi.mock('./RevisionHistorySection', () => ({
  RevisionHistorySection: () => null,
}));

vi.mock('../common/ResourceIdCell', () => ({
  ResourceIdCell: () => null,
}));

vi.mock('../common/RevisionIdCell', () => ({
  RevisionIdCell: () => null,
}));

vi.mock('../field/DetailFieldRenderer', () => ({
  DetailFieldRenderer: () => null,
}));

vi.mock('../job/JobStatusSection', () => ({
  JobStatusSection: () => null,
  JOB_STATUS_FIELDS: new Set(['status', 'retries', 'errmsg']),
  JOB_STATUS_COLORS: {} as Record<string, string>,
}));

vi.mock('../job/JobFieldsSection', () => ({
  JobFieldsSection: () => null,
}));

vi.mock('../../utils/errorNotification', () => ({
  showErrorNotification: vi.fn(),
  extractUniqueConflict: vi.fn().mockReturnValue(null),
}));

vi.mock('@tanstack/react-router', () => ({
  Link: (props: any) => (
    <a data-testid="back-link" data-to={props.to}>
      {props.children}
    </a>
  ),
  useNavigate: () => vi.fn(),
}));

// Mock async create job helpers — use vi.hoisted so the variable is available in the mock factory
const { mockAsyncCreateJobs } = vi.hoisted(() => {
  const mockAsyncCreateJobs: Record<string, string> = {};
  return { mockAsyncCreateJobs };
});

vi.mock('../../resources', async (importOriginal) => {
  const actual = (await importOriginal()) as any;
  return {
    ...actual,
    isAsyncCreateJob: (name: string) => name in mockAsyncCreateJobs,
    asyncCreateJobs: mockAsyncCreateJobs,
  };
});

import React from 'react';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MantineProvider } from '@mantine/core';
import { ResourceDetail } from './ResourceDetail';
import { groupFieldsForDisplay, type DisplayGroup } from './ResourceDetail';
import { showErrorNotification } from '../../utils/errorNotification';

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <MantineProvider>{children}</MantineProvider>
    </QueryClientProvider>
  );
}

function makeField(name: string): ResourceField {
  return {
    name,
    label: name,
    type: 'string',
    isArray: false,
    isRequired: false,
    isNullable: false,
  };
}

function makeConfig(overrides?: Partial<ResourceConfig<any>>): ResourceConfig<any> {
  return {
    name: 'test-job',
    label: 'Test Job',
    pluralLabel: 'Test Jobs',
    schema: 'TestJob',
    fields: [makeField('payload.command')],
    apiClient: {
      create: vi.fn(),
      list: vi.fn(),
      count: vi.fn(),
      get: vi.fn(),
      update: vi.fn(),
      delete: vi.fn(),
      permanentlyDelete: vi.fn(),
      restore: vi.fn(),
      revisionList: vi.fn(),
      switchRevision: vi.fn(),
      rerun: vi.fn().mockResolvedValue({ data: { resource_id: 'r1', revision_id: 'rev2' } }),
    },
    ...overrides,
  };
}

function makeMockDetail(dataOverrides: Record<string, any> = {}): UseResourceDetailResult<any> {
  return {
    resource: {
      data: {
        payload: { command: 'test' },
        status: 'failed',
        retries: 3,
        errmsg: 'boom',
        ...dataOverrides,
      },
      meta: {
        resource_id: 'r1',
        current_revision_id: 'rev1',
        schema_version: null,
        total_revision_count: 1,
        is_deleted: false,
        created_time: '2026-01-01T00:00:00Z',
        updated_time: '2026-01-01T00:00:00Z',
        created_by: 'test',
        updated_by: 'test',
      },
      revision_info: {
        uid: 'uid1',
        resource_id: 'r1',
        revision_id: 'rev1',
        parent_revision_id: null,
        parent_schema_version: null,
        schema_version: null,
        data_hash: 'abc',
        status: 'stable',
        created_time: '2026-01-01T00:00:00Z',
        updated_time: '2026-01-01T00:00:00Z',
        created_by: 'test',
        updated_by: 'test',
      },
    },
    loading: false,
    error: null,
    refresh: vi.fn(),
    update: vi.fn(),
    deleteResource: vi.fn(),
    permanentlyDelete: vi.fn(),
    restore: vi.fn(),
    switchRevision: vi.fn(),
    rerun: vi.fn().mockResolvedValue(undefined),
    logs: null,
    logsLoading: false,
    fetchLogs: vi.fn(),
    query: {} as any,
    isUpdatePending: false,
    isDeletePending: false,
    isRestorePending: false,
    isSwitchRevisionPending: false,
    isRerunPending: false,
  };
}

function renderDetail(config: ResourceConfig<any>, isJob = true) {
  return render(
    <ResourceDetail config={config} resourceId="r1" basePath={'/test' as any} isJob={isJob} />,
    { wrapper: createWrapper() },
  );
}

describe('ResourceDetail — Rerun button', () => {
  beforeEach(() => {
    cleanup();
    vi.mocked(showErrorNotification).mockReset();
  });

  it('shows Rerun button for job with failed status', () => {
    mockDetailResult = makeMockDetail({ status: 'failed' });
    const config = makeConfig();
    renderDetail(config, true);
    expect(screen.getByText('Rerun')).toBeTruthy();
  });

  it('shows Rerun button for job with completed status', () => {
    mockDetailResult = makeMockDetail({ status: 'completed' });
    const config = makeConfig();
    renderDetail(config, true);
    expect(screen.getByText('Rerun')).toBeTruthy();
  });

  it('does NOT show Rerun button for job with pending status', () => {
    mockDetailResult = makeMockDetail({ status: 'pending' });
    const config = makeConfig();
    renderDetail(config, true);
    expect(screen.queryByText('Rerun')).toBeNull();
  });

  it('does NOT show Rerun button for job with processing status', () => {
    mockDetailResult = makeMockDetail({ status: 'processing' });
    const config = makeConfig();
    renderDetail(config, true);
    expect(screen.queryByText('Rerun')).toBeNull();
  });

  it('does NOT show Rerun button for non-job resources', () => {
    mockDetailResult = makeMockDetail({ status: 'completed' });
    const config = makeConfig();
    renderDetail(config, false);
    expect(screen.queryByText('Rerun')).toBeNull();
  });

  it('does NOT show Rerun button when apiClient.rerun is not defined', () => {
    mockDetailResult = makeMockDetail({ status: 'failed' });
    const config = makeConfig();
    delete (config.apiClient as any).rerun;
    renderDetail(config, true);
    expect(screen.queryByText('Rerun')).toBeNull();
  });

  it('calls rerun when Rerun button is clicked', async () => {
    const detail = makeMockDetail({ status: 'failed' });
    mockDetailResult = detail;
    const config = makeConfig();
    renderDetail(config, true);

    fireEvent.click(screen.getByText('Rerun'));

    await waitFor(() => {
      expect(detail.rerun).toHaveBeenCalled();
    });
  });

  it('does not crash when rerun fails (hook handles error notification)', async () => {
    const rerunError = new Error('Queue unavailable');
    const detail = makeMockDetail({ status: 'failed' });
    detail.rerun = vi.fn().mockRejectedValue(rerunError);
    mockDetailResult = detail;
    const config = makeConfig();
    renderDetail(config, true);

    fireEvent.click(screen.getByText('Rerun'));

    await waitFor(() => {
      expect(detail.rerun).toHaveBeenCalled();
    });

    // Error notification is now handled by the useResourceDetail hook,
    // not the component — so showErrorNotification is NOT called here.
    // The component simply delegates to rerun() which swallows errors.
  });
});

// ============================================================================
// groupFieldsForDisplay — pure function tests
// ============================================================================

describe('groupFieldsForDisplay', () => {
  it('returns empty array for empty input', () => {
    expect(groupFieldsForDisplay([])).toEqual([]);
  });

  it('renders all top-level fields as single groups', () => {
    const fields = [makeField('name'), makeField('age'), makeField('email')];
    const groups = groupFieldsForDisplay(fields);
    expect(groups).toHaveLength(3);
    expect(groups.every((g) => g.kind === 'single')).toBe(true);
  });

  it('groups dot-notation sub-fields under their parent', () => {
    const fields = [
      makeField('payload.event_type'),
      makeField('payload.event_x2.type'),
      makeField('payload.event_x2.good'),
      makeField('payload.event_x2.great'),
      makeField('payload.event_x3'),
    ];
    const groups = groupFieldsForDisplay(fields);

    // payload.event_type → single
    expect(groups[0]).toEqual({ kind: 'single', field: fields[0] });
    // payload.event_x2.* → nested group
    expect(groups[1].kind).toBe('nested');
    const nested = groups[1] as Extract<DisplayGroup, { kind: 'nested' }>;
    expect(nested.parentPath).toBe('payload.event_x2');
    expect(nested.parentLabel).toBe('Event X2');
    expect(nested.children).toHaveLength(3);
    expect(nested.children[0].name).toBe('payload.event_x2.type');
    // payload.event_x3 → single
    expect(groups[2]).toEqual({ kind: 'single', field: fields[4] });
  });

  it('handles multiple separate nested groups', () => {
    const fields = [
      makeField('payload.event_type'),
      makeField('payload.event_x2.type'),
      makeField('payload.event_x2.good'),
      makeField('payload.event_x3'),
      makeField('payload.event_x.type'),
      makeField('payload.event_x.good'),
      makeField('payload.event_x.great'),
      makeField('payload.extra_data'),
    ];
    const groups = groupFieldsForDisplay(fields);

    expect(groups).toHaveLength(5);
    expect(groups[0].kind).toBe('single'); // event_type
    expect(groups[1].kind).toBe('nested'); // event_x2.*
    expect(groups[2].kind).toBe('single'); // event_x3
    expect(groups[3].kind).toBe('nested'); // event_x.*
    expect(groups[4].kind).toBe('single'); // extra_data

    const g1 = groups[1] as Extract<DisplayGroup, { kind: 'nested' }>;
    expect(g1.parentLabel).toBe('Event X2');
    expect(g1.children).toHaveLength(2);

    const g3 = groups[3] as Extract<DisplayGroup, { kind: 'nested' }>;
    expect(g3.parentLabel).toBe('Event X');
    expect(g3.children).toHaveLength(3);
  });

  it('works for regular resource (no payload prefix)', () => {
    const fields = [
      makeField('name'),
      makeField('address.street'),
      makeField('address.city'),
      makeField('address.zip'),
      makeField('email'),
    ];
    const groups = groupFieldsForDisplay(fields);

    expect(groups).toHaveLength(3);
    expect(groups[0]).toEqual({ kind: 'single', field: fields[0] });
    expect(groups[1].kind).toBe('nested');
    const nested = groups[1] as Extract<DisplayGroup, { kind: 'nested' }>;
    expect(nested.parentLabel).toBe('Address');
    expect(nested.children).toHaveLength(3);
    expect(groups[2]).toEqual({ kind: 'single', field: fields[4] });
  });

  it('single deeper field still forms a nested group', () => {
    const fields = [
      makeField('payload.name'),
      makeField('payload.config.timeout'),
      makeField('payload.enabled'),
    ];
    const groups = groupFieldsForDisplay(fields);

    expect(groups).toHaveLength(3);
    expect(groups[0].kind).toBe('single');
    expect(groups[1].kind).toBe('nested');
    const nested = groups[1] as Extract<DisplayGroup, { kind: 'nested' }>;
    expect(nested.parentLabel).toBe('Config');
    expect(nested.children).toHaveLength(1);
    expect(groups[2].kind).toBe('single');
  });

  it('all fields at same depth → all single', () => {
    const fields = [makeField('payload.a'), makeField('payload.b'), makeField('payload.c')];
    const groups = groupFieldsForDisplay(fields);
    expect(groups).toHaveLength(3);
    expect(groups.every((g) => g.kind === 'single')).toBe(true);
  });
});

// ============================================================================
// ResourceDetail — customization props
// ============================================================================

describe('ResourceDetail — customization props', () => {
  beforeEach(() => {
    cleanup();
    vi.mocked(showErrorNotification).mockReset();
  });

  function renderDetailCustom(
    configOverrides: Partial<ResourceConfig<any>> = {},
    props: Record<string, any> = {},
    isJob = false,
  ) {
    mockDetailResult = makeMockDetail();
    const config = makeConfig(configOverrides);
    return render(
      <ResourceDetail
        config={config}
        resourceId="r1"
        basePath={'/test' as any}
        isJob={isJob}
        {...props}
      />,
      { wrapper: createWrapper() },
    );
  }

  // ── showEditButton ──

  it('shows Edit button by default', () => {
    renderDetailCustom();
    expect(screen.getByText('Edit')).toBeTruthy();
  });

  it('hides Edit button when showEditButton=false', () => {
    renderDetailCustom({}, { showEditButton: false });
    expect(screen.queryByText('Edit')).toBeNull();
  });

  it('hides Edit button via detailConfig', () => {
    renderDetailCustom({ detailConfig: { showEditButton: false } });
    expect(screen.queryByText('Edit')).toBeNull();
  });

  it('props override detailConfig for showEditButton', () => {
    renderDetailCustom({ detailConfig: { showEditButton: false } }, { showEditButton: true });
    expect(screen.getByText('Edit')).toBeTruthy();
  });

  // ── showDeleteButton ──

  it('shows Delete button by default', () => {
    renderDetailCustom();
    expect(screen.getByText('Delete')).toBeTruthy();
  });

  it('hides Delete button when showDeleteButton=false', () => {
    renderDetailCustom({}, { showDeleteButton: false });
    expect(screen.queryByText('Delete')).toBeNull();
  });

  // ── showRevisionHistory ──

  it('renders RevisionHistorySection by default (mock returns null but called)', () => {
    // The mock returns null but exists; the key is that it's called
    renderDetailCustom();
    // RevisionHistorySection is mocked to return null, so we can't check display
    // but we verified it renders without error
  });

  // ── showBackButton ──

  it('shows Back button by default', () => {
    renderDetailCustom();
    expect(screen.getByText('Back')).toBeTruthy();
  });

  it('hides Back button when showBackButton=false', () => {
    renderDetailCustom({}, { showBackButton: false });
    expect(screen.queryByText('Back')).toBeNull();
  });

  // ── title ──

  it('uses default title for non-job resource', () => {
    renderDetailCustom();
    // Default: "Test Job Detail" (from config.label)
    expect(screen.getByText('Test Job Detail')).toBeTruthy();
  });

  it('shows "Job Detail" for job resource', () => {
    renderDetailCustom({}, {}, true);
    expect(screen.getByText('Job Detail')).toBeTruthy();
  });

  it('uses custom title from prop', () => {
    renderDetailCustom({}, { title: 'Custom Title' });
    expect(screen.getByText('Custom Title')).toBeTruthy();
  });

  it('reads title from detailConfig', () => {
    renderDetailCustom({ detailConfig: { title: 'Config Title' } });
    expect(screen.getByText('Config Title')).toBeTruthy();
  });

  it('prop title overrides detailConfig.title', () => {
    renderDetailCustom({ detailConfig: { title: 'Config Title' } }, { title: 'Prop Title' });
    expect(screen.getByText('Prop Title')).toBeTruthy();
    expect(screen.queryByText('Config Title')).toBeNull();
  });

  // ── wrappedInContainer ──

  it('has Container by default', () => {
    const { container } = renderDetailCustom();
    const containerEl = container.querySelector('.mantine-Container-root');
    expect(containerEl).toBeTruthy();
  });

  it('skips Container when wrappedInContainer=false', () => {
    const { container } = renderDetailCustom({}, { wrappedInContainer: false });
    const containerEl = container.querySelector('.mantine-Container-root');
    expect(containerEl).toBeNull();
  });

  // ── onClose ──

  it('uses onClose callback for Back button', () => {
    const onClose = vi.fn();
    renderDetailCustom({}, { onClose });
    fireEvent.click(screen.getByText('Back'));
    expect(onClose).toHaveBeenCalled();
  });

  // ── Combined config ──

  it('applies multiple detailConfig settings together', () => {
    renderDetailCustom({
      detailConfig: {
        showBackButton: false,
        showEditButton: false,
        showDeleteButton: false,
        title: 'Read-Only View',
      },
    });
    expect(screen.queryByText('Back')).toBeNull();
    expect(screen.queryByText('Edit')).toBeNull();
    expect(screen.queryByText('Delete')).toBeNull();
    expect(screen.getByText('Read-Only View')).toBeTruthy();
  });
});

// ============================================================================
// Async create job — back button navigates to parent resource
// ============================================================================
describe('ResourceDetail — async create job back button', () => {
  beforeEach(() => {
    cleanup();
    // Clear the mapping
    Object.keys(mockAsyncCreateJobs).forEach((k) => delete mockAsyncCreateJobs[k]);
  });

  it('shows back link pointing to job list for regular job resource', () => {
    mockDetailResult = makeMockDetail();

    const config = makeConfig({ name: 'pet-job' });
    render(
      <ResourceDetail
        config={config}
        resourceId="r1"
        basePath={'/autocrud-admin/pet-job' as any}
        isJob={true}
      />,
      { wrapper: createWrapper() },
    );

    const backLink = screen.getByTestId('back-link');
    expect(backLink.getAttribute('data-to')).toBe('/autocrud-admin/pet-job');
  });

  it('shows back link pointing to parent resource for async create job', () => {
    // Register this job as an async create job of "character"
    mockAsyncCreateJobs['new-char1-job'] = 'character';

    mockDetailResult = makeMockDetail();

    const config = makeConfig({ name: 'new-char1-job' });
    render(
      <ResourceDetail
        config={config}
        resourceId="r1"
        basePath={'/autocrud-admin/new-char1-job' as any}
        isJob={true}
      />,
      { wrapper: createWrapper() },
    );

    const backLink = screen.getByTestId('back-link');
    // Should navigate to parent (character), not to the job list
    expect(backLink.getAttribute('data-to')).toBe('/autocrud-admin/character');
  });
});

// ============================================================================
// ResourceDetail — handleDelete
// ============================================================================

describe('ResourceDetail — handleDelete', () => {
  beforeEach(() => {
    cleanup();
    Object.keys(mockAsyncCreateJobs).forEach((k) => delete mockAsyncCreateJobs[k]);
  });

  it('calls deleteResource when user confirms', () => {
    const detail = makeMockDetail();
    mockDetailResult = detail;
    window.confirm = vi.fn(() => true);

    renderDetail(makeConfig());
    fireEvent.click(screen.getByText('Delete'));

    expect(window.confirm).toHaveBeenCalled();
    expect(detail.deleteResource).toHaveBeenCalled();
  });

  it('does NOT call deleteResource when user cancels', () => {
    const detail = makeMockDetail();
    mockDetailResult = detail;
    window.confirm = vi.fn(() => false);

    renderDetail(makeConfig());
    fireEvent.click(screen.getByText('Delete'));

    expect(detail.deleteResource).not.toHaveBeenCalled();
  });
});

// ============================================================================
// ResourceDetail — handlePermanentlyDelete
// ============================================================================

describe('ResourceDetail — handlePermanentlyDelete', () => {
  beforeEach(() => {
    cleanup();
    Object.keys(mockAsyncCreateJobs).forEach((k) => delete mockAsyncCreateJobs[k]);
  });

  function renderDeletedDetail() {
    const detail = makeMockDetail();
    detail.resource!.meta.is_deleted = true;
    detail.permanentlyDelete = vi.fn().mockResolvedValue(undefined);
    mockDetailResult = detail;
    const config = makeConfig();
    render(<ResourceDetail config={config} resourceId="r1" basePath={'/test' as any} />, {
      wrapper: createWrapper(),
    });
    return detail;
  }

  it('calls permanentlyDelete and navigates when user confirms', async () => {
    const detail = renderDeletedDetail();
    window.confirm = vi.fn(() => true);

    fireEvent.click(screen.getByText('Permanently Delete'));

    await waitFor(() => {
      expect(detail.permanentlyDelete).toHaveBeenCalled();
    });
  });

  it('does NOT call permanentlyDelete when user cancels', () => {
    const detail = renderDeletedDetail();
    window.confirm = vi.fn(() => false);

    fireEvent.click(screen.getByText('Permanently Delete'));
    expect(detail.permanentlyDelete).not.toHaveBeenCalled();
  });

  it('handles permanentlyDelete error gracefully', async () => {
    const detail = makeMockDetail();
    detail.resource!.meta.is_deleted = true;
    detail.permanentlyDelete = vi.fn().mockRejectedValue(new Error('fail'));
    mockDetailResult = detail;
    window.confirm = vi.fn(() => true);

    const config = makeConfig();
    render(<ResourceDetail config={config} resourceId="r1" basePath={'/test' as any} />, {
      wrapper: createWrapper(),
    });

    fireEvent.click(screen.getByText('Permanently Delete'));

    await waitFor(() => {
      expect(detail.permanentlyDelete).toHaveBeenCalled();
    });
    // Should not throw — catch block swallows error
  });
});

// ============================================================================
// ResourceDetail — handleRestore
// ============================================================================

describe('ResourceDetail — handleRestore', () => {
  beforeEach(() => {
    cleanup();
    Object.keys(mockAsyncCreateJobs).forEach((k) => delete mockAsyncCreateJobs[k]);
  });

  it('calls restore when Restore button is clicked', () => {
    const detail = makeMockDetail();
    detail.resource!.meta.is_deleted = true;
    mockDetailResult = detail;

    renderDetail(makeConfig());
    fireEvent.click(screen.getByText('Restore'));
    expect(detail.restore).toHaveBeenCalled();
  });
});

// ============================================================================
// ResourceDetail — handleRevert (historical revision)
// ============================================================================

describe('ResourceDetail — handleRevert', () => {
  beforeEach(() => {
    cleanup();
    Object.keys(mockAsyncCreateJobs).forEach((k) => delete mockAsyncCreateJobs[k]);
  });

  it('calls switchRevision when user confirms revert', async () => {
    const detail = makeMockDetail();
    detail.switchRevision = vi.fn().mockResolvedValue(undefined);
    mockDetailResult = detail;
    window.confirm = vi.fn(() => true);

    const config = makeConfig();
    render(
      <ResourceDetail
        config={config}
        resourceId="r1"
        basePath={'/test' as any}
        initialRevision="rev-old"
      />,
      { wrapper: createWrapper() },
    );

    // Should show "Revert to this revision" button for historical revision
    const revertBtn = screen.getByText('Revert to this revision');
    fireEvent.click(revertBtn);

    await waitFor(() => {
      expect(detail.switchRevision).toHaveBeenCalledWith('rev-old');
    });
  });

  it('does NOT call switchRevision when user cancels revert', () => {
    const detail = makeMockDetail();
    detail.switchRevision = vi.fn();
    mockDetailResult = detail;
    window.confirm = vi.fn(() => false);

    const config = makeConfig();
    render(
      <ResourceDetail
        config={config}
        resourceId="r1"
        basePath={'/test' as any}
        initialRevision="rev-old"
      />,
      { wrapper: createWrapper() },
    );

    fireEvent.click(screen.getByText('Revert to this revision'));
    expect(detail.switchRevision).not.toHaveBeenCalled();
  });

  it('handles switchRevision error gracefully', async () => {
    const detail = makeMockDetail();
    detail.switchRevision = vi.fn().mockRejectedValue(new Error('fail'));
    mockDetailResult = detail;
    window.confirm = vi.fn(() => true);

    const config = makeConfig();
    render(
      <ResourceDetail
        config={config}
        resourceId="r1"
        basePath={'/test' as any}
        initialRevision="rev-old"
      />,
      { wrapper: createWrapper() },
    );

    fireEvent.click(screen.getByText('Revert to this revision'));

    await waitFor(() => {
      expect(detail.switchRevision).toHaveBeenCalled();
    });
  });
});

// ============================================================================
// ResourceDetail — handleEdit
// ============================================================================

describe('ResourceDetail — handleEdit', () => {
  beforeEach(() => {
    cleanup();
    Object.keys(mockAsyncCreateJobs).forEach((k) => delete mockAsyncCreateJobs[k]);
    vi.mocked(showErrorNotification).mockReset();
  });

  it('calls update on edit form submission', async () => {
    const detail = makeMockDetail();
    detail.update = vi.fn().mockResolvedValue(undefined);
    mockDetailResult = detail;

    renderDetail(makeConfig());

    // Open edit modal
    fireEvent.click(screen.getByText('Edit'));

    await waitFor(() => {
      const submitBtn = screen.getByTestId('edit-submit');
      fireEvent.click(submitBtn);
    });

    await waitFor(() => {
      expect(detail.update).toHaveBeenCalled();
    });
  });

  it('shows error notification when update fails', async () => {
    const detail = makeMockDetail();
    detail.update = vi.fn().mockRejectedValue(new Error('Update failed'));
    mockDetailResult = detail;

    renderDetail(makeConfig());
    fireEvent.click(screen.getByText('Edit'));

    await waitFor(() => {
      fireEvent.click(screen.getByTestId('edit-submit'));
    });

    await waitFor(() => {
      expect(showErrorNotification).toHaveBeenCalled();
    });
  });

  it('closes edit modal on cancel', async () => {
    mockDetailResult = makeMockDetail();
    renderDetail(makeConfig());

    fireEvent.click(screen.getByText('Edit'));

    await waitFor(() => {
      const cancelBtn = screen.getByTestId('edit-cancel');
      fireEvent.click(cancelBtn);
    });

    // Modal should close — edit form should no longer be visible
    await waitFor(() => {
      expect(screen.queryByTestId('edit-form')).toBeNull();
    });
  });
});

// ============================================================================
// ResourceDetail — field display rendering with visible fields
// ============================================================================

describe('ResourceDetail — field display rendering', () => {
  beforeEach(() => {
    cleanup();
    Object.keys(mockAsyncCreateJobs).forEach((k) => delete mockAsyncCreateJobs[k]);
  });

  it('displays field labels from visibleFields', () => {
    // Override the mutable mock to return some fields
    mockFieldDepthResult = {
      maxAvailableDepth: 1,
      depth: 1,
      setDepth: vi.fn(),
      visibleFields: [makeField('name'), makeField('level')],
      collapsedGroups: [],
    };

    const detail = makeMockDetail({ name: 'Hero', level: 42 });
    mockDetailResult = detail;

    const config = makeConfig({
      fields: [makeField('name'), makeField('level')],
    });
    render(<ResourceDetail config={config} resourceId="r1" basePath={'/test' as any} />, {
      wrapper: createWrapper(),
    });

    // Field labels should be visible in the table
    expect(screen.getByText('name')).toBeTruthy();
    expect(screen.getByText('level')).toBeTruthy();

    // Reset mock
    mockFieldDepthResult = {
      maxAvailableDepth: 1,
      depth: 1,
      setDepth: vi.fn(),
      visibleFields: [],
      collapsedGroups: [],
    };
  });

  it('renders loading state', () => {
    mockDetailResult = {
      ...makeMockDetail(),
      loading: true,
      resource: null,
    };

    const { container } = renderDetail(makeConfig());
    expect(container.querySelector('.mantine-Loader-root')).toBeTruthy();
  });

  it('renders error state', () => {
    mockDetailResult = {
      ...makeMockDetail(),
      error: new Error('Not found'),
      resource: null,
    };

    renderDetail(makeConfig());
    expect(screen.getByText(/Not found/)).toBeTruthy();
  });

  it('renders error state with default message when error has no message', () => {
    mockDetailResult = {
      ...makeMockDetail(),
      error: null,
      resource: null,
    };

    renderDetail(makeConfig());
    expect(screen.getByText(/Resource not found/)).toBeTruthy();
  });

  it('shows deleted alert for deleted resource', () => {
    const detail = makeMockDetail();
    detail.resource!.meta.is_deleted = true;
    mockDetailResult = detail;

    renderDetail(makeConfig());
    expect(screen.getByText('This resource has been deleted.')).toBeTruthy();
  });

  it('shows job status badge for job resource', () => {
    mockDetailResult = makeMockDetail({ status: 'completed' });
    renderDetail(makeConfig(), true);
    expect(screen.getByText('COMPLETED')).toBeTruthy();
  });

  it('displays displayNameField value when present', () => {
    const detail = makeMockDetail({ display_name: 'My Hero' });
    mockDetailResult = detail;

    const config = makeConfig({ displayNameField: 'display_name' });
    render(<ResourceDetail config={config} resourceId="r1" basePath={'/test' as any} />, {
      wrapper: createWrapper(),
    });

    expect(screen.getByText('My Hero')).toBeTruthy();
  });
});

// ============================================================================
// ResourceDetail — Edit form loading state regression
// ============================================================================

describe('ResourceDetail — edit form loading state regression', () => {
  beforeEach(() => {
    cleanup();
    Object.keys(mockAsyncCreateJobs).forEach((k) => delete mockAsyncCreateJobs[k]);
  });

  function openEditModal(isJob = false) {
    const config = makeConfig();
    const result = render(
      <ResourceDetail config={config} resourceId="r1" basePath={'/test' as any} isJob={isJob} />,
      { wrapper: createWrapper() },
    );
    // Click Edit to open the modal
    fireEvent.click(screen.getByText('Edit'));
    return result;
  }

  it('passes submitting=false to ResourceForm when update is not pending', async () => {
    mockDetailResult = makeMockDetail();
    mockDetailResult.isUpdatePending = false;

    openEditModal();

    await waitFor(() => {
      const form = screen.getByTestId('edit-form');
      expect(form.getAttribute('data-submitting')).toBe('false');
    });
  });

  it('passes submitting=true to ResourceForm when update mutation is in-flight', async () => {
    mockDetailResult = makeMockDetail();
    mockDetailResult.isUpdatePending = true;

    openEditModal();

    await waitFor(() => {
      const form = screen.getByTestId('edit-form');
      expect(form.getAttribute('data-submitting')).toBe('true');
    });
  });
});

// ============================================================================
// ResourceDetail — update action job query invalidation
// ============================================================================

vi.mock('@mantine/notifications', () => ({
  notifications: { show: vi.fn() },
}));

// Spy on queryClient.invalidateQueries — we capture the query client from the provider
const { mockInvalidateQueries: mockInvalidate } = vi.hoisted(() => ({
  mockInvalidateQueries: vi.fn(),
}));

// Re-import after mocks are set up
const { notifications: notifModule } = await import('@mantine/notifications');

describe('ResourceDetail — update action invalidates job queries', () => {
  beforeEach(() => {
    cleanup();
    mockInvalidate.mockClear();
    vi.mocked(notifModule.show).mockClear();
    Object.keys(mockAsyncCreateJobs).forEach((k) => delete mockAsyncCreateJobs[k]);
  });

  function makeUpdateConfig(
    actions: any[],
    overrides: Partial<ResourceConfig<any>> = {},
  ): ResourceConfig<any> {
    return makeConfig({
      name: 'character',
      label: 'Character',
      customUpdateActions: actions,
      ...overrides,
    });
  }

  it('invalidates job resource queries after job-mode update action', async () => {
    const apiMethod = vi.fn().mockResolvedValue({ data: { resource_id: 'r1' } });
    const detail = makeMockDetail();
    mockDetailResult = detail;

    const config = makeUpdateConfig([
      {
        name: 'level-up',
        label: 'Level Up',
        mode: 'update',
        fields: [],
        zodSchema: { parse: (v: any) => v, safeParse: (v: any) => ({ success: true, data: v }) },
        apiMethod,
        asyncMode: 'job',
        jobResourceName: 'level-up-job',
      },
    ]);

    // We spy on the QueryClient prototype to intercept invalidateQueries
    const spy = vi.spyOn(QueryClient.prototype, 'invalidateQueries');

    render(<ResourceDetail config={config} resourceId="r1" basePath={'/test' as any} />, {
      wrapper: createWrapper(),
    });

    // Open edit modal
    fireEvent.click(screen.getByText('Edit'));

    // Click the "Level Up" tab
    await waitFor(() => {
      const tab = screen.getByRole('tab', { name: 'Level Up' });
      fireEvent.click(tab);
    });

    // Click the action button
    await waitFor(() => {
      const buttons = screen.getAllByRole('button');
      const actionBtn = buttons.find((b) => b.textContent === 'Level Up');
      expect(actionBtn).toBeTruthy();
      fireEvent.click(actionBtn!);
    });

    await waitFor(() => {
      expect(apiMethod).toHaveBeenCalledWith('r1', {});
      // Should invalidate job queries
      const calls = spy.mock.calls;
      const jobInvalidation = calls.find((c) => JSON.stringify(c[0]).includes('level-up-job'));
      expect(jobInvalidation).toBeTruthy();
    });

    spy.mockRestore();
  });

  it('shows background notification for background-mode update action', async () => {
    const apiMethod = vi.fn().mockResolvedValue({ data: { resource_id: 'r1' } });
    mockDetailResult = makeMockDetail();

    const config = makeUpdateConfig([
      {
        name: 'heal',
        label: 'Heal',
        mode: 'update',
        fields: [],
        zodSchema: { parse: (v: any) => v, safeParse: (v: any) => ({ success: true, data: v }) },
        apiMethod,
        asyncMode: 'background',
      },
    ]);

    render(<ResourceDetail config={config} resourceId="r1" basePath={'/test' as any} />, {
      wrapper: createWrapper(),
    });

    fireEvent.click(screen.getByText('Edit'));

    await waitFor(() => {
      const tab = screen.getByRole('tab', { name: 'Heal' });
      fireEvent.click(tab);
    });

    await waitFor(() => {
      const buttons = screen.getAllByRole('button');
      const actionBtn = buttons.find((b) => b.textContent === 'Heal');
      expect(actionBtn).toBeTruthy();
      fireEvent.click(actionBtn!);
    });

    await waitFor(() => {
      expect(apiMethod).toHaveBeenCalledWith('r1', {});
      expect(notifModule.show).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'Heal',
          message: '已提交背景任務',
          color: 'blue',
        }),
      );
    });
  });

  it('does NOT invalidate job queries for sync update action', async () => {
    const apiMethod = vi.fn().mockResolvedValue({ data: { resource_id: 'r1' } });
    mockDetailResult = makeMockDetail();

    const config = makeUpdateConfig([
      {
        name: 'rename',
        label: 'Rename',
        mode: 'update',
        fields: [],
        zodSchema: { parse: (v: any) => v, safeParse: (v: any) => ({ success: true, data: v }) },
        apiMethod,
        // No asyncMode → sync
      },
    ]);

    const spy = vi.spyOn(QueryClient.prototype, 'invalidateQueries');

    render(<ResourceDetail config={config} resourceId="r1" basePath={'/test' as any} />, {
      wrapper: createWrapper(),
    });

    fireEvent.click(screen.getByText('Edit'));

    await waitFor(() => {
      const tab = screen.getByRole('tab', { name: 'Rename' });
      fireEvent.click(tab);
    });

    await waitFor(() => {
      const buttons = screen.getAllByRole('button');
      const actionBtn = buttons.find((b) => b.textContent === 'Rename');
      expect(actionBtn).toBeTruthy();
      fireEvent.click(actionBtn!);
    });

    await waitFor(() => {
      expect(apiMethod).toHaveBeenCalledWith('r1', {});
      // Should NOT have called invalidateQueries for any job resource
      const calls = spy.mock.calls;
      const jobInvalidation = calls.find((c) => JSON.stringify(c[0]).includes('-job'));
      expect(jobInvalidation).toBeUndefined();
      // Should NOT show notification
      expect(notifModule.show).not.toHaveBeenCalled();
    });

    spy.mockRestore();
  });
});
