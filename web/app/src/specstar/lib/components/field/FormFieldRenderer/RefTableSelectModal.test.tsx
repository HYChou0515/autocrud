/**
 * RefTableSelectModal — unit tests
 *
 * Tests:
 * 1. Renders ResourceTable with correct selectionMode and selectedIds
 * 2. alwaysSearchCondition is merged with is_deleted=false and passed to ResourceTable
 * 3. Without alwaysSearchCondition, only is_deleted=false is passed
 * 4. Returns null when config is not found
 * 5. onConfirm extracts IDs from selected rows using valueField
 * 6. Uses correct getRowId based on valueField prop
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { ResourceConfig, ResourceField } from '../../../resources';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../../../resources', () => ({
  getResource: (name: string) => mockGetResource(name),
}));

const mockGetResource = vi.fn();

// Capture ResourceTable props to verify what RefTableSelectModal passes
let capturedResourceTableProps: any = null;

vi.mock('../../table/ResourceTable', () => ({
  ResourceTable: (props: any) => {
    capturedResourceTableProps = props;
    return <div data-testid="resource-table" />;
  },
}));

import { render, screen, cleanup, fireEvent, act } from '@testing-library/react';
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
  capturedResourceTableProps = null;
  mockGetResource.mockReturnValue(makeConfig());
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('RefTableSelectModal', () => {
  it('passes selectionMode and selectedIds to ResourceTable', () => {
    render(
      <RefTableSelectModal
        opened={true}
        onClose={vi.fn()}
        onConfirm={vi.fn()}
        resourceName="character"
        mode="single"
        selectedValues={['id-1', 'id-2']}
        valueField="resource_id"
      />,
      { wrapper },
    );
    expect(capturedResourceTableProps).not.toBeNull();
    expect(capturedResourceTableProps.selectionMode).toBe('single');
    expect(capturedResourceTableProps.selectedIds).toEqual(['id-1', 'id-2']);
    expect(capturedResourceTableProps.canCreate).toBe(false);
    expect(capturedResourceTableProps.wrappedInContainer).toBe(false);
    expect(capturedResourceTableProps.initPageSize).toBe(10);
  });

  it('passes multi selectionMode when mode=multi', () => {
    render(
      <RefTableSelectModal
        opened={true}
        onClose={vi.fn()}
        onConfirm={vi.fn()}
        resourceName="character"
        mode="multi"
        selectedValues={[]}
        valueField="resource_id"
      />,
      { wrapper },
    );
    expect(capturedResourceTableProps.selectionMode).toBe('multi');
  });

  it('merges alwaysSearchCondition with is_deleted=false', () => {
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
    const passed = capturedResourceTableProps.alwaysSearchCondition;
    expect(passed).toContainEqual({ field: 'type', operator: 'eq', value: 'weapon' });
    expect(passed).toContainEqual({ field: 'is_deleted', operator: 'eq', value: false });
  });

  it('passes only is_deleted=false when no alwaysSearchCondition', () => {
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
    const passed = capturedResourceTableProps.alwaysSearchCondition;
    expect(passed).toEqual([{ field: 'is_deleted', operator: 'eq', value: false }]);
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

  it('getRowId uses resource_id when valueField=resource_id', () => {
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
    const getRowId = capturedResourceTableProps.getRowId;
    const row = {
      meta: { resource_id: 'abc', current_revision_id: 'rev-abc' },
      data: {},
    };
    expect(getRowId(row)).toBe('abc');
  });

  it('getRowId uses current_revision_id when valueField=current_revision_id', () => {
    render(
      <RefTableSelectModal
        opened={true}
        onClose={vi.fn()}
        onConfirm={vi.fn()}
        resourceName="character"
        mode="single"
        selectedValues={[]}
        valueField="current_revision_id"
      />,
      { wrapper },
    );
    const getRowId = capturedResourceTableProps.getRowId;
    const row = {
      meta: { resource_id: 'abc', current_revision_id: 'rev-abc' },
      data: {},
    };
    expect(getRowId(row)).toBe('rev-abc');
  });

  it('hides meta columns via column overrides', () => {
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
    const overrides = capturedResourceTableProps.columns?.overrides;
    expect(overrides).toBeDefined();
    expect(overrides.schema_version?.hidden).toBe(true);
    expect(overrides.is_deleted?.hidden).toBe(true);
    expect(overrides.created_by?.hidden).toBe(true);
    expect(overrides.updated_by?.hidden).toBe(true);
  });

  it('confirm button calls onConfirm with IDs from selected rows', () => {
    const onConfirm = vi.fn();
    const onClose = vi.fn();
    render(
      <RefTableSelectModal
        opened={true}
        onClose={onClose}
        onConfirm={onConfirm}
        resourceName="character"
        mode="multi"
        selectedValues={[]}
        valueField="resource_id"
      />,
      { wrapper },
    );

    // Simulate ResourceTable calling onSelectionChange with some rows
    const onSelectionChange = capturedResourceTableProps.onSelectionChange;
    act(() => {
      onSelectionChange([
        { data: { name: 'Alice' }, meta: { resource_id: 'r1', current_revision_id: 'rev-r1' } },
        { data: { name: 'Bob' }, meta: { resource_id: 'r2', current_revision_id: 'rev-r2' } },
      ]);
    });

    // Click confirm button (should now be enabled after state update)
    const confirmBtn = screen.getByRole('button', { name: '確認' });
    fireEvent.click(confirmBtn);

    expect(onConfirm).toHaveBeenCalledWith(['r1', 'r2']);
    expect(onClose).toHaveBeenCalled();
  });
});
