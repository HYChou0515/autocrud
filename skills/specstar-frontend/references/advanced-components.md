# Advanced Component Development

Guide for extending and customizing the SpecStar frontend component system.

## Table of Contents

- [Three-Layer Rendering Architecture](#three-layer-rendering-architecture)
- [resolveFieldKind Dispatch](#resolvefieldkind-dispatch)
- [Adding a New FieldKind](#adding-a-new-fieldkind)
- [Customizing Existing Renderers](#customizing-existing-renderers)
- [Deferred Blob Upload Pattern](#deferred-blob-upload-pattern)
- [Lazy Table Mode Upgrade](#lazy-table-mode-upgrade)
- [Field Depth Control](#field-depth-control)

---

## Three-Layer Rendering Architecture

Every field in SpecStar is rendered through one of three context-specific layers:

```
ResourceField
  ↓ resolveFieldKind(field) → FieldKind
  ↓
  ├── Table cell    → CellFieldRenderer   → CELL_RENDERERS[kind]
  ├── Detail page   → DetailFieldRenderer  → DETAIL_RENDERERS[kind]
  └── Form input    → FormFieldRenderer    → FIELD_RENDERERS[kind]
```

Each layer maintains its own **renderer registry** — a `Record<FieldKind, ReactComponent>` map that dispatches to the appropriate component. TypeScript exhaustiveness checking ensures every `FieldKind` has an entry in every registry.

### Layer Responsibilities

| Layer | Registry | Input | Output |
|-------|----------|-------|--------|
| **Cell** | `CELL_RENDERERS` | `{ value, field }` | Compact single-line display |
| **Detail** | `DETAIL_RENDERERS` | `{ value, field }` | Full-width read-only display |
| **Form** | `FIELD_RENDERERS` | `{ field, form, path }` | Interactive input with Mantine form binding |

### Registry Pattern

```typescript
// CellFieldRenderer/index.tsx
const CELL_RENDERERS: Record<FieldKind, React.FC<CellRenderProps>> = {
  hidden: () => null,
  text: TextCell,
  number: NumberCell,
  // ... every FieldKind has an entry
};

export function CellFieldRenderer({ field, value }: Props) {
  const kind = resolveFieldKind(field);
  const Renderer = CELL_RENDERERS[kind];
  return <Renderer value={value} field={field} />;
}
```

---

## resolveFieldKind Dispatch

**File**: `components/field/resolveFieldKind.ts`

Pure function that maps `ResourceField` → `FieldKind`. The resolution priority is strict and order-dependent:

```
1. hidden        ← field.constValue !== undefined (discriminator)
2. itemFields    ← field.itemFields.length > 0 (array of typed objects)
3. union         ← field.type === 'union' && field.unionMeta
4. binary        ← field.type === 'binary'
5. file          ← variant.type === 'file'
6. json          ← variant.type === 'json'
7. markdown      ← variant.type === 'markdown'
8. arrayString   ← field.type === 'array' && no itemFields
9. tags          ← variant.type === 'tags'
10. select       ← variant.type === 'select' || field has enum options
11. checkbox     ← variant.type === 'checkbox'
12. switch       ← variant.type === 'switch' || field.type === 'boolean'
13. date         ← variant.type === 'date'
14. numberSlider ← variant.type === 'slider'
15. number       ← variant.type === 'number' || field.type is numeric
16. textarea     ← variant.type === 'textarea'
17. refResourceId      ← field.ref.type === 'resource_id' (single)
18. refResourceIdMulti ← field.ref.type === 'resource_id' (array)
19. refRevisionId      ← field.ref.type === 'revision_id' (single)
20. refRevisionIdMulti ← field.ref.type === 'revision_id' (array)
21. text         ← fallback default
```

When no explicit `variant` is set on a field, `getDefaultVariant(field)` provides sensible defaults (e.g., boolean → switch, number → number, binary → file).

---

## Adding a New FieldKind

To add a completely new field rendering type:

### Step 1: Add to FieldKind Enum

```typescript
// resolveFieldKind.ts
export type FieldKind =
  | 'hidden'
  | 'itemFields'
  // ... existing kinds
  | 'myNewKind'    // ← add here
  | 'text';
```

### Step 2: Add Resolution Logic

```typescript
// resolveFieldKind.ts — in resolveFieldKind()
// Add BEFORE the text fallback, in the correct priority position
if (effectiveVariant.type === 'myNewType') {
  return 'myNewKind';
}
```

### Step 3: Implement Renderers for All Three Layers

```typescript
// CellFieldRenderer/ — compact display
function MyNewKindCell({ value, field }: CellRenderProps) {
  return <span>{/* compact rendering */}</span>;
}

// DetailFieldRenderer/ — full display
function MyNewKindDetail({ value, field }: DetailRenderProps) {
  return <div>{/* full read-only rendering */}</div>;
}

// FormFieldRenderer/ — editable input
function MyNewKindInput({ field, form, path }: FormRenderProps) {
  return <TextInput {...form.getInputProps(path)} />;
}
```

### Step 4: Register in All Three Registries

```typescript
// CellFieldRenderer/index.tsx
const CELL_RENDERERS: Record<FieldKind, ...> = {
  // ...
  myNewKind: MyNewKindCell,
};

// DetailFieldRenderer/index.tsx
const DETAIL_RENDERERS: Record<FieldKind, ...> = {
  // ...
  myNewKind: MyNewKindDetail,
};

// FormFieldRenderer/index.tsx
const FIELD_RENDERERS: Record<FieldKind, ...> = {
  // ...
  myNewKind: MyNewKindInput,
};
```

TypeScript will enforce that all registries are updated — if you miss one, you'll get a compile error.

### Step 5: (Optional) Add FieldVariant Type

If the new kind needs configuration options:

```typescript
// In the FieldVariant type definition
type FieldVariant =
  | { type: 'text' }
  | { type: 'myNewType'; customOption?: string; height?: number }
  // ...
```

---

## Customizing Existing Renderers

### Override a Single Kind's Rendering

To change how a specific `FieldKind` renders without creating a new kind, modify the corresponding renderer component directly:

```typescript
// Example: Customize how 'tags' renders in table cells
// CellFieldRenderer/TagsCell.tsx
function TagsCell({ value, field }: CellRenderProps) {
  const tags = Array.isArray(value) ? value : [];
  return (
    <Group gap={4}>
      {tags.slice(0, 3).map((tag) => (
        <Badge key={tag} size="xs" variant="light">
          {tag}
        </Badge>
      ))}
      {tags.length > 3 && <Text size="xs">+{tags.length - 3}</Text>}
    </Group>
  );
}
```

### Use resourceCustomization for Config-Level Changes

For changes that don't require component modification, use `resourceCustomization.ts`:

```typescript
export const customizations: ResourceCustomizations = {
  'character': {
    fields: {
      'bio': { variant: { type: 'markdown', height: 500 } },  // Override default
    },
  },
};
```

---

## Deferred Blob Upload Pattern

Binary fields use a deferred upload strategy for better UX:

```
1. User selects file in form
   ↓
2. File stored in form state (not uploaded yet)
   ↓
3. User clicks submit
   ↓
4. ResourceForm.handleSubmit():
   a. Upload all pending binary files via useBlobUpload
   b. Replace File objects with blob IDs in form data
   c. Send final form data to create/update API
```

**Implementation in ResourceForm**:

```typescript
const handleSubmit = async (values: Record<string, unknown>) => {
  // 1. Find all binary fields with File values
  const binaryFields = findBinaryFieldsWithFiles(values, config.fields);

  // 2. Upload each file, get blob IDs
  for (const { path, file } of binaryFields) {
    const result = await upload(file);
    if (!result) return; // Upload failed or cancelled
    setNestedValue(values, path, result.file_id);
  }

  // 3. Submit with blob IDs instead of File objects
  await onSubmit(values);
};
```

This pattern ensures:
- No orphaned blob uploads (file only uploaded when form is actually submitted)
- Progress tracking during submit
- Cancellation support

---

## Lazy Table Mode Upgrade

`ResourceTable` defaults to server-side pagination but can auto-upgrade to client mode:

```
Server Mode (default)
  ↓ All data fits on one page? or MRT needs client-side operation?
  ↓
Client Mode (auto-upgrade)
  - Fetches all rows at once
  - MRT handles sort/filter/paginate locally
```

This allows features like client-side column filtering to "just work" without manual configuration. The upgrade is transparent to the user.

---

## Field Depth Control

Complex nested models can produce deeply nested forms that are hard to navigate. The `useFieldDepth` hook addresses this:

```
Depth 1: Only top-level fields visible
         (nested objects collapsed into JSON editors)

Depth 2: Top-level + one level of nesting
         (deeply nested still collapsed)

Depth N: All nesting levels visible
         (full structured form)
```

**Detail mode** (`stripItemFields: true`): Array-of-objects fields remain visible as a section header, but their `itemFields` are stripped when depth is insufficient — the array items render as JSON.

**Form mode** (`stripItemFields: false`, default): Array-of-objects fields collapse entirely into a JSON editor when depth is insufficient.

The depth slider appears in both `ResourceDetail` and `ResourceCreate`/`ResourceForm` when `maxAvailableDepth > 1`.
