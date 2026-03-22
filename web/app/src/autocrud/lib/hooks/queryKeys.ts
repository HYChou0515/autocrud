/**
 * Unified query key factory for all resource-related TanStack Query queries.
 *
 * Usage:
 * ```ts
 * import { resourceKeys } from '@/autocrud/lib/hooks/queryKeys';
 *
 * // Invalidate all queries for a resource
 * queryClient.invalidateQueries({ queryKey: resourceKeys.all('character') });
 *
 * // Invalidate only lists
 * queryClient.invalidateQueries({ queryKey: resourceKeys.lists('character') });
 *
 * // Use in useQuery
 * useQuery({ queryKey: resourceKeys.detail('character', '123'), queryFn: ... });
 * ```
 *
 * Key hierarchy:
 * ```
 * ['resource', name]                               ← all(name)
 * ['resource', name, 'list']                       ← lists(name)
 * ['resource', name, 'list', params]               ← list(name, params)
 * ['resource', name, 'detail']                     ← details(name)
 * ['resource', name, 'detail', id]                 ← detail(name, id)
 * ['resource', name, 'detail', id, revisionId]     ← detail(name, id, revisionId)
 * ['resource', name, 'revisions', id]              ← revisions(name, id)
 * ['resource', name, 'logs', id]                   ← logs(name, id)
 * ```
 */

export const resourceKeys = {
  /** All queries for a given resource name. */
  all: (name: string) => ['resource', name] as const,

  /** All list queries for a resource. */
  lists: (name: string) => ['resource', name, 'list'] as const,

  /** A specific list query with params (limit, offset, sorts, etc.). */
  list: (name: string, params: Record<string, unknown> = {}) =>
    ['resource', name, 'list', params] as const,

  /** All detail queries for a resource. */
  details: (name: string) => ['resource', name, 'detail'] as const,

  /** A specific detail query for a resource instance. */
  detail: (name: string, id: string, revisionId?: string | null) => {
    const key = ['resource', name, 'detail', id] as const;
    return revisionId ? ([...key, revisionId] as const) : key;
  },

  /** Revision list queries for a resource instance. */
  revisions: (name: string, id: string) => ['resource', name, 'revisions', id] as const,

  /** Logs queries for a resource instance (job resources only). */
  logs: (name: string, id: string) => ['resource', name, 'logs', id] as const,
} as const;
