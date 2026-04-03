/**
 * useRestoreResource — Tests
 *
 * Covers:
 * - Successful restore calls apiClient.restore
 * - Cache invalidation
 * - Error notification
 * - Async throws on error
 * - Custom callbacks
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useRestoreResource } from './useRestoreResource';
import { makeConfig, createWrapper } from './test-helpers';

vi.mock('../utils/errorNotification', () => ({
  showErrorNotification: vi.fn(),
}));

import { showErrorNotification } from '../utils/errorNotification';

describe('useRestoreResource', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('calls apiClient.restore and returns result', async () => {
    const config = makeConfig();
    const { Wrapper } = createWrapper();

    const { result } = renderHook(() => useRestoreResource(config, 'r1'), { wrapper: Wrapper });

    await act(async () => {
      const res = await result.current.restoreAsync();
      expect(res).toEqual({ resource_id: 'r1', is_deleted: false });
    });

    expect(config.apiClient.restore).toHaveBeenCalledWith('r1');
  });

  it('invalidates detail + list caches on success', async () => {
    const config = makeConfig();
    const { Wrapper, queryClient } = createWrapper();
    const spy = vi.spyOn(queryClient, 'invalidateQueries');

    const { result } = renderHook(() => useRestoreResource(config, 'r1'), { wrapper: Wrapper });

    await act(async () => {
      await result.current.restoreAsync();
    });

    const keys = spy.mock.calls.map((c) => c[0]);
    expect(keys).toContainEqual(
      expect.objectContaining({ queryKey: ['resource', 'test', 'detail'] }),
    );
    expect(keys).toContainEqual(
      expect.objectContaining({ queryKey: ['resource', 'test', 'list'] }),
    );
  });

  it('shows error notification by default', async () => {
    const config = makeConfig();
    (config.apiClient.restore as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error('restore err'),
    );
    const { Wrapper } = createWrapper();

    const { result } = renderHook(() => useRestoreResource(config, 'r1'), { wrapper: Wrapper });

    await act(async () => {
      result.current.restore();
    });

    await waitFor(() => {
      expect(showErrorNotification).toHaveBeenCalledWith(expect.any(Error), 'Restore Failed');
    });
  });

  it('suppresses notification when showErrorNotification=false', async () => {
    const config = makeConfig();
    (config.apiClient.restore as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error('fail'));
    const { Wrapper } = createWrapper();

    const { result } = renderHook(
      () => useRestoreResource(config, 'r1', { showErrorNotification: false }),
      { wrapper: Wrapper },
    );

    await act(async () => {
      result.current.restore();
    });

    await waitFor(() => {
      expect(result.current.error).not.toBeNull();
    });

    expect(showErrorNotification).not.toHaveBeenCalled();
  });

  it('restoreAsync throws on error', async () => {
    const config = makeConfig();
    (config.apiClient.restore as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error('boom'));
    const { Wrapper } = createWrapper();

    const { result } = renderHook(
      () => useRestoreResource(config, 'r1', { showErrorNotification: false }),
      { wrapper: Wrapper },
    );

    await expect(
      act(async () => {
        await result.current.restoreAsync();
      }),
    ).rejects.toThrow('boom');
  });

  it('calls onSuccess callback', async () => {
    const config = makeConfig();
    const onSuccess = vi.fn();
    const { Wrapper } = createWrapper();

    const { result } = renderHook(() => useRestoreResource(config, 'r1', { onSuccess }), {
      wrapper: Wrapper,
    });

    await act(async () => {
      await result.current.restoreAsync();
    });

    expect(onSuccess).toHaveBeenCalledWith({ resource_id: 'r1', is_deleted: false }, undefined);
  });

  it('reset clears error', async () => {
    const config = makeConfig();
    (config.apiClient.restore as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error('err'));
    const { Wrapper } = createWrapper();

    const { result } = renderHook(
      () => useRestoreResource(config, 'r1', { showErrorNotification: false }),
      { wrapper: Wrapper },
    );

    await act(async () => {
      result.current.restore();
    });

    await waitFor(() => {
      expect(result.current.error).not.toBeNull();
    });

    act(() => result.current.reset());
    await waitFor(() => {
      expect(result.current.error).toBeNull();
    });
  });
});
