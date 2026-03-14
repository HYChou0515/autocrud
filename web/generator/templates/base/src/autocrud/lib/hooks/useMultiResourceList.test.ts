/**
 * useMultiResourceList — Tests for the generic multi-resource aggregation hook.
 *
 * Covers:
 * - Normal parallel fetch from multiple configs
 * - _source tagging on every row
 * - Sorting by updated_time (newest first)
 * - Empty entries returns empty items immediately
 * - Partial failure: fulfilled sources succeed, failed ones are skipped
 * - Total count aggregation
 * - Refresh triggers re-fetch
 * - Shared params are merged with per-entry params (entry wins)
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useMultiResourceList, type MultiResourceEntry } from './useMultiResourceList';
import type { ResourceConfig } from '../resources';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeConfig(name: string, overrides: Partial<ResourceConfig> = {}): ResourceConfig {
  return {
    name,
    label: name.charAt(0).toUpperCase() + name.slice(1),
    pluralLabel: name + 's',
    schema: name + 'Schema',
    fields: [],
    apiClient: {
      list: vi.fn().mockResolvedValue({ data: [] }),
      count: vi.fn().mockResolvedValue({ data: 0 }),
    } as any,
    ...overrides,
  };
}

function makeRow(rid: string, updatedTime: string, data: Record<string, unknown> = {}) {
  return {
    meta: { resource_id: rid, updated_time: updatedTime, created_time: updatedTime },
    data,
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('useMultiResourceList', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('returns empty items immediately when entries is empty', async () => {
    const { result } = renderHook(() => useMultiResourceList([]));

    // Should not even show loading state for empty entries
    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.items).toEqual([]);
    expect(result.current.totalCount).toBe(0);
    expect(result.current.totals).toEqual({});
    expect(result.current.error).toBeNull();
  });

  it('fetches data from a single config and tags _source', async () => {
    const config = makeConfig('alpha', {
      apiClient: {
        list: vi.fn().mockResolvedValue({
          data: [makeRow('r1', '2024-01-01T00:00:00Z', { foo: 'bar' })],
        }),
        count: vi.fn().mockResolvedValue({ data: 1 }),
      } as any,
    });

    const entries: MultiResourceEntry[] = [{ config }];
    const { result } = renderHook(() => useMultiResourceList(entries));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.items).toHaveLength(1);
    expect(result.current.items[0]._source).toBe('alpha');
    expect(result.current.items[0].data).toEqual({ foo: 'bar' });
    expect(result.current.totalCount).toBe(1);
    expect(result.current.totals).toEqual({ alpha: 1 });
    expect(result.current.error).toBeNull();
  });

  it('aggregates rows from multiple configs sorted by updated_time desc', async () => {
    const configA = makeConfig('alpha', {
      apiClient: {
        list: vi.fn().mockResolvedValue({
          data: [makeRow('a1', '2024-01-01T00:00:00Z'), makeRow('a2', '2024-01-03T00:00:00Z')],
        }),
        count: vi.fn().mockResolvedValue({ data: 2 }),
      } as any,
    });

    const configB = makeConfig('beta', {
      apiClient: {
        list: vi.fn().mockResolvedValue({
          data: [makeRow('b1', '2024-01-02T00:00:00Z')],
        }),
        count: vi.fn().mockResolvedValue({ data: 1 }),
      } as any,
    });

    const entries: MultiResourceEntry[] = [{ config: configA }, { config: configB }];
    const { result } = renderHook(() => useMultiResourceList(entries));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.items).toHaveLength(3);
    // Sorted newest first: a2 (Jan 3) > b1 (Jan 2) > a1 (Jan 1)
    expect(result.current.items[0].meta?.resource_id).toBe('a2');
    expect(result.current.items[0]._source).toBe('alpha');
    expect(result.current.items[1].meta?.resource_id).toBe('b1');
    expect(result.current.items[1]._source).toBe('beta');
    expect(result.current.items[2].meta?.resource_id).toBe('a1');
    expect(result.current.items[2]._source).toBe('alpha');

    expect(result.current.totalCount).toBe(3);
    expect(result.current.totals).toEqual({ alpha: 2, beta: 1 });
  });

  it('passes shared params and merges with entry params (entry wins)', async () => {
    const listFn = vi.fn().mockResolvedValue({ data: [] });
    const countFn = vi.fn().mockResolvedValue({ data: 0 });
    const config = makeConfig('res', {
      apiClient: { list: listFn, count: countFn } as any,
    });

    const entries: MultiResourceEntry[] = [{ config, params: { limit: 50 } }];
    const sharedParams = { limit: 10, offset: 0 };

    renderHook(() => useMultiResourceList(entries, sharedParams));

    await waitFor(() => {
      // Entry's limit=50 should override shared limit=10
      expect(listFn).toHaveBeenCalledWith({ limit: 50, offset: 0 });
      expect(countFn).toHaveBeenCalledWith({ limit: 50, offset: 0 });
    });
  });

  it('handles partial failure gracefully (one config fails, other succeeds)', async () => {
    const configOk = makeConfig('ok-resource', {
      apiClient: {
        list: vi.fn().mockResolvedValue({
          data: [makeRow('ok1', '2024-01-01T00:00:00Z')],
        }),
        count: vi.fn().mockResolvedValue({ data: 1 }),
      } as any,
    });

    const configFail = makeConfig('fail-resource', {
      apiClient: {
        list: vi.fn().mockRejectedValue(new Error('Network error')),
        count: vi.fn().mockRejectedValue(new Error('Network error')),
      } as any,
    });

    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    const entries: MultiResourceEntry[] = [{ config: configOk }, { config: configFail }];
    const { result } = renderHook(() => useMultiResourceList(entries));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    // The successful config's rows should still be present
    expect(result.current.items).toHaveLength(1);
    expect(result.current.items[0]._source).toBe('ok-resource');
    expect(result.current.totals).toEqual({ 'ok-resource': 1 });
    // Error from failed config is captured
    expect(result.current.error).toBeInstanceOf(Error);
    expect(result.current.error?.message).toBe('Network error');

    consoleSpy.mockRestore();
  });

  it('handles all configs failing', async () => {
    const config = makeConfig('broken', {
      apiClient: {
        list: vi.fn().mockRejectedValue(new Error('Server down')),
        count: vi.fn().mockRejectedValue(new Error('Server down')),
      } as any,
    });

    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    const { result } = renderHook(() => useMultiResourceList([{ config }]));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.items).toEqual([]);
    expect(result.current.totalCount).toBe(0);
    expect(result.current.error).toBeInstanceOf(Error);

    consoleSpy.mockRestore();
  });

  it('refresh triggers re-fetch', async () => {
    const listFn = vi.fn().mockResolvedValue({ data: [] });
    const countFn = vi.fn().mockResolvedValue({ data: 0 });
    const config = makeConfig('r', {
      apiClient: { list: listFn, count: countFn } as any,
    });

    const { result } = renderHook(() => useMultiResourceList([{ config }]));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(listFn).toHaveBeenCalledTimes(1);

    act(() => {
      result.current.refresh();
    });

    await waitFor(() => {
      expect(listFn).toHaveBeenCalledTimes(2);
    });
  });

  it('shows loading true initially when entries are provided', () => {
    const config = makeConfig('slow', {
      apiClient: {
        list: vi.fn().mockImplementation(() => new Promise(() => {})), // never resolves
        count: vi.fn().mockImplementation(() => new Promise(() => {})),
      } as any,
    });

    const { result } = renderHook(() => useMultiResourceList([{ config }]));

    expect(result.current.loading).toBe(true);
    expect(result.current.items).toEqual([]);
  });

  it('handles rows with missing updated_time in sorting', async () => {
    const config = makeConfig('mixed', {
      apiClient: {
        list: vi.fn().mockResolvedValue({
          data: [
            { meta: { resource_id: 'no-time' }, data: {} },
            makeRow('has-time', '2024-06-15T12:00:00Z'),
          ],
        }),
        count: vi.fn().mockResolvedValue({ data: 2 }),
      } as any,
    });

    const { result } = renderHook(() => useMultiResourceList([{ config }]));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.items).toHaveLength(2);
    // Row with time should come first (newer); row without time sorts last
    expect(result.current.items[0].meta?.resource_id).toBe('has-time');
    expect(result.current.items[1].meta?.resource_id).toBe('no-time');
  });
});
