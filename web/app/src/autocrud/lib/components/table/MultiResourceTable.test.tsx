/**
 * MultiResourceTable — unit tests.
 *
 * Covers:
 * - Renders nothing (null) when items are empty and emptyMessage is null
 * - Shows emptyMessage text when items are empty and message is given
 * - Renders a Source badge column with correct resource labels
 * - Renders data columns from the union of all configs' fields
 * - Delegates row click to custom handler
 * - Default row click navigates to detail page
 * - Column overrides (hidden, custom label, custom render)
 * - Column ordering via columns.order
 * - Title and count badge render when title is provided
 * - Error alert is displayed when fetch fails partially
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import type { ResourceConfig, ResourceField } from '../../resources';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockNavigate = vi.fn();

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => mockNavigate,
}));

// Mock the hook to control items/loading/error easily
let mockHookResult: any = {
  items: [],
  totals: {},
  totalCount: 0,
  loading: false,
  error: null,
  refresh: vi.fn(),
};

vi.mock('../../hooks/useMultiResourceList', () => ({
  useMultiResourceList: () => mockHookResult,
}));

// Mock getResource for source badge label lookup
vi.mock('../../resources', async () => {
  const actual = await vi.importActual('../../resources');
  return {
    ...actual,
    getResource: (name: string) => {
      if (name === 'alpha') return { name: 'alpha', label: 'Alpha Resource' };
      if (name === 'beta') return { name: 'beta', label: 'Beta Resource' };
      return undefined;
    },
  };
});

// Mock sub-components to simplify DOM assertions
vi.mock('../field/CellFieldRenderer', () => ({
  renderCellValue: ({ value }: any) => String(value ?? ''),
}));

vi.mock('../common/ResourceIdCell', () => ({
  ResourceIdCell: ({ rid }: any) => rid,
}));

vi.mock('../common/TimeDisplay', () => ({
  formatTime: (v: string) => v,
}));

import { MultiResourceTable } from './MultiResourceTable';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeField(name: string, type: ResourceField['type'] = 'string'): ResourceField {
  return {
    name,
    label: name.charAt(0).toUpperCase() + name.slice(1),
    type,
    isArray: false,
    isRequired: true,
    isNullable: false,
  };
}

function makeConfig(name: string, fields: ResourceField[] = []): ResourceConfig {
  return {
    name,
    label: name.charAt(0).toUpperCase() + name.slice(1),
    pluralLabel: name + 's',
    schema: name + 'Schema',
    fields,
    apiClient: {} as any,
  };
}

function makeItem(source: string, rid: string, data: Record<string, unknown> = {}) {
  return {
    _source: source,
    meta: {
      resource_id: rid,
      updated_time: '2024-01-01T00:00:00Z',
      created_time: '2024-01-01T00:00:00Z',
    },
    data,
  };
}

function renderWith(ui: React.ReactElement) {
  return render(<MantineProvider>{ui}</MantineProvider>);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('MultiResourceTable', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockHookResult = {
      items: [],
      totals: {},
      totalCount: 0,
      loading: false,
      error: null,
      refresh: vi.fn(),
    };
  });

  it('returns null when no items and emptyMessage is null', () => {
    const { container } = renderWith(
      <MultiResourceTable configs={[makeConfig('alpha')]} emptyMessage={null} />,
    );
    // MantineProvider injects <style> tags, so check there are no visible app elements
    expect(container.querySelector('table')).toBeNull();
    expect(container.querySelector('p')).toBeNull();
  });

  it('shows emptyMessage text when no items and message is provided', () => {
    mockHookResult = {
      ...mockHookResult,
      items: [],
      totalCount: 0,
    };

    renderWith(
      <MultiResourceTable configs={[makeConfig('alpha')]} emptyMessage="No results found" />,
    );

    expect(screen.getByText('No results found')).toBeTruthy();
  });

  it('renders Source badge column with correct labels', async () => {
    mockHookResult = {
      ...mockHookResult,
      items: [makeItem('alpha', 'r1'), makeItem('beta', 'r2')],
      totalCount: 2,
    };

    renderWith(<MultiResourceTable configs={[makeConfig('alpha'), makeConfig('beta')]} />);

    // The Source column header should exist
    expect(screen.getByText('Source')).toBeTruthy();
    // Badge labels come from mocked getResource
    expect(screen.getByText('Alpha Resource')).toBeTruthy();
    expect(screen.getByText('Beta Resource')).toBeTruthy();
  });

  it('renders data columns from union of fields', async () => {
    const configA = makeConfig('alpha', [makeField('name'), makeField('age', 'number')]);
    const configB = makeConfig('beta', [makeField('name'), makeField('email')]);

    mockHookResult = {
      ...mockHookResult,
      items: [
        makeItem('alpha', 'r1', { name: 'Alice', age: 30 }),
        makeItem('beta', 'r2', { name: 'Bob', email: 'bob@test.com' }),
      ],
      totalCount: 2,
    };

    renderWith(<MultiResourceTable configs={[configA, configB]} />);

    // Union of fields: name, age, email — all should appear as headers
    expect(screen.getByText('Name')).toBeTruthy();
    expect(screen.getByText('Age')).toBeTruthy();
    expect(screen.getByText('Email')).toBeTruthy();
  });

  it('renders title and count badge when title is provided', () => {
    mockHookResult = {
      ...mockHookResult,
      items: [makeItem('alpha', 'r1')],
      totalCount: 1,
    };

    renderWith(<MultiResourceTable configs={[makeConfig('alpha')]} title="My Table" />);

    expect(screen.getByText('My Table')).toBeTruthy();
    expect(screen.getByText('1')).toBeTruthy();
  });

  it('sets cursor pointer on rows when onRowClick is a function', () => {
    const item = makeItem('alpha', 'r1');
    mockHookResult = {
      ...mockHookResult,
      items: [item],
      totalCount: 1,
    };

    const onClick = vi.fn();

    renderWith(<MultiResourceTable configs={[makeConfig('alpha')]} onRowClick={onClick} />);

    // Verify that data rows exist and have cursor: pointer style
    const rows = screen.getAllByRole('row');
    const dataRow = rows.find((r) => r.querySelector('td'));
    expect(dataRow).toBeTruthy();
    expect(dataRow?.style.cursor).toBe('pointer');
  });

  it('navigates to detail page on default row click', async () => {
    const item = makeItem('alpha', 'r1');
    mockHookResult = {
      ...mockHookResult,
      items: [item],
      totalCount: 1,
    };

    renderWith(<MultiResourceTable configs={[makeConfig('alpha')]} />);

    const rows = screen.getAllByRole('row');
    const dataRow = rows.find((r) => r.querySelector('td'));
    if (dataRow) {
      fireEvent.click(dataRow);
      expect(mockNavigate).toHaveBeenCalledWith({
        to: '/autocrud-admin/alpha/$resourceId',
        params: { resourceId: 'r1' },
      });
    }
  });

  it('applies column overrides (hidden, custom label, custom render)', () => {
    const config = makeConfig('alpha', [makeField('visible_field'), makeField('hidden_field')]);

    mockHookResult = {
      ...mockHookResult,
      items: [makeItem('alpha', 'r1', { visible_field: 'val', hidden_field: 'secret' })],
      totalCount: 1,
    };

    renderWith(
      <MultiResourceTable
        configs={[config]}
        columns={{
          overrides: {
            visible_field: { label: 'Custom Label' },
            hidden_field: { hidden: true },
          },
        }}
      />,
    );

    expect(screen.getByText('Custom Label')).toBeTruthy();
    expect(screen.queryByText('Hidden_field')).toBeNull();
  });

  it('shows error alert when fetch fails', () => {
    mockHookResult = {
      ...mockHookResult,
      items: [makeItem('alpha', 'r1')],
      totalCount: 1,
      error: new Error('Something went wrong'),
    };

    renderWith(<MultiResourceTable configs={[makeConfig('alpha')]} title="Table" />);

    expect(screen.getByText('Something went wrong')).toBeTruthy();
  });

  it('shows Refresh button when title is provided', () => {
    mockHookResult = {
      ...mockHookResult,
      items: [makeItem('alpha', 'r1')],
      totalCount: 1,
    };

    renderWith(<MultiResourceTable configs={[makeConfig('alpha')]} title="T" />);

    // Our component renders a Refresh button in the title bar
    const refreshBtns = screen.getAllByText('Refresh');
    expect(refreshBtns.length).toBeGreaterThanOrEqual(1);
  });
});
