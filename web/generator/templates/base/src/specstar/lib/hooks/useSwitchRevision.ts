/**
 * useSwitchRevision — TanStack Query mutation hook for switching a resource's active revision.
 *
 * @example
 * ```tsx
 * const { switchRevision, switchRevisionAsync, isPending } =
 *   useSwitchRevision(config, resourceId);
 *
 * switchRevision('rev-abc-123');
 * ```
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import type { ResourceMeta } from '../../types/api';
import type { ResourceConfig } from '../resources';
import { resourceKeys } from './queryKeys';
import { showErrorNotification as showError } from '../utils/errorNotification';
import type { ResourceMutationOptions } from './types';

export type UseSwitchRevisionOptions = ResourceMutationOptions<ResourceMeta, string>;

export interface UseSwitchRevisionResult {
  /** Fire-and-forget revision switch. */
  switchRevision: (revisionId: string) => void;
  /** Awaitable revision switch — throws on error. */
  switchRevisionAsync: (revisionId: string) => Promise<ResourceMeta>;
  /** Whether a switch request is currently in flight. */
  isPending: boolean;
  /** The last error from a failed switch, or null. */
  error: Error | null;
  /** Reset mutation state. */
  reset: () => void;
}

/**
 * Hook for switching a resource's current active revision.
 *
 * @param config      The resource configuration.
 * @param resourceId  The ID of the resource.
 * @param options     Optional callbacks and behaviour overrides.
 */
export function useSwitchRevision<T>(
  config: ResourceConfig<T>,
  resourceId: string,
  options: UseSwitchRevisionOptions = {},
): UseSwitchRevisionResult {
  const queryClient = useQueryClient();
  const {
    onSuccess,
    onError,
    onSettled,
    showErrorNotification: showNotif = true,
    invalidateOnSuccess = true,
  } = options;

  const mutation = useMutation<ResourceMeta, Error, string>({
    mutationFn: async (revisionId: string) => {
      const res = await config.apiClient.switchRevision(resourceId, revisionId);
      return res.data;
    },
    onSuccess: async (data, revisionId) => {
      if (invalidateOnSuccess) {
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: resourceKeys.details(config.name) }),
          queryClient.invalidateQueries({ queryKey: resourceKeys.lists(config.name) }),
          queryClient.invalidateQueries({
            queryKey: resourceKeys.revisions(config.name, resourceId),
          }),
        ]);
      }
      await onSuccess?.(data, revisionId);
    },
    onError: async (error, revisionId) => {
      if (showNotif) showError(error, 'Switch Revision Failed');
      await onError?.(error, revisionId);
    },
    onSettled: async (data, error, revisionId) => {
      await onSettled?.(data ?? undefined, error, revisionId);
    },
  });

  return {
    switchRevision: (revisionId: string) => mutation.mutate(revisionId),
    switchRevisionAsync: (revisionId: string) => mutation.mutateAsync(revisionId),
    isPending: mutation.isPending,
    error: mutation.error,
    reset: mutation.reset,
  };
}
