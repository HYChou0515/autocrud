import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import { JobTable } from './JobTable';

// ── Mock ResourceTable ──
vi.mock('../table', () => ({
  ResourceTable: ({ config, basePath, columns }: any) => (
    <div data-testid="resource-table" data-base-path={basePath}>
      <span data-testid="columns">{JSON.stringify(columns)}</span>
    </div>
  ),
}));

// ── Mock helpers ──
vi.mock('../field/CellFieldRenderer/helpers', () => ({
  safeStringify: (v: any, indent?: number, maxLen?: number) => {
    const s = JSON.stringify(v, null, indent);
    return maxLen && s.length > maxLen ? s.slice(0, maxLen) : s;
  },
}));

beforeEach(() => {
  cleanup();
});

const mockConfig = {
  name: 'test-job',
  label: 'Test Job',
  apiClient: {} as any,
  fields: [],
  schema: {},
};

describe('JobTable', () => {
  it('renders ResourceTable with config and basePath', () => {
    render(
      <MantineProvider>
        <JobTable config={mockConfig as any} basePath="/jobs" />
      </MantineProvider>,
    );
    const table = screen.getByTestId('resource-table');
    expect(table).toBeDefined();
    expect(table.getAttribute('data-base-path')).toBe('/jobs');
  });

  it('provides column overrides with correct field order', () => {
    render(
      <MantineProvider>
        <JobTable config={mockConfig as any} basePath="/jobs" />
      </MantineProvider>,
    );
    const columnsEl = screen.getByTestId('columns');
    const columns = JSON.parse(columnsEl.textContent || '{}');
    expect(columns.order).toEqual([
      'status',
      'resource_id',
      'payload',
      'retries',
      'created_time',
      'updated_time',
      'errmsg',
    ]);
  });

  it('provides status column override', () => {
    render(
      <MantineProvider>
        <JobTable config={mockConfig as any} basePath="/jobs" />
      </MantineProvider>,
    );
    const columnsEl = screen.getByTestId('columns');
    const columns = JSON.parse(columnsEl.textContent || '{}');
    expect(columns.overrides.status.label).toBe('Status');
  });

  it('provides hidden periodic job fields', () => {
    render(
      <MantineProvider>
        <JobTable config={mockConfig as any} basePath="/jobs" />
      </MantineProvider>,
    );
    const columnsEl = screen.getByTestId('columns');
    const columns = JSON.parse(columnsEl.textContent || '{}');
    expect(columns.overrides.periodic_interval_seconds.hidden).toBe(true);
    expect(columns.overrides.periodic_max_runs.hidden).toBe(true);
    expect(columns.overrides.periodic_runs.hidden).toBe(true);
    expect(columns.overrides.periodic_initial_delay_seconds.hidden).toBe(true);
  });

  it('provides relative-time variant for time columns', () => {
    render(
      <MantineProvider>
        <JobTable config={mockConfig as any} basePath="/jobs" />
      </MantineProvider>,
    );
    const columnsEl = screen.getByTestId('columns');
    const columns = JSON.parse(columnsEl.textContent || '{}');
    expect(columns.overrides.created_time.variant).toBe('relative-time');
    expect(columns.overrides.updated_time.variant).toBe('relative-time');
  });
});

// ── Test renderPayload function indirectly by importing it ──
// Since renderPayload is not exported, we test it via the column render override
// which is passed as a function reference (not serializable). Let's test the
// core logic by importing the module and checking the function exists.
describe('JobTable renderPayload logic', () => {
  // renderPayload is internal, so we unit test the component-level behavior
  it('payload override label is Payload', () => {
    render(
      <MantineProvider>
        <JobTable config={mockConfig as any} basePath="/jobs" />
      </MantineProvider>,
    );
    const columnsEl = screen.getByTestId('columns');
    const columns = JSON.parse(columnsEl.textContent || '{}');
    expect(columns.overrides.payload.label).toBe('Payload');
  });

  it('errmsg column is hidden by default', () => {
    render(
      <MantineProvider>
        <JobTable config={mockConfig as any} basePath="/jobs" />
      </MantineProvider>,
    );
    const columnsEl = screen.getByTestId('columns');
    const columns = JSON.parse(columnsEl.textContent || '{}');
    expect(columns.overrides.errmsg.hidden).toBe(true);
  });
});
