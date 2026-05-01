import { useCallback } from 'react';
import { useQuery, useQueryClient, type UseQueryResult } from '@tanstack/react-query';
import type { FullResource } from '../../types/api';
import type { ResourceConfig } from '../resources';
import { resourceKeys } from './queryKeys';
import { fetchResourceList } from './primitives';

export interface UseResourceListParams {
  limit?: number;
  offset?: number;
  sorts?: string;
  [key: string]: any;
}

/**
 * Options for fine-tuning `useResourceList` behaviour.
 *
 * All options are optional — the hook works with zero configuration.
 */
export interface UseResourceListOptions<T> {
  /** Time in ms before cached data is considered stale. */
  staleTime?: number;
  /** Time in ms before inactive cache entries are garbage-collected. */
  gcTime?: number;
  /** Polling interval in ms (0 = disabled). */
  refetchInterval?: number;
  /** Whether to refetch when the browser window regains focus. */
  refetchOnWindowFocus?: boolean;
  /** Set to false to disable automatic fetching. */
  enabled?: boolean;
  /** Data to show while the first fetch is loading. */
  placeholderData?: { data: FullResource<T>[]; total: number };
  /** Transform/select from the raw fetched data. */
  select?: (data: { data: FullResource<T>[]; total: number }) => {
    data: FullResource<T>[];
    total: number;
  };
}

export interface UseResourceListResult<T> {
  data: FullResource<T>[];
  total: number;
  loading: boolean;
  error: Error | null;
  refresh: () => void;
  /** Raw TanStack Query result for advanced usage. */
  query: UseQueryResult<{ data: FullResource<T>[]; total: number }, Error>;
}

/**
 * Generic hook for resource list with pagination and sorting.
 *
 * Uses `@tanstack/react-query` for automatic caching, deduplication, and
 * background re-fetching.  The query key is derived from the resource name
 * and the request params so identical requests share the same cache entry.
 *
 * @param config   The resource configuration (from `getResource()`).
 * @param params   Query params (limit, offset, sorts, etc.).
 * @param options  Optional TanStack Query overrides for fine-tuning.
 */
export function useResourceList<T>(
  config: ResourceConfig<T>,
  params: UseResourceListParams = {},
  options: UseResourceListOptions<T> = {},
): UseResourceListResult<T> {
  const queryClient = useQueryClient();
  const resourceName = config?.name ?? '__none__';

  const listQuery = useQuery({
    queryKey: resourceKeys.list(resourceName, params),
    queryFn: () => fetchResourceList(config, params),
    enabled: options.enabled !== undefined ? options.enabled : !!config,
    staleTime: options.staleTime,
    gcTime: options.gcTime,
    refetchInterval: options.refetchInterval,
    refetchOnWindowFocus: options.refetchOnWindowFocus,
    placeholderData: options.placeholderData,
    select: options.select,
  });

  const refresh = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: resourceKeys.lists(resourceName) });
  }, [queryClient, resourceName]);

  return {
    data: listQuery.data?.data ?? [],
    total: listQuery.data?.total ?? 0,
    loading: listQuery.isLoading || listQuery.isFetching,
    error: listQuery.error ?? null,
    refresh,
    query: listQuery,
  };
}
