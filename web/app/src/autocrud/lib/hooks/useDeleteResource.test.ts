/**
 * useDeleteResource — Tests
 *
 * Covers:
 * - Soft delete calls apiClient.delete
 * - Permanent delete calls apiClient.permanentlyDelete
 * - Cache invalidation for both operations
 * - Error notification for both operations
 * - Combined isPending state
 * - Reset clears both mutation states
 * - Async variants throw on error
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useDeleteResource } from './useDeleteResource';
import { makeConfig, createWrapper } from './test-helpers';

vi.mock('../utils/errorNotification', () => ({
  showErrorNotification: vi.fn(),
}));

import { showErrorNotification } from '../utils/errorNotification';

describe('useDeleteResource', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // -- Soft delete ----------------------------------------------------------

  it('calls apiClient.delete for soft delete', async () => {
    const config = makeConfig();
    const { Wrapper } = createWrapper();

    const { result } = renderHook(() => useDeleteResource(config, 'r1'), { wrapper: Wrapper });

    await act(async () => {
      const res = await result.current.deleteResourceAsync();
      expect(res).toEqual({ resource_id: 'r1', is_deleted: true });
    });

    expect(config.apiClient.delete).toHaveBeenCalledWith('r1');
  });

  it('invalidates detail + list caches on soft delete', async () => {
    const config = makeConfig();
    const { Wrapper, queryClient } = createWrapper();
    const spy = vi.spyOn(queryClient, 'invalidateQueries');

    const { result } = renderHook(() => useDeleteResource(config, 'r1'), { wrapper: Wrapper });

    await act(async () => {
      await result.current.deleteResourceAsync();
    });

    const keys = spy.mock.calls.map((c) => c[0]);
    expect(keys).toContainEqual(
      expect.objectContaining({ queryKey: ['resource', 'test', 'detail'] }),
    );
    expect(keys).toContainEqual(
      expect.objectContaining({ queryKey: ['resource', 'test', 'list'] }),
    );
  });

  it('shows error notification on soft delete failure', async () => {
    const config = makeConfig();
    (config.apiClient.delete as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error('delete err'),
    );
    const { Wrapper } = createWrapper();

    const { result } = renderHook(() => useDeleteResource(config, 'r1'), { wrapper: Wrapper });

    await act(async () => {
      result.current.deleteResource();
    });

    await waitFor(() => {
      expect(showErrorNotification).toHaveBeenCalledWith(expect.any(Error), 'Delete Failed');
    });
  });

  // -- Permanent delete -----------------------------------------------------

  it('calls apiClient.permanentlyDelete for permanent delete', async () => {
    const config = makeConfig();
    const { Wrapper } = createWrapper();

    const { result } = renderHook(() => useDeleteResource(config, 'r1'), { wrapper: Wrapper });

    await act(async () => {
      await result.current.permanentlyDeleteAsync();
    });

    expect(config.apiClient.permanentlyDelete).toHaveBeenCalledWith('r1');
  });

  it('removes detail cache (not invalidate) on permanent delete to avoid 404 refetch', async () => {
    const config = makeConfig();
    const { Wrapper, queryClient } = createWrapper();

    // Pre-populate a detail cache entry for the resource being deleted
    queryClient.setQueryData(['resource', 'test', 'detail', 'r1'], {
      data: {},
      meta: { resource_id: 'r1' },
    });

    const removeSpy = vi.spyOn(queryClient, 'removeQueries');
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');

    const { result } = renderHook(() => useDeleteResource(config, 'r1'), { wrapper: Wrapper });

    await act(async () => {
      await result.current.permanentlyDeleteAsync();
    });

    // Should REMOVE detail queries (not invalidate, which would trigger refetch)
    expect(removeSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ['resource', 'test', 'detail', 'r1'] }),
    );

    // Should still invalidate list queries so the table refreshes
    const invalidatedKeys = invalidateSpy.mock.calls.map((c) => c[0]);
    expect(invalidatedKeys).toContainEqual(
      expect.objectContaining({ queryKey: ['resource', 'test', 'list'] }),
    );

    // The detail cache entry should be gone
    const cached = queryClient.getQueryData(['resource', 'test', 'detail', 'r1']);
    expect(cached).toBeUndefined();
  });

  it('shows error notification on permanent delete failure', async () => {
    const config = makeConfig();
    (config.apiClient.permanentlyDelete as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error('perm err'),
    );
    const { Wrapper } = createWrapper();

    const { result } = renderHook(() => useDeleteResource(config, 'r1'), { wrapper: Wrapper });

    await act(async () => {
      result.current.permanentlyDelete();
    });

    await waitFor(() => {
      expect(showErrorNotification).toHaveBeenCalledWith(
        expect.any(Error),
        'Permanently Delete Failed',
      );
    });
  });

  // -- Combined state -------------------------------------------------------

  it('isPending reflects either delete in flight', async () => {
    const config = makeConfig();
    let resolveSoftDelete: (v: any) => void;
    (config.apiClient.delete as ReturnType<typeof vi.fn>).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveSoftDelete = resolve;
        }),
    );
    const { Wrapper } = createWrapper();

    const { result } = renderHook(() => useDeleteResource(config, 'r1'), { wrapper: Wrapper });

    expect(result.current.isPending).toBe(false);

    act(() => {
      result.current.deleteResource();
    });

    await waitFor(() => {
      expect(result.current.isDeletePending).toBe(true);
      expect(result.current.isPending).toBe(true);
    });

    await act(async () => {
      resolveSoftDelete!({ data: { resource_id: 'r1', is_deleted: true } });
    });

    await waitFor(() => {
      expect(result.current.isPending).toBe(false);
    });
  });

  it('reset clears both mutation errors', async () => {
    const config = makeConfig();
    (config.apiClient.delete as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error('e'));
    const { Wrapper } = createWrapper();

    const { result } = renderHook(
      () => useDeleteResource(config, 'r1', { showErrorNotification: false }),
      { wrapper: Wrapper },
    );

    await act(async () => {
      result.current.deleteResource();
    });

    await waitFor(() => {
      expect(result.current.error).not.toBeNull();
    });

    act(() => result.current.reset());
    await waitFor(() => {
      expect(result.current.error).toBeNull();
    });
  });

  it('suppresses notification when showErrorNotification=false', async () => {
    const config = makeConfig();
    (config.apiClient.delete as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error('fail'));
    const { Wrapper } = createWrapper();

    const { result } = renderHook(
      () => useDeleteResource(config, 'r1', { showErrorNotification: false }),
      { wrapper: Wrapper },
    );

    await act(async () => {
      result.current.deleteResource();
    });

    await waitFor(() => {
      expect(result.current.error).not.toBeNull();
    });

    expect(showErrorNotification).not.toHaveBeenCalled();
  });

  it('deleteResourceAsync throws on error', async () => {
    const config = makeConfig();
    (config.apiClient.delete as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error('boom'));
    const { Wrapper } = createWrapper();

    const { result } = renderHook(
      () => useDeleteResource(config, 'r1', { showErrorNotification: false }),
      { wrapper: Wrapper },
    );

    await expect(
      act(async () => {
        await result.current.deleteResourceAsync();
      }),
    ).rejects.toThrow('boom');
  });
});
