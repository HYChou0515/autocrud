/**
 * useUpdateResource — TanStack Query mutation hook for updating a resource.
 *
 * Wraps `config.apiClient.update()` with automatic cache invalidation
 * (both detail and list caches) and error notification.
 *
 * @example
 * ```tsx
 * const { update, updateAsync, isPending } = useUpdateResource(config, resourceId);
 *
 * // Fire-and-forget
 * update(newData);
 *
 * // Awaitable
 * const result = await updateAsync(newData);
 * ```
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import type { RevisionInfo } from '../../types/api';
import type { ResourceConfig } from '../resources';
import { resourceKeys } from './queryKeys';
import { showErrorNotification as showError } from '../utils/errorNotification';
import type { ResourceMutationOptions } from './types';

export type UseUpdateResourceOptions<T> = ResourceMutationOptions<RevisionInfo, T>;

export interface UseUpdateResourceResult<T> {
  /** Fire-and-forget update. */
  update: (data: T) => void;
  /** Awaitable update — throws on error. */
  updateAsync: (data: T) => Promise<RevisionInfo>;
  /** Whether an update request is currently in flight. */
  isPending: boolean;
  /** The last error from a failed update, or null. */
  error: Error | null;
  /** Reset mutation state. */
  reset: () => void;
}

/**
 * Hook for updating an existing resource instance.
 *
 * @param config      The resource configuration.
 * @param resourceId  The ID of the resource to update.
 * @param options     Optional callbacks and behaviour overrides.
 */
export function useUpdateResource<T>(
  config: ResourceConfig<T>,
  resourceId: string,
  options: UseUpdateResourceOptions<T> = {},
): UseUpdateResourceResult<T> {
  const queryClient = useQueryClient();
  const {
    onSuccess,
    onError,
    onSettled,
    showErrorNotification: showNotif = true,
    invalidateOnSuccess = true,
  } = options;

  const mutation = useMutation<RevisionInfo, Error, T>({
    mutationFn: async (data: T) => {
      const res = await config.apiClient.update(resourceId, data);
      return res.data;
    },
    onSuccess: async (data, variables) => {
      if (invalidateOnSuccess) {
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: resourceKeys.details(config.name) }),
          queryClient.invalidateQueries({ queryKey: resourceKeys.lists(config.name) }),
        ]);
      }
      await onSuccess?.(data, variables);
    },
    onError: async (error, variables) => {
      if (showNotif) showError(error, 'Update Failed');
      await onError?.(error, variables);
    },
    onSettled: async (data, error, variables) => {
      await onSettled?.(data, error, variables);
    },
  });

  return {
    update: (data: T) => mutation.mutate(data),
    updateAsync: (data: T) => mutation.mutateAsync(data),
    isPending: mutation.isPending,
    error: mutation.error,
    reset: mutation.reset,
  };
}
