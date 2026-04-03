/**
 * useMultiResourceList — Aggregate data from multiple ResourceConfigs into
 * a single flat list.
 *
 * Each returned row carries a `_source` string indicating the resource name
 * it originally came from, so downstream components (e.g. MultiResourceTable)
 * can display or route by source.
 *
 * Fully generic — does **not** assume the resources are jobs or any other
 * specific type.
 *
 * Now uses `@tanstack/react-query` `useQueries` for automatic caching,
 * deduplication, and background re-fetching — while preserving the same
 * public return type for backward compatibility.
 */

import { useCallback, useMemo } from 'react';
import { useQueries, useQueryClient, type UseQueryResult } from '@tanstack/react-query';
import type { FullResource } from '../../types/api';
import type { ResourceConfig } from '../resources';
import type { UseResourceListParams } from './useResourceList';
import { resourceKeys } from './queryKeys';
import { fetchResourceList } from './primitives';

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

/**
 * A single entry describing which resource to query and with what params.
 */
export interface MultiResourceEntry {
  config: ResourceConfig;
  /** Per-resource query params (merged with shared `params`). */
  params?: UseResourceListParams;
}

/**
 * A `FullResource` row tagged with its source resource name.
 */
export type MultiResourceRow = FullResource<unknown> & { _source: string };

/**
 * Options for fine-tuning `useMultiResourceList` behaviour.
 */
export interface UseMultiResourceListOptions {
  /** Time in ms before cached data is considered stale. */
  staleTime?: number;
  /** Time in ms before inactive cache entries are garbage-collected. */
  gcTime?: number;
  /** Set to false to disable automatic fetching. */
  enabled?: boolean;
  /** Polling interval in ms. Set to automatically refetch on this interval. */
  refetchInterval?: number | false;
}

export interface UseMultiResourceListResult {
  /** Flat list of rows from all sources, newest first. */
  items: MultiResourceRow[];
  /** Per-source item count (from count endpoint). */
  totals: Record<string, number>;
  /** Sum of all source counts. */
  totalCount: number;
  loading: boolean;
  error: Error | null;
  refresh: () => void;
  /** Raw TanStack Query results for each entry (advanced usage). */
  queries: UseQueryResult<{ data: FullResource<unknown>[]; total: number }, Error>[];
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

/**
 * Fetch and aggregate list + count from multiple resources in parallel.
 *
 * @param entries      Array of `{ config, params? }` — one per resource.
 * @param sharedParams Query params applied to **every** resource (merged
 *                     with each entry's `params`, entry wins on conflict).
 * @param options      Optional TanStack Query overrides.
 *
 * @example
 * ```tsx
 * const { items, totalCount, loading } = useMultiResourceList(
 *   [
 *     { config: getResource('new-char1-job')! },
 *     { config: getResource('create-new-character2-job')! },
 *   ],
 *   { data_conditions: JSON.stringify([{ field_path: 'status', operator: 'in', value: ['pending', 'processing'] }]) },
 * );
 * ```
 */
export function useMultiResourceList(
  entries: MultiResourceEntry[],
  sharedParams: UseResourceListParams = {},
  options: UseMultiResourceListOptions = {},
): UseMultiResourceListResult {
  const queryClient = useQueryClient();

  // Build query configs for each entry
  const queryConfigs = useMemo(
    () =>
      entries.map((entry) => {
        const mergedParams = { ...sharedParams, ...entry.params };
        return {
          queryKey: resourceKeys.list(entry.config?.name ?? '__none__', mergedParams),
          queryFn: () => fetchResourceList(entry.config, mergedParams),
          enabled:
            options.enabled !== undefined ? options.enabled : !!entry.config && entries.length > 0,
          staleTime: options.staleTime,
          gcTime: options.gcTime,
          refetchInterval: options.refetchInterval,
        };
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [
      JSON.stringify(entries.map((e) => ({ name: e.config?.name, params: e.params }))),
      JSON.stringify(sharedParams),
      options.enabled,
      options.staleTime,
      options.gcTime,
      options.refetchInterval,
    ],
  );

  const queryResults = useQueries({ queries: queryConfigs }) as UseQueryResult<
    { data: FullResource<unknown>[]; total: number },
    Error
  >[];

  // Aggregate results
  const { items, totals, firstError } = useMemo(() => {
    const allRows: MultiResourceRow[] = [];
    const newTotals: Record<string, number> = {};
    let err: Error | null = null;

    for (let i = 0; i < queryResults.length; i++) {
      const qr = queryResults[i];
      const name = entries[i]?.config?.name ?? 'unknown';

      if (qr.error && !err) {
        err = qr.error;
      }

      if (qr.data) {
        for (const item of qr.data.data) {
          allRows.push({ ...item, _source: name });
        }
        newTotals[name] = qr.data.total;
      }
    }

    // Sort by updated_time descending (newest first)
    allRows.sort((a, b) => {
      const ta = a.meta?.updated_time ?? '';
      const tb = b.meta?.updated_time ?? '';
      return tb.localeCompare(ta);
    });

    return { items: allRows, totals: newTotals, firstError: err };
  }, [queryResults, entries]);

  const loading = queryResults.some((q) => q.isLoading);

  const totalCount = useMemo(() => Object.values(totals).reduce((sum, n) => sum + n, 0), [totals]);

  const refresh = useCallback(() => {
    for (const entry of entries) {
      if (entry.config?.name) {
        queryClient.invalidateQueries({ queryKey: resourceKeys.lists(entry.config.name) });
      }
    }
  }, [queryClient, entries]);

  return { items, totals, totalCount, loading, error: firstError, refresh, queries: queryResults };
}
