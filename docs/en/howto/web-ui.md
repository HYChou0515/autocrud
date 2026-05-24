# Web UI

SpecStar offers **two** ways to get an admin UI:

1. **Python-only, read-only admin** (no Node) — a server-rendered browse UI you
   mount from Python. Best when you just want to *see* your data and don't want
   a JS toolchain. See [below](#python-only-read-only-admin).
2. **Generated React app** — a full CRUD single-page app generated from your
   OpenAPI schema (needs Node / pnpm / vite). Best when you want a rich,
   customisable internal tool. That's the rest of this page.

---

## Python-only read-only admin

A server-rendered (Jinja2) admin for **browsing** resources — list, detail, and
revision history — with **no Node, pnpm, or vite**. Install the extra and mount
it on `apply()`:

```bash
pip install 'specstar[admin-ui]'
```

```python
spec.add_model(Issue)
spec.apply(app, admin_ui="/admin")   # browse at /admin
```

- Renders directly from your registered models; nothing to generate or rebuild.
- Reuses the app's `get_user` and `permission_checker` — a denied read returns
  `403`, never leaks data.
- **Read-only** by design: no create/edit/delete. For writes (forms) use the
  generated React app below, or the API directly.
- Without the `[admin-ui]` extra, `apply(admin_ui=...)` raises a clear
  `ImportError` telling you to install it.

---

## What the generator gives you

From a running SpecStar backend, the web generator can produce:

- TypeScript types from OpenAPI
- API clients for each resource
- list and detail pages
- create and edit forms
- a resource dashboard
- an admin navigation shell

The generated app is a normal React project, so you can keep customizing it after generation.

---

## Requirements

Before generating the UI, make sure you have:

- a running SpecStar backend
- the OpenAPI schema available at `/openapi.json`
- Node.js 18+
- `pnpm` or `npm`

---

## Quick start

### 1. Install the generator

```bash
npm install -g specstar-web-generator
```

Or with pnpm:

```bash
pnpm add -g specstar-web-generator
```

> The published package name is `specstar-web-generator`, while the command you run after installation is `specstar-web`.

### 2. Create a new frontend project

```bash
specstar-web init my-admin
cd my-admin
pnpm install
```

### 3. Generate code from your backend

Make sure your SpecStar API is already running, then fetch its schema:

```bash
specstar-web generate --url http://localhost:8000
```

### 4. Start the development server

```bash
pnpm dev
```

Then open:

- `http://localhost:5173`

---

## Typical workflow

Use this workflow during development:

1. update your SpecStar models in the backend
2. restart the backend if needed
3. re-run `specstar-web generate --url ...`
4. continue customizing the React app

This keeps the frontend aligned with the latest API schema.

---

## Generated project structure

A typical project contains these important areas:

```text
src/
├── specstar/
│   ├── generated/   # generated types, API clients, resource metadata
│   └── lib/         # reusable customizable components and customization hooks
└── routes/          # application routes
```

### Edit these files

You should customize the tracked files under `src/specstar/lib/` and the route layer.

Common customization points include:

- `resourceCustomization.ts` for field-level overrides
- `client.ts` for Axios configuration
- reusable components for custom layouts and rendering

### Avoid editing generated files directly

The files under `src/specstar/generated/` are overwritten whenever you regenerate from OpenAPI.

If you need stable custom behavior, add it in the tracked customization layer instead.

---

## Integrating into an existing React app

If you already have a React project, use the integrate command instead of creating a new app:

```bash
specstar-web integrate --url http://localhost:8000
```

This adds the SpecStar-generated pieces without replacing your main project configuration.

---

## Development proxy and API URL

The generated frontend typically uses a Vite development proxy.

- in development, API requests can go through `/api`
- the proxy forwards them to your backend target
- in production, set `VITE_API_URL` to the real backend URL

This avoids common CORS issues during local development.

---

## Related guides

- [Routes generation](/specstar/howto/routes)
- [Job Queue](/specstar/quickstart/job-queue)
- [Integrate with an existing FastAPI app](/specstar/quickstart/integrate-existing)

