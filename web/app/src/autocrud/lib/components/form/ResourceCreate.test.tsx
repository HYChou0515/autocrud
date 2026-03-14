/**
 * ResourceCreate — unit tests for customization props
 *
 * Tests:
 * 1. customFormOnly hides standard form tab
 * 2. onCancel callback is used instead of navigate
 * 3. wrappedInContainer=false skips Container
 * 4. showBackButton=false hides Back button
 * 5. title overrides default title
 * 6. Config-based customization via config.createConfig
 * 7. Props override config.createConfig
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { ResourceConfig, ResourceField, CustomCreateAction } from '../../resources';

const mockNavigate = vi.fn();

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => mockNavigate,
}));

vi.mock('./ResourceForm', () => ({
  ResourceForm: ({ onCancel, onSubmit, submitLabel }: any) => (
    <div data-testid="resource-form" data-submit-label={submitLabel}>
      <button data-testid="form-cancel" onClick={onCancel}>
        Cancel
      </button>
      <button data-testid="form-submit" onClick={() => onSubmit({})}>
        Submit
      </button>
    </div>
  ),
}));

vi.mock('../../utils/errorNotification', () => ({
  showErrorNotification: vi.fn(),
  extractUniqueConflict: vi.fn().mockReturnValue(null),
}));

import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import { ResourceCreate } from './ResourceCreate';

function makeField(name: string): ResourceField {
  return {
    name,
    label: name,
    type: 'string',
    isArray: false,
    isRequired: true,
    isNullable: false,
  };
}

function makeAction(name: string, label: string): CustomCreateAction {
  return {
    name,
    label,
    fields: [makeField('url')],
    apiMethod: vi.fn().mockResolvedValue({ data: { resource_id: 'r1', revision_id: 'rev1' } }),
  };
}

function makeConfig(overrides?: Partial<ResourceConfig<any>>): ResourceConfig<any> {
  return {
    name: 'test-resource',
    label: 'Test Resource',
    pluralLabel: 'Test Resources',
    schema: 'TestResource',
    fields: [makeField('name'), makeField('value')],
    apiClient: {
      create: vi.fn().mockResolvedValue({ data: { resource_id: 'r1', revision_id: 'rev1' } }),
      list: vi.fn(),
      count: vi.fn(),
      get: vi.fn(),
      update: vi.fn(),
      delete: vi.fn(),
      permanentlyDelete: vi.fn(),
      restore: vi.fn(),
      revisionList: vi.fn(),
      switchRevision: vi.fn(),
    },
    ...overrides,
  };
}

function renderCreate(
  config: ResourceConfig<any>,
  props: Partial<React.ComponentProps<typeof ResourceCreate>> = {},
) {
  return render(
    <MantineProvider>
      <ResourceCreate config={config} basePath="/test" {...props} />
    </MantineProvider>,
  );
}

describe('ResourceCreate — customization props', () => {
  beforeEach(() => {
    cleanup();
    mockNavigate.mockReset();
  });

  // ── Default behaviour ──

  it('renders with default title "Create {label}"', () => {
    const config = makeConfig();
    renderCreate(config);
    expect(screen.getByText('Create Test Resource')).toBeTruthy();
  });

  it('renders Back button by default', () => {
    const config = makeConfig();
    renderCreate(config);
    expect(screen.getByText('Back')).toBeTruthy();
  });

  it('wraps in Container by default (has standard form)', () => {
    const config = makeConfig();
    const { container } = renderCreate(config);
    // Container renders a div with mantine class
    const forms = container.querySelectorAll('[data-testid="resource-form"]');
    expect(forms.length).toBe(1);
  });

  // ── showBackButton ──

  it('hides Back button when showBackButton=false', () => {
    const config = makeConfig();
    renderCreate(config, { showBackButton: false });
    expect(screen.queryByText('Back')).toBeNull();
  });

  // ── title ──

  it('uses custom title from prop', () => {
    const config = makeConfig();
    renderCreate(config, { title: 'New Character' });
    expect(screen.getByText('New Character')).toBeTruthy();
    expect(screen.queryByText('Create Test Resource')).toBeNull();
  });

  // ── onCancel ──

  it('uses custom onCancel callback', () => {
    const config = makeConfig();
    const onCancel = vi.fn();
    renderCreate(config, { onCancel });

    // Click the form cancel button
    fireEvent.click(screen.getByTestId('form-cancel'));
    expect(onCancel).toHaveBeenCalled();
  });

  it('uses custom onCancel for Back button', () => {
    const config = makeConfig();
    const onCancel = vi.fn();
    renderCreate(config, { onCancel });

    fireEvent.click(screen.getByText('Back'));
    expect(onCancel).toHaveBeenCalled();
  });

  // ── wrappedInContainer ──

  it('skips Container when wrappedInContainer=false', () => {
    const config = makeConfig();
    const { container } = renderCreate(config, { wrappedInContainer: false });
    // Should not have a mantine Container element
    const containerEl = container.querySelector('.mantine-Container-root');
    expect(containerEl).toBeNull();
  });

  it('has Container when wrappedInContainer=true (default)', () => {
    const config = makeConfig();
    const { container } = renderCreate(config);
    const containerEl = container.querySelector('.mantine-Container-root');
    expect(containerEl).toBeTruthy();
  });

  // ── customFormOnly ──

  it('shows "Standard" tab when hasCustomActions and customFormOnly=false', () => {
    const config = makeConfig({
      customCreateActions: [makeAction('import', 'Import')],
    });
    renderCreate(config, { customFormOnly: false });
    expect(screen.getByText('Standard')).toBeTruthy();
    expect(screen.getByText('Import')).toBeTruthy();
  });

  it('hides "Standard" tab when customFormOnly=true', () => {
    const config = makeConfig({
      customCreateActions: [makeAction('import', 'Import'), makeAction('clone', 'Clone')],
    });
    renderCreate(config, { customFormOnly: true });
    expect(screen.queryByText('Standard')).toBeNull();
    expect(screen.getByText('Import')).toBeTruthy();
    expect(screen.getByText('Clone')).toBeTruthy();
  });

  it('shows only the custom form without tabs when customFormOnly=true and single action', () => {
    const config = makeConfig({
      customCreateActions: [makeAction('import', 'Import')],
    });
    renderCreate(config, { customFormOnly: true });
    // No tabs at all — just the form directly
    expect(screen.queryByText('Standard')).toBeNull();
    // The form is rendered with the action's submit label
    const form = screen.getByTestId('resource-form');
    expect(form.getAttribute('data-submit-label')).toBe('Import');
  });

  it('customFormOnly has no effect when no customCreateActions', () => {
    const config = makeConfig();
    renderCreate(config, { customFormOnly: true });
    // Standard form rendered as usual
    const forms = screen.getAllByTestId('resource-form');
    expect(forms.length).toBe(1);
  });

  // ── Config-based customization ──

  it('reads createConfig from config', () => {
    const config = makeConfig({
      createConfig: { showBackButton: false, title: 'Config Title' },
    });
    renderCreate(config);
    expect(screen.queryByText('Back')).toBeNull();
    expect(screen.getByText('Config Title')).toBeTruthy();
  });

  it('props override createConfig', () => {
    const config = makeConfig({
      createConfig: { title: 'Config Title', showBackButton: false },
    });
    renderCreate(config, { title: 'Prop Title', showBackButton: true });
    expect(screen.getByText('Prop Title')).toBeTruthy();
    expect(screen.queryByText('Config Title')).toBeNull();
    expect(screen.getByText('Back')).toBeTruthy();
  });

  // ── Custom create action — async job navigation ──

  it('navigates to basePath (not job detail) after async-job custom create action', async () => {
    const mockApiMethod = vi.fn().mockResolvedValue({
      data: { job_resource_id: 'job-123', resource_id: 'r1' },
    });

    const jobAction: CustomCreateAction = {
      name: 'create-special',
      label: 'Create Special',
      fields: [makeField('url')],
      apiMethod: mockApiMethod,
      asyncMode: 'job',
      jobResourceName: 'create-special-job',
    };

    const config = makeConfig({
      customCreateActions: [jobAction],
    });

    renderCreate(config, { customFormOnly: true });

    // Submit the custom action form
    fireEvent.click(screen.getByTestId('form-submit'));

    await waitFor(() => {
      expect(mockApiMethod).toHaveBeenCalled();
      // Should navigate to basePath (/test), NOT to the job detail page
      expect(mockNavigate).toHaveBeenCalledWith({ to: '/test' });
    });

    // Verify it did NOT navigate to the job detail page
    expect(mockNavigate).not.toHaveBeenCalledWith(
      expect.objectContaining({ to: expect.stringContaining('create-special-job') }),
    );
  });

  it('navigates to basePath after non-async custom create action', async () => {
    const mockApiMethod = vi.fn().mockResolvedValue({
      data: { resource_id: 'r1', revision_id: 'rev1' },
    });

    const action: CustomCreateAction = {
      name: 'import',
      label: 'Import',
      fields: [makeField('url')],
      apiMethod: mockApiMethod,
    };

    const config = makeConfig({
      customCreateActions: [action],
    });

    renderCreate(config, { customFormOnly: true });

    fireEvent.click(screen.getByTestId('form-submit'));

    await waitFor(() => {
      expect(mockApiMethod).toHaveBeenCalled();
      expect(mockNavigate).toHaveBeenCalledWith({ to: '/test' });
    });
  });
});
