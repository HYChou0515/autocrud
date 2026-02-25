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
      listFull: vi.fn(),
      count: vi.fn(),
      getFull: vi.fn(),
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
        is_deleted: false,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
        created_by: 'test',
      },
      revision_info: {
        resource_id: 'r1',
        revision_id: 'rev1',
        revision_status: 'stable',
        created_at: '2026-01-01T00:00:00Z',
        created_by: 'test',
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
