/**
 * useResourceList — Tests for the generic resource list hook.
 *
 * Covers:
 * - Normal fetch with mocked apiClient
 * - Graceful handling when config is undefined (no crash)
 * - Refresh triggers re-fetch (via query invalidation)
 * - Error handling
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
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

/** Create a fresh QueryClient + wrapper for each test */
function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
    },
  });
  const Wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
  return { Wrapper, queryClient };
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
    const { Wrapper } = createWrapper();
    const { result } = renderHook(() => useResourceList(config, { limit: 10, offset: 0 }), {
      wrapper: Wrapper,
    });

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
    const { Wrapper } = createWrapper();
    const { result } = renderHook(
      () => useResourceList(undefined as unknown as ResourceConfig, { limit: 10 }),
      { wrapper: Wrapper },
    );

    // With react-query and enabled: false, loading should be false
    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    // Should return empty results, not crash
    expect(result.current.data).toEqual([]);
    expect(result.current.total).toBe(0);
    expect(result.current.error).toBeNull();
  });

  it('does not crash when config is null', async () => {
    const { Wrapper } = createWrapper();
    const { result } = renderHook(() => useResourceList(null as unknown as ResourceConfig, {}), {
      wrapper: Wrapper,
    });

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

    const { Wrapper } = createWrapper();

    const { result } = renderHook(() => useResourceList(config), {
      wrapper: Wrapper,
    });

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.error).toBeInstanceOf(Error);
    expect(result.current.error?.message).toBe('Network error');
    expect(result.current.data).toEqual([]);
  });

  it('refresh triggers re-fetch via query invalidation', async () => {
    const listFn = vi.fn().mockResolvedValue({ data: [{ meta: {}, data: {} }] });
    const countFn = vi.fn().mockResolvedValue({ data: 1 });
    const config = makeConfig({
      apiClient: { list: listFn, count: countFn } as any,
    });

    const { Wrapper } = createWrapper();
    const { result } = renderHook(() => useResourceList(config), {
      wrapper: Wrapper,
    });

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(listFn).toHaveBeenCalledTimes(1);

    // Trigger refresh (invalidates query)
    act(() => {
      result.current.refresh();
    });

    await waitFor(() => {
      expect(listFn).toHaveBeenCalledTimes(2);
    });
  });

  // ── New options tests ────────────────────────────────────────────

  it('exposes raw TanStack Query result via query field', async () => {
    const config = makeConfig();
    const { Wrapper } = createWrapper();

    const { result } = renderHook(() => useResourceList(config, { limit: 10 }), {
      wrapper: Wrapper,
    });

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    // query should be a full UseQueryResult object
    expect(result.current.query).toBeTruthy();
    expect(result.current.query.isSuccess).toBe(true);
    expect(result.current.query.data).toEqual({
      data: [{ meta: { resource_id: '1' }, data: { a: 1 } }],
      total: 1,
    });
  });

  it('accepts options.enabled = false to prevent fetching', async () => {
    const listFn = vi.fn().mockResolvedValue({ data: [] });
    const countFn = vi.fn().mockResolvedValue({ data: 0 });
    const config = makeConfig({
      apiClient: { list: listFn, count: countFn } as any,
    });

    const { Wrapper } = createWrapper();

    const { result } = renderHook(
      () => useResourceList(config, { limit: 10 }, { enabled: false }),
      { wrapper: Wrapper },
    );

    // Should not fetch when enabled=false
    expect(listFn).not.toHaveBeenCalled();
    expect(result.current.data).toEqual([]);
  });

  it('accepts options.staleTime', async () => {
    const config = makeConfig();
    const { Wrapper } = createWrapper();

    const { result } = renderHook(
      () => useResourceList(config, { limit: 10 }, { staleTime: 60_000 }),
      { wrapper: Wrapper },
    );

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    // The query should have completed successfully
    expect(result.current.query.isStale).toBe(false);
  });

  it('works with zero options (backward compat)', async () => {
    const config = makeConfig();
    const { Wrapper } = createWrapper();

    // Calling without the 3rd arg = same as before
    const { result } = renderHook(() => useResourceList(config, { limit: 5 }), {
      wrapper: Wrapper,
    });

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.data).toHaveLength(1);
    expect(result.current.total).toBe(1);
  });
});
