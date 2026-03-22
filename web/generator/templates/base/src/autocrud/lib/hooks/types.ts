/**
 * Shared types for resource mutation hooks.
 *
 * All mutation hooks (useCreateResource, useUpdateResource, etc.) share
 * the same base options interface for consistency.
 */

/**
 * Base options for all resource mutation hooks.
 *
 * All options have sensible defaults so you can use the hooks with zero configuration.
 */
export interface ResourceMutationOptions<TData = unknown, TVariables = unknown> {
  /**
   * Callback fired after a successful mutation.
   * Receives the response data from the API.
   */
  onSuccess?: (data: TData, variables: TVariables) => void | Promise<void>;

  /**
   * Callback fired when the mutation encounters an error.
   * If `showErrorNotification` is also true, the notification fires first.
   */
  onError?: (error: Error, variables: TVariables) => void | Promise<void>;

  /**
   * Callback fired after either success or error.
   */
  onSettled?: (
    data: TData | undefined,
    error: Error | null,
    variables: TVariables,
  ) => void | Promise<void>;

  /**
   * Whether to automatically show an error notification on failure.
   * @default true
   */
  showErrorNotification?: boolean;

  /**
   * Whether to invalidate relevant query caches after a successful mutation.
   * The exact caches invalidated depend on the mutation type.
   * @default true
   */
  invalidateOnSuccess?: boolean;
}
