import { useCallback } from 'react';
import { useQuery, useQueryClient, type UseQueryResult } from '@tanstack/react-query';
import type { FullResource } from '../../types/api';
import type { ResourceConfig } from '../resources';
import { resourceKeys } from './queryKeys';
import { fetchResourceDetail, fetchResourceLogs } from './primitives';
import { useUpdateResource, type UseUpdateResourceOptions } from './useUpdateResource';
import { useDeleteResource, type UseDeleteResourceOptions } from './useDeleteResource';
import { useRestoreResource, type UseRestoreResourceOptions } from './useRestoreResource';
import { useSwitchRevision, type UseSwitchRevisionOptions } from './useSwitchRevision';
import { useRerunResource, type UseRerunResourceOptions } from './useRerunResource';

/**
 * Options for fine-tuning `useResourceDetail` behaviour.
 *
 * All options are optional — the hook works identically to before when
 * called without options (`useResourceDetail(config, id, revisionId)`).
 */
export interface UseResourceDetailOptions<T = any> {
  /** Revision ID to fetch (alternative to the positional 3rd argument). */
  revisionId?: string | null;
  /** TanStack Query options for the detail fetch. */
  queryOptions?: {
    staleTime?: number;
    gcTime?: number;
    refetchInterval?: number;
    enabled?: boolean;
  };
  /** Override options for the internal update mutation. */
  updateOptions?: UseUpdateResourceOptions<T>;
  /** Override options for the internal delete mutation. */
  deleteOptions?: UseDeleteResourceOptions;
  /** Override options for the internal restore mutation. */
  restoreOptions?: UseRestoreResourceOptions;
  /** Override options for the internal switchRevision mutation. */
  switchRevisionOptions?: UseSwitchRevisionOptions;
  /** Override options for the internal rerun mutation. */
  rerunOptions?: UseRerunResourceOptions;
}

export interface UseResourceDetailResult<T> {
  resource: FullResource<T> | null;
  loading: boolean;
  error: Error | null;
  refresh: () => void;
  update: (data: T) => Promise<void>;
  deleteResource: () => Promise<void>;
  permanentlyDelete: () => Promise<void>;
  restore: () => Promise<void>;
  switchRevision: (revisionId: string) => Promise<void>;
  rerun: () => Promise<void>;
  /** Fetched job execution logs (null if not loaded yet, undefined if 204 No Content) */
  logs: string | null | undefined;
  /** Whether logs are currently being fetched */
  logsLoading: boolean;
  /** Fetch (or re-fetch) execution logs for the current resource */
  fetchLogs: () => void;
  /** Raw TanStack Query result for the detail fetch. */
  query: UseQueryResult<FullResource<T>, Error>;
  /** Whether an update mutation is in flight. */
  isUpdatePending: boolean;
  /** Whether any delete mutation is in flight. */
  isDeletePending: boolean;
  /** Whether a restore mutation is in flight. */
  isRestorePending: boolean;
  /** Whether a switch-revision mutation is in flight. */
  isSwitchRevisionPending: boolean;
  /** Whether a rerun mutation is in flight. */
  isRerunPending: boolean;
}

/**
 * Generic hook for resource detail with revision history.
 *
 * Backward compatible: `useResourceDetail(config, id, 'rev123')` still works.
 * New usage: `useResourceDetail(config, id, { revisionId: 'rev123', queryOptions: { ... } })`.
 *
 * @param config              The resource configuration.
 * @param resourceId          The ID of the resource to fetch.
 * @param revisionIdOrOptions A revision ID string (backward compat) or options object.
 * @param maybeOptions        Options when the 3rd arg is a revision ID string.
 */
export function useResourceDetail<T>(
  config: ResourceConfig<T>,
  resourceId: string,
  revisionIdOrOptions?: string | null | UseResourceDetailOptions<T>,
  maybeOptions?: UseResourceDetailOptions<T>,
): UseResourceDetailResult<T> {
  // Parse overloaded arguments
  let revisionId: string | null | undefined;
  let options: UseResourceDetailOptions<T>;

  if (typeof revisionIdOrOptions === 'object' && revisionIdOrOptions !== null) {
    options = revisionIdOrOptions;
    revisionId = options.revisionId;
  } else {
    revisionId = revisionIdOrOptions;
    options = maybeOptions ?? {};
  }

  const queryClient = useQueryClient();
  const queryOpts = options.queryOptions ?? {};

  // ── Detail query ────────────────────────────────────────────────
  const detailQuery = useQuery<FullResource<T>, Error>({
    queryKey: resourceKeys.detail(config.name, resourceId, revisionId),
    queryFn: () => fetchResourceDetail(config, resourceId, revisionId),
    enabled: queryOpts.enabled !== undefined ? queryOpts.enabled : !!config && !!resourceId,
    staleTime: queryOpts.staleTime,
    gcTime: queryOpts.gcTime,
    refetchInterval: queryOpts.refetchInterval,
  });

  const refresh = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: resourceKeys.details(config.name) });
    queryClient.invalidateQueries({
      queryKey: resourceKeys.revisions(config.name, resourceId),
    });
  }, [queryClient, config.name, resourceId]);

  // ── Mutations (composed from Phase 2 hooks) ────────────────────
  // Update keeps showErrorNotification=false because the component needs to
  // inspect errors for unique-constraint field highlighting before notifying.
  // All other mutations delegate notification to their hooks (default: true).
  const updateMutation = useUpdateResource<T>(config, resourceId, {
    showErrorNotification: false,
    ...options.updateOptions,
  });
  const deleteMutation = useDeleteResource(config, resourceId, {
    ...options.deleteOptions,
  });
  const restoreMutation = useRestoreResource(config, resourceId, {
    ...options.restoreOptions,
  });
  const switchMutation = useSwitchRevision(config, resourceId, {
    ...options.switchRevisionOptions,
  });
  const rerunMutation = useRerunResource(config, resourceId, {
    ...options.rerunOptions,
  });

  // ── Backward-compatible mutation wrappers ───────────────────────
  // `update` re-throws so callers can inspect errors (e.g. unique constraints).
  // All other mutations swallow errors — the hooks already show notifications.
  const update = useCallback(
    async (data: T) => {
      await updateMutation.updateAsync(data);
    },
    [updateMutation],
  );

  const deleteResource = useCallback(async () => {
    await deleteMutation.deleteResourceAsync().catch(() => {});
  }, [deleteMutation]);

  const permanentlyDelete = useCallback(async () => {
    await deleteMutation.permanentlyDeleteAsync();
  }, [deleteMutation]);

  const restore = useCallback(async () => {
    await restoreMutation.restoreAsync().catch(() => {});
  }, [restoreMutation]);

  const switchRevision = useCallback(
    async (revId: string) => {
      await switchMutation.switchRevisionAsync(revId);
    },
    [switchMutation],
  );

  const rerun = useCallback(async () => {
    await rerunMutation.rerunAsync().catch(() => {});
  }, [rerunMutation]);

  // ── Logs query ──────────────────────────────────────────────────
  const logsQuery = useQuery<string | undefined, Error>({
    queryKey: resourceKeys.logs(config.name, resourceId),
    queryFn: () => fetchResourceLogs(config, resourceId),
    enabled: false, // Only fetch on demand via refetch()
  });

  const fetchLogsRefetch = useCallback(() => {
    logsQuery.refetch();
  }, [logsQuery]);

  return {
    resource: detailQuery.data ?? null,
    loading: detailQuery.isLoading,
    error: detailQuery.error ?? null,
    refresh,
    update,
    deleteResource,
    permanentlyDelete,
    restore,
    switchRevision,
    rerun,
    logs: logsQuery.data === undefined ? (logsQuery.isFetched ? undefined : null) : logsQuery.data,
    logsLoading: logsQuery.isFetching,
    fetchLogs: fetchLogsRefetch,
    query: detailQuery,
    isUpdatePending: updateMutation.isPending,
    isDeletePending: deleteMutation.isPending,
    isRestorePending: restoreMutation.isPending,
    isSwitchRevisionPending: switchMutation.isPending,
    isRerunPending: rerunMutation.isPending,
  };
}
