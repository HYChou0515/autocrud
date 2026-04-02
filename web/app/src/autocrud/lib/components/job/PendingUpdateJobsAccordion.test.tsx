import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import { PendingUpdateJobsAccordion } from './PendingUpdateJobsAccordion';

// ── Mock resources ──
const mockGetAsyncUpdateJobChildren = vi.fn();
const mockGetResource = vi.fn();

vi.mock('../../resources', () => ({
  getAsyncUpdateJobChildren: (name: string) => mockGetAsyncUpdateJobChildren(name),
  getResource: (name: string) => mockGetResource(name),
}));

// ── Mock useMultiResourceList ──
const mockUseMultiResourceList = vi.fn();

vi.mock('../../hooks/useMultiResourceList', () => ({
  useMultiResourceList: (...args: any[]) => mockUseMultiResourceList(...args),
}));

// ── Mock MultiResourceTable ──
vi.mock('../table/MultiResourceTable', () => ({
  MultiResourceTable: (props: any) => (
    <div data-testid="multi-resource-table">
      <span>{props.configs?.length ?? 0} configs</span>
    </div>
  ),
}));

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  mockGetAsyncUpdateJobChildren.mockReturnValue([]);
  mockGetResource.mockReturnValue(null);
  mockUseMultiResourceList.mockReturnValue({ totalCount: 0, loading: false });
});

function renderComponent(parentResourceName = 'character', resourceId = 'res-1') {
  return render(
    <MantineProvider>
      <PendingUpdateJobsAccordion
        parentResourceName={parentResourceName}
        resourceId={resourceId}
      />
    </MantineProvider>,
  );
}

describe('PendingUpdateJobsAccordion', () => {
  it('renders nothing when no async-update job children', () => {
    mockGetAsyncUpdateJobChildren.mockReturnValue([]);
    const { container } = renderComponent();
    // MantineProvider injects styles, so check for absence of accordion content
    expect(container.querySelector('.mantine-Accordion-root')).toBeNull();
  });

  it('renders nothing when no pending jobs and not loading', () => {
    mockGetAsyncUpdateJobChildren.mockReturnValue(['char-update-job']);
    mockGetResource.mockReturnValue({
      name: 'char-update-job',
      label: 'Char Update Job',
      fields: [],
      apiClient: {},
    });
    mockUseMultiResourceList.mockReturnValue({ totalCount: 0, loading: false });

    const { container } = renderComponent();
    expect(container.querySelector('.mantine-Accordion-root')).toBeNull();
  });

  it('renders accordion when there are pending jobs', () => {
    mockGetAsyncUpdateJobChildren.mockReturnValue(['char-update-job']);
    mockGetResource.mockReturnValue({
      name: 'char-update-job',
      label: 'Char Update Job',
      fields: [],
      apiClient: {},
    });
    mockUseMultiResourceList.mockReturnValue({ totalCount: 3, loading: false });

    renderComponent();
    expect(screen.getByText('Updating in progress')).toBeDefined();
    expect(screen.getByText('3')).toBeDefined();
  });

  it('shows loading indicator when loading', () => {
    mockGetAsyncUpdateJobChildren.mockReturnValue(['char-update-job']);
    mockGetResource.mockReturnValue({
      name: 'char-update-job',
      label: 'Char Update Job',
      fields: [],
      apiClient: {},
    });
    mockUseMultiResourceList.mockReturnValue({ totalCount: 0, loading: true });

    renderComponent();
    // Should still render the accordion when loading
    expect(screen.getByText('Updating in progress')).toBeDefined();
    expect(screen.getByText('…')).toBeDefined();
  });

  it('filters out null resource configs', () => {
    mockGetAsyncUpdateJobChildren.mockReturnValue(['valid-job', 'invalid-job']);
    mockGetResource.mockImplementation((name: string) => {
      if (name === 'valid-job')
        return { name: 'valid-job', label: 'Valid Job', fields: [], apiClient: {} };
      return null;
    });
    mockUseMultiResourceList.mockReturnValue({ totalCount: 1, loading: false });

    renderComponent();
    expect(screen.getByText('Updating in progress')).toBeDefined();
  });
});
