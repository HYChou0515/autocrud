import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import { JobFieldsSection } from './JobFieldsSection';

beforeEach(() => {
  cleanup();
});

const wrap = (ui: React.ReactElement) => render(<MantineProvider>{ui}</MantineProvider>);

describe('JobFieldsSection', () => {
  it('renders nothing when no extra fields', () => {
    const { container } = wrap(
      <JobFieldsSection data={{ status: 'pending', retries: 0, payload: {} }} />,
    );
    expect(container.textContent).not.toContain('Job Fields');
  });

  it('renders nothing for data with only status fields', () => {
    const { container } = wrap(
      <JobFieldsSection
        data={{
          status: 'completed',
          retries: 2,
          max_retries: 5,
          errmsg: null,
          last_heartbeat_at: null,
          payload: { foo: 1 },
          artifact: {},
        }}
      />,
    );
    expect(container.textContent).not.toContain('Job Fields');
  });

  it('renders other fields as key-value table', () => {
    wrap(
      <JobFieldsSection
        data={{
          status: 'pending',
          payload: {},
          custom_field: 'hello',
          another_field: 42,
        }}
      />,
    );
    expect(screen.getByText('Job Fields')).toBeDefined();
    expect(screen.getByText('custom_field')).toBeDefined();
    expect(screen.getByText('hello')).toBeDefined();
    expect(screen.getByText('another_field')).toBeDefined();
    expect(screen.getByText('42')).toBeDefined();
  });

  it('filters out JOB_STATUS_FIELDS from rendering', () => {
    const { container } = wrap(
      <JobFieldsSection
        data={{
          status: 'processing',
          retries: 3,
          max_retries: 5,
          errmsg: 'some error',
          last_heartbeat_at: '2024-01-01',
          periodic_interval_seconds: 60,
          periodic_max_runs: 10,
          periodic_runs: 5,
          periodic_initial_delay_seconds: 30,
          payload: {},
          artifact: {},
          my_extra: 'visible',
        }}
      />,
    );
    expect(container.textContent).toContain('my_extra');
    expect(container.textContent).toContain('visible');
    // status fields should NOT appear
    expect(container.textContent).not.toContain('retries');
    expect(container.textContent).not.toContain('errmsg');
  });

  it('renders object values via renderSimpleValue', () => {
    wrap(
      <JobFieldsSection
        data={{
          status: 'pending',
          payload: {},
          nested_obj: { a: 1, b: 'two' },
        }}
      />,
    );
    expect(screen.getByText('nested_obj')).toBeDefined();
  });

  it('renders boolean values', () => {
    wrap(
      <JobFieldsSection
        data={{
          status: 'pending',
          payload: {},
          is_active: true,
          is_deleted: false,
        }}
      />,
    );
    expect(screen.getByText('is_active')).toBeDefined();
    expect(screen.getByText('is_deleted')).toBeDefined();
  });

  it('renders null values', () => {
    wrap(
      <JobFieldsSection
        data={{
          status: 'pending',
          payload: {},
          empty_field: null,
        }}
      />,
    );
    expect(screen.getByText('empty_field')).toBeDefined();
  });
});
