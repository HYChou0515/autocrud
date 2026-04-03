/**
 * useResourceDetail — Tests for the composite detail + mutation hook.
 *
 * Covers:
 * - Fetches resource detail via TanStack Query
 * - Backward-compatible signature (config, id, revisionId)
 * - Options object signature (config, id, { revisionId, ... })
 * - update() delegates to useUpdateResource
 * - deleteResource() delegates to useDeleteResource
 * - permanentlyDelete() delegates to useDeleteResource
 * - restore() delegates to useRestoreResource
 * - switchRevision() delegates to useSwitchRevision
 * - rerun() delegates to useRerunResource
 * - Logs are fetched on demand (disabled by default)
 * - Mutation pending states are exposed
 * - update() has error notification suppressed (component handles unique constraints)
 * - Simple mutations (delete, restore, rerun) show error notification and swallow errors
 * - permanentlyDelete() and switchRevision() still throw (component needs post-success logic)
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useResourceDetail } from './useResourceDetail';
import { makeConfig, createWrapper } from './test-helpers';

vi.mock('../utils/errorNotification', () => ({
  showErrorNotification: vi.fn(),
}));

import { showErrorNotification } from '../utils/errorNotification';

describe('useResourceDetail', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // -- Detail query ---------------------------------------------------------

  it('fetches resource detail on mount', async () => {
    const config = makeConfig();
    const { Wrapper } = createWrapper();

    const { result } = renderHook(() => useResourceDetail(config, 'r1'), { wrapper: Wrapper });

    expect(result.current.loading).toBe(true);

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.resource).toBeTruthy();
    expect(config.apiClient.get).toHaveBeenCalledWith('r1', { include_deleted: true });
    expect(result.current.error).toBeNull();
  });

  it('fetches with revision ID (positional string)', async () => {
    const config = makeConfig();
    const { Wrapper } = createWrapper();

    const { result } = renderHook(() => useResourceDetail(config, 'r1', 'rev-42'), {
      wrapper: Wrapper,
    });

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(config.apiClient.get).toHaveBeenCalledWith('r1', {
      include_deleted: true,
      revision_id: 'rev-42',
    });
  });

  it('fetches with revision ID (options object)', async () => {
    const config = makeConfig();
    const { Wrapper } = createWrapper();

    const { result } = renderHook(() => useResourceDetail(config, 'r1', { revisionId: 'rev-99' }), {
      wrapper: Wrapper,
    });

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(config.apiClient.get).toHaveBeenCalledWith('r1', {
      include_deleted: true,
      revision_id: 'rev-99',
    });
  });

  it('handles null revisionId (backward compat)', async () => {
    const config = makeConfig();
    const { Wrapper } = createWrapper();

    const { result } = renderHook(() => useResourceDetail(config, 'r1', null), {
      wrapper: Wrapper,
    });

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(config.apiClient.get).toHaveBeenCalledWith('r1', { include_deleted: true });
  });

  it('handles fetch error', async () => {
    const config = makeConfig();
    (config.apiClient.get as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error('Not found'),
    );
    const { Wrapper } = createWrapper();

    const { result } = renderHook(() => useResourceDetail(config, 'r1'), { wrapper: Wrapper });

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.error).toBeInstanceOf(Error);
    expect(result.current.resource).toBeNull();
  });

  it('exposes query object for advanced usage', async () => {
    const config = makeConfig();
    const { Wrapper } = createWrapper();

    const { result } = renderHook(() => useResourceDetail(config, 'r1'), { wrapper: Wrapper });

    await waitFor(() => {
      expect(result.current.query).toBeTruthy();
      expect(result.current.query.isSuccess).toBe(true);
    });
  });

  // -- Mutations (delegated) -----------------------------------------------

  it('update delegates to apiClient.update', async () => {
    const config = makeConfig();
    const { Wrapper } = createWrapper();

    const { result } = renderHook(() => useResourceDetail(config, 'r1'), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.update({ name: 'New' } as any);
    });

    expect(config.apiClient.update).toHaveBeenCalledWith('r1', { name: 'New' });
  });

  it('deleteResource delegates to apiClient.delete', async () => {
    const config = makeConfig();
    const { Wrapper } = createWrapper();

    const { result } = renderHook(() => useResourceDetail(config, 'r1'), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.deleteResource();
    });

    expect(config.apiClient.delete).toHaveBeenCalledWith('r1');
  });

  it('permanentlyDelete delegates to apiClient.permanentlyDelete', async () => {
    const config = makeConfig();
    const { Wrapper } = createWrapper();

    const { result } = renderHook(() => useResourceDetail(config, 'r1'), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.permanentlyDelete();
    });

    expect(config.apiClient.permanentlyDelete).toHaveBeenCalledWith('r1');
  });

  it('restore delegates to apiClient.restore', async () => {
    const config = makeConfig();
    const { Wrapper } = createWrapper();

    const { result } = renderHook(() => useResourceDetail(config, 'r1'), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.restore();
    });

    expect(config.apiClient.restore).toHaveBeenCalledWith('r1');
  });

  it('switchRevision delegates to apiClient.switchRevision', async () => {
    const config = makeConfig();
    const { Wrapper } = createWrapper();

    const { result } = renderHook(() => useResourceDetail(config, 'r1'), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.switchRevision('rev-target');
    });

    expect(config.apiClient.switchRevision).toHaveBeenCalledWith('r1', 'rev-target');
  });

  it('rerun delegates to apiClient.rerun', async () => {
    const config = makeConfig();
    const { Wrapper } = createWrapper();

    const { result } = renderHook(() => useResourceDetail(config, 'r1'), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.rerun();
    });

    expect(config.apiClient.rerun).toHaveBeenCalledWith('r1');
  });

  // -- Error notification behaviour -------------------------------------------

  it('update does not show error notification (component handles unique constraints)', async () => {
    const config = makeConfig();
    (config.apiClient.update as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error('update err'),
    );
    const { Wrapper } = createWrapper();

    const { result } = renderHook(() => useResourceDetail(config, 'r1'), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.loading).toBe(false));

    await expect(
      act(async () => {
        await result.current.update({} as any);
      }),
    ).rejects.toThrow('update err');

    // update has showErrorNotification: false — component handles it
    expect(showErrorNotification).not.toHaveBeenCalled();
  });

  it('deleteResource shows error notification and swallows errors', async () => {
    const config = makeConfig();
    (config.apiClient.delete as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error('delete err'),
    );
    const { Wrapper } = createWrapper();

    const { result } = renderHook(() => useResourceDetail(config, 'r1'), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.loading).toBe(false));

    // Should NOT throw (errors swallowed in wrapper)
    await act(async () => {
      await result.current.deleteResource();
    });

    expect(showErrorNotification).toHaveBeenCalledWith(expect.any(Error), 'Delete Failed');
  });

  it('permanentlyDelete shows error notification but re-throws', async () => {
    const config = makeConfig();
    (config.apiClient.permanentlyDelete as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error('perm delete err'),
    );
    const { Wrapper } = createWrapper();

    const { result } = renderHook(() => useResourceDetail(config, 'r1'), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.loading).toBe(false));

    // Should throw (component needs to prevent navigate)
    await expect(
      act(async () => {
        await result.current.permanentlyDelete();
      }),
    ).rejects.toThrow('perm delete err');

    expect(showErrorNotification).toHaveBeenCalledWith(
      expect.any(Error),
      'Permanently Delete Failed',
    );
  });

  it('restore shows error notification and swallows errors', async () => {
    const config = makeConfig();
    (config.apiClient.restore as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error('restore err'),
    );
    const { Wrapper } = createWrapper();

    const { result } = renderHook(() => useResourceDetail(config, 'r1'), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.restore();
    });

    expect(showErrorNotification).toHaveBeenCalledWith(expect.any(Error), 'Restore Failed');
  });

  it('switchRevision shows error notification but re-throws', async () => {
    const config = makeConfig();
    (config.apiClient.switchRevision as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error('switch err'),
    );
    const { Wrapper } = createWrapper();

    const { result } = renderHook(() => useResourceDetail(config, 'r1'), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.loading).toBe(false));

    await expect(
      act(async () => {
        await result.current.switchRevision('rev-99');
      }),
    ).rejects.toThrow('switch err');

    expect(showErrorNotification).toHaveBeenCalledWith(expect.any(Error), 'Switch Revision Failed');
  });

  it('rerun shows error notification and swallows errors', async () => {
    const config = makeConfig();
    (config.apiClient.rerun as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error('rerun err'),
    );
    const { Wrapper } = createWrapper();

    const { result } = renderHook(() => useResourceDetail(config, 'r1'), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.rerun();
    });

    expect(showErrorNotification).toHaveBeenCalledWith(expect.any(Error), 'Rerun Failed');
  });

  it('user can enable error notification via mutation options', async () => {
    const config = makeConfig();
    (config.apiClient.update as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error('update err'),
    );
    const { Wrapper } = createWrapper();

    const { result } = renderHook(
      () =>
        useResourceDetail(config, 'r1', {
          updateOptions: { showErrorNotification: true },
        }),
      { wrapper: Wrapper },
    );

    await waitFor(() => expect(result.current.loading).toBe(false));

    await expect(
      act(async () => {
        await result.current.update({} as any);
      }),
    ).rejects.toThrow('update err');

    expect(showErrorNotification).toHaveBeenCalledWith(expect.any(Error), 'Update Failed');
  });

  // -- Mutation pending states ----------------------------------------------

  it('exposes mutation pending states', async () => {
    const config = makeConfig();
    const { Wrapper } = createWrapper();

    const { result } = renderHook(() => useResourceDetail(config, 'r1'), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.loading).toBe(false));

    // All mutations should be idle initially
    expect(result.current.isUpdatePending).toBe(false);
    expect(result.current.isDeletePending).toBe(false);
    expect(result.current.isRestorePending).toBe(false);
    expect(result.current.isSwitchRevisionPending).toBe(false);
    expect(result.current.isRerunPending).toBe(false);
  });

  // -- Logs -----------------------------------------------------------------

  it('logs are not fetched by default (on demand only)', async () => {
    const config = makeConfig();
    const { Wrapper } = createWrapper();

    const { result } = renderHook(() => useResourceDetail(config, 'r1'), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.loading).toBe(false));

    // Logs should be null (not fetched yet)
    expect(result.current.logs).toBeNull();
    expect(result.current.logsLoading).toBe(false);

    // getLogs should NOT have been called yet
    expect(config.apiClient.getLogs).not.toHaveBeenCalled();
  });

  it('fetchLogs triggers log fetch', async () => {
    const config = makeConfig();
    const { Wrapper } = createWrapper();

    const { result } = renderHook(() => useResourceDetail(config, 'r1'), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.loading).toBe(false));

    // Trigger logs fetch
    act(() => {
      result.current.fetchLogs();
    });

    await waitFor(() => {
      expect(config.apiClient.getLogs).toHaveBeenCalledWith('r1');
    });
  });

  // -- Refresh --------------------------------------------------------------

  it('refresh invalidates detail + revision caches', async () => {
    const config = makeConfig();
    const { Wrapper, queryClient } = createWrapper();
    const spy = vi.spyOn(queryClient, 'invalidateQueries');

    const { result } = renderHook(() => useResourceDetail(config, 'r1'), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.loading).toBe(false));

    act(() => {
      result.current.refresh();
    });

    const keys = spy.mock.calls.map((c) => c[0]);
    expect(keys).toContainEqual(
      expect.objectContaining({ queryKey: ['resource', 'test', 'detail'] }),
    );
    expect(keys).toContainEqual(
      expect.objectContaining({ queryKey: ['resource', 'test', 'revisions', 'r1'] }),
    );
  });

  // -- Options with 4th parameter -------------------------------------------

  it('supports positional revisionId with options as 4th param', async () => {
    const config = makeConfig();
    const onSuccess = vi.fn();
    const { Wrapper } = createWrapper();

    const { result } = renderHook(
      () => useResourceDetail(config, 'r1', 'rev-42', { updateOptions: { onSuccess } }),
      { wrapper: Wrapper },
    );

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(config.apiClient.get).toHaveBeenCalledWith('r1', {
      include_deleted: true,
      revision_id: 'rev-42',
    });

    await act(async () => {
      await result.current.update({ x: 1 } as any);
    });

    expect(onSuccess).toHaveBeenCalled();
  });
});
