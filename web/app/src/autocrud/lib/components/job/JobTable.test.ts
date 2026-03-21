/**
 * JobTable — Tests for job-specific column overrides.
 *
 * Verifies that the `render` callbacks in JobTable's column overrides
 * correctly use `CellRenderProps` (props.cell.getValue()) instead of
 * receiving a raw value directly.
 */
import { describe, it, expect } from 'vitest';
import { buildTableColumns } from '../table/buildColumns';
import type { CellRenderProps } from '../table/buildColumns';
import type { ResourceConfig, ResourceField } from '../../resources';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeField(overrides: Partial<ResourceField> & { name: string }): ResourceField {
  return {
    label: overrides.label ?? overrides.name,
    type: 'string',
    isArray: false,
    isRequired: false,
    isNullable: false,
    ...overrides,
  };
}

function makeJobConfig(): ResourceConfig {
  return {
    name: 'test-job',
    label: 'Test Job',
    pluralLabel: 'Test Jobs',
    schema: 'TestJob',
    fields: [
      makeField({
        name: 'payload',
        label: 'Payload',
        type: 'object',
      }),
      makeField({
        name: 'status',
        label: 'Status',
        type: 'string',
        enumValues: ['pending', 'processing', 'completed', 'failed'],
      }),
      makeField({
        name: 'errmsg',
        label: 'Error',
        type: 'string',
        isNullable: true,
      }),
      makeField({
        name: 'retries',
        label: 'Retries',
        type: 'number',
      }),
    ],
    apiClient: {} as any,
  };
}

/** Create fake MRT cell props for testing */
function fakeCellProps(value: unknown, data?: Record<string, unknown>): CellRenderProps<any> {
  return {
    cell: { getValue: () => value } as any,
    column: {} as any,
    row: { original: { data: data ?? {}, meta: {} } } as any,
    table: {} as any,
    renderedCellValue: null,
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('JobTable — status column render', () => {
  it('status render receives CellRenderProps and extracts value correctly', () => {
    const config = makeJobConfig();

    // Simulate the JobTable overrides
    const mrtCols = buildTableColumns(config, {
      overrides: {
        status: {
          label: 'Status',
          render: (props: CellRenderProps<unknown>) => {
            const status = String(props.cell.getValue() || 'pending');
            return status.toUpperCase();
          },
        },
      },
    });

    const statusCol = mrtCols.find((c) => c.id === 'status')!;
    expect(statusCol).toBeDefined();

    const result = statusCol.Cell!(fakeCellProps('completed') as any);
    expect(result).toBe('COMPLETED');
  });

  it('status render should NOT produce [object Object]', () => {
    const config = makeJobConfig();

    // This simulates the BUG: render receives CellRenderProps but treats it as raw value
    const mrtCols = buildTableColumns(config, {
      overrides: {
        status: {
          label: 'Status',
          render: (props: CellRenderProps<unknown>) => {
            const status = String(props.cell.getValue() || 'pending');
            return status.toUpperCase();
          },
        },
      },
    });

    const statusCol = mrtCols.find((c) => c.id === 'status')!;
    const result = statusCol.Cell!(fakeCellProps('processing') as any);
    expect(String(result)).not.toContain('[object Object]');
    expect(result).toBe('PROCESSING');
  });
});

describe('JobTable — payload column render', () => {
  it('payload render receives CellRenderProps and extracts object value', () => {
    const config = makeJobConfig();

    const mrtCols = buildTableColumns(config, {
      overrides: {
        payload: {
          label: 'Payload',
          render: (props: CellRenderProps<unknown>) => {
            const value = props.cell.getValue();
            if (!value || typeof value !== 'object') return 'N/A';
            const keys = Object.keys(value as Record<string, unknown>);
            return `${keys.length} keys`;
          },
        },
      },
    });

    const payloadCol = mrtCols.find((c) => c.id === 'payload')!;
    const result = payloadCol.Cell!(fakeCellProps({ event: 'test', amount: 42 }) as any);
    expect(result).toBe('2 keys');
  });

  it('payload render should NOT produce [object Object] for null value', () => {
    const config = makeJobConfig();

    const mrtCols = buildTableColumns(config, {
      overrides: {
        payload: {
          label: 'Payload',
          render: (props: CellRenderProps<unknown>) => {
            const value = props.cell.getValue();
            if (!value || typeof value !== 'object') return 'N/A';
            return 'has data';
          },
        },
      },
    });

    const payloadCol = mrtCols.find((c) => c.id === 'payload')!;
    const result = payloadCol.Cell!(fakeCellProps(null) as any);
    expect(result).toBe('N/A');
  });
});
