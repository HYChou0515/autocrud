# Web UI

SpecStar can generate a complete React admin application from your backend's OpenAPI schema.

This is useful when you want a working internal tool quickly without building list pages, forms, clients, and revision views by hand.

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
public/              # static assets, including the app logo
src/
├── specstar/
│   ├── generated/   # generated types, API clients, resource metadata, branding
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

## Naming and branding

The generated app is *your* admin console, so it carries your name and logo rather than SpecStar's.

The title shown in the browser tab, on the landing page, and in the admin header is resolved on every `generate`, from the first of these that is set:

1. the `title` field in `.specstarrc.json`
2. the `info.title` of your backend's OpenAPI spec
3. `SpecStar Admin`, as a fallback

The logo works the same way, via the `logo` field, defaulting to the SpecStar mark shipped at `public/specstar-mark.svg`.

Both live in `.specstarrc.json` at the project root:

```json
{
  "mantineVersion": "8",
  "title": "Northwind Console",
  "logo": "/northwind.svg"
}
```

A `logo` value is a URL path served from `public/`, so `"/northwind.svg"` means `public/northwind.svg`. Drop your own file in there and point `logo` at it.

Because most backends already set a real `info.title`, you usually get a correctly named console without configuring anything. A backend that never set one reports the stock `FastAPI` title, which is ignored so it cannot become your app's name.

Both values are written into `src/specstar/generated/branding.ts` and stamped into `index.html` — the browser reads the tab name and favicon from the HTML before React starts, so both stay in step. Run `generate` again after editing `.specstarrc.json` to apply a change.

---

## Related guides

- [Routes generation](/specstar/howto/routes)
- [Job Queue](/specstar/quickstart/job-queue)
- [Integrate with an existing FastAPI app](/specstar/quickstart/integrate-existing)

