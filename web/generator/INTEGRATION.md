# AutoCRUD Web — Integration Guide

將 AutoCRUD 自動生成的管理介面整合到你既有的 React 專案中。

## 概覽

`autocrud-web integrate` 命令會將必要的 library 檔案複製到你的專案中，並從你的 AutoCRUD 後端生成 API client 和路由頁面，**不會覆請**你的 `package.json`、`tsconfig.json`、`vite.config.ts` 等頂層設定檔。

## 前置條件

- Node.js >= 18
- pnpm（推薦）或 npm/yarn
- 既有的 React + Vite 專案
- 運行中的 AutoCRUD 後端（提供 `/openapi.json`）

## Step 1：安裝依賴

### Runtime Dependencies

```bash
pnpm add @mantine/core @mantine/dates @mantine/form @mantine/hooks \
  @mantine/notifications @monaco-editor/react @tabler/icons-react \
  @tanstack/react-router @tanstack/react-virtual \
  axios clsx dayjs mantine-form-zod-resolver \
  "mantine-react-table@2.0.0-beta.9" react-markdown remark-gfm zod
```

### Dev Dependencies

```bash
pnpm add -D @tanstack/router-plugin \
  postcss-preset-mantine postcss-simple-vars
```

## Step 2：設定 TypeScript Path Alias

在你的 `tsconfig.app.json`（或 `tsconfig.json`）中設定 `@/*` path alias：

```jsonc
{
  "compilerOptions": {
    // ... 你原有的設定
    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"]
    }
  }
}
```

> **注意**：如果你已經有不同的路徑 alias 設定，需要確保 `@/*` → `./src/*` 的對應存在，因為所有生成的代碼都使用這個 alias。

## Step 3：設定 Vite

更新 `vite.config.ts`，加入 TanStack Router plugin 和 path alias：

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { TanStackRouterVite } from '@tanstack/router-plugin/vite'
import path from 'path'

export default defineConfig({
  plugins: [
    TanStackRouterVite({ quoteStyle: 'single' }),
    react(),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  // ... 你原有的設定
})
```

**重要**：`TanStackRouterVite` 必須在 `react()` plugin **之前**。

## Step 4：設定 PostCSS (Mantine CSS)

建立或更新 `postcss.config.mjs`：

```javascript
export default {
  plugins: {
    'postcss-preset-mantine': {},
    'postcss-simple-vars': {
      variables: {
        'mantine-breakpoint-xs': '36em',
        'mantine-breakpoint-sm': '48em',
        'mantine-breakpoint-md': '62em',
        'mantine-breakpoint-lg': '75em',
        'mantine-breakpoint-xl': '88em',
      },
    },
  },
}
```

## Step 5：執行 Integrate

確保你的 AutoCRUD 後端正在運行，然後在你的專案根目錄執行：

```bash
# 基本用法（後端在 localhost:8000，spec 在 /openapi.json）
npx autocrud-web integrate --url http://localhost:8000

# 如果後端有路徑前綴
npx autocrud-web integrate --url http://localhost:8000 --base-path /api/v1

# 如果 OpenAPI spec 在不同路徑
npx autocrud-web integrate --url http://localhost:8000 --openapi-path /api/v1/openapi.json

# 指定不同的 output 目錄
npx autocrud-web integrate --url http://localhost:8000 --output src
```

這會：
1. 複製 `src/lib/`（components、hooks、utils、client.ts）
2. 複製 `src/types/`（API type definitions）
3. 複製 layout route 檔案（`__root.tsx`、`autocrud-admin.tsx`）
4. 從你的後端生成 `src/generated/`（types、API clients）
5. 生成路由頁面到 `src/routes/autocrud-admin/`
6. 寫入 `.env` 設定 `VITE_API_URL`

## Step 6：設定 App 入口

在你的 App 入口（通常是 `App.tsx` 或 `main.tsx`）中加入 Mantine Provider：

```tsx
import { MantineProvider } from '@mantine/core'
import { Notifications } from '@mantine/notifications'

// Mantine CSS — 必須引入
import '@mantine/core/styles.css'
import '@mantine/notifications/styles.css'
import '@mantine/dates/styles.css'

function App() {
  return (
    <MantineProvider>
      <Notifications />
      {/* 你原有的 app 內容 */}
      {/* AutoCRUD 路由會自動透過 TanStack Router 掛載在 /autocrud-admin 下 */}
    </MantineProvider>
  )
}
```

### 如果你使用 TanStack Router

AutoCRUD 生成的路由使用 file-based routing（TanStack Router plugin）。生成的路由結構：

```
src/routes/
├── __root.tsx              ← Layout（含 navbar）
├── autocrud-admin.tsx      ← Admin layout
├── index.tsx               ← 首頁
└── autocrud-admin/
    ├── index.tsx            ← Dashboard
    ├── {resource}/
    │   ├── index.tsx        ← List page
    │   ├── create.tsx       ← Create page
    │   └── $resourceId.tsx  ← Detail page
```

### 如果你使用 React Router 或其他 router

你需要手動把生成的頁面組件整合到你的 router 設定中。生成的頁面組件都可以獨立使用：

```tsx
import { ResourceTable } from '@/lib/components/ResourceTable'
import { getResource } from '@/lib/resources'

// 在你的路由中使用
function UsersPage() {
  const config = getResource('users')!
  return <ResourceTable config={config} basePath="/admin/users" />
}
```

## Step 7：驗證

啟動開發伺服器：

```bash
pnpm dev
```

打開瀏覽器，前往：
- `http://localhost:5173/` — 首頁
- `http://localhost:5173/autocrud-admin` — AutoCRUD 管理介面

## CLI 參數參考

| 參數 | 說明 | 預設值 |
|---|---|---|
| `-u, --url <api-url>` | AutoCRUD 後端 URL | `http://localhost:8000` |
| `-o, --output <directory>` | 輸出目錄（你的 src/） | `src` |
| `--openapi-path <path>` | OpenAPI spec 路徑 | `/openapi.json` |
| `--base-path <path>` | API 路徑前綴（自動偵測若省略） | 自動偵測 |
| `--api-base-url <url>` | Runtime API URL（寫入 .env） | `--url` + `--base-path` |

## 檔案結構

integrate 命令會建立/複製以下檔案：

### 自動複製（library）
- `src/lib/client.ts` — Axios HTTP client
- `src/lib/resources.ts` — Resource registry
- `src/lib/resourceCustomization.ts` — Customization utilities
- `src/lib/components/` — 所有 UI 組件
- `src/lib/hooks/` — React hooks
- `src/lib/utils/` — Utility functions
- `src/lib/types/` — Internal types
- `src/types/api.ts` — API type definitions

### 自動生成（from OpenAPI）
- `src/generated/types.ts` — TypeScript interfaces
- `src/generated/resources.ts` — Resource metadata
- `src/generated/api/` — API clients (one per resource)

### 自動生成（routes）
- `src/routes/index.tsx` — Root page
- `src/routes/autocrud-admin/index.tsx` — Dashboard
- `src/routes/autocrud-admin/{resource}/` — CRUD pages

### 不會被覆蓋
- `package.json`
- `tsconfig.json` / `tsconfig.app.json` / `tsconfig.node.json`
- `vite.config.ts`
- `postcss.config.mjs`
- `index.html`
- `eslint.config.js`

## 常見問題

### Q: 如果我的後端 API 有路徑前綴（如 `/api/v1`），怎麼辦？

Generator 會自動偵測路徑前綴。如果自動偵測有問題，可以手動指定：

```bash
npx autocrud-web integrate --url http://localhost:8000 --base-path /api/v1
```

### Q: 生成後的 API client 打的是什麼 URL？

API client 使用 `src/lib/client.ts` 中的 axios instance，base URL 來自：
1. 環境變數 `VITE_API_URL`（由 `.env` 設定）
2. Fallback: `http://localhost:8000`

integrate/generate 命令會自動寫入 `.env`。

### Q: 我可以修改生成的檔案嗎？

可以！生成的路由和 API client 可以自由修改。但注意：
- `src/generated/` 下的檔案會在 re-generate 時被覆蓋
- `src/routes/autocrud-admin/` 下的路由也會被重新生成
- `src/lib/` 下的 library 檔案不會被 `generate` 覆蓋，只有 `integrate` 會更新

### Q: 如何更新 library 到新版本？

重新執行 `integrate` 命令會更新 `src/lib/` 和 `src/types/` 目錄：

```bash
npx autocrud-web integrate --url http://localhost:8000
```

### Q: 我的 tsconfig 有自訂設定，會衝突嗎？

只要確保以下設定存在即可：
- `"baseUrl": "."` + `"paths": { "@/*": ["./src/*"] }`
- `"jsx": "react-jsx"`
- `"moduleResolution": "bundler"` 或 `"node"`

其他設定不會衝突。

### Q: 產生的 .env 會覆蓋我的其他環境變數嗎？

不會。如果 `.env` 已存在，只會更新/新增 `VITE_API_URL` 這一行，其他行不會被修改。
