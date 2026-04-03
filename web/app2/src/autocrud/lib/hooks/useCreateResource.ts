/**
 * useCreateResource — TanStack Query mutation hook for creating a resource.
 *
 * Wraps `config.apiClient.create()` with automatic cache invalidation and
 * error notification. Users can override defaults via options.
 *
 * @example
 * ```tsx
 * const { create, createAsync, isPending } = useCreateResource(config, {
 *   onSuccess: (data) => navigate(`/admin/${data.resource_id}`),
 * });
 *
 * // Fire-and-forget (for buttons)
 * <Button onClick={() => create(formValues)} loading={isPending}>Save</Button>
 *
 * // Awaitable (for sequential logic)
 * const result = await createAsync(formValues);
 * ```
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import type { RevisionInfo } from '../../types/api';
import type { ResourceConfig } from '../resources';
import { resourceKeys } from './queryKeys';
import { showErrorNotification as showError } from '../utils/errorNotification';
import type { ResourceMutationOptions } from './types';

export type UseCreateResourceOptions<T> = ResourceMutationOptions<RevisionInfo, T>;

export interface UseCreateResourceResult<T> {
  /** Fire-and-forget create — does not throw on error. */
  create: (data: T) => void;
  /** Awaitable create — throws on error so callers can catch. */
  createAsync: (data: T) => Promise<RevisionInfo>;
  /** Whether a create request is currently in flight. */
  isPending: boolean;
  /** The last error from a failed create, or null. */
  error: Error | null;
  /** Reset mutation state (clear error, data, etc.). */
  reset: () => void;
}

/**
 * Hook for creating a new resource instance.
 *
 * @param config  The resource configuration (from `getResource()`).
 * @param options Optional callbacks and behaviour overrides.
 */
export function useCreateResource<T>(
  config: ResourceConfig<T>,
  options: UseCreateResourceOptions<T> = {},
): UseCreateResourceResult<T> {
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
      const res = await config.apiClient.create(data);
      return res.data;
    },
    onSuccess: async (data, variables) => {
      if (invalidateOnSuccess) {
        await queryClient.invalidateQueries({ queryKey: resourceKeys.lists(config.name) });
      }
      await onSuccess?.(data, variables);
    },
    onError: async (error, variables) => {
      if (showNotif) showError(error, 'Create Failed');
      await onError?.(error, variables);
    },
    onSettled: async (data, error, variables) => {
      await onSettled?.(data, error, variables);
    },
  });

  return {
    create: (data: T) => mutation.mutate(data),
    createAsync: (data: T) => mutation.mutateAsync(data),
    isPending: mutation.isPending,
    error: mutation.error,
    reset: mutation.reset,
  };
}
