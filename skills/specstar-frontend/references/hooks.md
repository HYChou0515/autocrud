# Hooks Reference

Complete inventory of all hooks exported from `app/src/specstar/lib/hooks/`. All hooks are re-exported from `hooks/index.ts`.

## Table of Contents

- [Query Hooks](#query-hooks)
- [Mutation Hooks](#mutation-hooks)
- [Utility Hooks](#utility-hooks)
- [Query Key Factory](#query-key-factory)
- [Primitive Fetchers](#primitive-fetchers)
- [Shared Types](#shared-types)

---

## Query Hooks

### `useResourceList`

**File**: `hooks/useResourceList.ts`

Paginated resource list with server-side search, sorting, and filtering.

```typescript
function useResourceList<T>(
  config: ResourceConfig<T>,
  params?: UseResourceListParams,
  options?: UseResourceListOptions<T>,
): UseResourceListResult<T>;
```

**Parameters**:

| Name | Type | Description |
|------|------|-------------|
| `config` | `ResourceConfig<T>` | Resource configuration from registry |
| `params.limit` | `number` | Page size |
| `params.offset` | `number` | Pagination offset |
| `params.sorts` | `string` | Sort expression (e.g. `'name:asc'`) |
| `params.search` | `string` | Free-text search query |
| `params.*` | `Record<string, unknown>` | Additional custom query parameters |
| `options.staleTime` | `number` | TanStack Query stale time |
| `options.gcTime` | `number` | Garbage collection time |
| `options.refetchInterval` | `number` | Auto-refetch interval (ms) |

**Returns**: `UseResourceListResult<T>`

| Property | Type | Description |
|----------|------|-------------|
| `data` | `FullResource<T>[]` | Array of resources |
| `total` | `number` | Total count from server |
| `loading` | `boolean` | Whether fetching |
| `error` | `Error \| null` | Last fetch error |
| `refresh` | `() => void` | Manually invalidate list cache |
| `query` | `UseQueryResult` | Raw TanStack Query result (advanced) |

**Query Key**: `resourceKeys.list(resourceName, params)`

---

### `useResourceDetail`

**File**: `hooks/useResourceDetail.ts`

Single resource detail with integrated mutation methods (update, delete, restore, switch revision, rerun, logs).

```typescript
function useResourceDetail<T>(
  config: ResourceConfig<T>,
  resourceId: string,
  revisionIdOrOptions?: string | null | UseResourceDetailOptions<T>,
  maybeOptions?: UseResourceDetailOptions<T>,
): UseResourceDetailResult<T>;
```

**Parameters**:

| Name | Type | Description |
|------|------|-------------|
| `config` | `ResourceConfig<T>` | Resource configuration |
| `resourceId` | `string` | Resource ID |
| `revisionIdOrOptions` | `string \| null \| Options` | Revision ID (backward compat) or options object |
| `maybeOptions` | `Options` | Options when 3rd arg is revision ID |

**Options** (`UseResourceDetailOptions<T>`):

| Property | Type | Description |
|----------|------|-------------|
| `revisionId` | `string \| null` | Fetch specific revision |
| `queryOptions` | `UseQueryOptions` | TanStack Query overrides |

**Returns**: `UseResourceDetailResult<T>`

| Property | Type | Description |
|----------|------|-------------|
| `resource` | `FullResource<T> \| null` | The fetched resource |
| `loading` | `boolean` | Whether fetching detail |
| `error` | `Error \| null` | Fetch error |
| `refresh` | `() => void` | Invalidate detail + revision caches |
| `update` | `(data: T) => Promise<void>` | Update mutation (re-throws) |
| `deleteResource` | `() => Promise<void>` | Soft delete mutation |
| `permanentlyDelete` | `() => Promise<void>` | Permanent delete mutation |
| `restore` | `() => Promise<void>` | Restore soft-deleted resource |
| `switchRevision` | `(revisionId: string) => Promise<void>` | Switch active revision |
| `rerun` | `() => Promise<void>` | Rerun job resource |
| `logs` | `string \| null \| undefined` | Job logs (`null`=not loaded, `undefined`=204) |
| `logsLoading` | `boolean` | Whether logs are fetching |
| `fetchLogs` | `() => void` | Trigger logs fetch on demand |
| `isUpdatePending` | `boolean` | Update mutation in flight |
| `isDeletePending` | `boolean` | Delete mutation in flight |
| `isRestorePending` | `boolean` | Restore mutation in flight |
| `isSwitchRevisionPending` | `boolean` | Switch revision in flight |
| `isRerunPending` | `boolean` | Rerun mutation in flight |
| `query` | `UseQueryResult` | Raw detail query |

**Query Keys**:
- Detail: `resourceKeys.detail(name, id)` or `resourceKeys.detail(name, id, revisionId)`
- Logs: `resourceKeys.logs(name, id)`

---

### `useMultiResourceList`

**File**: `hooks/useMultiResourceList.ts`

Aggregated paginated list from multiple resources, fetched in parallel.

```typescript
function useMultiResourceList(
  entries: MultiResourceEntry[],
  sharedParams?: UseResourceListParams,
  options?: UseMultiResourceListOptions,
): UseMultiResourceListResult;
```

**Parameters**:

| Name | Type | Description |
|------|------|-------------|
| `entries` | `MultiResourceEntry[]` | Array of `{ config, params? }` |
| `sharedParams` | `UseResourceListParams` | Applied to all resources |
| `options` | `UseMultiResourceListOptions` | TanStack Query overrides |

**Returns**: `UseMultiResourceListResult`

| Property | Type | Description |
|----------|------|-------------|
| `items` | `MultiResourceRow[]` | Flat list with `_source: string` tag |
| `totals` | `Record<string, number>` | Per-resource count |
| `totalCount` | `number` | Sum of all counts |
| `loading` | `boolean` | Any resource loading |
| `error` | `Error \| null` | First error encountered |
| `refresh` | `() => void` | Invalidate all resource lists |
| `queries` | `UseQueryResult[]` | Raw per-entry query results |

**Behavior**: Rows sorted by `updated_time` descending (newest first). Each row tagged with `_source` resource name.

---

## Mutation Hooks

All mutation hooks follow a consistent pattern:
- Accept `config: ResourceConfig` + resource-specific params
- Accept `options?: { onSuccess?, onError?, onSettled?, showErrorNotification?, invalidateOnSuccess? }`
- Return `{ actionName, actionNameAsync, isPending, error, reset }`
- Fire-and-forget via `actionName()`, awaitable (throws) via `actionNameAsync()`
- Auto-show error notification (default: `true`)
- Auto-invalidate caches on success (default: `true`)

### `useCreateResource`

**File**: `hooks/useCreateResource.ts`

```typescript
function useCreateResource<T>(
  config: ResourceConfig<T>,
  options?: UseCreateResourceOptions<T>,
): UseCreateResourceResult<T>;
```

| Return Property | Type | Description |
|----------------|------|-------------|
| `create` | `(data: T) => void` | Fire-and-forget create |
| `createAsync` | `(data: T) => Promise<RevisionInfo>` | Awaitable (throws) |
| `isPending` | `boolean` | Mutation in flight |
| `error` | `Error \| null` | Last error |
| `reset` | `() => void` | Clear error/state |

**Invalidates**: `resourceKeys.lists(name)` on success.

### `useUpdateResource`

**File**: `hooks/useUpdateResource.ts`

```typescript
function useUpdateResource<T>(
  config: ResourceConfig<T>,
  resourceId: string,
  options?: UseUpdateResourceOptions<T>,
): UseUpdateResourceResult<T>;
```

| Return Property | Type | Description |
|----------------|------|-------------|
| `update` | `(data: T) => void` | Fire-and-forget update |
| `updateAsync` | `(data: T) => Promise<RevisionInfo>` | Awaitable (throws) |
| `isPending` | `boolean` | Mutation in flight |
| `error` | `Error \| null` | Last error |
| `reset` | `() => void` | Clear state |

**Invalidates**: `resourceKeys.details(name)` + `resourceKeys.lists(name)` on success.

### `useDeleteResource`

**File**: `hooks/useDeleteResource.ts`

```typescript
function useDeleteResource<T>(
  config: ResourceConfig<T>,
  resourceId: string,
  options?: UseDeleteResourceOptions,
): UseDeleteResourceResult;
```

| Return Property | Type | Description |
|----------------|------|-------------|
| `deleteResource` | `() => void` | Soft delete (fire-and-forget) |
| `deleteResourceAsync` | `() => Promise<ResourceMeta>` | Awaitable soft delete |
| `permanentlyDelete` | `() => void` | Permanent delete (fire-and-forget) |
| `permanentlyDeleteAsync` | `() => Promise<void>` | Awaitable permanent delete |
| `isDeletePending` | `boolean` | Soft delete in flight |
| `isPermanentDeletePending` | `boolean` | Permanent delete in flight |
| `isPending` | `boolean` | Either operation in flight |
| `error` | `Error \| null` | Last error from either |
| `reset` | `() => void` | Clear both states |

**Invalidates**:
- Soft delete: `details` + `lists`
- Permanent delete: **Removes** detail query (no 404) + invalidates `lists`

### `useRestoreResource`

**File**: `hooks/useRestoreResource.ts`

```typescript
function useRestoreResource<T>(
  config: ResourceConfig<T>,
  resourceId: string,
  options?: UseRestoreResourceOptions,
): UseRestoreResourceResult;
```

| Return Property | Type | Description |
|----------------|------|-------------|
| `restore` | `() => void` | Fire-and-forget restore |
| `restoreAsync` | `() => Promise<ResourceMeta>` | Awaitable (throws) |
| `isPending` | `boolean` | In flight |
| `error` | `Error \| null` | Last error |
| `reset` | `() => void` | Clear state |

**Invalidates**: `resourceKeys.details(name)` + `resourceKeys.lists(name)`.

### `useSwitchRevision`

**File**: `hooks/useSwitchRevision.ts`

```typescript
function useSwitchRevision<T>(
  config: ResourceConfig<T>,
  resourceId: string,
  options?: UseSwitchRevisionOptions,
): UseSwitchRevisionResult;
```

| Return Property | Type | Description |
|----------------|------|-------------|
| `switchRevision` | `(revisionId: string) => void` | Fire-and-forget |
| `switchRevisionAsync` | `(revisionId: string) => Promise<ResourceMeta>` | Awaitable |
| `isPending` | `boolean` | In flight |
| `error` | `Error \| null` | Last error |
| `reset` | `() => void` | Clear state |

**Invalidates**: `resourceKeys.details(name)` + `resourceKeys.lists(name)` + `resourceKeys.revisions(name, id)`.

### `useRerunResource`

**File**: `hooks/useRerunResource.ts`

```typescript
function useRerunResource<T>(
  config: ResourceConfig<T>,
  resourceId: string,
  options?: UseRerunResourceOptions,
): UseRerunResourceResult;
```

| Return Property | Type | Description |
|----------------|------|-------------|
| `rerun` | `() => void` | Fire-and-forget rerun |
| `rerunAsync` | `() => Promise<RevisionInfo>` | Awaitable |
| `isPending` | `boolean` | In flight |
| `error` | `Error \| null` | Last error |
| `reset` | `() => void` | Clear state |

**Invalidates**: `resourceKeys.details(name)` + `resourceKeys.lists(name)`.

Throws immediately if `config.apiClient.rerun` is not available (non-job resources).

### `useBlobUpload`

**File**: `hooks/useBlobUpload.ts`

Chunked file upload with progress tracking and cancellation support.

```typescript
function useBlobUpload(options?: {
  chunkSize?: number;        // Default: 1 MB
  chunkThreshold?: number;   // Default: 10 MB
  concurrency?: number;      // Default: 4
}): UseBlobUploadReturn;
```

| Return Property | Type | Description |
|----------------|------|-------------|
| `upload` | `(file: File) => Promise<BlobUploadResult \| null>` | Start upload (null on error/cancel) |
| `cancel` | `() => void` | Cancel current upload |
| `status` | `BlobUploadStatus` | `'idle' \| 'uploading' \| 'finalizing' \| 'done' \| 'error' \| 'cancelled'` |
| `progress` | `BlobUploadProgress` | `{ loaded, total, percent, elapsed, eta }` |
| `error` | `string \| null` | Error message |
| `reset` | `() => void` | Reset to idle |

**Behavior**:
- **Small files** (≤ threshold): Single `POST /blobs/upload`
- **Large files** (> threshold): Chunked — session create → parallel chunk uploads → finalize
- Tracks elapsed time, ETA, and percent complete
- Cancellable via `cancel()`

**Standalone function**: `uploadFileToBlob(file, options)` — non-hook version for use outside React components.

---

## Utility Hooks

### `useAdvancedSearch`

**File**: `hooks/useAdvancedSearch.ts`

Manages advanced search UI state with bidirectional MRT table sync and URL persistence.

```typescript
function useAdvancedSearch(options: UseAdvancedSearchOptions): UseAdvancedSearchReturn;
```

**Options**:

| Property | Type | Description |
|----------|------|-------------|
| `config` | `ResourceConfig` | Resource configuration |
| `searchableFields?` | `SearchableField[]` | Custom searchable fields (auto-generated if omitted) |
| `disableQB?` | `boolean` | Disable Query Builder mode |
| `onSearchChange` | `(search: ActiveSearchState) => void` | Callback when search submitted |
| `mrtColumnFilters?` | `MRT_ColumnFiltersState` | Mantine React Table column filters |
| `mrtSorting?` | `MRT_SortingState` | Mantine React Table sorting |
| `onMrtSortingChange?` | `(sorting: MRT_SortingState) => void` | Sync sorting to MRT |

**Returns** (key properties):

| Property | Type | Description |
|----------|------|-------------|
| `searchMode` | `'condition' \| 'qb'` | Current search mode |
| `advancedOpen` | `boolean` | Whether panel is open |
| `setAdvancedOpen` | `Dispatch<boolean>` | Toggle panel |
| `activeSearch` | `ActiveSearchState` | Current submitted search (synced to URL) |
| `editingState` | `EditingState` | Current editing state (not yet submitted) |
| `handleConditionSearch` | `() => void` | Submit condition mode search |
| `handleConditionClear` | `() => void` | Clear condition mode |
| `handleQBSubmit` | `() => void` | Submit QB mode search |
| `handleQBClear` | `() => void` | Clear QB mode |
| `normalizedSearchableFields` | `NormalizedSearchableField[]` | Searchable fields with labels |
| `sortFieldOptions` | `{ value; label }[]` | Available sort-by fields |
| `activeBackendCount` | `number` | Active search conditions count |
| `filterDepth` / `setFilterDepth` | `number` / `(n) => void` | Nested field depth control |
| `maxFilterDepth` | `number` | Max available depth |

**Exported Helpers**:
- `mrtFiltersToConditions()` — Convert MRT column filters to search conditions
- `mrtSortingToSortBy()` — Convert MRT sorting to sort string
- `sortByToMrtSorting()` — Convert sort string to MRT sorting
- `normalizeSearchableFields()` — Normalize searchable field definitions
- `buildSortFieldOptions()` — Build sort field dropdown options

### `useFieldDepth`

**File**: `hooks/useFieldDepth.ts`

Computes visible/collapsed fields based on nesting depth.

```typescript
function useFieldDepth(options: UseFieldDepthOptions): UseFieldDepthReturn;
```

**Options**:

| Property | Type | Description |
|----------|------|-------------|
| `fields` | `ResourceField[]` | All available fields |
| `maxFormDepth?` | `number` | Override initial depth (default: maxAvailableDepth) |
| `stripItemFields?` | `boolean` | Detail mode: keep array fields visible but strip itemFields. Form mode (default): collapse to JSON |

**Returns**:

| Property | Type | Description |
|----------|------|-------------|
| `maxAvailableDepth` | `number` | Max nesting depth in field tree |
| `depth` | `number` | Current depth level |
| `setDepth` | `(n: number) => void` | Update depth |
| `visibleFields` | `ResourceField[]` | Fields visible at current depth |
| `collapsedGroups` | `{ path, label }[]` | Fields collapsed into JSON editors |

---

## Query Key Factory

**File**: `hooks/queryKeys.ts`

Standardized TanStack Query keys for consistent cache management.

```typescript
const resourceKeys = {
  all:       (name: string) => ['resource', name],
  lists:     (name: string) => ['resource', name, 'list'],
  list:      (name: string, params?: Record<string, unknown>) =>
               ['resource', name, 'list', params],
  details:   (name: string) => ['resource', name, 'detail'],
  detail:    (name: string, id: string, revisionId?: string | null) =>
               ['resource', name, 'detail', id, ...(revisionId ? [revisionId] : [])],
  revisions: (name: string, id: string) => ['resource', name, 'revisions', id],
  logs:      (name: string, id: string) => ['resource', name, 'logs', id],
};
```

**Usage for cache invalidation**:

```typescript
import { useQueryClient } from '@tanstack/react-query';
import { resourceKeys } from '@/specstar/lib/hooks';

const queryClient = useQueryClient();

// Invalidate all lists for a resource
queryClient.invalidateQueries({ queryKey: resourceKeys.lists('character') });

// Remove a specific detail (e.g., after permanent delete)
queryClient.removeQueries({ queryKey: resourceKeys.detail('character', id) });

// Invalidate everything for a resource
queryClient.invalidateQueries({ queryKey: resourceKeys.all('character') });
```

---

## Primitive Fetchers

**File**: `hooks/primitives.ts`

Non-hook async functions for use outside React components (loaders, scripts, etc.).

```typescript
// Fetch paginated list + total count (parallel)
async function fetchResourceList<T>(
  config: ResourceConfig<T>,
  params?: UseResourceListParams,
): Promise<{ data: FullResource<T>[]; total: number }>;

// Fetch single resource detail
async function fetchResourceDetail<T>(
  config: ResourceConfig<T>,
  id: string,
  revisionId?: string | null,
): Promise<FullResource<T>>;

// Fetch revision history
async function fetchResourceRevisions<T>(
  config: ResourceConfig<T>,
  id: string,
  params?: RevisionListParams,
): Promise<RevisionListResponse>;

// Fetch job logs (returns undefined if not supported or 204)
async function fetchResourceLogs<T>(
  config: ResourceConfig<T>,
  id: string,
): Promise<string | undefined>;
```

---

## Shared Types

**File**: `hooks/types.ts`

```typescript
/** Base mutation options shared by all mutation hooks */
interface ResourceMutationOptions<TData, TVariables> {
  onSuccess?: (data: TData, variables: TVariables) => void | Promise<void>;
  onError?: (error: Error, variables: TVariables) => void | Promise<void>;
  onSettled?: (data: TData | undefined, error: Error | null, variables: TVariables)
    => void | Promise<void>;
  showErrorNotification?: boolean;    // default: true
  invalidateOnSuccess?: boolean;       // default: true
}
```
