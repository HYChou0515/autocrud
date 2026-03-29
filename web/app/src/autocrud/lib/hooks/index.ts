/**
 * AutoCRUD Hooks — barrel export for all hooks, query keys, primitives, and types.
 *
 * @example
 * ```ts
 * import {
 *   useResourceList,
 *   useCreateResource,
 *   resourceKeys,
 *   fetchResourceDetail,
 * } from '@/autocrud/lib/hooks';
 * ```
 */

// Query key factory
export { resourceKeys } from './queryKeys';

// Primitive (non-hook) fetcher functions
export {
  fetchResourceList,
  fetchResourceDetail,
  fetchResourceRevisions,
  fetchResourceLogs,
} from './primitives';

// Shared types
export type { ResourceMutationOptions } from './types';

// Query hooks
export { useResourceList } from './useResourceList';
export type {
  UseResourceListParams,
  UseResourceListOptions,
  UseResourceListResult,
} from './useResourceList';

export { useResourceDetail } from './useResourceDetail';
export type { UseResourceDetailOptions, UseResourceDetailResult } from './useResourceDetail';

export { useMultiResourceList } from './useMultiResourceList';
export type {
  MultiResourceEntry,
  MultiResourceRow,
  UseMultiResourceListOptions,
  UseMultiResourceListResult,
} from './useMultiResourceList';

export { useAdvancedSearch } from './useAdvancedSearch';
export { useFieldDepth } from './useFieldDepth';

// Mutation hooks
export { useCreateResource } from './useCreateResource';
export type { UseCreateResourceOptions, UseCreateResourceResult } from './useCreateResource';

export { useUpdateResource } from './useUpdateResource';
export type { UseUpdateResourceOptions, UseUpdateResourceResult } from './useUpdateResource';

export { useDeleteResource } from './useDeleteResource';
export type { UseDeleteResourceOptions, UseDeleteResourceResult } from './useDeleteResource';

export { useRestoreResource } from './useRestoreResource';
export type { UseRestoreResourceOptions, UseRestoreResourceResult } from './useRestoreResource';

export { useSwitchRevision } from './useSwitchRevision';
export type { UseSwitchRevisionOptions, UseSwitchRevisionResult } from './useSwitchRevision';

export { useRerunResource } from './useRerunResource';
export type { UseRerunResourceOptions, UseRerunResourceResult } from './useRerunResource';

// Blob upload hook
export { useBlobUpload } from './useBlobUpload';
export type {
  BlobUploadStatus,
  BlobUploadProgress,
  BlobUploadResult,
  UseBlobUploadReturn,
} from './useBlobUpload';
