import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import { MetadataSection, type MetadataSectionProps } from './MetadataSection';

// Mock child components to simplify testing
vi.mock('../common/TimeDisplay', () => ({
  TimeDisplay: ({ time, format }: any) => <span data-testid="time-display">{time} ({format})</span>,
}));

vi.mock('../common/ResourceIdCell', () => ({
  ResourceIdCell: ({ rid }: any) => <span data-testid="resource-id">{rid}</span>,
}));

vi.mock('../common/RevisionIdCell', () => ({
  RevisionIdCell: ({ revisionId }: any) => <span data-testid="revision-id">{revisionId}</span>,
}));

beforeEach(() => {
  cleanup();
});

const wrap = (ui: React.ReactElement) => render(<MantineProvider>{ui}</MantineProvider>);

const baseMeta: MetadataSectionProps['meta'] = {
  resource_id: 'res-123',
  current_revision_id: 'rev-456',
  created_time: '2024-01-01T00:00:00Z',
  updated_time: '2024-06-15T12:00:00Z',
  created_by: 'alice',
  updated_by: 'bob',
};

describe('MetadataSection', () => {
  it('renders metadata title', () => {
    wrap(<MetadataSection meta={baseMeta} />);
    expect(screen.getByText('Metadata')).toBeDefined();
  });

  it('renders resource ID', () => {
    wrap(<MetadataSection meta={baseMeta} />);
    expect(screen.getByTestId('resource-id').textContent).toBe('res-123');
  });

  it('renders revision ID', () => {
    wrap(<MetadataSection meta={baseMeta} />);
    expect(screen.getByTestId('revision-id').textContent).toBe('rev-456');
  });

  it('renders created/updated times', () => {
    wrap(<MetadataSection meta={baseMeta} />);
    const times = screen.getAllByTestId('time-display');
    expect(times.length).toBeGreaterThanOrEqual(2);
  });

  it('renders created/updated by', () => {
    const { container } = wrap(<MetadataSection meta={baseMeta} />);
    expect(container.textContent).toContain('by alice');
    expect(container.textContent).toContain('by bob');
  });

  it('renders revision status badge when provided', () => {
    const meta = { ...baseMeta, revision_status: 'stable' };
    wrap(<MetadataSection meta={meta} />);
    expect(screen.getByText('stable')).toBeDefined();
  });

  it('does not render revision status when not provided', () => {
    const { container } = wrap(<MetadataSection meta={baseMeta} />);
    expect(container.querySelectorAll('.mantine-Badge-root').length).toBeLessThanOrEqual(1);
  });

  it('renders total revision count in full variant', () => {
    const meta = { ...baseMeta, total_revision_count: 5 };
    wrap(<MetadataSection meta={meta} variant="full" />);
    expect(screen.getByText('5')).toBeDefined();
    expect(screen.getByText('Total Revisions')).toBeDefined();
  });

  it('does not render total revision count in compact variant', () => {
    const meta = { ...baseMeta, total_revision_count: 5 };
    const { container } = wrap(<MetadataSection meta={meta} variant="compact" />);
    expect(container.textContent).not.toContain('Total Revisions');
  });

  it('defaults to full variant', () => {
    const meta = { ...baseMeta, total_revision_count: 3 };
    wrap(<MetadataSection meta={meta} />);
    expect(screen.getByText('Total Revisions')).toBeDefined();
  });

  it('uses revisionInfo for updated time when provided', () => {
    const revisionInfo = { updated_time: '2024-12-25T00:00:00Z', updated_by: 'carol' };
    const { container } = wrap(<MetadataSection meta={baseMeta} revisionInfo={revisionInfo} />);
    expect(container.textContent).toContain('by carol');
  });
});
