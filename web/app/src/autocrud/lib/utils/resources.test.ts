import { describe, it, expect, beforeEach } from 'vitest';
import { resources, applyCustomizations } from '../resources';
import type { ResourceConfig } from '../resources';

/** Helper: register a minimal resource config for testing */
function registerResource(overrides: Partial<ResourceConfig> = {}): ResourceConfig {
  const config: ResourceConfig = {
    name: 'test-job',
    label: 'Test Job',
    pluralLabel: 'Test Jobs',
    schema: 'TestJob',
    fields: [
      {
        name: 'payload',
        label: 'Payload',
        type: 'object',
        isArray: false,
        isRequired: true,
        isNullable: false,
      },
      {
        name: 'status',
        label: 'Status',
        type: 'string',
        isArray: false,
        isRequired: false,
        isNullable: false,
      },
      {
        name: 'errmsg',
        label: 'Errmsg',
        type: 'string',
        isArray: false,
        isRequired: false,
        isNullable: false,
      },
      {
        name: 'retries',
        label: 'Retries',
        type: 'number',
        isArray: false,
        isRequired: false,
        isNullable: false,
      },
    ],
    defaultHiddenFields: ['status', 'errmsg', 'retries'],
    apiClient: {} as any,
    ...overrides,
  };
  resources[config.name] = config;
  return config;
}

describe('applyCustomizations — showHiddenFields', () => {
  beforeEach(() => {
    // Clean up resources registry
    for (const key of Object.keys(resources)) {
      delete resources[key];
    }
  });

  it('removes listed fields from defaultHiddenFields via showHiddenFields', () => {
    registerResource();

    applyCustomizations({
      'test-job': {
        showHiddenFields: ['status'],
      },
    } as any);

    expect(resources['test-job'].defaultHiddenFields).toEqual(['errmsg', 'retries']);
  });

  it('removes multiple fields from defaultHiddenFields', () => {
    registerResource();

    applyCustomizations({
      'test-job': {
        showHiddenFields: ['status', 'retries'],
      },
    } as any);

    expect(resources['test-job'].defaultHiddenFields).toEqual(['errmsg']);
  });

  it('does nothing when showHiddenFields is not provided', () => {
    registerResource();

    applyCustomizations({
      'test-job': {
        label: 'Renamed Job',
      },
    } as any);

    expect(resources['test-job'].defaultHiddenFields).toEqual(['status', 'errmsg', 'retries']);
    expect(resources['test-job'].label).toBe('Renamed Job');
  });

  it('does nothing when resource has no defaultHiddenFields', () => {
    registerResource({ defaultHiddenFields: undefined });

    applyCustomizations({
      'test-job': {
        showHiddenFields: ['status'],
      },
    } as any);

    // No error, defaultHiddenFields stays undefined
    expect(resources['test-job'].defaultHiddenFields).toBeUndefined();
  });

  it('can reveal all hidden fields to make them all visible', () => {
    registerResource();

    applyCustomizations({
      'test-job': {
        showHiddenFields: ['status', 'errmsg', 'retries'],
      },
    } as any);

    expect(resources['test-job'].defaultHiddenFields).toEqual([]);
  });
});
