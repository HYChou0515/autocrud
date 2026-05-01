/**
 * useRestoreResource — TanStack Query mutation hook for restoring a soft-deleted resource.
 *
 * @example
 * ```tsx
 * const { restore, restoreAsync, isPending } = useRestoreResource(config, resourceId);
 * ```
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import type { ResourceMeta } from '../../types/api';
import type { ResourceConfig } from '../resources';
import { resourceKeys } from './queryKeys';
import { showErrorNotification as showError } from '../utils/errorNotification';
import type { ResourceMutationOptions } from './types';

export type UseRestoreResourceOptions = ResourceMutationOptions<ResourceMeta, void>;

export interface UseRestoreResourceResult {
  /** Fire-and-forget restore. */
  restore: () => void;
  /** Awaitable restore — throws on error. */
  restoreAsync: () => Promise<ResourceMeta>;
  /** Whether a restore request is currently in flight. */
  isPending: boolean;
  /** The last error from a failed restore, or null. */
  error: Error | null;
  /** Reset mutation state. */
  reset: () => void;
}

/**
 * Hook for restoring a soft-deleted resource.
 *
 * @param config      The resource configuration.
 * @param resourceId  The ID of the resource to restore.
 * @param options     Optional callbacks and behaviour overrides.
 */
export function useRestoreResource<T>(
  config: ResourceConfig<T>,
  resourceId: string,
  options: UseRestoreResourceOptions = {},
): UseRestoreResourceResult {
  const queryClient = useQueryClient();
  const {
    onSuccess,
    onError,
    onSettled,
    showErrorNotification: showNotif = true,
    invalidateOnSuccess = true,
  } = options;

  const mutation = useMutation<ResourceMeta, Error, void>({
    mutationFn: async () => {
      const res = await config.apiClient.restore(resourceId);
      return res.data;
    },
    onSuccess: async (data) => {
      if (invalidateOnSuccess) {
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: resourceKeys.details(config.name) }),
          queryClient.invalidateQueries({ queryKey: resourceKeys.lists(config.name) }),
        ]);
      }
      await onSuccess?.(data, undefined);
    },
    onError: async (error) => {
      if (showNotif) showError(error, 'Restore Failed');
      await onError?.(error, undefined);
    },
    onSettled: async (data, error) => {
      await onSettled?.(data ?? undefined, error, undefined);
    },
  });

  return {
    restore: () => mutation.mutate(),
    restoreAsync: () => mutation.mutateAsync(),
    isPending: mutation.isPending,
    error: mutation.error,
    reset: mutation.reset,
  };
}
