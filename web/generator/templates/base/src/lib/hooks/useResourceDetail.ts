import { useState, useEffect, useCallback } from 'react';
import type { FullResource } from '../../types/api';
import type { ResourceConfig } from '../resources';

export interface UseResourceDetailResult<T> {
  resource: FullResource<T> | null;
  loading: boolean;
  error: Error | null;
  refresh: () => void;
  update: (data: T) => Promise<void>;
  deleteResource: () => Promise<void>;
  restore: () => Promise<void>;
  switchRevision: (revisionId: string) => Promise<void>;
}

/**
 * Generic hook for resource detail with revision history
 */
export function useResourceDetail<T>(
  config: ResourceConfig<T>,
  resourceId: string,
  revisionId?: string | null,
): UseResourceDetailResult<T> {
  const [resource, setResource] = useState<FullResource<T> | null>(null);
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
        const params = revisionId ? { revision_id: revisionId } : undefined;
        const res = await config.apiClient.getFull(resourceId, params);
        if (!cancelled) {
          setResource(res.data);
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
  }, [config.apiClient, resourceId, revisionId, refreshCount]);

  const update = useCallback(
    async (data: T) => {
      await config.apiClient.update(resourceId, data);
      refresh();
    },
    [config.apiClient, resourceId, refresh],
  );

  const deleteResource = useCallback(async () => {
    await config.apiClient.delete(resourceId);
    refresh();
  }, [config.apiClient, resourceId, refresh]);

  const restore = useCallback(async () => {
    await config.apiClient.restore(resourceId);
    refresh();
  }, [config.apiClient, resourceId, refresh]);

  const switchRevision = useCallback(
    async (revisionId: string) => {
      await config.apiClient.switchRevision(resourceId, revisionId);
      refresh();
    },
    [config.apiClient, resourceId, refresh],
  );

  return { resource, loading, error, refresh, update, deleteResource, restore, switchRevision };
}
