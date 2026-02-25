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
- `-u, --url <api-url>`: API base URL (default: `http://localhost:8000`)
- `-o, --output <directory>`: Output directory (default: `src`)
- `--openapi-path <path>`: Path to OpenAPI spec endpoint (default: `/openapi.json`)
- `--base-path <path>`: API base path prefix, auto-detected if omitted
- `--api-base-url <url>`: Runtime API base URL written to `.env` (defaults to `--url` + detected base path)

Example:
```bash
autocrud-web generate --url http://localhost:8000
# With non-root API prefix:
autocrud-web generate --url http://localhost:8000 --base-path /api/v1
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
│   ├── generated/
│   │   ├── types.ts           # TypeScript interfaces
│   │   ├── resources.ts       # Resource registry
│   │   └── api/
│   │       ├── characterApi.ts
│   │       ├── guildApi.ts
│   │       └── ...
│   ├── routes/
│   │   ├── __root.tsx         # Root layout
│   │   ├── index.tsx          # Dashboard
│   │   ├── character/
│   │   │   ├── index.tsx      # List page
│   │   │   ├── create.tsx     # Create page
│   │   │   └── $resourceId.tsx # Detail page
│   │   └── ...
│   ├── lib/
│   │   └── client.ts          # Axios instance
│   └── types/
│       └── api.ts             # Shared types
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

## CORS Configuration

Your AutoCRUD backend needs CORS middleware. For FastAPI:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # or ["http://localhost:5173"] for development
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




