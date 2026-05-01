/**
 * useSwitchRevision — Tests
 *
 * Covers:
 * - Successful switch calls apiClient.switchRevision
 * - Invalidates detail, list, AND revisions caches
 * - Error notification
 * - Async throws on error
 * - Custom callbacks
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useSwitchRevision } from './useSwitchRevision';
import { makeConfig, createWrapper } from './test-helpers';

vi.mock('../utils/errorNotification', () => ({
  showErrorNotification: vi.fn(),
}));

import { showErrorNotification } from '../utils/errorNotification';

describe('useSwitchRevision', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('calls apiClient.switchRevision with resourceId and revisionId', async () => {
    const config = makeConfig();
    const { Wrapper } = createWrapper();

    const { result } = renderHook(() => useSwitchRevision(config, 'r1'), { wrapper: Wrapper });

    await act(async () => {
      const res = await result.current.switchRevisionAsync('rev-abc');
      expect(res).toEqual({ resource_id: 'r1', current_revision_id: 'rev-switched' });
    });

    expect(config.apiClient.switchRevision).toHaveBeenCalledWith('r1', 'rev-abc');
  });

  it('invalidates detail, list, and revisions caches', async () => {
    const config = makeConfig();
    const { Wrapper, queryClient } = createWrapper();
    const spy = vi.spyOn(queryClient, 'invalidateQueries');

    const { result } = renderHook(() => useSwitchRevision(config, 'r1'), { wrapper: Wrapper });

    await act(async () => {
      await result.current.switchRevisionAsync('rev-xyz');
    });

    const keys = spy.mock.calls.map((c) => c[0]);
    expect(keys).toContainEqual(
      expect.objectContaining({ queryKey: ['resource', 'test', 'detail'] }),
    );
    expect(keys).toContainEqual(
      expect.objectContaining({ queryKey: ['resource', 'test', 'list'] }),
    );
    expect(keys).toContainEqual(
      expect.objectContaining({ queryKey: ['resource', 'test', 'revisions', 'r1'] }),
    );
  });

  it('shows error notification by default', async () => {
    const config = makeConfig();
    (config.apiClient.switchRevision as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error('switch err'),
    );
    const { Wrapper } = createWrapper();

    const { result } = renderHook(() => useSwitchRevision(config, 'r1'), { wrapper: Wrapper });

    await act(async () => {
      result.current.switchRevision('rev-bad');
    });

    await waitFor(() => {
      expect(showErrorNotification).toHaveBeenCalledWith(
        expect.any(Error),
        'Switch Revision Failed',
      );
    });
  });

  it('suppresses notification when showErrorNotification=false', async () => {
    const config = makeConfig();
    (config.apiClient.switchRevision as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error('fail'),
    );
    const { Wrapper } = createWrapper();

    const { result } = renderHook(
      () => useSwitchRevision(config, 'r1', { showErrorNotification: false }),
      { wrapper: Wrapper },
    );

    await act(async () => {
      result.current.switchRevision('rev-bad');
    });

    await waitFor(() => {
      expect(result.current.error).not.toBeNull();
    });

    expect(showErrorNotification).not.toHaveBeenCalled();
  });

  it('switchRevisionAsync throws on error', async () => {
    const config = makeConfig();
    (config.apiClient.switchRevision as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error('boom'),
    );
    const { Wrapper } = createWrapper();

    const { result } = renderHook(
      () => useSwitchRevision(config, 'r1', { showErrorNotification: false }),
      { wrapper: Wrapper },
    );

    await expect(
      act(async () => {
        await result.current.switchRevisionAsync('rev-bad');
      }),
    ).rejects.toThrow('boom');
  });

  it('calls onSuccess callback with data and revisionId', async () => {
    const config = makeConfig();
    const onSuccess = vi.fn();
    const { Wrapper } = createWrapper();

    const { result } = renderHook(() => useSwitchRevision(config, 'r1', { onSuccess }), {
      wrapper: Wrapper,
    });

    await act(async () => {
      await result.current.switchRevisionAsync('rev-abc');
    });

    expect(onSuccess).toHaveBeenCalledWith(
      { resource_id: 'r1', current_revision_id: 'rev-switched' },
      'rev-abc',
    );
  });

  it('reset clears error', async () => {
    const config = makeConfig();
    (config.apiClient.switchRevision as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error('err'),
    );
    const { Wrapper } = createWrapper();

    const { result } = renderHook(
      () => useSwitchRevision(config, 'r1', { showErrorNotification: false }),
      { wrapper: Wrapper },
    );

    await act(async () => {
      result.current.switchRevision('rev-bad');
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
