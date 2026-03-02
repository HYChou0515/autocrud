# AutoCRUD Web Generator

🚀 Code generator for AutoCRUD frontend applications. Automatically generates a complete React/TypeScript/Mantine web application from your AutoCRUD API's OpenAPI specification.

## Features

- **TypeScript Types**: Auto-generated from OpenAPI schemas
- **API Clients**: Axios-based clients for all resources
- **List Pages**: Server-side pagination with Mantine React Table
- **Detail Pages**: View, edit, and revision history
- **Create Pages**: Auto-generated forms with validation
- **Dashboard**: Resource overview with counts
- **TanStack Router**: File-based routing

## Installation

```bash
npm install -g autocrud-web-generator
# or
pnpm add -g autocrud-web-generator
```

## Usage

### Initialize a New Project

```bash
autocrud-web init my-app
cd my-app
pnpm install
```

### Generate Code from API

Make sure your AutoCRUD backend is running, then:

```bash
pnpm generate --url http://localhost:8000
```

### Start Development Server

```bash
pnpm dev
```

Visit `http://localhost:5173` to see your generated app.

## CLI Commands

### `autocrud-web init <project-name>`

Initialize a new AutoCRUD Web project.

Options:
- `-d, --dir <directory>`: Target directory (default: current directory)

Example:
```bash
autocrud-web init my-game-admin
```

### `autocrud-web generate`

Generate code from AutoCRUD API OpenAPI spec.

Options:
- `-u, --url <api-url>`: Backend API URL — used to fetch the OpenAPI spec and written to `.env` as the Vite dev proxy target (default: `http://localhost:8000`)
- `-o, --output <directory>`: Output directory (default: `src`)
- `--openapi-path <path>`: Path to OpenAPI spec endpoint (default: `/openapi.json`)
- `--base-path <path>`: API base path prefix, auto-detected if omitted

Example:
```bash
autocrud-web generate --url http://localhost:8000
# With non-root API prefix:
autocrud-web generate --url http://localhost:8000 --base-path /api/v1
```

After running, `.env` will contain:
```env
VITE_API_URL=/api
API_PROXY_TARGET=http://localhost:8000
```

### `autocrud-web integrate`

Integrate AutoCRUD generated code into an **existing** React project without overwriting your `package.json`, `tsconfig`, `vite.config.ts`, etc.

Options: same as `generate`.

```bash
autocrud-web integrate --url http://localhost:8000
```

See [INTEGRATION.md](INTEGRATION.md) for a detailed step-by-step guide.

## Generated Structure

```
my-app/
├── src/
│   ├── autocrud/
│   │   ├── generated/           # Auto-generated (gitignored)
│   │   │   ├── types.ts         # TypeScript interfaces
│   │   │   ├── resources.ts     # Resource registry
│   │   │   └── api/
│   │   │       ├── characterApi.ts
│   │   │       ├── guildApi.ts
│   │   │       └── ...
│   │   ├── lib/                 # Template components (tracked)
│   │   │   ├── client.ts        # Axios instance
│   │   │   ├── resources.ts     # Resource config helpers
│   │   │   ├── components/      # Reusable UI components
│   │   │   ├── hooks/           # Custom React hooks
│   │   │   └── utils/           # Utility functions
│   │   └── types/               # Shared types (tracked)
│   │       └── api.ts
│   ├── routes/
│   │   ├── __root.tsx           # Root layout
│   │   ├── index.tsx            # Dashboard
│   │   ├── autocrud-admin/
│   │   │   ├── character/
│   │   │   │   ├── index.tsx    # List page
│   │   │   │   ├── create.tsx   # Create page
│   │   │   │   └── $resourceId.tsx # Detail page
│   │   │   └── ...
│   │   └── ...
│   ├── App.tsx
│   └── main.tsx
├── package.json
└── vite.config.ts
```

## Tech Stack

- **React 19** + **TypeScript**
- **Vite** - Build tool
- **Mantine 7** - UI components
- **Mantine React Table** - Data tables
- **TanStack Router** - File-based routing
- **Axios** - HTTP client

## Development Workflow

1. **Initialize**: `autocrud-web init my-app`
2. **Install dependencies**: `pnpm install`
3. **Generate code**: `pnpm generate --url http://your-api:8000`
4. **Start dev server**: `pnpm dev`
5. **Make API changes** → Re-run `pnpm generate`

## Requirements

- Node.js >= 18.0.0
- AutoCRUD backend with OpenAPI spec at `/openapi.json`

## API Proxy & Environment Variables

The generated app uses a **Vite dev server proxy** to avoid CORS issues during development.

### How It Works

| Environment | `VITE_API_URL` | Request Path | Actual Target |
|-------------|----------------|-------------|---------------|
| **Dev** | `/api` (default) | `/api/character` → Vite proxy | `http://localhost:8000/character` |
| **Prod** | `http://server:port` | `http://server:port/character` | Direct to backend |

All API requests go through the Axios client in `src/lib/client.ts`, which reads `VITE_API_URL` as its base URL.

In dev mode, requests to `/api/*` are intercepted by the Vite dev server and forwarded to the backend (with the `/api` prefix stripped). This means **no CORS configuration is needed** on the backend for development.

### Environment Variables

The generator writes a `.env` file (git-ignored) with these variables:

| Variable | Scope | Default | Description |
|----------|-------|---------|-------------|
| `VITE_API_URL` | Browser (runtime) | `/api` | Base URL for Axios requests. Use `/api` for dev (proxy), or a full URL for prod. |
| `API_PROXY_TARGET` | Vite dev server only | `http://localhost:8000` | Backend URL that `/api` requests are proxied to. **Not exposed to the browser.** |

See `.env.example` for reference.

### Development (Default)

No extra config needed — just start the backend and the dev server:

```bash
# Terminal 1: Start your AutoCRUD backend
uv run python examples/rpg_game_api.py

# Terminal 2: Start the frontend dev server
cd app && pnpm dev
```

The Vite dev server will proxy `/api/*` → `http://localhost:8000/*`.

If your backend runs on a different host or port, edit `.env`:

```env
API_PROXY_TARGET=http://192.168.1.100:9000
```

### Production

For production builds, set `VITE_API_URL` to the actual backend URL:

```env
VITE_API_URL=http://your-server:8000
```

Then build:

```bash
pnpm build
```

The proxy is only active during `pnpm dev` — production builds use `VITE_API_URL` directly.

### CORS (Optional)

With the dev proxy, you generally **don't need** CORS on the backend. However, if you prefer direct browser-to-backend requests (e.g., set `VITE_API_URL=http://localhost:8000` without proxy), configure CORS:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## License

MIT

## Gallery

<img width="2144" height="2472" alt="image" src="https://github.com/user-attachments/assets/80fa4a6f-1363-4dfd-9641-92831c86839e" />
<img width="2144" height="3966" alt="image" src="https://github.com/user-attachments/assets/bacd5cec-4ffb-46a1-97b0-fca5a0f7a0af" />
<img width="2144" height="1338" alt="image" src="https://github.com/user-attachments/assets/cac3a5e6-81a8-46cf-bfea-93a79f8dff11" />
<img width="2144" height="1338" alt="image" src="https://github.com/user-attachments/assets/0bf35c07-a845-4bfd-8300-eea215201a54" />




