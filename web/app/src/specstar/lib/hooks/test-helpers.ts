/**
 * Shared test helpers for mutation hook tests.
 *
 * Provides consistent mock setup and QueryClient wrapper for all mutation hooks.
 */

import React from 'react';
import { vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ResourceConfig } from '../resources';

/**
 * Create a minimal ResourceConfig with fully mocked apiClient.
 */
export function makeConfig(name = 'test', overrides: Partial<ResourceConfig> = {}): ResourceConfig {
  const noop = vi.fn().mockResolvedValue({ data: {} });
  return {
    name,
    label: name.charAt(0).toUpperCase() + name.slice(1),
    pluralLabel: name + 's',
    schema: name + 'Schema',
    fields: [],
    apiClient: {
      create: vi.fn().mockResolvedValue({
        data: { resource_id: 'new-1', revision_id: 'rev-1' },
      }),
      list: noop,
      count: noop,
      get: vi.fn().mockResolvedValue({
        data: { data: {}, meta: { resource_id: 'r1' }, revision_info: {} },
      }),
      update: vi.fn().mockResolvedValue({
        data: { resource_id: 'r1', revision_id: 'rev-2' },
      }),
      delete: vi.fn().mockResolvedValue({
        data: { resource_id: 'r1', is_deleted: true },
      }),
      permanentlyDelete: vi.fn().mockResolvedValue(undefined),
      restore: vi.fn().mockResolvedValue({
        data: { resource_id: 'r1', is_deleted: false },
      }),
      revisionList: noop,
      switchRevision: vi.fn().mockResolvedValue({
        data: { resource_id: 'r1', current_revision_id: 'rev-switched' },
      }),
      rerun: vi.fn().mockResolvedValue({
        data: { resource_id: 'r1', revision_id: 'rev-rerun' },
      }),
      getLogs: vi.fn().mockResolvedValue({ data: 'log output' }),
    },
    ...overrides,
  };
}

/**
 * Create a fresh QueryClient + React wrapper for hook tests.
 * Each test should call this to get isolated cache state.
 */
export function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  const Wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
  return { Wrapper, queryClient };
}
