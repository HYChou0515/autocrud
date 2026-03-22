/**
 * useUpdateResource — Tests
 *
 * Covers:
 * - Successful update calls apiClient.update
 * - Invalidates both detail and list caches
 * - Error notification by default
 * - showErrorNotification: false suppresses notification
 * - invalidateOnSuccess: false skips cache invalidation
 * - Custom callbacks (onSuccess, onError, onSettled)
 * - updateAsync throws on error
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useUpdateResource } from './useUpdateResource';
import { makeConfig, createWrapper } from './test-helpers';

vi.mock('../utils/errorNotification', () => ({
  showErrorNotification: vi.fn(),
}));

import { showErrorNotification } from '../utils/errorNotification';

describe('useUpdateResource', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('calls apiClient.update with resourceId and data', async () => {
    const config = makeConfig();
    const { Wrapper } = createWrapper();

    const { result } = renderHook(() => useUpdateResource(config, 'r1'), { wrapper: Wrapper });

    await act(async () => {
      const res = await result.current.updateAsync({ name: 'Updated' } as any);
      expect(res).toEqual({ resource_id: 'r1', revision_id: 'rev-2' });
    });

    expect(config.apiClient.update).toHaveBeenCalledWith('r1', { name: 'Updated' });
  });

  it('invalidates both detail and list caches on success', async () => {
    const config = makeConfig();
    const { Wrapper, queryClient } = createWrapper();
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');

    const { result } = renderHook(() => useUpdateResource(config, 'r1'), { wrapper: Wrapper });

    await act(async () => {
      await result.current.updateAsync({} as any);
    });

    const keys = invalidateSpy.mock.calls.map((c) => c[0]);
    expect(keys).toContainEqual(
      expect.objectContaining({ queryKey: ['resource', 'test', 'detail'] }),
    );
    expect(keys).toContainEqual(
      expect.objectContaining({ queryKey: ['resource', 'test', 'list'] }),
    );
  });

  it('shows error notification by default', async () => {
    const config = makeConfig();
    (config.apiClient.update as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error('Update failed'),
    );
    const { Wrapper } = createWrapper();

    const { result } = renderHook(() => useUpdateResource(config, 'r1'), { wrapper: Wrapper });

    await act(async () => {
      result.current.update({} as any);
    });

    await waitFor(() => {
      expect(showErrorNotification).toHaveBeenCalledWith(expect.any(Error), 'Update Failed');
    });
  });

  it('suppresses notification when showErrorNotification=false', async () => {
    const config = makeConfig();
    (config.apiClient.update as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error('fail'));
    const { Wrapper } = createWrapper();

    const { result } = renderHook(
      () => useUpdateResource(config, 'r1', { showErrorNotification: false }),
      { wrapper: Wrapper },
    );

    await act(async () => {
      result.current.update({} as any);
    });

    await waitFor(() => {
      expect(result.current.error).toBeInstanceOf(Error);
    });

    expect(showErrorNotification).not.toHaveBeenCalled();
  });

  it('skips invalidation when invalidateOnSuccess=false', async () => {
    const config = makeConfig();
    const { Wrapper, queryClient } = createWrapper();
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');

    const { result } = renderHook(
      () => useUpdateResource(config, 'r1', { invalidateOnSuccess: false }),
      { wrapper: Wrapper },
    );

    await act(async () => {
      await result.current.updateAsync({} as any);
    });

    expect(invalidateSpy).not.toHaveBeenCalled();
  });

  it('calls onSuccess callback', async () => {
    const config = makeConfig();
    const onSuccess = vi.fn();
    const { Wrapper } = createWrapper();

    const { result } = renderHook(() => useUpdateResource(config, 'r1', { onSuccess }), {
      wrapper: Wrapper,
    });

    const payload = { name: 'X' } as any;
    await act(async () => {
      await result.current.updateAsync(payload);
    });

    expect(onSuccess).toHaveBeenCalledWith({ resource_id: 'r1', revision_id: 'rev-2' }, payload);
  });

  it('updateAsync throws on error', async () => {
    const config = makeConfig();
    (config.apiClient.update as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error('boom'));
    const { Wrapper } = createWrapper();

    const { result } = renderHook(
      () => useUpdateResource(config, 'r1', { showErrorNotification: false }),
      { wrapper: Wrapper },
    );

    await expect(
      act(async () => {
        await result.current.updateAsync({} as any);
      }),
    ).rejects.toThrow('boom');
  });

  it('reset clears error', async () => {
    const config = makeConfig();
    (config.apiClient.update as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error('err'));
    const { Wrapper } = createWrapper();

    const { result } = renderHook(
      () => useUpdateResource(config, 'r1', { showErrorNotification: false }),
      { wrapper: Wrapper },
    );

    await act(async () => {
      result.current.update({} as any);
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
