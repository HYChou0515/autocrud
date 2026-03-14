/**
 * PendingJobsAccordion — unit tests.
 *
 * Covers:
 * - Returns null when parent has no async-create job children
 * - Returns null when there are job children but zero pending items
 * - Renders accordion with count badge when pending jobs exist
 * - Shows loading indicator while fetching
 * - Passes correct PENDING_PARAMS to useMultiResourceList
 * - Renders MultiResourceTable inside accordion panel
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

// Mock resources module — control getAsyncCreateJobChildren & getResource
const mockGetAsyncCreateJobChildren = vi.fn<(name: string) => string[]>().mockReturnValue([]);
const mockGetResource = vi.fn().mockReturnValue(undefined);

vi.mock('../../resources', () => ({
  getAsyncCreateJobChildren: (name: string) => mockGetAsyncCreateJobChildren(name),
  getResource: (name: string) => mockGetResource(name),
}));

// Mock useMultiResourceList to control returned data
let mockMultiResult: any = {
  items: [],
  totals: {},
  totalCount: 0,
  loading: false,
  error: null,
  refresh: vi.fn(),
};
const mockUseMultiResourceList = vi.fn().mockImplementation(() => mockMultiResult);

vi.mock('../../hooks/useMultiResourceList', () => ({
  useMultiResourceList: (...args: any[]) => mockUseMultiResourceList(...args),
}));

// Mock MultiResourceTable to simplify assertions
vi.mock('../table/MultiResourceTable', () => ({
  MultiResourceTable: (props: any) => (
    <div data-testid="multi-resource-table" data-configs={props.configs?.length ?? 0} />
  ),
}));

import { PendingJobsAccordion } from './PendingJobsAccordion';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeJobConfig(name: string) {
  return {
    name,
    label: name,
    pluralLabel: name + 's',
    schema: name + 'Schema',
    fields: [],
    apiClient: {} as any,
  };
}

function renderWith(ui: React.ReactElement) {
  return render(<MantineProvider>{ui}</MantineProvider>);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('PendingJobsAccordion', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetAsyncCreateJobChildren.mockReturnValue([]);
    mockGetResource.mockReturnValue(undefined);
    mockMultiResult = {
      items: [],
      totals: {},
      totalCount: 0,
      loading: false,
      error: null,
      refresh: vi.fn(),
    };
  });

  it('returns null when parent has no async-create job children', () => {
    mockGetAsyncCreateJobChildren.mockReturnValue([]);

    const { container } = renderWith(<PendingJobsAccordion parentResourceName="character" />);

    // MantineProvider injects <style> tags — check no accordion rendered
    expect(container.querySelector('[data-accordion]')).toBeNull();
    expect(screen.queryByText('Creating in progress')).toBeNull();
  });

  it('returns null when there are children but zero pending items', () => {
    mockGetAsyncCreateJobChildren.mockReturnValue(['job-a']);
    mockGetResource.mockReturnValue(makeJobConfig('job-a'));

    // Hook returns 0 items
    mockMultiResult = {
      items: [],
      totals: {},
      totalCount: 0,
      loading: false,
      error: null,
      refresh: vi.fn(),
    };

    const { container } = renderWith(<PendingJobsAccordion parentResourceName="character" />);

    // No accordion rendered
    expect(container.querySelector('[data-accordion]')).toBeNull();
    expect(screen.queryByText('Creating in progress')).toBeNull();
  });

  it('renders accordion with count badge when pending jobs exist', () => {
    mockGetAsyncCreateJobChildren.mockReturnValue(['job-a', 'job-b']);
    mockGetResource.mockImplementation((name: string) => {
      if (name === 'job-a') return makeJobConfig('job-a');
      if (name === 'job-b') return makeJobConfig('job-b');
      return undefined;
    });

    mockMultiResult = {
      items: [
        { _source: 'job-a', meta: { resource_id: 'j1' }, data: { status: 'pending' } },
        { _source: 'job-b', meta: { resource_id: 'j2' }, data: { status: 'processing' } },
      ],
      totals: { 'job-a': 1, 'job-b': 1 },
      totalCount: 2,
      loading: false,
      error: null,
      refresh: vi.fn(),
    };

    renderWith(<PendingJobsAccordion parentResourceName="character" />);

    // Accordion title and badge
    expect(screen.getByText('Creating in progress')).toBeTruthy();
    expect(screen.getByText('2')).toBeTruthy();
  });

  it('shows loading indicator while fetching', () => {
    mockGetAsyncCreateJobChildren.mockReturnValue(['job-a']);
    mockGetResource.mockReturnValue(makeJobConfig('job-a'));

    mockMultiResult = {
      items: [],
      totals: {},
      totalCount: 1, // must be > 0 to not hide accordion
      loading: true,
      error: null,
      refresh: vi.fn(),
    };

    renderWith(<PendingJobsAccordion parentResourceName="character" />);

    // Loading text in badge
    expect(screen.getByText('…')).toBeTruthy();
    // Accordion may render label in multiple places; verify at least one exists
    const labels = screen.getAllByText('Creating in progress');
    expect(labels.length).toBeGreaterThanOrEqual(1);
  });

  it('passes correct pending filter params to useMultiResourceList', () => {
    mockGetAsyncCreateJobChildren.mockReturnValue(['job-a']);
    mockGetResource.mockReturnValue(makeJobConfig('job-a'));

    renderWith(<PendingJobsAccordion parentResourceName="character" />);

    // Check the second argument (sharedParams) passed to hook
    expect(mockUseMultiResourceList).toHaveBeenCalled();
    const callArgs = mockUseMultiResourceList.mock.calls[0];
    const sharedParams = callArgs[1];

    expect(sharedParams).toBeDefined();
    expect(sharedParams.limit).toBe(100);

    const conditions = JSON.parse(sharedParams.data_conditions);
    expect(conditions).toEqual([
      { field_path: 'status', operator: 'in', value: ['pending', 'processing'] },
    ]);
  });

  it('passes resolved job configs as entries to the hook', () => {
    mockGetAsyncCreateJobChildren.mockReturnValue(['job-a', 'job-b']);
    const configA = makeJobConfig('job-a');
    const configB = makeJobConfig('job-b');
    mockGetResource.mockImplementation((name: string) => {
      if (name === 'job-a') return configA;
      if (name === 'job-b') return configB;
      return undefined;
    });

    renderWith(<PendingJobsAccordion parentResourceName="character" />);

    const callArgs = mockUseMultiResourceList.mock.calls[0];
    const entries = callArgs[0];

    expect(entries).toHaveLength(2);
    expect(entries[0].config).toBe(configA);
    expect(entries[1].config).toBe(configB);
  });

  it('filters out unresolved configs (getResource returns undefined)', () => {
    mockGetAsyncCreateJobChildren.mockReturnValue(['job-found', 'job-missing']);
    mockGetResource.mockImplementation((name: string) => {
      if (name === 'job-found') return makeJobConfig('job-found');
      return undefined;
    });

    renderWith(<PendingJobsAccordion parentResourceName="character" />);

    const entries = mockUseMultiResourceList.mock.calls[0][0];
    expect(entries).toHaveLength(1);
    expect(entries[0].config.name).toBe('job-found');
  });
});
