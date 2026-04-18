# Web UI

AutoCRUD can generate a complete React admin application from your backend's OpenAPI schema.

This is useful when you want a working internal tool quickly without building list pages, forms, clients, and revision views by hand.

---

## What the generator gives you

From a running AutoCRUD backend, the web generator can produce:

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

- a running AutoCRUD backend
- the OpenAPI schema available at `/openapi.json`
- Node.js 18+
- `pnpm` or `npm`

---

## Quick start

### 1. Install the generator

```bash
npm install -g autocrud-web-generator
```

Or with pnpm:

```bash
pnpm add -g autocrud-web-generator
```

### 2. Create a new frontend project

```bash
autocrud-web init my-admin
cd my-admin
pnpm install
```

### 3. Generate code from your backend

Make sure your AutoCRUD API is already running, then fetch its schema:

```bash
autocrud-web generate --url http://localhost:8000
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

1. update your AutoCRUD models in the backend
2. restart the backend if needed
3. re-run `autocrud-web generate --url ...`
4. continue customizing the React app

This keeps the frontend aligned with the latest API schema.

---

## Generated project structure

A typical project contains these important areas:

```text
src/
├── autocrud/
│   ├── generated/   # generated types, API clients, resource metadata
│   └── lib/         # reusable tracked components and customization hooks
└── routes/          # application routes
```

### Edit these files

You should customize the tracked files under `src/autocrud/lib/` and the route layer.

Common customization points include:

- `resourceCustomization.ts` for field-level overrides
- `client.ts` for Axios configuration
- reusable components for custom layouts and rendering

### Avoid editing generated files directly

The files under `src/autocrud/generated/` are overwritten whenever you regenerate from OpenAPI.

If you need stable custom behavior, add it in the tracked customization layer instead.

---

## Integrating into an existing React app

If you already have a React project, use the integrate command instead of creating a new app:

```bash
autocrud-web integrate --url http://localhost:8000
```

This adds the AutoCRUD-generated pieces without replacing your main project configuration.

---

## Development proxy and API URL

The generated frontend typically uses a Vite development proxy.

- in development, API requests can go through `/api`
- the proxy forwards them to your backend target
- in production, set `VITE_API_URL` to the real backend URL

This avoids common CORS issues during local development.

---

## Related guides

- [Routes generation](/autocrud/howto/routes)
- [Job Queue](/autocrud/quickstart/job-queue)
- [Integrate with an existing FastAPI app](/autocrud/quickstart/integrate-existing)

