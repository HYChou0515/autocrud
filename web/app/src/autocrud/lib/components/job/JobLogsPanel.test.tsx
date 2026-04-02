import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import { JobLogsPanel } from './JobLogsPanel';

beforeEach(() => cleanup());

function renderPanel(props: Partial<React.ComponentProps<typeof JobLogsPanel>> = {}) {
  return render(
    <MantineProvider>
      <JobLogsPanel
        logs={null}
        loading={false}
        onFetch={vi.fn()}
        available={true}
        {...props}
      />
    </MantineProvider>,
  );
}

describe('JobLogsPanel', () => {
  it('renders nothing when not available', () => {
    const { container } = renderPanel({ available: false });
    expect(container.querySelector('.mantine-Paper-root')).toBeNull();
  });

  it('renders "Load Logs" button when logs is null', () => {
    renderPanel({ logs: null, loading: false });
    expect(screen.getByText('Load Logs')).toBeTruthy();
    expect(screen.getByText(/Click "Load Logs"/)).toBeTruthy();
  });

  it('renders "Refresh" button when logs is available', () => {
    renderPanel({ logs: 'Some log content', loading: false });
    expect(screen.getByText('Refresh')).toBeTruthy();
  });

  it('shows loading state', () => {
    renderPanel({ logs: null, loading: true });
    expect(screen.getByText(/Loading logs/)).toBeTruthy();
  });

  it('shows "No logs available" when logs is undefined', () => {
    renderPanel({ logs: undefined, loading: false });
    expect(screen.getByText(/No logs available/)).toBeTruthy();
  });

  it('renders log text content', () => {
    renderPanel({ logs: 'ERROR: something went wrong\nINFO: recovered', loading: false });
    expect(screen.getByText(/ERROR: something went wrong/)).toBeTruthy();
  });

  it('calls onFetch when button clicked', () => {
    const onFetch = vi.fn();
    renderPanel({ logs: null, loading: false, onFetch });
    screen.getByText('Load Logs').click();
    expect(onFetch).toHaveBeenCalled();
  });

  it('disables button when loading', () => {
    const { container } = renderPanel({ logs: 'data', loading: true });
    const btn = Array.from(container.querySelectorAll('button')).find(
      (b) => b.textContent === 'Refresh',
    );
    expect(btn?.hasAttribute('data-disabled') || btn?.getAttribute('disabled') !== null).toBeTruthy();
  });
});
