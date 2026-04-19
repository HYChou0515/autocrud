# Component Reference

Complete inventory of all components in `app/src/autocrud/lib/components/`. Components are imported directly from their module paths — there is no barrel `index.ts` export.

## Table of Contents

- [Top-Level Page Components](#top-level-page-components)
- [Form Components](#form-components)
- [Detail Components](#detail-components)
- [Table & Search Components](#table--search-components)
- [Job Components](#job-components)
- [Common Components](#common-components)
- [Field Renderers — Three-Layer System](#field-renderers--three-layer-system)

---

## Top-Level Page Components

### `ResourceTable`

**Path**: `components/ResourceTable.tsx`

Server-side paginated resource list with lazy client-mode upgrade. Integrates mantine-react-table for sorting, filtering, and column customization.

**Key Props**:
- `config: ResourceConfig` — Resource configuration from registry
- `customization?: ResourceCustomization` — Table/field overrides from `resourceCustomization.ts`
- `basePath?: string` — URL prefix for navigation links

**Features**:
- Server-side pagination with `useResourceList`
- Column auto-generation from `config.fields` via `buildColumns()`
- Advanced search panel integration (`useAdvancedSearch`)
- Bidirectional sync between MRT column filters and advanced search conditions
- Lazy upgrade: starts server mode, auto-switches to client mode when needed
- Batch delete support
- Pending jobs accordion (for async-create resources)

### `ResourceCreate`

**Path**: `components/ResourceCreate.tsx`

Create page with auto-generated form. Supports custom create actions (tabs) for resources with multiple creation endpoints.

**Key Props**:
- `config: ResourceConfig` — Resource configuration
- `customization?: ResourceCustomization` — Create form overrides

**Features**:
- Standard form submission via `useCreateResource`
- Custom action tabs when `customization.create.customActions` is defined
- Union type support (wraps form values in `{ data: values }`)
- Unique constraint error handling (sets field-level form errors)
- Navigation to detail page on success

### `ResourceDetail`

**Path**: `components/ResourceDetail.tsx`

Detail/edit page with metadata display, edit form, revision history, job info, and delete/restore controls.

**Key Props**:
- `config: ResourceConfig` — Resource configuration
- `resourceId: string` — ID of the resource to display
- `customization?: ResourceCustomization` — Detail page overrides

**Features**:
- Edit mode toggle with `ResourceForm`
- Metadata section (ID, revision, timestamps, authors)
- Revision history with tree timeline or list view
- Soft delete, permanent delete, restore actions
- Revision switch
- Job logs display (for job resources)
- Custom update actions (tabs in edit mode)
- Pending update jobs accordion
- Field depth control (collapse deep nested fields to JSON)

### `Dashboard`

**Path**: `components/Dashboard.tsx`

Resource overview page showing resource counts and quick navigation links.

### `BackupRestore`

**Path**: `components/BackupRestore.tsx` (actually at `lib/components/BackupRestore.tsx`)

Global and per-model backup/restore UI. Exports data as JSON, imports with duplicate handling (overwrite/skip/raise).

### `JobTable`

**Path**: `components/JobTable.tsx`

Specialized resource table for job resources. Extends `ResourceTable` with job-specific columns (status badge, payload preview, retry count).

### `MigrationStatus`

**Path**: `components/MigrationStatus.tsx`

Migration dry-run and execution UI with streaming progress display.

### `PendingJobsAccordion`

**Path**: `components/PendingJobsAccordion.tsx`

Displays pending async-create jobs above the resource list. Aggregates jobs from relevant job resources and shows them in a collapsible accordion.

---

## Form Components

### `ResourceForm`

**Path**: `components/ResourceForm.tsx`

Generic reusable form for create and edit operations. Supports dual mode: structured form or raw JSON editor.

**Key Props**:
- `config: ResourceConfig` — Resource configuration
- `fields: ResourceField[]` — Fields to render
- `initialValues?: Record<string, unknown>` — Pre-populated values (edit mode)
- `onSubmit: (values) => void` — Form submission handler
- `mode: 'create' | 'edit'` — Current mode
- `formRef?: React.Ref` — Ref for external form control (e.g., `setFieldError`)

**Features**:
- Auto-generates form fields from `ResourceField[]` via `FormFieldRenderer`
- Form/JSON toggle (switch between structured form and Monaco JSON editor)
- Binary field deferred upload coordination (files stored in form state, uploaded on submit)
- Zod schema validation
- Field depth control integration

### `useResourceForm` (Hook)

**Path**: `components/ResourceForm.tsx` (co-located)

Internal hook that manages form state, validation, and blob upload coordination.

---

## Detail Components

### `MetadataSection`

**Path**: `components/MetadataSection.tsx`

Read-only metadata display: resource ID, revision ID, created/updated timestamps, created/updated by, status (draft/stable), deleted flag.

### `RevisionHistorySection`

**Path**: `components/RevisionHistorySection.tsx`

Revision history display with two view modes:
- **Timeline**: `RevisionTreeTimeline` — interactive revision DAG
- **List**: Flat list sorted by creation time

Supports revision switching and sorting controls.

### `RevisionTreeTimeline`

**Path**: `components/RevisionTreeTimeline.tsx`

Interactive parent-child revision visualization. Renders a tree/DAG of revisions with:
- Virtualized scrolling for large revision histories
- Active revision highlighting
- Click-to-switch revision
- Expand/collapse branches

---

## Table & Search Components

### `MultiResourceTable`

**Path**: `components/MultiResourceTable.tsx`

Aggregates rows from multiple resources into a single table. Uses `useMultiResourceList` to fetch in parallel. Each row is tagged with `_source` resource name.

### `AdvancedSearchPanel`

**Path**: `components/AdvancedSearchPanel.tsx`

Collapsible panel with two search modes:
- **Condition mode**: Structured field-based search (`SearchForm` + `MetaSearchForm`)
- **QB mode**: Free-text Query Builder expression input

Integrates with `useAdvancedSearch` hook for state management and URL sync.

### `SearchForm`

**Path**: `components/SearchForm.tsx`

Data field search form with:
- Field selector dropdown (from searchable fields)
- Operator selector (equals, contains, gt, lt, etc.)
- Value input (type-aware: text, number, date, select for enums)
- Add/remove condition buttons

### `MetaSearchForm`

**Path**: `components/MetaSearchForm.tsx`

Meta field filtering: date ranges (created_time, updated_time), author filters (created_by, updated_by), status filters, search_after.

### `buildColumns` (Utility)

**Path**: `components/buildColumns.ts`

Auto-generates mantine-react-table column definitions from `ResourceField[]`. Maps each field through `CellFieldRenderer` for display. Handles column ordering, visibility defaults, and ref field column linking.

---

## Job Components

### `JobStatusSection`

**Path**: `components/JobStatusSection.tsx`

Job status display: status badge (pending/running/completed/failed/cancelled), retry count, heartbeat, periodic schedule info.

### `JobFieldsSection`

**Path**: `components/JobFieldsSection.tsx`

Renders non-status, non-payload job fields in a structured layout.

### `JobArtifactSection`

**Path**: `components/JobArtifactSection.tsx`

Type-aware artifact display for completed jobs. Renders artifacts based on MIME type (JSON, text, binary).

### `JobLogsPanel`

**Path**: `components/JobLogsPanel.tsx`

Plain-text log viewer with auto-refresh for running jobs. Uses `fetchResourceLogs` to poll for updates.

### `PendingUpdateJobsAccordion`

**Path**: `components/PendingUpdateJobsAccordion.tsx`

Displays pending update jobs on the detail page. Similar to `PendingJobsAccordion` but scoped to a single resource.

---

## Common Components

**Path**: `components/common/`

### `RefLink` / `RefLinkList`

Clickable link to a referenced resource. Navigates to the resource detail page. `RefLinkList` renders multiple refs.

### `RefRevisionLink` / `RefRevisionLinkList`

Clickable link to a specific revision of a referenced resource. Includes copy-to-clipboard for revision ID.

### `ResourceIdCell`

Compact resource ID display with short format (first 8 chars) + copy-to-clipboard on click.

### `RevisionIdCell`

Smart revision number extraction from revision ID string. Displays as `#N` format.

### `TimeDisplay`

Relative/full/short time display with i18n support (zh-tw locale via dayjs). Shows "2 hours ago" format with full timestamp on hover.

---

## Field Renderers — Three-Layer System

All field renderers share the same `FieldKind` enum resolved by `resolveFieldKind.ts`. The resolution priority:

```
hidden → itemFields → union → binary → file → json → markdown →
arrayString → tags → select → checkbox → switch → date →
numberSlider → number → textarea → refResourceId →
refResourceIdMulti → refRevisionId → refRevisionIdMulti → text
```

### Layer 1: CellFieldRenderer

**Path**: `components/field/CellFieldRenderer/`

Compact single-line rendering for table cells. Registry-based dispatch: `CELL_RENDERERS` map keyed by `FieldKind`.

| FieldKind | Cell Rendering |
|-----------|---------------|
| `hidden` | Not rendered |
| `itemFields` | Object count badge |
| `union` | Discriminator value or type tag |
| `binary` | File icon indicator / image thumbnail |
| `file` | File icon |
| `json` | `{...}` preview (truncated) |
| `markdown` | Plain text excerpt |
| `arrayString` | Comma-joined truncated list |
| `tags` | Mantine `Badge` components |
| `select` | Label text |
| `checkbox` / `switch` | Check/cross icon |
| `date` | Formatted date string |
| `number` / `numberSlider` | Numeric value |
| `textarea` | Truncated text |
| `refResourceId` | `RefLink` component |
| `refResourceIdMulti` | `RefLinkList` component |
| `refRevisionId` | `RefRevisionLink` component |
| `refRevisionIdMulti` | `RefRevisionLinkList` component |
| `text` | Truncated string |

### Layer 2: DetailFieldRenderer

**Path**: `components/field/DetailFieldRenderer/`

Full-width read-only rendering for detail pages.

| Sub-Component | Purpose |
|---------------|---------|
| `BinaryFieldDisplay` | Image inline preview (if image MIME type) + download link + file metadata |
| `ArrayFieldDisplay` | Numbered cards with nested table for array-of-objects |
| `UnionFieldDisplay` | Discriminator badge + rendered variant fields |
| `StructuralUnionFieldDisplay` | Runtime variant inference (no discriminator) — tries each variant |
| `CollapsibleJson` | Expandable JSON viewer with syntax highlighting |

### Layer 3: FormFieldRenderer

**Path**: `components/field/FormFieldRenderer/`

Interactive input rendering for create/edit forms. Registry-based dispatch: `FIELD_RENDERERS` map.

| Sub-Component | Purpose |
|---------------|---------|
| `RefSelect` | Searchable dropdown for single `resource_id` ref |
| `RefMultiSelect` | Multi-select for array of `resource_id` refs |
| `RefRevisionSelect` | Searchable dropdown for single `revision_id` ref |
| `RefRevisionMultiSelect` | Multi-select for array of `revision_id` refs |
| `ArrayFieldRenderer` | Repeatable list with add/remove/reorder for typed arrays |
| `UnionFieldRenderer` | Discriminated/structural/simple union input |
| `BinaryFieldEditor` | Deferred file upload (file stored in form state, uploaded on submit) or URL input |
| `JsonEditor` | Monaco editor with JSON syntax highlighting + validation |
| `MarkdownEditor` | Monaco editor + live markdown preview side-by-side |

### `resolveFieldKind`

**Path**: `components/field/resolveFieldKind.ts`

Pure function dispatching `ResourceField` → `FieldKind`. Single source of truth for all three layers. Uses `getDefaultVariant()` to apply default variant when no explicit variant is set.

**FieldKind enum** (21 values):
`hidden`, `itemFields`, `union`, `binary`, `file`, `json`, `markdown`, `arrayString`, `tags`, `select`, `checkbox`, `switch`, `date`, `numberSlider`, `number`, `textarea`, `refResourceId`, `refResourceIdMulti`, `refRevisionId`, `refRevisionIdMulti`, `text`
