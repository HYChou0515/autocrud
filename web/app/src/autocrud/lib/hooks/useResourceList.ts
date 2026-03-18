import { useCallback } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import type { FullResource } from '../../types/api';
import type { ResourceConfig } from '../resources';

export interface UseResourceListParams {
  limit?: number;
  offset?: number;
  sorts?: string;
  [key: string]: any;
}

export interface UseResourceListResult<T> {
  data: FullResource<T>[];
  total: number;
  loading: boolean;
  error: Error | null;
  refresh: () => void;
}

/**
 * Generic hook for resource list with pagination and sorting.
 *
 * Uses `@tanstack/react-query` for automatic caching, deduplication, and
 * background re-fetching.  The query key is derived from the resource name
 * and the request params so identical requests share the same cache entry.
 */
export function useResourceList<T>(
  config: ResourceConfig<T>,
  params: UseResourceListParams = {},
): UseResourceListResult<T> {
  const queryClient = useQueryClient();
  const resourceName = config?.name ?? '__none__';

  const listQuery = useQuery({
    queryKey: ['resource-list', resourceName, params] as const,
    queryFn: async () => {
      const [list, cnt] = await Promise.all([
        config.apiClient.list(params),
        config.apiClient.count(params),
      ]);
      return { data: list.data as FullResource<T>[], total: cnt.data as number };
    },
    enabled: !!config,
  });

  const refresh = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['resource-list', resourceName] });
  }, [queryClient, resourceName]);

  return {
    data: listQuery.data?.data ?? [],
    total: listQuery.data?.total ?? 0,
    loading: listQuery.isLoading || listQuery.isFetching,
    error: listQuery.error ?? null,
    refresh,
  };
}
