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

vi.mock('../../hooks/useResourceDetail', () => ({
  useResourceDetail: () => mockDetailResult,
}));

vi.mock('../../hooks/useFieldDepth', () => ({
  useFieldDepth: () => ({
    maxAvailableDepth: 1,
    depth: 1,
    setDepth: vi.fn(),
    visibleFields: [],
    collapsedGroups: [],
  }),
}));

vi.mock('../form/ResourceForm', () => ({
  ResourceForm: () => null,
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
  Link: (props: any) => props.children,
}));

import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import { ResourceDetail } from './ResourceDetail';
import { groupFieldsForDisplay, type DisplayGroup } from './ResourceDetail';
import { showErrorNotification } from '../../utils/errorNotification';

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
    restore: vi.fn(),
    switchRevision: vi.fn(),
    rerun: vi.fn().mockResolvedValue(undefined),
  };
}

function renderDetail(config: ResourceConfig<any>, isJob = true) {
  return render(
    <MantineProvider>
      <ResourceDetail config={config} resourceId="r1" basePath={'/test' as any} isJob={isJob} />
    </MantineProvider>,
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

  it('shows error notification on rerun failure', async () => {
    const rerunError = new Error('Queue unavailable');
    const detail = makeMockDetail({ status: 'failed' });
    detail.rerun = vi.fn().mockRejectedValue(rerunError);
    mockDetailResult = detail;
    const config = makeConfig();
    renderDetail(config, true);

    fireEvent.click(screen.getByText('Rerun'));

    await waitFor(() => {
      expect(showErrorNotification).toHaveBeenCalledWith(rerunError, 'Rerun Failed');
    });
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
