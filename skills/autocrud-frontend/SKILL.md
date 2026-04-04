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

### Key Components

| Component | Purpose |
|-----------|---------|
| `ResourceTable` | List/search with server-side pagination (mantine-react-table) |
| `ResourceCreate` | Auto-generated create form from schema |
| `ResourceForm` | Reusable form for create/edit |
| `ResourceDetail` | Detail + edit + revision history + RevisionTreeTimeline |
| `Dashboard` | Resource overview with counts |
| `BackupRestore` | Export/import UI |
| `JobTable` | Message queue job management |
| `RefLink` | Clickable link to referenced resource |
| `RefSelect` | Searchable dropdown for ref fields |

## Hooks Reference

### Query Hooks (read data)

```typescript
import {
  useResourceList,
  useResourceDetail,
  useMultiResourceList,
  useAdvancedSearch,
  useFieldDepth,
} from '@/autocrud/lib/hooks';

// Paginated list with search
const { data, isLoading, totalCount } = useResourceList('character', {
  limit: 20,
  offset: 0,
  search: 'warrior',
});

// Single resource detail
const { data: character, isLoading } = useResourceDetail('character', resourceId);

// Multiple resources at once
const { rows, isLoading } = useMultiResourceList([
  { resourceName: 'character', limit: 5 },
  { resourceName: 'guild', limit: 5 },
]);

// Advanced search with QB-like conditions
const { conditions, addCondition, removeCondition, results } =
  useAdvancedSearch('character');

// Analyze field nesting depth
const maxDepth = useFieldDepth(resource.fields);
```

### Mutation Hooks (modify data)

```typescript
import {
  useCreateResource,
  useUpdateResource,
  useDeleteResource,
  useRestoreResource,
  useSwitchRevision,
  useRerunResource,
  useBlobUpload,
} from '@/autocrud/lib/hooks';

// Create
const { mutate: create } = useCreateResource('character');
create({ name: 'Alice', level: 1 });

// Update
const { mutate: update } = useUpdateResource('character', resourceId);
update({ name: 'Alice Updated', level: 2 });

// Delete (soft)
const { mutate: remove } = useDeleteResource('character');
remove(resourceId);

// Restore
const { mutate: restore } = useRestoreResource('character');
restore(resourceId);

// Switch revision
const { mutate: switchRev } = useSwitchRevision('character', resourceId);
switchRev(revisionId);

// Rerun failed job
const { mutate: rerun } = useRerunResource('character', resourceId);
rerun();

// Upload blob
const { upload, progress, isUploading } = useBlobUpload('character');
upload(resourceId, file);
```

### Query Key Factory

```typescript
import { resourceKeys } from '@/autocrud/lib/hooks';

// For cache invalidation with TanStack Query
resourceKeys.lists('character');           // all character lists
resourceKeys.detail('character', id);      // specific character
resourceKeys.revisions('character', id);   // revision history
```

### Primitive Fetchers (non-hook)

```typescript
import {
  fetchResourceList,
  fetchResourceDetail,
  fetchResourceRevisions,
  fetchResourceLogs,
} from '@/autocrud/lib/hooks';

// Use in loaders, server components, or outside React
const characters = await fetchResourceList('character', { limit: 10 });
const detail = await fetchResourceDetail('character', id);
```

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
