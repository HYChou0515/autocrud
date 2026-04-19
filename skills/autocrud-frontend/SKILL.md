---
name: autocrud-frontend
description: Build React admin interfaces with AutoCRUD Web — a code generator that creates production-ready CRUD UIs from AutoCRUD FastAPI backends. Use this skill whenever the user is working with autocrud-web-generator, customizing generated React apps, configuring resource fields or variants, using AutoCRUD hooks (useResourceList, useResourceDetail, useCreateResource), modifying field renderers, working with the resource registry, or building any React frontend that connects to an AutoCRUD API. Also use when the user mentions autocrud-web, resourceCustomization, getResource, FieldVariant, generator init/generate/integrate, or Mantine components in an AutoCRUD context.
---

# AutoCRUD Frontend

AutoCRUD Web is a **code generator** that parses OpenAPI specs from AutoCRUD backends and generates a complete, standalone React admin interface. The generated app uses React 19, Mantine 8, TanStack Router, and includes full CRUD pages, API clients, and type definitions.

## Quick Start

```bash
# 1. Start your AutoCRUD backend
uvicorn main:app --reload

# 2. Generate the frontend app
cd web
make gen-app          # Scaffolds app + installs deps + generates code

# 3. Run the dev server
make dev-app          # Starts Vite on default port
```

After backend schema changes:

```bash
make regen-app        # Re-generates types, API clients, and routes
```

## Generator CLI

The CLI tool (`autocrud-web`) has three commands:

### `init <project-name>` — Scaffold a new app

```bash
npx autocrud-web init my-admin --mantine 8 --include-tests
```

| Option | Default | Description |
|--------|---------|-------------|
| `--dir <directory>` | `.` | Target directory |
| `--mantine <7\|8>` | `7` | Mantine major version |
| `--include-tests` | `false` | Include test files |

### `generate` — Generate code from backend

```bash
npx autocrud-web generate --url http://localhost:8000
```

| Option | Default | Description |
|--------|---------|-------------|
| `--url <api-url>` | `http://localhost:8000` | Backend URL for OpenAPI spec |
| `--output <dir>` | `src` | Output directory |
| `--openapi-path <path>` | `/openapi.json` | OpenAPI endpoint path |
| `--base-path <path>` | auto-detected | API base path prefix |
| `--proxy-path <path>` | `/api` | Vite dev server proxy path |

### `integrate` — Add AutoCRUD to existing React project

```bash
npx autocrud-web integrate --url http://localhost:8000 --mantine 8 --force
```

Same options as `init` + `generate` combined, plus `--force` to overwrite without prompting.

## App Architecture

```
app/src/
├── autocrud/
│   ├── generated/              ← AUTO-GENERATED (overwritten on each generate)
│   │   ├── types.ts            ← OpenAPI → TypeScript interfaces
│   │   ├── resources.ts        ← Resource registry + Zod schemas
│   │   └── api/                ← Axios clients (one per resource)
│   ├── lib/                    ← Reusable components (safe to customize)
│   │   ├── client.ts           ← Axios instance + URL builders
│   │   ├── resources.ts        ← Resource registry logic + types
│   │   ├── resourceCustomization.ts  ← YOUR customization entry point
│   │   ├── components/         ← UI components (Table, Detail, Form, etc.)
│   │   ├── hooks/              ← React hooks for CRUD operations
│   │   ├── types/              ← Internal type definitions
│   │   └── utils/              ← Form utils, display helpers, etc.
│   └── types/
│       └── api.ts              ← API type definitions
├── routes/
│   ├── __root.tsx              ← Root layout
│   ├── index.tsx               ← Home page
│   ├── autocrud-admin.tsx      ← Admin layout
│   └── autocrud-admin/
│       ├── index.tsx           ← Dashboard
│       ├── backup.tsx          ← Backup/restore page
│       └── {resource}/         ← Per-resource CRUD pages
│           ├── index.tsx       ← List + search
│           ├── create.tsx      ← Create form
│           └── $resourceId.tsx ← Detail + edit + revisions
```

**Key rule**: Never edit files in `autocrud/generated/` — they are overwritten on each `generate`. Customize through `resourceCustomization.ts` and by editing components in `autocrud/lib/`.

## Resource Registry

All resources are accessed through a type-safe registry, not direct imports:

```typescript
import { getResource, getResourceNames } from '@/autocrud/lib/resources';

// Get a single resource config
const resource = getResource('character');
resource.name;           // 'character'
resource.label;          // 'Character'
resource.fields;         // ResourceField[]
resource.apiClient;      // { create, list, get, update, delete, ... }
resource.zodSchema;      // Zod validation schema

// Get all resource names
const names = getResourceNames();  // ['character', 'skill', 'guild', ...]
```

## Resource Customization

`resourceCustomization.ts` is the main entry point for customizing the generated app. The generator **never overwrites** this file.

```typescript
// src/autocrud/lib/resourceCustomization.ts
import type { ResourceCustomizations } from '../generated/resources';

export const customizations: ResourceCustomizations = {
  'character': {
    // Override labels
    label: 'Hero',
    pluralLabel: 'Heroes',

    // Field-level customizations
    fields: {
      'bio': { variant: { type: 'textarea', rows: 5 } },
      'stats': { variant: { type: 'json', height: 300 } },
      'description': { variant: { type: 'markdown', height: 400 } },
      'code': { variant: { type: 'monaco', language: 'python', height: 500 } },
      'level': { variant: { type: 'slider', sliderMin: 1, sliderMax: 100 } },
      'tags': { variant: { type: 'tags', maxTags: 10 } },
      'role': { variant: { type: 'select' } },
      'is_active': { variant: { type: 'switch' } },
      'guild_id': {
        label: 'Guild',
        ref: { resource: 'guild', type: 'resource_id' },
      },
    },

    // Reveal hidden fields (e.g., job management fields)
    showHiddenFields: ['debug_info'],

    // Max nesting depth before fields collapse to JSON editor
    maxFormDepth: 3,

    // Table configuration
    table: {
      initPageSize: 50,
      defaultSort: [{ id: 'name', desc: false }],
      disableAdvancedSearch: false,
      density: 'xs',
      mrtOptions: {
        enableRowSelection: true,
      },
    },

    // Create form configuration
    create: {
      title: 'Create New Hero',
    },

    // Detail page configuration
    detail: {
      showRevisionHistory: true,
      showDeleteButton: true,
    },
  },
};
```

### All FieldVariant Types

| Type | Options | Use Case |
|------|---------|----------|
| `text` | — | Default string input |
| `textarea` | `rows?: number` | Multi-line text |
| `monaco` | `language?: string`, `height?: number` | Code editor (JSON, Python, etc.) |
| `markdown` | `height?: number` | Markdown editor with preview |
| `number` | `min?`, `max?`, `step?` | Number input |
| `slider` | `sliderMin?`, `sliderMax?`, `step?` | Slider input |
| `select` | `options?: {value, label}[]` | Dropdown (auto-populated from enum) |
| `checkbox` | — | Boolean checkbox |
| `switch` | — | Boolean toggle (default for booleans) |
| `date` | — | Date picker |
| `file` | `accept?`, `multiple?` | File upload |
| `json` | `height?: number` | JSON editor (Monaco) |
| `tags` | `maxTags?`, `splitChars?` | Tag input |
| `array` | `itemType?`, `minItems?`, `maxItems?` | Array editor |
| `union` | `variant?: 'radio.group' \| 'radio.card'` | Union type selector |

### FieldRef — Cross-Resource References

```typescript
fields: {
  'owner_id': {
    ref: { resource: 'user', type: 'resource_id' },
    // Renders as a searchable dropdown (RefSelect component)
  },
  'approved_revision': {
    ref: { resource: 'user', type: 'revision_id' },
    // References a specific revision, not latest
  },
}
```

## Component Architecture

### Three-Layer Field Rendering

Components follow a three-layer rendering pattern based on context:

| Layer | Directory | When Used |
|-------|-----------|-----------|
| **Cell** | `components/field/CellFieldRenderer/` | Table cells (compact display) |
| **Detail** | `components/field/DetailFieldRenderer/` | Detail page (full display with binary, unions) |
| **Form** | `components/field/FormFieldRenderer/` | Create/edit forms (interactive inputs) |

`resolveFieldKind.ts` dispatches to the correct renderer based on field type, variant, and annotations. The resolution order: hidden → itemFields → union → binary → file → json → markdown → arrayString → tags → select → checkbox → switch → date → number → textarea → ref → text.

### All Components

| Category | Components |
|----------|------------|
| **Page** | `ResourceTable`, `ResourceCreate`, `ResourceDetail`, `Dashboard`, `BackupRestore`, `JobTable`, `MigrationStatus`, `PendingJobsAccordion` |
| **Form** | `ResourceForm` (dual mode: structured form / JSON editor, deferred blob upload) |
| **Detail** | `MetadataSection`, `RevisionHistorySection`, `RevisionTreeTimeline` |
| **Table/Search** | `MultiResourceTable`, `AdvancedSearchPanel`, `SearchForm`, `MetaSearchForm`, `buildColumns` |
| **Job** | `JobStatusSection`, `JobFieldsSection`, `JobArtifactSection`, `JobLogsPanel`, `PendingUpdateJobsAccordion` |
| **Common** | `RefLink`/`RefLinkList`, `RefRevisionLink`/`RefRevisionLinkList`, `ResourceIdCell`, `RevisionIdCell`, `TimeDisplay` |
| **Cell Renderers** | 21 FieldKind renderers — compact single-line table display |
| **Detail Renderers** | `BinaryFieldDisplay`, `ArrayFieldDisplay`, `UnionFieldDisplay`, `StructuralUnionFieldDisplay`, `CollapsibleJson` |
| **Form Renderers** | `RefSelect`/`RefMultiSelect`, `ArrayFieldRenderer`, `UnionFieldRenderer`, `BinaryFieldEditor`, `JsonEditor`, `MarkdownEditor` |

> **Full reference** with props, behavior, and patterns: see `references/components.md`

## Hooks Reference

All hooks are exported from `@/autocrud/lib/hooks`.

### Query Hooks

| Hook | Purpose | Returns |
|------|---------|--------|
| `useResourceList(config, params?, options?)` | Paginated list with search/sort | `{ data, total, loading, refresh }` |
| `useResourceDetail(config, id, options?)` | Detail + integrated mutations | `{ resource, update, deleteResource, restore, switchRevision, rerun, logs, ... }` |
| `useMultiResourceList(entries, params?, options?)` | Aggregate multiple resources | `{ items, totals, totalCount }` |

### Mutation Hooks

All mutation hooks return `{ action, actionAsync, isPending, error, reset }`. Options: `{ onSuccess?, onError?, showErrorNotification?, invalidateOnSuccess? }`.

| Hook | API Call | Invalidates |
|------|----------|------------|
| `useCreateResource(config, options?)` | `apiClient.create(data)` | `lists` |
| `useUpdateResource(config, id, options?)` | `apiClient.update(id, data)` | `details` + `lists` |
| `useDeleteResource(config, id, options?)` | `apiClient.delete(id)` / `permanentlyDelete(id)` | `details` + `lists` |
| `useRestoreResource(config, id, options?)` | `apiClient.restore(id)` | `details` + `lists` |
| `useSwitchRevision(config, id, options?)` | `apiClient.switchRevision(id, revId)` | `details` + `lists` + `revisions` |
| `useRerunResource(config, id, options?)` | `apiClient.rerun(id)` | `details` + `lists` |
| `useBlobUpload(options?)` | Chunked upload with progress | N/A (stateful: status, progress, cancel) |

### Utility Hooks

| Hook | Purpose |
|------|--------|
| `useAdvancedSearch(options)` | Manages condition/QB search state, syncs URL + MRT table |
| `useFieldDepth(options)` | Computes visible/collapsed fields by nesting depth |

### Non-Hook Exports

| Export | Purpose |
|--------|--------|
| `resourceKeys` | TanStack Query key factory: `.all()`, `.lists()`, `.list()`, `.details()`, `.detail()`, `.revisions()`, `.logs()` |
| `fetchResourceList`, `fetchResourceDetail`, `fetchResourceRevisions`, `fetchResourceLogs` | Primitive async fetchers for use outside React |

> **Full reference** with signatures, parameter types, return types, and query key patterns: see `references/hooks.md`

## Axios Client Configuration

The shared Axios instance is in `lib/client.ts`:

```typescript
import { client, getBaseUrl, getBlobUrl } from '@/autocrud/lib/client';

// Make custom API calls
const response = await client.get('/custom-endpoint');

// Build blob URLs for images/downloads
const imageUrl = getBlobUrl(fileId);  // → /api/v1/autocrud/blobs/{fileId}
```

Environment variable `VITE_API_URL` controls the base URL (defaults to `/api`).

## URL Path & Proxy Configuration

In development, API requests flow: **Axios** (`VITE_API_URL` + `basePath` + resource) → **Vite proxy** (strips `VITE_API_URL` prefix) → **Backend** (receives `basePath` + resource).

Key variables in `.env`:
- `VITE_API_URL` — Axios base URL + Vite proxy match prefix (default `/api`)
- `API_PROXY_TARGET` — Backend URL (e.g., `http://localhost:8000`)

The generator auto-detects `basePath` from OpenAPI spec (e.g., `/v1/autocrud`) and injects it into generated API clients via `setApiBasePath()`.

### When You Change Backend root_path or Router Prefix

**Correct procedure**: (1) Start backend with new config → (2) `make regen-app` → (3) Restart Vite dev server. The generator re-detects paths automatically.

**Important**: `root_path` only affects OpenAPI spec metadata, not actual routes. `APIRouter(prefix=...)` is what physically changes route paths.

**Custom proxy mapping**: If your proxy prefix maps to a different backend prefix (not just removal), edit `vite.config.ts` rewrite manually — the generator does not modify `vite.config.ts` after initial `init`.

> **Full reference** with request chain diagrams, troubleshooting checklist, and common mistakes: see `references/url-path-proxy.md`

## Error Handling

Three utility functions in `lib/utils/errorNotification.ts`:

| Function | Purpose |
|----------|--------|
| `extractErrorMessage(error)` | Parses Axios errors → human-readable string. Handles FastAPI `HTTPException` (string detail) and `ValidationError` (array detail with field paths) |
| `extractUniqueConflict(error)` | Detects 409 unique constraint → `{ field, message, conflictingResourceId? }` or `null` |
| `showErrorNotification(error, title?)` | Shows Mantine notification (red, 8s, multi-line) |

Mutation hooks auto-call `showErrorNotification` by default (configurable via `showErrorNotification: false`). Two calling patterns: `create()` (fire-and-forget, notification only) vs `createAsync()` (awaitable, throws for try/catch).

Axios interceptor in `lib/client.ts` logs all errors: `console.error('[API Error]', status, data)`.

> **Full reference** with patterns, component-level handling, and testing guide: see `references/error-handling.md`

## Advanced Component Development

The three-layer field renderer system (Cell/Detail/Form) uses registry-based dispatch via `resolveFieldKind()`. Each layer has a `Record<FieldKind, Component>` map ensuring TypeScript exhaustiveness.

To **add a new FieldKind**: (1) extend the `FieldKind` type, (2) add resolution logic, (3) implement renderer for all three layers, (4) register in all three registry maps.

To **customize rendering**: use `resourceCustomization.ts` for config-level changes (variant overrides), or edit the renderer component directly for visual changes.

Key patterns: **Deferred blob upload** (file stored in form state, uploaded on submit), **Lazy table upgrade** (server-side → client-side when needed), **Field depth control** (collapse nested fields beyond a depth threshold).

> **Full reference** with step-by-step guide and code examples: see `references/advanced-components.md`

## Template Sync Mechanism

During development, `app/` is the source of truth. `make sync-templates` runs rsync to copy `app/ → generator/templates/base/`, excluding generated files (`src/autocrud/generated`, `src/routes/autocrud-admin`, `routeTree.gen.ts`) and build artifacts (`node_modules`, `dist`, `.vite`, `coverage`).

**Key rules**:
- Never edit `generator/templates/base/` directly — always edit in `app/` and sync
- Never edit `src/autocrud/generated/` — overwritten by `generate`
- `resourceCustomization.ts` is safe — generator skips it if it already exists

**Flows**: `make sync-templates` (dev → templates), `init` (templates → new app), `generate` (backend OpenAPI → generated/).

> **Full reference** with rsync breakdown, exclude list, and workflow details: see `references/template-sync.md`

## Common Recipes

### Custom Table Cell Rendering

Override how a field appears in the table by modifying `CellFieldRenderer`:

```typescript
// In your route's index.tsx
import { ResourceTable } from '@/autocrud/lib/components';

// Use table config to customize columns via mrtOptions
const resource = getResource('character');
// Customize via resourceCustomization.ts → table.mrtOptions
```

### Binary File Upload & Preview

Binary fields (`Binary` in Python model) automatically render as:
- **Form**: File upload input (`BinaryFieldEditor`)
- **Detail**: Download link + inline preview for images (`BinaryFieldDisplay`)
- **Table**: File icon indicator

No extra configuration needed — just define `avatar: Binary | None = None` in your backend model.

### Theme & Style Customization

Edit `app/src/App.tsx` to customize the Mantine theme:

```typescript
import { MantineProvider, createTheme } from '@mantine/core';

const theme = createTheme({
  primaryColor: 'blue',
  fontFamily: 'Inter, sans-serif',
});

// Applied in the App component's MantineProvider
```

### Adding Custom Pages

Add new routes using TanStack Router file-based routing:

```typescript
// src/routes/autocrud-admin/analytics.tsx
import { createFileRoute } from '@tanstack/react-router';

export const Route = createFileRoute('/autocrud-admin/analytics')({
  component: AnalyticsPage,
});

function AnalyticsPage() {
  return <div>Custom analytics page</div>;
}
```

## Development Workflow

### Daily Development

```bash
make dev-app          # Start Vite dev server
```

### Backend Schema Changed

```bash
make regen-app        # Re-generate types, API clients, routes
git diff              # Review changes
```

### Build for Production

```bash
make build            # Production build (generator + app)
```

### Run Tests

```bash
cd app && pnpm test   # Vitest test suite
```

### Code Style

```bash
make style            # lint:fix + prettier
```

### Key Make Commands

| Command | Purpose |
|---------|---------|
| `make gen-app` | Full scaffold: build generator + create app + install + generate |
| `make reset-app` | Delete app + regenerate from scratch |
| `make regen-app` | Re-generate code only (backend must be running) |
| `make clean-app` | Delete entire app directory |
| `make dev-app` | Start Vite dev server |
| `make rebuild` | Rebuild generator + regenerate code |
| `make style` | Auto-fix lint + format |
| `make test` | Run generator + app tests |

## Key Dependencies

| Package | Purpose |
|---------|---------|
| React 19 | UI framework |
| Mantine 8 | Component library |
| TanStack Router | File-based routing |
| mantine-react-table 2.0 | Server-side data tables |
| Zod 4 | Schema validation |
| Axios | HTTP client |
| @monaco-editor/react | Code editor for JSON/markdown |
| react-markdown | Markdown rendering |
| dayjs | Date formatting |
| Vitest | Testing |
