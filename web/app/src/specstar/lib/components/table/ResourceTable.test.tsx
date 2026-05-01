/**
 * ResourceTable — unit tests for row selection feature.
 *
 * Tests:
 * 1. No selectionMode: no checkboxes rendered, row click navigates
 * 2. selectionMode='single': enables row selection, single select behavior
 * 3. selectionMode='multi': enables multi-row selection
 * 4. selectedIds: controlled pre-selection via prop
 * 5. onSelectionChange: callback fires with FullResourceRow objects
 * 6. getRowId: custom row ID extraction function
 * 7. Selection mode overrides onRowClick (row click selects instead of navigates)
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { ResourceConfig, ResourceField } from '../../resources';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockNavigate = vi.fn();

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => mockNavigate,
}));

const mockUseResourceList = vi.fn();

vi.mock('../../hooks/useResourceList', () => ({
  useResourceList: (...args: any[]) => mockUseResourceList(...args),
}));

vi.mock('./buildColumns', () => ({
  buildTableColumns: (_config: any) => {
    // Return a minimal column for name field so MRT can render
    return [
      {
        accessorKey: 'data.name',
        header: 'Name',
        id: 'name',
      },
    ];
  },
}));

vi.mock('./AdvancedSearchPanel', () => ({
  AdvancedSearchPanel: () => <div data-testid="advanced-search-panel" />,
}));

vi.mock('../common/TimeDisplay', () => ({
  formatTime: (v: string) => v,
}));

import { render, cleanup, fireEvent } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ResourceTable } from './ResourceTable';
import type { FullResourceRow } from '../../../types/api';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeField(name: string): ResourceField {
  return {
    name,
    label: name.charAt(0).toUpperCase() + name.slice(1),
    type: 'string',
    isArray: false,
    isRequired: false,
    isNullable: false,
  };
}

function makeConfig(name = 'character'): ResourceConfig<any> {
  return {
    name,
    label: 'Character',
    pluralLabel: 'Characters',
    schema: 'Character',
    displayNameField: 'name',
    fields: [makeField('name'), makeField('level')],
    defaultHiddenFields: [],
    apiClient: {} as any,
  } as any;
}

function makeRow(id: string, name: string): FullResourceRow<any> {
  return {
    data: { name },
    meta: {
      resource_id: id,
      current_revision_id: `rev-${id}`,
      schema_version: 'v1',
      total_revision_count: 1,
      created_time: '2024-01-01T00:00:00Z',
      updated_time: '2024-01-01T00:00:00Z',
      created_by: 'test',
      updated_by: 'test',
      is_deleted: false,
    },
    revision_info: {
      uid: `uid-${id}`,
      resource_id: id,
      revision_id: `rev-${id}`,
      parent_revision_id: null,
      parent_schema_version: null,
      schema_version: 'v1',
      data_hash: 'hash',
      status: 'stable' as const,
      created_time: '2024-01-01T00:00:00Z',
      updated_time: '2024-01-01T00:00:00Z',
      created_by: 'test',
      updated_by: 'test',
    },
  };
}

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <MantineProvider>{children}</MantineProvider>
    </QueryClientProvider>
  );
}

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

const sampleData = [makeRow('r1', 'Alice'), makeRow('r2', 'Bob'), makeRow('r3', 'Charlie')];

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  mockUseResourceList.mockReturnValue({
    data: sampleData,
    total: 3,
    loading: false,
    error: null,
    refresh: vi.fn(),
    query: {} as any,
  });
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ResourceTable — row selection', () => {
  it('does not render checkboxes when selectionMode is not set', () => {
    render(<ResourceTable config={makeConfig()} basePath="/characters" />, { wrapper });
    // MRT checkbox column has role="checkbox" on header
    const checkboxes = document.querySelectorAll('input[type="checkbox"]');
    expect(checkboxes.length).toBe(0);
  });

  it('renders checkboxes when selectionMode="multi"', () => {
    render(<ResourceTable config={makeConfig()} basePath="/characters" selectionMode="multi" />, {
      wrapper,
    });
    // MRT should render checkbox inputs for each row + header
    const checkboxes = document.querySelectorAll('input[type="checkbox"]');
    expect(checkboxes.length).toBeGreaterThan(0);
  });

  it('renders radio buttons when selectionMode="single"', () => {
    render(<ResourceTable config={makeConfig()} basePath="/characters" selectionMode="single" />, {
      wrapper,
    });
    // In single mode, MRT renders radio inputs
    const radios = document.querySelectorAll('input[type="radio"]');
    // If MRT uses radio for single, check that. Otherwise checkboxes exist.
    const checkboxes = document.querySelectorAll('input[type="checkbox"]');
    // At least one of these should be present (MRT implementation detail)
    expect(radios.length + checkboxes.length).toBeGreaterThan(0);
  });

  it('calls onSelectionChange with selected row objects', async () => {
    const onSelectionChange = vi.fn();
    render(
      <ResourceTable
        config={makeConfig()}
        basePath="/characters"
        selectionMode="multi"
        onSelectionChange={onSelectionChange}
      />,
      { wrapper },
    );

    // Click first data row to select it
    const rows = document.querySelectorAll('tbody tr');
    expect(rows.length).toBeGreaterThan(0);
    fireEvent.click(rows[0]);

    // onSelectionChange should be called (via effect) with row objects
    // Wait for the effect to fire
    await vi.waitFor(() => {
      expect(onSelectionChange).toHaveBeenCalled();
    });

    const lastCall = onSelectionChange.mock.calls[onSelectionChange.mock.calls.length - 1];
    const selectedRows = lastCall[0] as FullResourceRow<any>[];
    expect(selectedRows.length).toBe(1);
    expect(selectedRows[0].meta.resource_id).toBe('r1');
  });

  it('pre-selects rows via selectedIds prop', () => {
    const onSelectionChange = vi.fn();
    render(
      <ResourceTable
        config={makeConfig()}
        basePath="/characters"
        selectionMode="multi"
        selectedIds={['r1', 'r3']}
        onSelectionChange={onSelectionChange}
      />,
      { wrapper },
    );

    // The onSelectionChange effect should fire with pre-selected rows
    // (selectedIds triggers initial rowSelection state)
    // Check that checkboxes for r1 and r3 are checked
    const checkboxes = document.querySelectorAll('input[type="checkbox"]:checked');
    // At least r1 + r3 should be checked (may include header "select all")
    expect(checkboxes.length).toBeGreaterThanOrEqual(2);
  });

  it('uses custom getRowId when provided', async () => {
    const onSelectionChange = vi.fn();
    const customGetRowId = (row: FullResourceRow<any>) => row?.meta?.current_revision_id ?? '';

    render(
      <ResourceTable
        config={makeConfig()}
        basePath="/characters"
        selectionMode="single"
        selectedIds={['rev-r2']}
        getRowId={customGetRowId}
        onSelectionChange={onSelectionChange}
      />,
      { wrapper },
    );

    // Wait for effect to fire with revision-based ID
    await vi.waitFor(() => {
      expect(onSelectionChange).toHaveBeenCalled();
    });

    const lastCall = onSelectionChange.mock.calls[onSelectionChange.mock.calls.length - 1];
    const selectedRows = lastCall[0] as FullResourceRow<any>[];
    expect(selectedRows.length).toBe(1);
    expect(selectedRows[0].meta.current_revision_id).toBe('rev-r2');
  });

  it('single mode row click replaces previous selection', async () => {
    const onSelectionChange = vi.fn();
    render(
      <ResourceTable
        config={makeConfig()}
        basePath="/characters"
        selectionMode="single"
        onSelectionChange={onSelectionChange}
      />,
      { wrapper },
    );

    const rows = document.querySelectorAll('tbody tr');
    // Click first row
    fireEvent.click(rows[0]);

    await vi.waitFor(() => {
      expect(onSelectionChange).toHaveBeenCalled();
    });

    // Click second row — should replace, not add
    fireEvent.click(rows[1]);

    await vi.waitFor(() => {
      const calls = onSelectionChange.mock.calls;
      const lastCall = calls[calls.length - 1];
      const selectedRows = lastCall[0] as FullResourceRow<any>[];
      expect(selectedRows.length).toBe(1);
      expect(selectedRows[0].meta.resource_id).toBe('r2');
    });
  });

  it('multi mode row click toggles selection', async () => {
    const onSelectionChange = vi.fn();
    render(
      <ResourceTable
        config={makeConfig()}
        basePath="/characters"
        selectionMode="multi"
        onSelectionChange={onSelectionChange}
      />,
      { wrapper },
    );

    const rows = document.querySelectorAll('tbody tr');
    // Click first row
    fireEvent.click(rows[0]);
    // Click second row
    fireEvent.click(rows[1]);

    await vi.waitFor(() => {
      const calls = onSelectionChange.mock.calls;
      const lastCall = calls[calls.length - 1];
      const selectedRows = lastCall[0] as FullResourceRow<any>[];
      expect(selectedRows.length).toBe(2);
    });
  });

  it('selection mode prevents default navigation on row click', async () => {
    render(<ResourceTable config={makeConfig()} basePath="/characters" selectionMode="single" />, {
      wrapper,
    });

    const rows = document.querySelectorAll('tbody tr');
    fireEvent.click(rows[0]);

    // navigate should NOT be called (selection mode takes over)
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it('without selectionMode, row click navigates to detail', () => {
    render(<ResourceTable config={makeConfig()} basePath="/characters" />, { wrapper });

    const rows = document.querySelectorAll('tbody tr');
    expect(rows.length).toBeGreaterThan(0);
    fireEvent.click(rows[0]);

    expect(mockNavigate).toHaveBeenCalledWith({
      to: '/characters/$resourceId',
      params: { resourceId: 'r1' },
    });
  });

  it('passes useResourceList params correctly (server mode)', () => {
    render(
      <ResourceTable
        config={makeConfig()}
        basePath="/characters"
        selectionMode="multi"
        initPageSize={15}
      />,
      { wrapper },
    );

    expect(mockUseResourceList).toHaveBeenCalled();
    const params = mockUseResourceList.mock.calls[0][1] as Record<string, unknown>;
    expect(params.limit).toBe(15);
    expect(params.offset).toBe(0);
  });
});
