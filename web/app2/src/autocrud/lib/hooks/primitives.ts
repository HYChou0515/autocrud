/**
 * Primitive (non-hook) async fetcher functions for resource data.
 *
 * These are extracted from the query hooks so that users can reuse them
 * in their own `useQuery`, `useSWR`, or plain `await` calls without
 * depending on our specific hook wrappers.
 *
 * @example
 * ```ts
 * import { fetchResourceList, fetchResourceDetail } from '@/autocrud/lib/hooks/primitives';
 *
 * // Use with your own useQuery
 * const query = useQuery({
 *   queryKey: ['my-custom-key'],
 *   queryFn: () => fetchResourceList(config, { limit: 10 }),
 * });
 *
 * // Or just await directly
 * const detail = await fetchResourceDetail(config, 'abc-123');
 * ```
 */

import type { FullResource, RevisionListResponse, RevisionListParams } from '../../types/api';
import type { ResourceConfig } from '../resources';
import type { UseResourceListParams } from './useResourceList';

/**
 * Fetch a paginated list of resources along with total count.
 *
 * Calls `config.apiClient.list()` and `config.apiClient.count()` in parallel.
 */
export async function fetchResourceList<T>(
  config: ResourceConfig<T>,
  params: UseResourceListParams = {},
): Promise<{ data: FullResource<T>[]; total: number }> {
  const [list, cnt] = await Promise.all([
    config.apiClient.list(params),
    config.apiClient.count(params),
  ]);
  return { data: list.data as FullResource<T>[], total: cnt.data as number };
}

/**
 * Fetch a single resource by ID, optionally at a specific revision.
 *
 * Passes `include_deleted: true` so soft-deleted resources are also returned.
 */
export async function fetchResourceDetail<T>(
  config: ResourceConfig<T>,
  id: string,
  revisionId?: string | null,
): Promise<FullResource<T>> {
  const params: Record<string, unknown> = { include_deleted: true };
  if (revisionId) params.revision_id = revisionId;
  const res = await config.apiClient.get(id, params);
  return res.data;
}

/**
 * Fetch the revision list for a resource instance.
 */
export async function fetchResourceRevisions<T>(
  config: ResourceConfig<T>,
  id: string,
  params?: RevisionListParams,
): Promise<RevisionListResponse> {
  const res = await config.apiClient.revisionList(id, params);
  return res.data;
}

/**
 * Fetch execution logs for a job resource.
 *
 * Returns `undefined` if the resource doesn't support logs or 204 No Content.
 */
export async function fetchResourceLogs<T>(
  config: ResourceConfig<T>,
  id: string,
): Promise<string | undefined> {
  if (!config.apiClient.getLogs) return undefined;
  const res = await config.apiClient.getLogs(id);
  // 204 No Content → axios returns empty string
  return res.data || undefined;
}
