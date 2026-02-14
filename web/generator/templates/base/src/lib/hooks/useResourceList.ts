import { useState, useEffect, useCallback } from 'react';
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
 * Generic hook for resource list with pagination and sorting
 */
export function useResourceList<T>(
  config: ResourceConfig<T>,
  params: UseResourceListParams = {},
): UseResourceListResult<T> {
  const [data, setData] = useState<FullResource<T>[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [refreshCount, setRefreshCount] = useState(0);

  const refresh = useCallback(() => {
    setRefreshCount((c) => c + 1);
  }, []);

  useEffect(() => {
    let cancelled = false;

    const fetchData = async () => {
      setLoading(true);
      setError(null);
      try {
        const [list, cnt] = await Promise.all([
          config.apiClient.listFull(params),
          config.apiClient.count(params),
        ]);
        if (!cancelled) {
          setData(list.data);
          setTotal(cnt.data);
        }
      } catch (e) {
        if (!cancelled) {
          setError(e as Error);
          console.error('fetch error', e);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    fetchData();

    return () => {
      cancelled = true;
    };
  }, [config.apiClient, JSON.stringify(params), refreshCount]);

  return { data, total, loading, error, refresh };
}
