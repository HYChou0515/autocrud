/**
 * useDeleteResource — TanStack Query mutation hook for deleting a resource.
 *
 * Combines soft delete (`config.apiClient.delete()`) and permanent delete
 * (`config.apiClient.permanentlyDelete()`) into a single hook since both
 * are typically used on the same page. Each operation has its own
 * `isPending` state.
 *
 * @example
 * ```tsx
 * const {
 *   deleteResource,
 *   permanentlyDelete,
 *   isDeletePending,
 *   isPermanentDeletePending,
 * } = useDeleteResource(config, resourceId);
 * ```
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import type { ResourceMeta } from '../../types/api';
import type { ResourceConfig } from '../resources';
import { resourceKeys } from './queryKeys';
import { showErrorNotification as showError } from '../utils/errorNotification';
import type { ResourceMutationOptions } from './types';

export type UseDeleteResourceOptions = ResourceMutationOptions<ResourceMeta | void, void>;

export interface UseDeleteResourceResult {
  /** Soft delete — marks resource as deleted but keeps it recoverable. */
  deleteResource: () => void;
  /** Awaitable soft delete. */
  deleteResourceAsync: () => Promise<ResourceMeta>;
  /** Permanently delete — irrecoverable. */
  permanentlyDelete: () => void;
  /** Awaitable permanent delete. */
  permanentlyDeleteAsync: () => Promise<void>;
  /** Whether a soft-delete request is in flight. */
  isDeletePending: boolean;
  /** Whether a permanent-delete request is in flight. */
  isPermanentDeletePending: boolean;
  /** Combined: whether any delete operation is in flight. */
  isPending: boolean;
  /** The last error from either delete operation. */
  error: Error | null;
  /** Reset both mutation states. */
  reset: () => void;
}

/**
 * Hook for deleting a resource (soft or permanent).
 *
 * @param config      The resource configuration.
 * @param resourceId  The ID of the resource to delete.
 * @param options     Optional callbacks and behaviour overrides.
 */
export function useDeleteResource<T>(
  config: ResourceConfig<T>,
  resourceId: string,
  options: UseDeleteResourceOptions = {},
): UseDeleteResourceResult {
  const queryClient = useQueryClient();
  const {
    onSuccess,
    onError,
    onSettled,
    showErrorNotification: showNotif = true,
    invalidateOnSuccess = true,
  } = options;

  const invalidateCaches = async () => {
    if (!invalidateOnSuccess) return;
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: resourceKeys.details(config.name) }),
      queryClient.invalidateQueries({ queryKey: resourceKeys.lists(config.name) }),
    ]);
  };

  const softDelete = useMutation<ResourceMeta, Error, void>({
    mutationFn: async () => {
      const res = await config.apiClient.delete(resourceId);
      return res.data;
    },
    onSuccess: async (data) => {
      await invalidateCaches();
      await onSuccess?.(data, undefined);
    },
    onError: async (error) => {
      if (showNotif) showError(error, 'Delete Failed');
      await onError?.(error, undefined);
    },
    onSettled: async (data, error) => {
      await onSettled?.(data ?? undefined, error, undefined);
    },
  });

  const permDelete = useMutation<void, Error, void>({
    mutationFn: async () => {
      await config.apiClient.permanentlyDelete(resourceId);
    },
    onSuccess: async () => {
      // Remove (not invalidate) the detail query for this resource so
      // TanStack Query does NOT refetch a now-deleted resource (→ 404).
      // Only invalidate the list queries so the table refreshes.
      if (invalidateOnSuccess) {
        queryClient.removeQueries({
          queryKey: resourceKeys.detail(config.name, resourceId),
        });
        await queryClient.invalidateQueries({
          queryKey: resourceKeys.lists(config.name),
        });
      }
      await onSuccess?.(undefined, undefined);
    },
    onError: async (error) => {
      if (showNotif) showError(error, 'Permanently Delete Failed');
      await onError?.(error, undefined);
    },
    onSettled: async (data, error) => {
      await onSettled?.(data ?? undefined, error, undefined);
    },
  });

  return {
    deleteResource: () => softDelete.mutate(),
    deleteResourceAsync: () => softDelete.mutateAsync(),
    permanentlyDelete: () => permDelete.mutate(),
    permanentlyDeleteAsync: () => permDelete.mutateAsync(),
    isDeletePending: softDelete.isPending,
    isPermanentDeletePending: permDelete.isPending,
    isPending: softDelete.isPending || permDelete.isPending,
    error: softDelete.error ?? permDelete.error,
    reset: () => {
      softDelete.reset();
      permDelete.reset();
    },
  };
}
