/**
 * useResourceList — Tests for the generic resource list hook.
 *
 * Covers:
 * - Normal fetch with mocked apiClient
 * - Graceful handling when config is undefined (no crash)
 * - Refresh triggers re-fetch
 * - Error handling
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useResourceList } from './useResourceList';
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
      list: vi.fn().mockResolvedValue({ data: [{ meta: { resource_id: '1' }, data: { a: 1 } }] }),
      count: vi.fn().mockResolvedValue({ data: 1 }),
    } as any,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('useResourceList', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('fetches data with valid config', async () => {
    const config = makeConfig();
    const { result } = renderHook(() => useResourceList(config, { limit: 10, offset: 0 }));

    // Initially loading
    expect(result.current.loading).toBe(true);

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.data).toHaveLength(1);
    expect(result.current.total).toBe(1);
    expect(result.current.error).toBeNull();
    expect(config.apiClient.list).toHaveBeenCalledWith({ limit: 10, offset: 0 });
    expect(config.apiClient.count).toHaveBeenCalledWith({ limit: 10, offset: 0 });
  });

  it('does not crash when config is undefined', async () => {
    // This is the bug scenario: getResource() returns undefined,
    // and RefTableSelectModal passes it as config! to useResourceList.
    const { result } = renderHook(() =>
      useResourceList(undefined as unknown as ResourceConfig, { limit: 10 }),
    );

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    // Should return empty results, not crash
    expect(result.current.data).toEqual([]);
    expect(result.current.total).toBe(0);
    expect(result.current.error).toBeNull();
  });

  it('does not crash when config is null', async () => {
    const { result } = renderHook(() => useResourceList(null as unknown as ResourceConfig, {}));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.data).toEqual([]);
    expect(result.current.total).toBe(0);
  });

  it('handles fetch error gracefully', async () => {
    const config = makeConfig({
      apiClient: {
        list: vi.fn().mockRejectedValue(new Error('Network error')),
        count: vi.fn().mockRejectedValue(new Error('Network error')),
      } as any,
    });

    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    const { result } = renderHook(() => useResourceList(config));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.error).toBeInstanceOf(Error);
    expect(result.current.error?.message).toBe('Network error');
    expect(result.current.data).toEqual([]);

    consoleSpy.mockRestore();
  });

  it('refresh triggers re-fetch', async () => {
    const listFn = vi.fn().mockResolvedValue({ data: [{ meta: {}, data: {} }] });
    const countFn = vi.fn().mockResolvedValue({ data: 1 });
    const config = makeConfig({
      apiClient: { list: listFn, count: countFn } as any,
    });

    const { result } = renderHook(() => useResourceList(config));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(listFn).toHaveBeenCalledTimes(1);

    // Trigger refresh
    act(() => {
      result.current.refresh();
    });

    await waitFor(() => {
      expect(listFn).toHaveBeenCalledTimes(2);
    });
  });
});
