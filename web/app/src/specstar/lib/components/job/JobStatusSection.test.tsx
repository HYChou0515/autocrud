import { describe, it, expect, beforeEach } from 'vitest';
import { render, cleanup } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import { JobStatusSection, JOB_STATUS_COLORS, JOB_STATUS_FIELDS } from './JobStatusSection';

beforeEach(() => {
  cleanup();
});

const wrap = (ui: React.ReactElement) => render(<MantineProvider>{ui}</MantineProvider>);

describe('JOB_STATUS_COLORS', () => {
  it('has expected color mappings', () => {
    expect(JOB_STATUS_COLORS['pending']).toBe('gray');
    expect(JOB_STATUS_COLORS['processing']).toBe('blue');
    expect(JOB_STATUS_COLORS['completed']).toBe('green');
    expect(JOB_STATUS_COLORS['failed']).toBe('red');
  });
});

describe('JOB_STATUS_FIELDS', () => {
  it('contains expected fields', () => {
    expect(JOB_STATUS_FIELDS.has('status')).toBe(true);
    expect(JOB_STATUS_FIELDS.has('retries')).toBe(true);
    expect(JOB_STATUS_FIELDS.has('max_retries')).toBe(true);
    expect(JOB_STATUS_FIELDS.has('errmsg')).toBe(true);
    expect(JOB_STATUS_FIELDS.has('last_heartbeat_at')).toBe(true);
    expect(JOB_STATUS_FIELDS.has('periodic_interval_seconds')).toBe(true);
    expect(JOB_STATUS_FIELDS.has('periodic_max_runs')).toBe(true);
    expect(JOB_STATUS_FIELDS.has('periodic_runs')).toBe(true);
    expect(JOB_STATUS_FIELDS.has('periodic_initial_delay_seconds')).toBe(true);
  });
});

describe('JobStatusSection', () => {
  it('renders status badge with correct status text', () => {
    const { container } = wrap(<JobStatusSection data={{ status: 'pending' }} />);
    expect(container.textContent).toContain('PENDING');
    expect(container.textContent).toContain('Job Status');
  });

  it('renders completed status', () => {
    const { container } = wrap(<JobStatusSection data={{ status: 'completed' }} />);
    expect(container.textContent).toContain('COMPLETED');
  });

  it('renders failed status with error message', () => {
    const { container } = wrap(
      <JobStatusSection data={{ status: 'failed', errmsg: 'Something went wrong' }} />,
    );
    expect(container.textContent).toContain('FAILED');
    expect(container.textContent).toContain('Something went wrong');
  });

  it('renders retries with max_retries', () => {
    const { container } = wrap(
      <JobStatusSection data={{ status: 'processing', retries: 2, max_retries: 5 }} />,
    );
    expect(container.textContent).toContain('2 / 5');
  });

  it('renders retries without max_retries', () => {
    const { container } = wrap(<JobStatusSection data={{ status: 'processing', retries: 3 }} />);
    expect(container.textContent).toContain('Retries');
    expect(container.textContent).toContain('3');
  });

  it('renders unknown status gracefully', () => {
    const { container } = wrap(<JobStatusSection data={{ status: 'unknown_status' }} />);
    expect(container.textContent).toContain('UNKNOWN_STATUS');
  });

  it('renders empty data gracefully', () => {
    const { container } = wrap(<JobStatusSection data={{}} />);
    expect(container.textContent).toContain('UNKNOWN');
    expect(container.textContent).toContain('Job Status');
  });

  it('renders last heartbeat timestamp', () => {
    const { container } = wrap(
      <JobStatusSection
        data={{ status: 'processing', last_heartbeat_at: '2024-01-15T10:30:00Z' }}
      />,
    );
    expect(container.textContent).toContain('2024-01-15T10:30:00Z');
  });

  it('shows N/A for missing heartbeat', () => {
    const { container } = wrap(<JobStatusSection data={{ status: 'pending' }} />);
    expect(container.textContent).toContain('N/A');
  });

  it('renders periodic job fields', () => {
    const { container } = wrap(
      <JobStatusSection
        data={{
          status: 'processing',
          periodic_interval_seconds: 60,
          periodic_max_runs: 10,
          periodic_runs: 5,
          periodic_initial_delay_seconds: 30,
        }}
      />,
    );
    expect(container.textContent).toContain('60s');
    expect(container.textContent).toContain('30s');
    expect(container.textContent).toContain('10');
  });

  it('shows Unlimited when periodic_max_runs is 0', () => {
    const { container } = wrap(
      <JobStatusSection
        data={{
          status: 'pending',
          periodic_interval_seconds: 60,
          periodic_max_runs: 0,
        }}
      />,
    );
    expect(container.textContent).toContain('Unlimited');
  });

  it('renders progress bar for periodic runs', () => {
    const { container } = wrap(
      <JobStatusSection
        data={{
          status: 'processing',
          periodic_interval_seconds: 60,
          periodic_max_runs: 10,
          periodic_runs: 5,
        }}
      />,
    );
    // Should contain the progress element
    const progressBar = container.querySelector('[role="progressbar"]');
    expect(progressBar).not.toBeNull();
  });

  it('renders all standard rows', () => {
    const { container } = wrap(
      <JobStatusSection
        data={{
          status: 'failed',
          retries: 1,
          max_retries: 3,
          errmsg: 'timeout',
          last_heartbeat_at: '2024-06-01',
          periodic_interval_seconds: 120,
          periodic_max_runs: 5,
          periodic_runs: 2,
          periodic_initial_delay_seconds: 10,
        }}
      />,
    );
    expect(container.textContent).toContain('Status');
    expect(container.textContent).toContain('Retries');
    expect(container.textContent).toContain('Error Message');
    expect(container.textContent).toContain('Last Heartbeat');
    expect(container.textContent).toContain('Periodic Interval');
    expect(container.textContent).toContain('Periodic Max Runs');
    expect(container.textContent).toContain('Periodic Runs');
    expect(container.textContent).toContain('Periodic Initial Delay');
  });
});
