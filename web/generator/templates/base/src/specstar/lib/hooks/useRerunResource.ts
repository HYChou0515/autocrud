/**
 * useRerunResource — TanStack Query mutation hook for rerunning a job resource.
 *
 * Only usable with job resources that have `config.apiClient.rerun` defined.
 * If the API method is not available, the mutation will throw immediately.
 *
 * @example
 * ```tsx
 * const { rerun, rerunAsync, isPending } = useRerunResource(config, resourceId);
 *
 * <Button onClick={() => rerun()} loading={isPending}>Rerun</Button>
 * ```
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import type { RevisionInfo } from '../../types/api';
import type { ResourceConfig } from '../resources';
import { resourceKeys } from './queryKeys';
import { showErrorNotification as showError } from '../utils/errorNotification';
import type { ResourceMutationOptions } from './types';

export type UseRerunResourceOptions = ResourceMutationOptions<RevisionInfo, void>;

export interface UseRerunResourceResult {
  /** Fire-and-forget rerun. */
  rerun: () => void;
  /** Awaitable rerun — throws on error. */
  rerunAsync: () => Promise<RevisionInfo>;
  /** Whether a rerun request is currently in flight. */
  isPending: boolean;
  /** The last error from a failed rerun, or null. */
  error: Error | null;
  /** Reset mutation state. */
  reset: () => void;
}

/**
 * Hook for rerunning a job resource.
 *
 * @param config      The resource configuration (must be a job resource with `apiClient.rerun`).
 * @param resourceId  The ID of the job resource to rerun.
 * @param options     Optional callbacks and behaviour overrides.
 */
export function useRerunResource<T>(
  config: ResourceConfig<T>,
  resourceId: string,
  options: UseRerunResourceOptions = {},
): UseRerunResourceResult {
  const queryClient = useQueryClient();
  const {
    onSuccess,
    onError,
    onSettled,
    showErrorNotification: showNotif = true,
    invalidateOnSuccess = true,
  } = options;

  const mutation = useMutation<RevisionInfo, Error, void>({
    mutationFn: async () => {
      if (!config.apiClient.rerun) {
        throw new Error(`Resource "${config.name}" does not support rerun`);
      }
      const res = await config.apiClient.rerun(resourceId);
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
      if (showNotif) showError(error, 'Rerun Failed');
      await onError?.(error, undefined);
    },
    onSettled: async (data, error) => {
      await onSettled?.(data ?? undefined, error, undefined);
    },
  });

  return {
    rerun: () => mutation.mutate(),
    rerunAsync: () => mutation.mutateAsync(),
    isPending: mutation.isPending,
    error: mutation.error,
    reset: mutation.reset,
  };
}
