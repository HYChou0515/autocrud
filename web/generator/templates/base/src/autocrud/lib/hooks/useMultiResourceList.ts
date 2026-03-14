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
 */

import { useState, useEffect, useCallback, useMemo } from 'react';
import type { FullResource } from '../../types/api';
import type { ResourceConfig } from '../resources';
import type { UseResourceListParams } from './useResourceList';

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
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

/**
 * Fetch and aggregate list + count from multiple resources in parallel.
 *
 * @param entries  Array of `{ config, params? }` — one per resource.
 * @param sharedParams  Query params applied to **every** resource (merged
 *                      with each entry's `params`, entry wins on conflict).
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
): UseMultiResourceListResult {
  const [items, setItems] = useState<MultiResourceRow[]>([]);
  const [totals, setTotals] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(entries.length > 0);
  const [error, setError] = useState<Error | null>(null);
  const [refreshCount, setRefreshCount] = useState(0);

  const refresh = useCallback(() => setRefreshCount((c) => c + 1), []);

  // Stabilise the dependency so the effect only re-runs when inputs change
  const entriesKey = useMemo(
    () =>
      JSON.stringify(
        entries.map((e) => ({
          name: e.config?.name,
          params: e.params,
        })),
      ),
    [entries],
  );
  const sharedParamsKey = useMemo(() => JSON.stringify(sharedParams), [sharedParams]);

  useEffect(() => {
    if (entries.length === 0) {
      setItems([]);
      setTotals({});
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    const fetchAll = async () => {
      const results = await Promise.allSettled(
        entries.map(async (entry) => {
          const config = entry.config;
          if (!config) throw new Error('Missing config');
          const mergedParams = { ...sharedParams, ...entry.params };

          const [listRes, countRes] = await Promise.all([
            config.apiClient.list(mergedParams),
            config.apiClient.count(mergedParams),
          ]);

          const rows: MultiResourceRow[] = listRes.data.map((item: FullResource<unknown>) => ({
            ...item,
            _source: config.name,
          }));

          return { name: config.name, rows, count: countRes.data as number };
        }),
      );

      if (cancelled) return;

      const allRows: MultiResourceRow[] = [];
      const newTotals: Record<string, number> = {};
      let firstError: Error | null = null;

      for (const r of results) {
        if (r.status === 'fulfilled') {
          allRows.push(...r.value.rows);
          newTotals[r.value.name] = r.value.count;
        } else {
          if (!firstError)
            firstError = r.reason instanceof Error ? r.reason : new Error(String(r.reason));
          console.error('useMultiResourceList fetch error:', r.reason);
        }
      }

      // Sort by updated_time descending (newest first)
      allRows.sort((a, b) => {
        const ta = a.meta?.updated_time ?? '';
        const tb = b.meta?.updated_time ?? '';
        return tb.localeCompare(ta);
      });

      setItems(allRows);
      setTotals(newTotals);
      setError(firstError);
      setLoading(false);
    };

    fetchAll();

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entriesKey, sharedParamsKey, refreshCount]);

  const totalCount = useMemo(() => Object.values(totals).reduce((sum, n) => sum + n, 0), [totals]);

  return { items, totals, totalCount, loading, error, refresh };
}
