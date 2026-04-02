import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import { JobArtifactSection } from './JobArtifactSection';

// ── Mock child components ──
vi.mock('../field/DetailFieldRenderer', () => ({
  DetailFieldRenderer: ({ field, value }: any) => (
    <span data-testid={`detail-field-${field.name}`}>{JSON.stringify(value)}</span>
  ),
}));

vi.mock('../field/DetailFieldRenderer/CollapsibleJson', () => ({
  CollapsibleJson: ({ value }: any) => (
    <span data-testid="collapsible-json">{JSON.stringify(value)}</span>
  ),
}));

vi.mock('@/autocrud/lib/utils/formUtils', () => ({
  getByPath: (obj: any, path: string) => {
    const parts = path.split('.');
    let val = obj;
    for (const p of parts) {
      if (val == null) return undefined;
      val = val[p];
    }
    return val;
  },
}));

beforeEach(() => {
  cleanup();
});

const makeField = (name: string, label?: string) => ({
  name,
  label: label || name,
  type: 'string' as const,
  isArray: false,
  isRequired: false,
  isNullable: false,
});

describe('JobArtifactSection', () => {
  it('renders nothing when no groups, no collapsed groups, and no artifact', () => {
    const { container } = render(
      <MantineProvider>
        <JobArtifactSection data={{}} groups={[]} collapsedGroups={[]} />
      </MantineProvider>,
    );
    // MantineProvider injects styles; check component didn't render content
    expect(container.querySelector('table')).toBeNull();
    expect(screen.queryByText('Artifact')).toBeNull();
  });

  it('renders nothing when artifact is null and no groups', () => {
    const { container } = render(
      <MantineProvider>
        <JobArtifactSection data={{ artifact: null }} groups={[]} collapsedGroups={[]} />
      </MantineProvider>,
    );
    expect(container.querySelector('table')).toBeNull();
    expect(screen.queryByText('Artifact')).toBeNull();
  });

  it('renders Artifact title when there are groups', () => {
    render(
      <MantineProvider>
        <JobArtifactSection
          data={{ result: 'ok' }}
          groups={[{ kind: 'single', field: makeField('result', 'Result') }]}
          collapsedGroups={[]}
        />
      </MantineProvider>,
    );
    expect(screen.getByText('Artifact')).toBeDefined();
  });

  it('renders single field groups with DetailFieldRenderer', () => {
    render(
      <MantineProvider>
        <JobArtifactSection
          data={{ result: 'success' }}
          groups={[{ kind: 'single', field: makeField('result', 'Result') }]}
          collapsedGroups={[]}
        />
      </MantineProvider>,
    );
    expect(screen.getByText('Result')).toBeDefined();
    expect(screen.getByTestId('detail-field-result')).toBeDefined();
  });

  it('renders nested groups with children', () => {
    render(
      <MantineProvider>
        <JobArtifactSection
          data={{ artifact: { name: 'test', value: 42 } }}
          groups={[
            {
              kind: 'nested',
              parentPath: 'artifact',
              parentLabel: 'Artifact Data',
              children: [makeField('artifact.name', 'Name'), makeField('artifact.value', 'Value')],
            },
          ]}
          collapsedGroups={[]}
        />
      </MantineProvider>,
    );
    expect(screen.getByText('Artifact Data')).toBeDefined();
    expect(screen.getByTestId('detail-field-artifact.name')).toBeDefined();
    expect(screen.getByTestId('detail-field-artifact.value')).toBeDefined();
  });

  it('renders N/A when nested group parent value is null', () => {
    render(
      <MantineProvider>
        <JobArtifactSection
          data={{}}
          groups={[
            {
              kind: 'nested',
              parentPath: 'artifact',
              parentLabel: 'Artifact Data',
              children: [makeField('artifact.name', 'Name')],
            },
          ]}
          collapsedGroups={[]}
        />
      </MantineProvider>,
    );
    expect(screen.getByText('N/A')).toBeDefined();
  });

  it('renders collapsed groups with CollapsibleJson', () => {
    render(
      <MantineProvider>
        <JobArtifactSection
          data={{ extra: { nested: true } }}
          groups={[]}
          collapsedGroups={[{ path: 'extra', label: 'Extra Data' }]}
        />
      </MantineProvider>,
    );
    expect(screen.getByText('Extra Data')).toBeDefined();
    expect(screen.getByTestId('collapsible-json')).toBeDefined();
  });

  it('renders N/A for collapsed groups with null value', () => {
    render(
      <MantineProvider>
        <JobArtifactSection
          data={{}}
          groups={[]}
          collapsedGroups={[{ path: 'missing', label: 'Missing' }]}
        />
      </MantineProvider>,
    );
    expect(screen.getByText('Missing')).toBeDefined();
    expect(screen.getByText('N/A')).toBeDefined();
  });

  it('renders when artifact exists but groups are empty', () => {
    render(
      <MantineProvider>
        <JobArtifactSection
          data={{ artifact: { value: 42 } }}
          groups={[]}
          collapsedGroups={[]}
        />
      </MantineProvider>,
    );
    expect(screen.getByText('Artifact')).toBeDefined();
  });
});
