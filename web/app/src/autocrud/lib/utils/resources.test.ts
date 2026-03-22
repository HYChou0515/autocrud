import { describe, it, expect, beforeEach } from 'vitest';
import {
  resources,
  applyCustomizations,
  asyncCreateJobs,
  isJobResource,
  getStandaloneJobNames,
  isAsyncCreateJob,
  getAsyncCreateJobChildren,
} from '../resources';
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

// ============================================================================
// isJobResource / getStandaloneJobNames
// ============================================================================
describe('isJobResource', () => {
  beforeEach(() => {
    for (const key of Object.keys(resources)) delete resources[key];
    for (const key of Object.keys(asyncCreateJobs)) delete asyncCreateJobs[key];
  });

  it('returns true for a resource with isJob: true', () => {
    registerResource({ name: 'my-job', isJob: true });
    expect(isJobResource('my-job')).toBe(true);
  });

  it('returns false for a regular resource', () => {
    registerResource({ name: 'character', isJob: undefined });
    expect(isJobResource('character')).toBe(false);
  });

  it('returns false for an unknown resource', () => {
    expect(isJobResource('nonexistent')).toBe(false);
  });
});

describe('getStandaloneJobNames', () => {
  beforeEach(() => {
    for (const key of Object.keys(resources)) delete resources[key];
    for (const key of Object.keys(asyncCreateJobs)) delete asyncCreateJobs[key];
  });

  it('returns job resources that are NOT async-create jobs', () => {
    registerResource({ name: 'pet-job', isJob: true });
    registerResource({ name: 'new-char-job', isJob: true });
    registerResource({ name: 'character', isJob: undefined });

    // new-char-job is an async-create job for character
    Object.assign(asyncCreateJobs, { 'new-char-job': 'character' });

    const standalone = getStandaloneJobNames();
    expect(standalone).toEqual(['pet-job']);
  });

  it('returns empty array when no standalone jobs exist', () => {
    registerResource({ name: 'character', isJob: undefined });
    registerResource({ name: 'new-char-job', isJob: true });
    Object.assign(asyncCreateJobs, { 'new-char-job': 'character' });

    expect(getStandaloneJobNames()).toEqual([]);
  });

  it('returns all jobs when none are async-create jobs', () => {
    registerResource({ name: 'job-a', isJob: true });
    registerResource({ name: 'job-b', isJob: true });
    registerResource({ name: 'character', isJob: undefined });

    const standalone = getStandaloneJobNames();
    expect(standalone).toEqual(['job-a', 'job-b']);
  });

  it('returns empty array when no job resources exist', () => {
    registerResource({ name: 'character', isJob: undefined });
    expect(getStandaloneJobNames()).toEqual([]);
  });
});

describe('isAsyncCreateJob / getAsyncCreateJobChildren', () => {
  beforeEach(() => {
    for (const key of Object.keys(resources)) delete resources[key];
    for (const key of Object.keys(asyncCreateJobs)) delete asyncCreateJobs[key];
  });

  it('isAsyncCreateJob returns true for mapped jobs', () => {
    Object.assign(asyncCreateJobs, { 'new-char-job': 'character' });
    expect(isAsyncCreateJob('new-char-job')).toBe(true);
    expect(isAsyncCreateJob('pet-job')).toBe(false);
  });

  it('getAsyncCreateJobChildren returns children for a parent', () => {
    Object.assign(asyncCreateJobs, {
      'new-char1-job': 'character',
      'new-char2-job': 'character',
      'pet-create-job': 'pet',
    });
    expect(getAsyncCreateJobChildren('character')).toEqual(['new-char1-job', 'new-char2-job']);
    expect(getAsyncCreateJobChildren('pet')).toEqual(['pet-create-job']);
    expect(getAsyncCreateJobChildren('guild')).toEqual([]);
  });
});
