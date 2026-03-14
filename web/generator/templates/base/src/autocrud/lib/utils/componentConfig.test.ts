/**
 * Tests for component-level config (TableConfig, CreateConfig, DetailConfig)
 * via applyCustomizations and ResourceConfig merging.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { resources, applyCustomizations } from '../resources';
import type { ResourceConfig } from '../resources';

function registerResource(overrides: Partial<ResourceConfig> = {}): ResourceConfig {
  const config: ResourceConfig = {
    name: 'test-resource',
    label: 'Test Resource',
    pluralLabel: 'Test Resources',
    schema: 'TestResource',
    fields: [
      {
        name: 'name',
        label: 'Name',
        type: 'string',
        isArray: false,
        isRequired: true,
        isNullable: false,
      },
    ],
    apiClient: {} as any,
    ...overrides,
  };
  resources[config.name] = config;
  return config;
}

describe('applyCustomizations — component-level configs', () => {
  beforeEach(() => {
    for (const key of Object.keys(resources)) {
      delete resources[key];
    }
  });

  // ── TableConfig ──

  it('sets tableConfig from customization.table', () => {
    registerResource();

    applyCustomizations({
      'test-resource': {
        table: { canCreate: false, initPageSize: 50 },
      },
    } as any);

    expect(resources['test-resource'].tableConfig).toEqual({
      canCreate: false,
      initPageSize: 50,
    });
  });

  it('merges tableConfig with existing config', () => {
    registerResource({
      tableConfig: { canCreate: true, width: 'lg' },
    });

    applyCustomizations({
      'test-resource': {
        table: { canCreate: false, initPageSize: 50 },
      },
    } as any);

    expect(resources['test-resource'].tableConfig).toEqual({
      canCreate: false,
      width: 'lg',
      initPageSize: 50,
    });
  });

  it('sets tableConfig with alwaysSearchCondition', () => {
    registerResource();

    applyCustomizations({
      'test-resource': {
        table: {
          alwaysSearchCondition: [{ field: 'tag', operator: 'eq', value: 'important' }],
        },
      },
    } as any);

    expect(resources['test-resource'].tableConfig?.alwaysSearchCondition).toEqual([
      { field: 'tag', operator: 'eq', value: 'important' },
    ]);
  });

  it('sets tableConfig with rowPerPageOptions', () => {
    registerResource();

    applyCustomizations({
      'test-resource': {
        table: { rowPerPageOptions: [10, 25, 50, 100] },
      },
    } as any);

    expect(resources['test-resource'].tableConfig?.rowPerPageOptions).toEqual([10, 25, 50, 100]);
  });

  it('sets tableConfig wrappedInContainer to false', () => {
    registerResource();

    applyCustomizations({
      'test-resource': {
        table: { wrappedInContainer: false },
      },
    } as any);

    expect(resources['test-resource'].tableConfig?.wrappedInContainer).toBe(false);
  });

  it('sets tableConfig with disableGlobalSearch and disableAdvancedSearch', () => {
    registerResource();

    applyCustomizations({
      'test-resource': {
        table: { disableGlobalSearch: true, disableAdvancedSearch: true },
      },
    } as any);

    expect(resources['test-resource'].tableConfig?.disableGlobalSearch).toBe(true);
    expect(resources['test-resource'].tableConfig?.disableAdvancedSearch).toBe(true);
  });

  it('sets tableConfig with density and title', () => {
    registerResource();

    applyCustomizations({
      'test-resource': {
        table: { density: 'md', title: 'Custom Title' },
      },
    } as any);

    expect(resources['test-resource'].tableConfig?.density).toBe('md');
    expect(resources['test-resource'].tableConfig?.title).toBe('Custom Title');
  });

  // ── CreateConfig ──

  it('sets createConfig from customization.create', () => {
    registerResource();

    applyCustomizations({
      'test-resource': {
        create: { customFormOnly: true, showBackButton: false },
      },
    } as any);

    expect(resources['test-resource'].createConfig).toEqual({
      customFormOnly: true,
      showBackButton: false,
    });
  });

  it('merges createConfig with existing config', () => {
    registerResource({
      createConfig: { wrappedInContainer: false, title: 'Existing Title' },
    });

    applyCustomizations({
      'test-resource': {
        create: { customFormOnly: true },
      },
    } as any);

    expect(resources['test-resource'].createConfig).toEqual({
      wrappedInContainer: false,
      title: 'Existing Title',
      customFormOnly: true,
    });
  });

  it('sets createConfig with onCancel callback', () => {
    registerResource();
    const cancelFn = () => {};

    applyCustomizations({
      'test-resource': {
        create: { onCancel: cancelFn },
      },
    } as any);

    expect(resources['test-resource'].createConfig?.onCancel).toBe(cancelFn);
  });

  it('sets createConfig with title override', () => {
    registerResource();

    applyCustomizations({
      'test-resource': {
        create: { title: 'New Character' },
      },
    } as any);

    expect(resources['test-resource'].createConfig?.title).toBe('New Character');
  });

  // ── DetailConfig ──

  it('sets detailConfig from customization.detail', () => {
    registerResource();

    applyCustomizations({
      'test-resource': {
        detail: {
          showEditButton: false,
          showDeleteButton: false,
          showRevisionHistory: false,
        },
      },
    } as any);

    expect(resources['test-resource'].detailConfig).toEqual({
      showEditButton: false,
      showDeleteButton: false,
      showRevisionHistory: false,
    });
  });

  it('merges detailConfig with existing config', () => {
    registerResource({
      detailConfig: { wrappedInContainer: false, title: 'Existing' },
    });

    applyCustomizations({
      'test-resource': {
        detail: { showEditButton: false },
      },
    } as any);

    expect(resources['test-resource'].detailConfig).toEqual({
      wrappedInContainer: false,
      title: 'Existing',
      showEditButton: false,
    });
  });

  it('sets detailConfig with onClose callback', () => {
    registerResource();
    const closeFn = () => {};

    applyCustomizations({
      'test-resource': {
        detail: { onClose: closeFn },
      },
    } as any);

    expect(resources['test-resource'].detailConfig?.onClose).toBe(closeFn);
  });

  it('sets detailConfig with showBackButton false', () => {
    registerResource();

    applyCustomizations({
      'test-resource': {
        detail: { showBackButton: false },
      },
    } as any);

    expect(resources['test-resource'].detailConfig?.showBackButton).toBe(false);
  });

  // ── Combined ──

  it('sets all three configs in a single customization', () => {
    registerResource();

    applyCustomizations({
      'test-resource': {
        table: { canCreate: false },
        create: { customFormOnly: true },
        detail: { showRevisionHistory: false },
      },
    } as any);

    expect(resources['test-resource'].tableConfig).toEqual({ canCreate: false });
    expect(resources['test-resource'].createConfig).toEqual({ customFormOnly: true });
    expect(resources['test-resource'].detailConfig).toEqual({ showRevisionHistory: false });
  });

  it('does not set configs when not provided in customization', () => {
    registerResource();

    applyCustomizations({
      'test-resource': {
        label: 'Renamed',
      },
    } as any);

    expect(resources['test-resource'].tableConfig).toBeUndefined();
    expect(resources['test-resource'].createConfig).toBeUndefined();
    expect(resources['test-resource'].detailConfig).toBeUndefined();
  });

  it('warns for unknown resource and skips', () => {
    registerResource();
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

    applyCustomizations({
      nonexistent: {
        table: { canCreate: false },
      },
    } as any);

    expect(warnSpy).toHaveBeenCalledWith(
      expect.stringContaining("resource 'nonexistent' not found"),
    );
    warnSpy.mockRestore();
  });
});
