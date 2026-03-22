/**
 * useCreateResource — Tests
 *
 * Covers:
 * - Successful create calls apiClient.create and invalidates list cache
 * - Error shows notification by default
 * - showErrorNotification: false suppresses notification
 * - invalidateOnSuccess: false skips cache invalidation
 * - Custom onSuccess / onError / onSettled callbacks
 * - createAsync throws on error (for try/catch usage)
 * - Reset clears error state
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useCreateResource } from './useCreateResource';
import { makeConfig, createWrapper } from './test-helpers';

vi.mock('../utils/errorNotification', () => ({
  showErrorNotification: vi.fn(),
}));

import { showErrorNotification } from '../utils/errorNotification';

describe('useCreateResource', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('calls apiClient.create and returns result', async () => {
    const config = makeConfig();
    const { Wrapper } = createWrapper();

    const { result } = renderHook(() => useCreateResource(config), { wrapper: Wrapper });

    await act(async () => {
      const res = await result.current.createAsync({ name: 'Alice' } as any);
      expect(res).toEqual({ resource_id: 'new-1', revision_id: 'rev-1' });
    });

    expect(config.apiClient.create).toHaveBeenCalledWith({ name: 'Alice' });
  });

  it('invalidates list cache on success', async () => {
    const config = makeConfig();
    const { Wrapper, queryClient } = createWrapper();
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');

    const { result } = renderHook(() => useCreateResource(config), { wrapper: Wrapper });

    await act(async () => {
      await result.current.createAsync({ name: 'Bob' } as any);
    });

    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        queryKey: ['resource', 'test', 'list'],
      }),
    );
  });

  it('shows error notification by default on failure', async () => {
    const config = makeConfig();
    (config.apiClient.create as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error('Create failed'),
    );
    const { Wrapper } = createWrapper();

    const { result } = renderHook(() => useCreateResource(config), { wrapper: Wrapper });

    await act(async () => {
      result.current.create({ name: 'fail' } as any);
    });

    await waitFor(() => {
      expect(result.current.error).toBeInstanceOf(Error);
    });

    expect(showErrorNotification).toHaveBeenCalledWith(expect.any(Error), 'Create Failed');
  });

  it('suppresses notification when showErrorNotification=false', async () => {
    const config = makeConfig();
    (config.apiClient.create as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error('Create failed'),
    );
    const { Wrapper } = createWrapper();

    const { result } = renderHook(
      () => useCreateResource(config, { showErrorNotification: false }),
      { wrapper: Wrapper },
    );

    await act(async () => {
      result.current.create({} as any);
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

    const { result } = renderHook(() => useCreateResource(config, { invalidateOnSuccess: false }), {
      wrapper: Wrapper,
    });

    await act(async () => {
      await result.current.createAsync({} as any);
    });

    expect(invalidateSpy).not.toHaveBeenCalled();
  });

  it('calls onSuccess callback with data and variables', async () => {
    const config = makeConfig();
    const onSuccess = vi.fn();
    const { Wrapper } = createWrapper();

    const { result } = renderHook(() => useCreateResource(config, { onSuccess }), {
      wrapper: Wrapper,
    });

    const payload = { name: 'Carol' } as any;
    await act(async () => {
      await result.current.createAsync(payload);
    });

    expect(onSuccess).toHaveBeenCalledWith({ resource_id: 'new-1', revision_id: 'rev-1' }, payload);
  });

  it('calls onError callback', async () => {
    const config = makeConfig();
    (config.apiClient.create as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error('fail'));
    const onError = vi.fn();
    const { Wrapper } = createWrapper();

    const { result } = renderHook(
      () => useCreateResource(config, { onError, showErrorNotification: false }),
      { wrapper: Wrapper },
    );

    await act(async () => {
      result.current.create({} as any);
    });

    await waitFor(() => {
      expect(onError).toHaveBeenCalledWith(expect.any(Error), expect.anything());
    });
  });

  it('calls onSettled callback on both success and error', async () => {
    const config = makeConfig();
    const onSettled = vi.fn();
    const { Wrapper } = createWrapper();

    const { result } = renderHook(() => useCreateResource(config, { onSettled }), {
      wrapper: Wrapper,
    });

    await act(async () => {
      await result.current.createAsync({} as any);
    });

    expect(onSettled).toHaveBeenCalledTimes(1);
  });

  it('createAsync throws on error for try/catch usage', async () => {
    const config = makeConfig();
    (config.apiClient.create as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error('boom'));
    const { Wrapper } = createWrapper();

    const { result } = renderHook(
      () => useCreateResource(config, { showErrorNotification: false }),
      { wrapper: Wrapper },
    );

    await expect(
      act(async () => {
        await result.current.createAsync({} as any);
      }),
    ).rejects.toThrow('boom');
  });

  it('reset clears error state', async () => {
    const config = makeConfig();
    (config.apiClient.create as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error('err'));
    const { Wrapper } = createWrapper();

    const { result } = renderHook(
      () => useCreateResource(config, { showErrorNotification: false }),
      { wrapper: Wrapper },
    );

    await act(async () => {
      result.current.create({} as any);
    });

    await waitFor(() => {
      expect(result.current.error).not.toBeNull();
    });

    act(() => {
      result.current.reset();
    });

    await waitFor(() => {
      expect(result.current.error).toBeNull();
    });
  });

  it('isPending is true while create is in flight', async () => {
    const config = makeConfig();
    let resolveCreate: (v: any) => void;
    (config.apiClient.create as ReturnType<typeof vi.fn>).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveCreate = resolve;
        }),
    );
    const { Wrapper } = createWrapper();

    const { result } = renderHook(() => useCreateResource(config), { wrapper: Wrapper });

    expect(result.current.isPending).toBe(false);

    act(() => {
      result.current.create({} as any);
    });

    await waitFor(() => {
      expect(result.current.isPending).toBe(true);
    });

    await act(async () => {
      resolveCreate!({ data: { resource_id: 'x', revision_id: 'y' } });
    });

    await waitFor(() => {
      expect(result.current.isPending).toBe(false);
    });
  });
});
