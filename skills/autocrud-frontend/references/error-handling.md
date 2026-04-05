# Error Handling & Debugging

Error handling patterns used across the AutoCRUD frontend app. All utilities are in `app/src/autocrud/lib/utils/errorNotification.ts`.

## Table of Contents

- [Error Utility Functions](#error-utility-functions)
- [Mutation Hook Error Pattern](#mutation-hook-error-pattern)
- [Component-Level Error Handling](#component-level-error-handling)
- [Axios Response Interceptor](#axios-response-interceptor)
- [Testing Error Handling](#testing-error-handling)

---

## Error Utility Functions

### `extractErrorMessage(error: unknown): string`

Parses Axios error responses into human-readable messages. Handles two FastAPI formats:

**Format 1 — HTTPException** (string detail):
```json
{ "detail": "Resource not found" }
```
→ Returns: `"Resource not found"`

**Format 2 — ValidationError** (array detail):
```json
{
  "detail": [
    { "loc": ["body", "name"], "msg": "field required", "type": "missing" },
    { "loc": ["body", "age"], "msg": "must be positive", "type": "value_error" }
  ]
}
```
→ Returns (multi-line):
```
name: field required
age: must be positive
```

**Fallback chain**: `detail string` → `detail array` → `status code message` → `error.message` → `"An unexpected error occurred"`

The `"body"` prefix is automatically filtered from field paths. Nested paths use ` → ` separator (e.g., `address → city: field required`).

### `extractUniqueConflict(error: unknown): UniqueConflictInfo | null`

Detects 409 Unique Constraint errors from AutoCRUD backend.

**Expected 409 body**:
```json
{
  "detail": {
    "message": "Username already taken",
    "field": "username",
    "conflicting_resource_id": "user-123"
  }
}
```

**Returns** `UniqueConflictInfo`:
```typescript
{
  field: string;                     // "username"
  message: string;                   // "Username already taken"
  conflictingResourceId?: string;    // "user-123" (optional)
}
```

Returns `null` if: not a 409, detail is a string, or no `field` property.

### `showErrorNotification(error: unknown, title?: string)`

Display an error notification using Mantine's notification system.

```typescript
notifications.show({
  title: title || 'Operation Failed',
  message: extractErrorMessage(error),
  color: 'red',
  autoClose: 8000,          // 8 seconds
  withCloseButton: true,
  style: { whiteSpace: 'pre-line' },  // Preserve multi-line formatting
});
```

---

## Mutation Hook Error Pattern

All mutation hooks (`useCreateResource`, `useUpdateResource`, `useDeleteResource`, `useRestoreResource`, `useSwitchRevision`, `useRerunResource`) use a dual-track error pattern:

### Options Interface

```typescript
interface ResourceMutationOptions<TData, TVariables> {
  onSuccess?: (data: TData, variables: TVariables) => void | Promise<void>;
  onError?: (error: Error, variables: TVariables) => void | Promise<void>;
  onSettled?: (data, error, variables) => void | Promise<void>;
  showErrorNotification?: boolean;    // default: true — auto-shows toast
  invalidateOnSuccess?: boolean;       // default: true — auto-invalidates cache
}
```

### Dual Calling Patterns

```typescript
const { create, createAsync, isPending, error } = useCreateResource(config, {
  showErrorNotification: true,  // default
  onError: (err) => { /* custom error handling */ },
});

// Pattern 1: Fire-and-forget — errors shown as notification only
create({ name: 'Hero' });

// Pattern 2: Awaitable — throws on error for try/catch handling
try {
  const result = await createAsync({ name: 'Hero' });
  navigate(`/admin/character/${result.resource_id}`);
} catch (err) {
  // Error notification already shown (if enabled)
  // Additional custom handling here
}
```

### Error Flow

```
API call fails
  ↓
useMutation.onError fires
  ├── showErrorNotification enabled? → showErrorNotification(error, 'Create Failed')
  └── options.onError provided? → call options.onError(error, variables)
  ↓
If called via createAsync() → re-throws error to caller's try/catch
If called via create() → error stored in mutation.error state
```

---

## Component-Level Error Handling

### ResourceCreate — Unique Constraint Handling

```typescript
const { createAsync } = useCreateResource(config, {
  onError: (error) => {
    const conflict = extractUniqueConflict(error);
    if (conflict && formRef.current) {
      // Set field-level error instead of generic toast
      formRef.current.setFieldError(
        conflict.field,
        `此值已被使用 (unique constraint)`
      );
    }
  },
});

const handleSubmit = async (values) => {
  try {
    const result = await createAsync(values);
    navigate({ to: `${basePath}/${result.resource_id}` });
  } catch {
    // Error already handled in onError callback
  }
};
```

### ResourceDetail — Custom Action Error Handling

For custom update actions (non-standard mutations), error handling is explicit:

```typescript
const handleUpdateAction = async (action, values) => {
  setSubmitting(true);
  try {
    await action.apiMethod(resourceId, values);
    setActiveAction(null);
    setEditOpen(false);

    if (action.asyncMode === 'background') {
      notifications.show({
        title: action.label,
        message: '已提交背景任務',
        color: 'blue',
      });
    }
    refresh();
  } catch (error) {
    showErrorNotification(error, `${action.label} Failed`);
  } finally {
    setSubmitting(false);
  }
};
```

---

## Axios Response Interceptor

**File**: `lib/client.ts`

Global interceptor logs all API errors to console:

```typescript
client.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error('[API Error]', error.response?.status, error.response?.data);
    return Promise.reject(error);
  },
);
```

This ensures every API error is logged at `[API Error]` prefix regardless of whether the calling code handles the error. Useful for debugging in browser DevTools.

**Note**: There are no error boundary components in the app. Errors bubble from hooks to the nearest try/catch or become `mutation.error` state. The notification system serves as the primary user-facing error feedback.

---

## Testing Error Handling

To test error notification behavior, mock `@mantine/notifications`:

```typescript
const mockShow = vi.hoisted(() => vi.fn());
vi.mock('@mantine/notifications', () => ({
  notifications: { show: mockShow },
}));

it('shows error notification for validation error', () => {
  const error = {
    response: {
      status: 422,
      data: {
        detail: [
          { loc: ['body', 'name'], msg: 'field required', type: 'missing' },
        ],
      },
    },
  };

  showErrorNotification(error, 'Create Failed');

  expect(mockShow).toHaveBeenCalledWith(
    expect.objectContaining({
      title: 'Create Failed',
      message: 'name: field required',
      color: 'red',
    }),
  );
});
```
