/**
 * primitives — Tests for the non-hook async fetcher functions.
 *
 * These are pure async functions so they can be tested without React rendering.
 */

import { describe, it, expect, vi } from 'vitest';
import {
  fetchResourceList,
  fetchResourceDetail,
  fetchResourceRevisions,
  fetchResourceLogs,
} from './primitives';
import type { ResourceConfig } from '../resources';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeConfig(overrides: Partial<ResourceConfig> = {}): ResourceConfig {
  return {
    name: 'test',
    label: 'Test',
    pluralLabel: 'Tests',
    schema: 'TestSchema',
    fields: [],
    apiClient: {
      list: vi.fn().mockResolvedValue({ data: [{ data: {}, meta: {}, revision_info: {} }] }),
      count: vi.fn().mockResolvedValue({ data: 42 }),
      get: vi
        .fn()
        .mockResolvedValue({ data: { data: { name: 'a' }, meta: {}, revision_info: {} } }),
      create: vi.fn(),
      update: vi.fn(),
      delete: vi.fn(),
      permanentlyDelete: vi.fn(),
      restore: vi.fn(),
      revisionList: vi.fn().mockResolvedValue({
        data: { meta: {}, revisions: [{ revision_id: 'r1' }], total: 1, has_more: false },
      }),
      switchRevision: vi.fn(),
      getLogs: vi.fn().mockResolvedValue({ data: 'log line 1\nlog line 2' }),
    },
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('fetchResourceList', () => {
  it('calls list() and count() in parallel and returns combined result', async () => {
    const config = makeConfig();
    const result = await fetchResourceList(config, { limit: 10, offset: 0 });

    expect(config.apiClient.list).toHaveBeenCalledWith({ limit: 10, offset: 0 });
    expect(config.apiClient.count).toHaveBeenCalledWith({ limit: 10, offset: 0 });
    expect(result.data).toHaveLength(1);
    expect(result.total).toBe(42);
  });

  it('uses default empty params', async () => {
    const config = makeConfig();
    await fetchResourceList(config);

    expect(config.apiClient.list).toHaveBeenCalledWith({});
    expect(config.apiClient.count).toHaveBeenCalledWith({});
  });

  it('propagates errors from list()', async () => {
    const config = makeConfig({
      apiClient: {
        ...makeConfig().apiClient,
        list: vi.fn().mockRejectedValue(new Error('list failed')),
      },
    });

    await expect(fetchResourceList(config)).rejects.toThrow('list failed');
  });

  it('propagates errors from count()', async () => {
    const config = makeConfig({
      apiClient: {
        ...makeConfig().apiClient,
        count: vi.fn().mockRejectedValue(new Error('count failed')),
      },
    });

    await expect(fetchResourceList(config)).rejects.toThrow('count failed');
  });
});

describe('fetchResourceDetail', () => {
  it('fetches by id with include_deleted', async () => {
    const config = makeConfig();
    const result = await fetchResourceDetail(config, 'abc-123');

    expect(config.apiClient.get).toHaveBeenCalledWith('abc-123', { include_deleted: true });
    expect(result.data).toEqual({ name: 'a' });
  });

  it('passes revision_id when provided', async () => {
    const config = makeConfig();
    await fetchResourceDetail(config, 'abc-123', 'rev-456');

    expect(config.apiClient.get).toHaveBeenCalledWith('abc-123', {
      include_deleted: true,
      revision_id: 'rev-456',
    });
  });

  it('does not pass revision_id when null', async () => {
    const config = makeConfig();
    await fetchResourceDetail(config, 'abc-123', null);

    expect(config.apiClient.get).toHaveBeenCalledWith('abc-123', { include_deleted: true });
  });

  it('propagates errors', async () => {
    const config = makeConfig({
      apiClient: {
        ...makeConfig().apiClient,
        get: vi.fn().mockRejectedValue(new Error('not found')),
      },
    });

    await expect(fetchResourceDetail(config, 'abc')).rejects.toThrow('not found');
  });
});

describe('fetchResourceRevisions', () => {
  it('fetches revision list', async () => {
    const config = makeConfig();
    const result = await fetchResourceRevisions(config, 'abc-123', { limit: 5 });

    expect(config.apiClient.revisionList).toHaveBeenCalledWith('abc-123', { limit: 5 });
    expect(result.revisions).toHaveLength(1);
    expect(result.total).toBe(1);
  });

  it('works without params', async () => {
    const config = makeConfig();
    await fetchResourceRevisions(config, 'abc-123');

    expect(config.apiClient.revisionList).toHaveBeenCalledWith('abc-123', undefined);
  });
});

describe('fetchResourceLogs', () => {
  it('returns log content when getLogs is available', async () => {
    const config = makeConfig();
    const result = await fetchResourceLogs(config, 'job-1');

    expect(config.apiClient.getLogs).toHaveBeenCalledWith('job-1');
    expect(result).toBe('log line 1\nlog line 2');
  });

  it('returns undefined when getLogs is not available', async () => {
    const config = makeConfig({
      apiClient: {
        ...makeConfig().apiClient,
        getLogs: undefined,
      },
    });

    const result = await fetchResourceLogs(config, 'job-1');
    expect(result).toBeUndefined();
  });

  it('returns undefined for empty response (204 No Content)', async () => {
    const config = makeConfig({
      apiClient: {
        ...makeConfig().apiClient,
        getLogs: vi.fn().mockResolvedValue({ data: '' }),
      },
    });

    const result = await fetchResourceLogs(config, 'job-1');
    expect(result).toBeUndefined();
  });
});
