import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup, waitFor } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import { Dashboard } from './Dashboard';

// ── Mock resources ──
const mockGetResourceNames = vi.fn();
const mockGetResource = vi.fn();

vi.mock('../resources', () => ({
  getResourceNames: () => mockGetResourceNames(),
  getResource: (name: string) => mockGetResource(name),
}));

vi.mock('@tanstack/react-router', () => ({
  Link: ({ children, to, ...props }: any) => (
    <a href={to} {...props}>
      {children}
    </a>
  ),
}));

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function setupResources(
  resources: { name: string; label: string; count: number; error?: boolean }[],
) {
  mockGetResourceNames.mockReturnValue(resources.map((r) => r.name));
  mockGetResource.mockImplementation((name: string) => {
    const res = resources.find((r) => r.name === name);
    if (!res) return null;
    return {
      label: res.label,
      apiClient: {
        count: res.error
          ? vi.fn().mockRejectedValue(new Error('API error'))
          : vi.fn().mockResolvedValue({ data: res.count }),
      },
    };
  });
}

describe('Dashboard', () => {
  it('renders dashboard title', () => {
    setupResources([]);
    render(
      <MantineProvider>
        <Dashboard />
      </MantineProvider>,
    );
    expect(screen.getByText('Dashboard')).toBeDefined();
    expect(screen.getByText('SpecStar Resource Overview')).toBeDefined();
  });

  it('shows resource cards with counts after loading', async () => {
    setupResources([
      { name: 'character', label: 'Character', count: 42 },
      { name: 'equipment', label: 'Equipment', count: 10 },
    ]);

    render(
      <MantineProvider>
        <Dashboard />
      </MantineProvider>,
    );

    // Initially should show loading or labels
    expect(screen.getByText('Character')).toBeDefined();
    expect(screen.getByText('Equipment')).toBeDefined();

    // After loading
    await waitFor(() => {
      expect(screen.getByText('42 resources')).toBeDefined();
      expect(screen.getByText('10 resources')).toBeDefined();
    });
  });

  it('shows 0 count on API error', async () => {
    setupResources([{ name: 'character', label: 'Character', count: 0, error: true }]);

    render(
      <MantineProvider>
        <Dashboard />
      </MantineProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText('0 resources')).toBeDefined();
    });
  });

  it('renders cards as links', async () => {
    setupResources([{ name: 'character', label: 'Character', count: 5 }]);

    const { container } = render(
      <MantineProvider>
        <Dashboard />
      </MantineProvider>,
    );

    await waitFor(() => {
      const link = container.querySelector('a[href="/specstar-admin/character"]');
      expect(link).not.toBeNull();
    });
  });

  it('renders with no resources', () => {
    setupResources([]);
    render(
      <MantineProvider>
        <Dashboard />
      </MantineProvider>,
    );
    expect(screen.getByText('Dashboard')).toBeDefined();
  });
});
