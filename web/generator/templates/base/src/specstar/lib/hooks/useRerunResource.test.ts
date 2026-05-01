/**
 * useRerunResource — Tests
 *
 * Covers:
 * - Successful rerun calls apiClient.rerun
 * - Throws when rerun is not defined on config
 * - Cache invalidation
 * - Error notification
 * - Async throws on error
 * - Custom callbacks
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useRerunResource } from './useRerunResource';
import { makeConfig, createWrapper } from './test-helpers';

vi.mock('../utils/errorNotification', () => ({
  showErrorNotification: vi.fn(),
}));

import { showErrorNotification } from '../utils/errorNotification';

describe('useRerunResource', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('calls apiClient.rerun with resourceId', async () => {
    const config = makeConfig();
    const { Wrapper } = createWrapper();

    const { result } = renderHook(() => useRerunResource(config, 'r1'), { wrapper: Wrapper });

    await act(async () => {
      const res = await result.current.rerunAsync();
      expect(res).toEqual({ resource_id: 'r1', revision_id: 'rev-rerun' });
    });

    expect(config.apiClient.rerun).toHaveBeenCalledWith('r1');
  });

  it('throws when apiClient.rerun is not defined', async () => {
    const config = makeConfig('norerun', {
      apiClient: {
        ...makeConfig().apiClient,
        rerun: undefined,
      },
    });
    const { Wrapper } = createWrapper();

    const { result } = renderHook(
      () => useRerunResource(config, 'r1', { showErrorNotification: false }),
      { wrapper: Wrapper },
    );

    await expect(
      act(async () => {
        await result.current.rerunAsync();
      }),
    ).rejects.toThrow('does not support rerun');
  });

  it('invalidates detail + list caches on success', async () => {
    const config = makeConfig();
    const { Wrapper, queryClient } = createWrapper();
    const spy = vi.spyOn(queryClient, 'invalidateQueries');

    const { result } = renderHook(() => useRerunResource(config, 'r1'), { wrapper: Wrapper });

    await act(async () => {
      await result.current.rerunAsync();
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
    (config.apiClient.rerun as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error('rerun err'),
    );
    const { Wrapper } = createWrapper();

    const { result } = renderHook(() => useRerunResource(config, 'r1'), { wrapper: Wrapper });

    await act(async () => {
      result.current.rerun();
    });

    await waitFor(() => {
      expect(showErrorNotification).toHaveBeenCalledWith(expect.any(Error), 'Rerun Failed');
    });
  });

  it('suppresses notification when showErrorNotification=false', async () => {
    const config = makeConfig();
    (config.apiClient.rerun as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error('fail'));
    const { Wrapper } = createWrapper();

    const { result } = renderHook(
      () => useRerunResource(config, 'r1', { showErrorNotification: false }),
      { wrapper: Wrapper },
    );

    await act(async () => {
      result.current.rerun();
    });

    await waitFor(() => {
      expect(result.current.error).not.toBeNull();
    });

    expect(showErrorNotification).not.toHaveBeenCalled();
  });

  it('rerunAsync throws on error', async () => {
    const config = makeConfig();
    (config.apiClient.rerun as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error('boom'));
    const { Wrapper } = createWrapper();

    const { result } = renderHook(
      () => useRerunResource(config, 'r1', { showErrorNotification: false }),
      { wrapper: Wrapper },
    );

    await expect(
      act(async () => {
        await result.current.rerunAsync();
      }),
    ).rejects.toThrow('boom');
  });

  it('calls onSuccess callback', async () => {
    const config = makeConfig();
    const onSuccess = vi.fn();
    const { Wrapper } = createWrapper();

    const { result } = renderHook(() => useRerunResource(config, 'r1', { onSuccess }), {
      wrapper: Wrapper,
    });

    await act(async () => {
      await result.current.rerunAsync();
    });

    expect(onSuccess).toHaveBeenCalledWith(
      { resource_id: 'r1', revision_id: 'rev-rerun' },
      undefined,
    );
  });

  it('reset clears error', async () => {
    const config = makeConfig();
    (config.apiClient.rerun as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error('err'));
    const { Wrapper } = createWrapper();

    const { result } = renderHook(
      () => useRerunResource(config, 'r1', { showErrorNotification: false }),
      { wrapper: Wrapper },
    );

    await act(async () => {
      result.current.rerun();
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
