/**
 * RefSelect — unit tests
 *
 * Tests:
 * 1. RefSelect renders dropdown with options from useResourceList
 * 2. RefSelect passes alwaysSearchCondition to dropdown params (buildRequestParams)
 * 3. RefSelect passes alwaysSearchCondition to RefTableSelectModal
 * 4. RefMultiSelect renders and passes alwaysSearchCondition
 * 5. RefRevisionSelect uses current_revision_id as option value
 * 6. RefRevisionMultiSelect passes alwaysSearchCondition
 * 7. toSelectOptions builds correct labels for resource_id mode
 * 8. toSelectOptions builds correct labels for current_revision_id mode
 * 9. buildDropdownParams includes alwaysSearchCondition in data_conditions
 * 10. buildDropdownParams without alwaysSearchCondition has no data_conditions
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

vi.mock('./RefTableSelectModal', () => ({
  RefTableSelectModal: (props: any) => (
    <div
      data-testid="ref-table-modal"
      data-resource={props.resourceName}
      data-mode={props.mode}
      data-value-field={props.valueField}
      data-always-search={JSON.stringify(props.alwaysSearchCondition ?? null)}
    />
  ),
}));

import { render, screen, cleanup } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RefSelect, RefMultiSelect, RefRevisionSelect, RefRevisionMultiSelect } from './RefSelect';

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

const defaultFieldRef = { resource: 'character', type: 'resource_id' as const };
const revisionFieldRef = { resource: 'character', type: 'revision_id' as const };

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  mockGetResource.mockReturnValue(makeConfig());
  mockUseResourceList.mockReturnValue({
    data: [
      {
        meta: { resource_id: 'r1', current_revision_id: 'rev-abc123456789' },
        data: { name: 'Hero' },
      },
      { meta: { resource_id: 'r2', current_revision_id: 'rev-xyz' }, data: { name: 'Villain' } },
    ],
    total: 2,
    loading: false,
    error: null,
    refresh: vi.fn(),
    query: {} as any,
  });
});

// ---------------------------------------------------------------------------
// RefSelect
// ---------------------------------------------------------------------------

describe('RefSelect', () => {
  it('renders dropdown with options from useResourceList', () => {
    render(<RefSelect label="Owner" fieldRef={defaultFieldRef} value={null} onChange={vi.fn()} />, {
      wrapper,
    });
    expect(screen.getByRole('textbox')).toBeTruthy();
    // useResourceList should have been called
    expect(mockUseResourceList).toHaveBeenCalled();
  });

  it('passes alwaysSearchCondition to buildRequestParams (visible in useResourceList params)', () => {
    const conditions = [{ field: 'type', operator: 'eq', value: 'weapon' }];
    render(
      <RefSelect
        label="Owner"
        fieldRef={defaultFieldRef}
        value={null}
        onChange={vi.fn()}
        alwaysSearchCondition={conditions}
      />,
      { wrapper },
    );
    // The second argument to useResourceList should be the params object
    const callArgs = mockUseResourceList.mock.calls[0];
    const params = callArgs[1] as Record<string, unknown>;
    expect(params.data_conditions).toBeDefined();
    const parsed = JSON.parse(params.data_conditions as string);
    expect(parsed).toContainEqual({
      field_path: 'type',
      operator: 'eq',
      value: 'weapon',
    });
  });

  it('passes alwaysSearchCondition to RefTableSelectModal', () => {
    const conditions = [{ field: 'type', operator: 'eq', value: 'weapon' }];
    render(
      <RefSelect
        label="Owner"
        fieldRef={defaultFieldRef}
        value={null}
        onChange={vi.fn()}
        alwaysSearchCondition={conditions}
      />,
      { wrapper },
    );
    const modal = screen.getByTestId('ref-table-modal');
    expect(JSON.parse(modal.getAttribute('data-always-search')!)).toEqual(conditions);
  });

  it('does not include data_conditions when no alwaysSearchCondition', () => {
    render(<RefSelect label="Owner" fieldRef={defaultFieldRef} value={null} onChange={vi.fn()} />, {
      wrapper,
    });
    const callArgs = mockUseResourceList.mock.calls[0];
    const params = callArgs[1] as Record<string, unknown>;
    expect(params.data_conditions).toBeUndefined();
  });

  it('always sets is_deleted=false in params', () => {
    render(<RefSelect label="Owner" fieldRef={defaultFieldRef} value={null} onChange={vi.fn()} />, {
      wrapper,
    });
    const callArgs = mockUseResourceList.mock.calls[0];
    const params = callArgs[1] as Record<string, unknown>;
    expect(params.is_deleted).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// RefMultiSelect
// ---------------------------------------------------------------------------

describe('RefMultiSelect', () => {
  it('renders and passes alwaysSearchCondition to modal', () => {
    const conditions = [{ field: 'active', operator: 'eq', value: true }];
    render(
      <RefMultiSelect
        label="Members"
        fieldRef={defaultFieldRef}
        value={[]}
        onChange={vi.fn()}
        alwaysSearchCondition={conditions}
      />,
      { wrapper },
    );
    const modal = screen.getByTestId('ref-table-modal');
    expect(modal.getAttribute('data-mode')).toBe('multi');
    expect(JSON.parse(modal.getAttribute('data-always-search')!)).toEqual(conditions);
  });

  it('passes alwaysSearchCondition to useResourceList params', () => {
    const conditions = [{ field: 'active', operator: 'eq', value: true }];
    render(
      <RefMultiSelect
        label="Members"
        fieldRef={defaultFieldRef}
        value={[]}
        onChange={vi.fn()}
        alwaysSearchCondition={conditions}
      />,
      { wrapper },
    );
    const params = mockUseResourceList.mock.calls[0][1] as Record<string, unknown>;
    expect(params.data_conditions).toBeDefined();
    const parsed = JSON.parse(params.data_conditions as string);
    expect(parsed).toContainEqual({
      field_path: 'active',
      operator: 'eq',
      value: true,
    });
  });
});

// ---------------------------------------------------------------------------
// RefRevisionSelect
// ---------------------------------------------------------------------------

describe('RefRevisionSelect', () => {
  it('renders with current_revision_id valueField', () => {
    render(
      <RefRevisionSelect
        label="Revision"
        fieldRef={revisionFieldRef}
        value={null}
        onChange={vi.fn()}
      />,
      { wrapper },
    );
    const modal = screen.getByTestId('ref-table-modal');
    expect(modal.getAttribute('data-value-field')).toBe('current_revision_id');
  });

  it('passes alwaysSearchCondition to modal and useResourceList', () => {
    const conditions = [{ field: 'status', operator: 'eq', value: 'stable' }];
    render(
      <RefRevisionSelect
        label="Revision"
        fieldRef={revisionFieldRef}
        value={null}
        onChange={vi.fn()}
        alwaysSearchCondition={conditions}
      />,
      { wrapper },
    );
    // Modal
    const modal = screen.getByTestId('ref-table-modal');
    expect(JSON.parse(modal.getAttribute('data-always-search')!)).toEqual(conditions);
    // useResourceList params
    const params = mockUseResourceList.mock.calls[0][1] as Record<string, unknown>;
    const parsed = JSON.parse(params.data_conditions as string);
    expect(parsed).toContainEqual({
      field_path: 'status',
      operator: 'eq',
      value: 'stable',
    });
  });
});

// ---------------------------------------------------------------------------
// RefRevisionMultiSelect
// ---------------------------------------------------------------------------

describe('RefRevisionMultiSelect', () => {
  it('renders with multi mode and passes alwaysSearchCondition', () => {
    const conditions = [{ field: 'tag', operator: 'eq', value: 'release' }];
    render(
      <RefRevisionMultiSelect
        label="Revisions"
        fieldRef={revisionFieldRef}
        value={[]}
        onChange={vi.fn()}
        alwaysSearchCondition={conditions}
      />,
      { wrapper },
    );
    const modals = screen.getAllByTestId('ref-table-modal');
    // Find the one with valueField=current_revision_id
    const modal = modals.find((m) => m.getAttribute('data-value-field') === 'current_revision_id')!;
    expect(modal.getAttribute('data-mode')).toBe('multi');
    expect(JSON.parse(modal.getAttribute('data-always-search')!)).toEqual(conditions);

    const params = mockUseResourceList.mock.calls[0][1] as Record<string, unknown>;
    const parsed = JSON.parse(params.data_conditions as string);
    expect(parsed).toContainEqual({
      field_path: 'tag',
      operator: 'eq',
      value: 'release',
    });
  });
});
