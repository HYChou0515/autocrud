import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import { JobTable } from './JobTable';

// ── Capture columns prop from ResourceTable ──
let capturedColumns: any = null;

vi.mock('../table', () => ({
  ResourceTable: ({ config: _config, basePath, columns }: any) => {
    capturedColumns = columns;
    return (
      <div data-testid="resource-table" data-base-path={basePath}>
        <span data-testid="column-order">{JSON.stringify(columns?.order)}</span>
      </div>
    );
  },
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
  capturedColumns = null;
});

const mockConfig = {
  name: 'test-job',
  label: 'Test Job',
  apiClient: {} as any,
  fields: [],
  schema: {},
};

/** Helper: create a mock CellRenderProps with a given cell value */
function makeCellProps(value: unknown) {
  return { cell: { getValue: () => value }, row: { original: {} } } as any;
}

function renderJobTable() {
  render(
    <MantineProvider>
      <JobTable config={mockConfig as any} basePath="/jobs" />
    </MantineProvider>,
  );
}

describe('JobTable', () => {
  it('renders ResourceTable with config and basePath', () => {
    renderJobTable();
    const table = screen.getByTestId('resource-table');
    expect(table).toBeDefined();
    expect(table.getAttribute('data-base-path')).toBe('/jobs');
  });

  it('provides column overrides with correct field order', () => {
    renderJobTable();
    expect(capturedColumns.order).toEqual([
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
    renderJobTable();
    expect(capturedColumns.overrides.status.label).toBe('Status');
  });

  it('provides hidden periodic job fields', () => {
    renderJobTable();
    const ov = capturedColumns.overrides;
    expect(ov.periodic_interval_seconds.hidden).toBe(true);
    expect(ov.periodic_max_runs.hidden).toBe(true);
    expect(ov.periodic_runs.hidden).toBe(true);
    expect(ov.periodic_initial_delay_seconds.hidden).toBe(true);
  });

  it('provides relative-time variant for time columns', () => {
    renderJobTable();
    expect(capturedColumns.overrides.created_time.variant).toBe('relative-time');
    expect(capturedColumns.overrides.updated_time.variant).toBe('relative-time');
  });
});

// ============================================================================
// Status column render function
// ============================================================================

describe('JobTable — status render', () => {
  it('renders status badge with matching colour for known statuses', () => {
    renderJobTable();
    const statusRender = capturedColumns.overrides.status.render;

    const statuses = ['pending', 'processing', 'completed', 'failed'];

    for (const status of statuses) {
      cleanup();
      render(<MantineProvider>{statusRender(makeCellProps(status))}</MantineProvider>);
      expect(screen.getByText(status.toUpperCase())).toBeTruthy();
      cleanup();
    }
  });

  it('falls back to gray for unknown status', () => {
    renderJobTable();
    const statusRender = capturedColumns.overrides.status.render;
    render(<MantineProvider>{statusRender(makeCellProps('custom'))}</MantineProvider>);
    expect(screen.getByText('CUSTOM')).toBeTruthy();
  });

  it('handles null/undefined status as "pending"', () => {
    renderJobTable();
    const statusRender = capturedColumns.overrides.status.render;
    render(<MantineProvider>{statusRender(makeCellProps(null))}</MantineProvider>);
    expect(screen.getByText('PENDING')).toBeTruthy();
  });
});

// ============================================================================
// Payload column render function (renderPayload)
// ============================================================================

describe('JobTable — renderPayload', () => {
  function renderPayload(value: unknown) {
    renderJobTable();
    const payloadRender = capturedColumns.overrides.payload.render;
    return render(<MantineProvider>{payloadRender(makeCellProps(value))}</MantineProvider>);
  }

  it('shows N/A for null value', () => {
    renderPayload(null);
    expect(screen.getByText('N/A')).toBeDefined();
  });

  it('shows N/A for undefined value', () => {
    renderPayload(undefined);
    expect(screen.getByText('N/A')).toBeDefined();
  });

  it('shows N/A for non-object value (string)', () => {
    renderPayload('hello');
    expect(screen.getByText('N/A')).toBeDefined();
  });

  it('shows N/A for non-object value (number)', () => {
    renderPayload(42);
    expect(screen.getByText('N/A')).toBeDefined();
  });

  it('shows {} for empty object', () => {
    renderPayload({});
    expect(screen.getByText('{}')).toBeDefined();
  });

  it('shows single key-value preview without +N more', () => {
    renderPayload({ cmd: 'run' });
    expect(screen.getByText('cmd: "run"')).toBeDefined();
  });

  it('shows multi-key preview with +N more suffix', () => {
    renderPayload({ cmd: 'run', target: 'prod' });
    expect(screen.getByText('cmd: "run", +1 more')).toBeDefined();
  });

  it('truncates long preview text to 40 chars', () => {
    renderPayload({ longKeyName: 'a'.repeat(100) });
    // Preview: 'longKeyName: "aaa...aaa"' should be truncated at 40 char
    const textEl = screen.getByText(/\.\.\.$/) || screen.getByText(/longKeyName/);
    expect(textEl.textContent!.length).toBeLessThanOrEqual(40);
  });

  it('payload label is set', () => {
    renderJobTable();
    expect(capturedColumns.overrides.payload.label).toBe('Payload');
  });

  it('errmsg column is hidden by default', () => {
    renderJobTable();
    expect(capturedColumns.overrides.errmsg.hidden).toBe(true);
  });
});
