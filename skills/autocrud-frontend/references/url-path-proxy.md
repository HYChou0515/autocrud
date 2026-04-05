# URL Path & Proxy Configuration

How API URLs are resolved from frontend request to backend endpoint, and how to correctly handle changes to `root_path` or router prefix.

## Table of Contents

- [Complete Request Chain](#complete-request-chain)
- [Key Concepts](#key-concepts)
- [How the Generator Detects Paths](#how-the-generator-detects-paths)
- [Changing Backend root_path or Router Prefix](#changing-backend-root_path-or-router-prefix)
- [Custom Proxy Path Mapping](#custom-proxy-path-mapping)
- [Production Deployment](#production-deployment)
- [Troubleshooting](#troubleshooting)

---

## Complete Request Chain

In development, every API request flows through three layers:

```
Frontend (Axios)          Vite Dev Proxy              Backend (FastAPI)
─────────────────         ──────────────              ─────────────────
GET {VITE_API_URL}        Match proxyPath prefix      Receive final path
    {basePath}            Rewrite: remove prefix      at actual route
    /{resource}           Forward to target
```

### Concrete Example

Backend routes at `/v1/autocrud/character`. Config:
- `VITE_API_URL=/api` (proxy prefix)
- `API_PROXY_TARGET=http://localhost:8000` (backend URL)
- `basePath=/v1/autocrud` (auto-detected from OpenAPI)

```
1. Axios sends:    GET /api/v1/autocrud/character
                        ^^^^ VITE_API_URL (baseURL)
                            ^^^^^^^^^^^^^^ basePath
                                          ^^^^^^^^^^ resource

2. Vite matches:   /api prefix ✓

3. Vite rewrites:  Remove /api → /v1/autocrud/character

4. Vite forwards:  GET http://localhost:8000/v1/autocrud/character

5. Backend serves: Route /v1/autocrud/character ✓
```

---

## Key Concepts

| Concept | Where Set | What It Does | Example |
|---------|-----------|-------------|---------|
| **`VITE_API_URL`** | `.env` | Axios `baseURL` + Vite proxy match prefix | `/api`, `/blog-api` |
| **`API_PROXY_TARGET`** | `.env` | Vite proxy forwarding target (dev only) | `http://localhost:8000` |
| **`basePath`** | Auto-detected or `--base-path` | Path prefix in generated API clients | `/v1/autocrud` |
| **`apiBasePath`** | `setApiBasePath()` in generated `resources.ts` | Runtime base path for blob URLs | `/v1/autocrud` |
| **`proxyPath`** | `--proxy-path` CLI option | Written to `VITE_API_URL` in `.env` | `/api` (default) |
| **`root_path`** | FastAPI constructor | Affects OpenAPI `servers` field only, not actual routes | `/v1/autocrud` |
| **`APIRouter.prefix`** | Python code | Directly changes registered route paths | `/api/v1` |

### Important Distinction: root_path vs APIRouter.prefix

- **`root_path`** only affects the OpenAPI spec `servers` field and ASGI scope. It does **NOT** change the actual URL paths that FastAPI registers. The routes remain at their original paths.
- **`APIRouter(prefix=...)`** directly changes the registered route paths. If you change prefix from `/v1/autocrud` to `/autocrud`, all routes physically move.

---

## How the Generator Detects Paths

When you run `npx autocrud-web generate`, the generator:

1. **Fetches** `{url}/openapi.json`
2. **Auto-detects `basePath`** via `detectBasePath()`:
   - Scans all POST endpoints with request body schemas
   - Strips the last path segment (resource name) from each
   - Returns the common prefix if all match
   ```
   POST /v1/autocrud/character → prefix /v1/autocrud
   POST /v1/autocrud/guild     → prefix /v1/autocrud
   Common = /v1/autocrud ✓
   ```
3. **Generates code** with detected basePath:
   - `generated/resources.ts`: calls `setApiBasePath('/v1/autocrud')`
   - `generated/api/characterApi.ts`: `const BASE = '/v1/autocrud/character'`
4. **Writes `.env`**:
   - `VITE_API_URL={proxyPath}` (default `/api`)
   - `API_PROXY_TARGET={url}`

---

## Changing Backend root_path or Router Prefix

### The Correct Procedure

When you change the backend's `root_path` or router prefix:

**Step 1:** Ensure the backend is running with the new configuration.

**Step 2:** Re-run the generator:
```bash
make regen-app
# or
npx autocrud-web generate --url http://localhost:8000
```

This automatically:
- Re-detects the new `basePath` from the updated OpenAPI spec
- Regenerates all API client BASE paths
- Updates `setApiBasePath()` call
- Updates `.env` proxy config

**Step 3:** Restart the Vite dev server (proxy config is read at startup).

### If You Also Need a Custom Proxy Prefix

```bash
npx autocrud-web generate --url http://localhost:8000 --proxy-path /blog-api
```

This sets `VITE_API_URL=/blog-api` in `.env`, configuring both Axios and the Vite proxy to use `/blog-api` as the prefix.

---

## Custom Proxy Path Mapping

The default Vite proxy rewrite **removes the proxy prefix entirely**:

```typescript
// vite.config.ts (default behavior)
proxy: {
  [proxyPath]: {                    // e.g., '/api'
    target: proxyTarget,            // e.g., 'http://localhost:8000'
    changeOrigin: true,
    rewrite: (p) => p.replace(new RegExp(`^${proxyPath}`), ''),
    // /api/v1/autocrud/character → /v1/autocrud/character
  },
}
```

This works correctly when:
- **Proxy path**: `/api` (or any custom prefix)
- **Backend routes**: `/v1/autocrud/character`
- **Request**: `/api/v1/autocrud/character` → removes `/api` → `/v1/autocrud/character` ✓

### When You Need Custom Rewrite

If your proxy prefix needs to **map to a different backend prefix** (not just be removed), edit `vite.config.ts` manually:

```typescript
// Example: /blog-api/* should reach /autocrud/* on backend
rewrite: (p) => p.replace(/^\/blog-api/, '/autocrud'),
// /blog-api/author → /autocrud/author ✓
```

**Warning**: The generator does NOT modify `vite.config.ts` after initial `init`. If you need non-standard rewrite rules, you must edit it manually.

### When Custom Rewrite Is Needed

| Scenario | Rewrite | Manual Edit? |
|----------|---------|-------------|
| Standard: `/api` → remove prefix | `p.replace(/^\/api/, '')` | No (default) |
| Custom prefix: `/blog-api` → remove prefix | `p.replace(/^\/blog-api/, '')` | No (handled by `--proxy-path`) |
| Prefix mapping: `/blog-api` → `/autocrud` | `p.replace(/^\/blog-api/, '/autocrud')` | **Yes** |
| Multiple backends | Multiple proxy entries | **Yes** |

---

## Production Deployment

In production, there's no Vite proxy. Configure `VITE_API_URL` at build time:

### Direct API URL

```bash
VITE_API_URL=https://api.example.com npm run build
```

Axios sends requests directly to `https://api.example.com/v1/autocrud/character`.

### Behind Reverse Proxy (Nginx, etc.)

```bash
VITE_API_URL=/api npm run build
```

Configure your reverse proxy to forward `/api/*` to the backend, similar to the Vite dev proxy.

Example nginx config:
```nginx
location /api/ {
    proxy_pass http://backend:8000/;    # Trailing / strips /api prefix
}
```

---

## Troubleshooting

### "Frontend can't reach any API endpoints"

**Diagnosis checklist:**

1. **Check `.env`** — Is `VITE_API_URL` correct? Is `API_PROXY_TARGET` pointing to the right backend?
   ```bash
   cat app/.env
   ```

2. **Check generated API paths** — Do they match backend routes?
   ```bash
   grep "const BASE" app/src/autocrud/generated/api/*.ts
   ```

3. **Check `setApiBasePath`** — Is it using the correct base path?
   ```bash
   grep "setApiBasePath" app/src/autocrud/generated/resources.ts
   ```

4. **Check browser DevTools Network tab** — What URL is Axios actually requesting? What does the backend respond?

5. **Check Vite proxy rewrite** — Manually trace the rewrite:
   ```
   Request:  {VITE_API_URL}{basePath}/{resource}
   Rewrite:  Remove {VITE_API_URL} prefix
   Forward:  {API_PROXY_TARGET}{basePath}/{resource}
   Backend:  Must serve at {basePath}/{resource}
   ```

### Common Mistakes

| Mistake | Symptom | Fix |
|---------|---------|-----|
| Changed backend prefix but didn't `regen-app` | 404 on all endpoints | Run `make regen-app` |
| Changed `.env` but didn't restart Vite | Proxy still using old config | Restart Vite dev server |
| Proxy rewrite removes prefix that backend needs | 404 (path too short) | Edit `vite.config.ts` rewrite rule |
| `VITE_API_URL` set to full URL in dev | Vite proxy doesn't intercept | Use relative path (e.g., `/api`) in dev |
| `basePath` in generated code doesn't match backend | 404 on specific resources | Re-run generator with `--base-path` override |
| Using `root_path` thinking it changes routes | Routes unchanged, confusion | `root_path` only affects OpenAPI spec; use `APIRouter(prefix=...)` for actual route changes |

### Quick Fix Commands

```bash
# Nuclear option: regenerate everything
make regen-app && cd app && pnpm dev

# Just update .env proxy config
npx autocrud-web generate --url http://localhost:8000 --proxy-path /my-prefix

# Check what the generator would detect
curl http://localhost:8000/openapi.json | python3 -c "
import json, sys
spec = json.load(sys.stdin)
for p in spec.get('paths', {}):
    print(p)
"
```
