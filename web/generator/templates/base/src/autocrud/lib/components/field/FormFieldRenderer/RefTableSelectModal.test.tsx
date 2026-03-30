/**
 * RefTableSelectModal — unit tests
 *
 * Tests:
 * 1. Modal uses buildRequestParams to build params
 * 2. alwaysSearchCondition is included in data_conditions
 * 3. is_deleted=false is always set
 * 4. Without alwaysSearchCondition, data_conditions is absent
 * 5. Params include correct pagination
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { ResourceConfig, ResourceField } from '../../../resources';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockUseResourceList = vi.fn();

vi.mock('../../../hooks/useResourceList', () => ({
  useResourceList: (...args: any[]) => mockUseResourceList(...args),
}));

vi.mock('../../../resources', () => ({
  getResource: (name: string) => mockGetResource(name),
}));

const mockGetResource = vi.fn();

vi.mock('../../table/buildColumns', () => ({
  buildTableColumns: () => [],
}));

vi.mock('../../table/AdvancedSearchPanel', () => ({
  AdvancedSearchPanel: () => <div data-testid="advanced-search-panel" />,
}));

import { render, cleanup } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RefTableSelectModal } from './RefTableSelectModal';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

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

function makeConfig(name = 'character'): ResourceConfig<any> {
  return {
    name,
    label: 'Character',
    pluralLabel: 'Characters',
    schema: 'Character',
    displayNameField: 'name',
    fields: [makeField('name'), makeField('level')],
    defaultHiddenFields: [],
  } as any;
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

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  mockGetResource.mockReturnValue(makeConfig());
  mockUseResourceList.mockReturnValue({
    data: [],
    total: 0,
    loading: false,
    error: null,
    refresh: vi.fn(),
    query: {} as any,
  });
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('RefTableSelectModal', () => {
  it('calls useResourceList with params built by buildRequestParams', () => {
    render(
      <RefTableSelectModal
        opened={true}
        onClose={vi.fn()}
        onConfirm={vi.fn()}
        resourceName="character"
        mode="single"
        selectedValues={[]}
        valueField="resource_id"
      />,
      { wrapper },
    );
    expect(mockUseResourceList).toHaveBeenCalled();
    const params = mockUseResourceList.mock.calls[0][1] as Record<string, unknown>;
    // buildRequestParams sets limit/offset for server mode
    expect(params.limit).toBe(10); // default pageSize
    expect(params.offset).toBe(0);
    expect(params.is_deleted).toBe(false);
  });

  it('includes alwaysSearchCondition in data_conditions', () => {
    const conditions = [{ field: 'type', operator: 'eq', value: 'weapon' }];
    render(
      <RefTableSelectModal
        opened={true}
        onClose={vi.fn()}
        onConfirm={vi.fn()}
        resourceName="character"
        mode="single"
        selectedValues={[]}
        valueField="resource_id"
        alwaysSearchCondition={conditions}
      />,
      { wrapper },
    );
    const params = mockUseResourceList.mock.calls[0][1] as Record<string, unknown>;
    expect(params.data_conditions).toBeDefined();
    const parsed = JSON.parse(params.data_conditions as string);
    expect(parsed).toContainEqual({
      field_path: 'type',
      operator: 'eq',
      value: 'weapon',
    });
  });

  it('does not include data_conditions when no alwaysSearchCondition', () => {
    render(
      <RefTableSelectModal
        opened={true}
        onClose={vi.fn()}
        onConfirm={vi.fn()}
        resourceName="character"
        mode="single"
        selectedValues={[]}
        valueField="resource_id"
      />,
      { wrapper },
    );
    const params = mockUseResourceList.mock.calls[0][1] as Record<string, unknown>;
    expect(params.data_conditions).toBeUndefined();
  });

  it('always sets is_deleted=false', () => {
    render(
      <RefTableSelectModal
        opened={true}
        onClose={vi.fn()}
        onConfirm={vi.fn()}
        resourceName="character"
        mode="multi"
        selectedValues={[]}
        valueField="resource_id"
        alwaysSearchCondition={[{ field: 'x', operator: 'eq', value: 1 }]}
      />,
      { wrapper },
    );
    const params = mockUseResourceList.mock.calls[0][1] as Record<string, unknown>;
    expect(params.is_deleted).toBe(false);
  });

  it('returns null when config is not found', () => {
    mockGetResource.mockReturnValue(undefined);
    const { container } = render(
      <RefTableSelectModal
        opened={true}
        onClose={vi.fn()}
        onConfirm={vi.fn()}
        resourceName="nonexistent"
        mode="single"
        selectedValues={[]}
        valueField="resource_id"
      />,
      { wrapper },
    );
    // When config is not found, component returns null — no Modal dialog rendered
    expect(container.querySelector('[class*="Modal"]')).toBeNull();
  });
});
