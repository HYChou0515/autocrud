/**
 * resources.ts — tests for the resource registry functions.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
  resources,
  asyncCreateJobs,
  asyncUpdateJobs,
  isAsyncCreateJob,
  isAsyncUpdateJob,
  getAsyncCreateJobChildren,
  getAsyncUpdateJobChildren,
  isJobResource,
  getStandaloneJobNames,
  getResource,
  getResourceNames,
  applyCustomizations,
} from './resources';
import type { ResourceConfig } from './resources';

// Helper to register a resource for testing
function registerResource(name: string, overrides: Partial<ResourceConfig> = {}) {
  resources[name] = {
    name,
    label: overrides.label ?? name,
    pluralLabel: overrides.pluralLabel ?? `${name}s`,
    fields: overrides.fields ?? [],
    api: {} as any,
    isJob: overrides.isJob ?? false,
    ...overrides,
  } as ResourceConfig;
}

beforeEach(() => {
  // Clean up registry between tests
  for (const key of Object.keys(resources)) delete resources[key];
  for (const key of Object.keys(asyncCreateJobs)) delete asyncCreateJobs[key];
  for (const key of Object.keys(asyncUpdateJobs)) delete asyncUpdateJobs[key];
});

describe('resource registry', () => {
  it('getResource returns undefined for missing resource', () => {
    expect(getResource('nonexistent')).toBeUndefined();
  });

  it('getResource returns registered resource', () => {
    registerResource('user');
    expect(getResource('user')).toBeDefined();
    expect(getResource('user')?.name).toBe('user');
  });

  it('getResourceNames returns empty array when no resources', () => {
    expect(getResourceNames()).toEqual([]);
  });

  it('getResourceNames returns all registered names', () => {
    registerResource('user');
    registerResource('post');
    expect(getResourceNames().sort()).toEqual(['post', 'user']);
  });
});

describe('async job helpers', () => {
  it('isAsyncCreateJob returns false for non-job', () => {
    expect(isAsyncCreateJob('user')).toBe(false);
  });

  it('isAsyncCreateJob returns true for registered create job', () => {
    asyncCreateJobs['create-user-job'] = 'user';
    expect(isAsyncCreateJob('create-user-job')).toBe(true);
  });

  it('isAsyncUpdateJob returns false for non-job', () => {
    expect(isAsyncUpdateJob('user')).toBe(false);
  });

  it('isAsyncUpdateJob returns true for registered update job', () => {
    asyncUpdateJobs['update-user-job'] = 'user';
    expect(isAsyncUpdateJob('update-user-job')).toBe(true);
  });

  it('getAsyncCreateJobChildren returns children for parent', () => {
    asyncCreateJobs['create-user-job'] = 'user';
    asyncCreateJobs['create-post-job'] = 'post';
    asyncCreateJobs['create-user-job-2'] = 'user';
    const children = getAsyncCreateJobChildren('user');
    expect(children.sort()).toEqual(['create-user-job', 'create-user-job-2']);
  });

  it('getAsyncCreateJobChildren returns empty for no matches', () => {
    expect(getAsyncCreateJobChildren('user')).toEqual([]);
  });

  it('getAsyncUpdateJobChildren returns children for parent', () => {
    asyncUpdateJobs['update-user-job'] = 'user';
    const children = getAsyncUpdateJobChildren('user');
    expect(children).toEqual(['update-user-job']);
  });

  it('getAsyncUpdateJobChildren returns empty for no matches', () => {
    expect(getAsyncUpdateJobChildren('nonexistent')).toEqual([]);
  });
});

describe('job resource helpers', () => {
  it('isJobResource returns false for non-job', () => {
    registerResource('user', { isJob: false });
    expect(isJobResource('user')).toBe(false);
  });

  it('isJobResource returns true for job resource', () => {
    registerResource('my-job', { isJob: true });
    expect(isJobResource('my-job')).toBe(true);
  });

  it('isJobResource returns false for missing resource', () => {
    expect(isJobResource('missing')).toBe(false);
  });

  it('getStandaloneJobNames returns jobs not in async maps', () => {
    registerResource('user', { isJob: false });
    registerResource('standalone-job', { isJob: true });
    registerResource('create-user-job', { isJob: true });
    asyncCreateJobs['create-user-job'] = 'user';
    const names = getStandaloneJobNames();
    expect(names).toEqual(['standalone-job']);
  });

  it('getStandaloneJobNames returns empty when no standalone jobs', () => {
    registerResource('user', { isJob: false });
    expect(getStandaloneJobNames()).toEqual([]);
  });
});

describe('applyCustomizations', () => {
  it('applies field variant customization', () => {
    registerResource('user', {
      fields: [
        {
          name: 'bio',
          label: 'Bio',
          type: 'string',
          isArray: false,
          isRequired: false,
          isNullable: false,
        },
      ],
    });
    applyCustomizations({
      user: {
        fields: {
          bio: { variant: { type: 'textarea', rows: 5 } },
        },
      },
    });
    expect(getResource('user')?.fields[0].variant).toEqual({ type: 'textarea', rows: 5 });
  });

  it('applies field label customization', () => {
    registerResource('user', {
      fields: [
        {
          name: 'bio',
          label: 'Bio',
          type: 'string',
          isArray: false,
          isRequired: false,
          isNullable: false,
        },
      ],
    });
    applyCustomizations({
      user: { fields: { bio: { label: 'Biography' } } },
    });
    expect(getResource('user')?.fields[0].label).toBe('Biography');
  });

  it('applies field ref customization', () => {
    registerResource('post', {
      fields: [
        {
          name: 'author_id',
          label: 'Author',
          type: 'string',
          isArray: false,
          isRequired: false,
          isNullable: false,
        },
      ],
    });
    applyCustomizations({
      post: { fields: { author_id: { ref: { resource: 'user', type: 'resource_id' } } } },
    });
    expect(getResource('post')?.fields[0].ref?.resource).toBe('user');
  });

  it('applies resource label overrides', () => {
    registerResource('user');
    applyCustomizations({
      user: { label: 'Member', pluralLabel: 'Members' },
    });
    expect(getResource('user')?.label).toBe('Member');
    expect(getResource('user')?.pluralLabel).toBe('Members');
  });

  it('applies maxFormDepth override', () => {
    registerResource('user');
    applyCustomizations({
      user: { maxFormDepth: 3 },
    });
    expect(getResource('user')?.maxFormDepth).toBe(3);
  });

  it('warns for missing resource', () => {
    const spy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    applyCustomizations({
      nonexistent: { label: 'X' },
    });
    expect(spy).toHaveBeenCalledWith(expect.stringContaining('nonexistent'));
    spy.mockRestore();
  });

  it('warns for missing field', () => {
    registerResource('user', { fields: [] });
    const spy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    applyCustomizations({
      user: { fields: { missing_field: { label: 'X' } } },
    });
    expect(spy).toHaveBeenCalledWith(expect.stringContaining('missing_field'));
    spy.mockRestore();
  });

  it('skips null config entries', () => {
    registerResource('user');
    // Pass null-ish config — should not throw
    applyCustomizations({ user: undefined as any });
    expect(getResource('user')).toBeDefined();
  });

  it('applies showHiddenFields', () => {
    registerResource('user', {
      defaultHiddenFields: ['secret', 'internal'],
      fields: [],
    });
    applyCustomizations({
      user: { showHiddenFields: ['secret'] },
    } as any);
    expect(getResource('user')?.defaultHiddenFields).toEqual(['internal']);
  });

  it('applies zodSchema override', () => {
    const mockSchema = { shape: {} } as any;
    registerResource('user', { zodSchema: mockSchema });
    const customizer = vi.fn().mockReturnValue({ shape: { custom: true } } as any);
    applyCustomizations({
      user: { zodSchema: customizer },
    });
    expect(customizer).toHaveBeenCalledWith(mockSchema);
  });

  it('applies table config override', () => {
    registerResource('user');
    applyCustomizations({
      user: { table: { canCreate: false, initPageSize: 50 } },
    });
    expect(getResource('user')?.tableConfig?.canCreate).toBe(false);
    expect(getResource('user')?.tableConfig?.initPageSize).toBe(50);
  });

  it('applies create config override', () => {
    registerResource('user');
    applyCustomizations({
      user: { create: { width: 'lg' } },
    } as any);
    expect(getResource('user')?.createConfig).toBeDefined();
  });

  it('applies detail config override', () => {
    registerResource('user');
    applyCustomizations({
      user: { detail: { width: 'xl' } },
    } as any);
    expect(getResource('user')?.detailConfig).toBeDefined();
  });

  it('applies table mrtOptions merge', () => {
    registerResource('user', { tableConfig: { mrtOptions: { enablePagination: true } as any } });
    applyCustomizations({
      user: { table: { mrtOptions: { enableSorting: false } as any } },
    });
    const tc = getResource('user')?.tableConfig;
    expect((tc?.mrtOptions as any)?.enablePagination).toBe(true);
    expect((tc?.mrtOptions as any)?.enableSorting).toBe(false);
  });
});
