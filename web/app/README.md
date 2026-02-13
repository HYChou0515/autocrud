# AutoCRUD Web App

自動從 AutoCRUD 後端 API 生成的前端管理介面。

## 技術棧

- **Vite** + **TypeScript** + **React**
- **Mantine** (UI Framework)
- **TanStack Router** (File-based routing)
- **Mantine React Table** (Data tables)
- **Axios** (HTTP client)

## 快速開始

```bash
# 1. 安裝依賴
pnpm install

# 2. 從 API 自動生成程式碼（指定你的 AutoCRUD 後端 URL）
pnpm generate --url http://0.0.0.0:8000

# 3. 啟動開發伺服器
pnpm dev
```

## 架構

```
src/
├── types/api.ts          # 共用 API 型別 (ResourceMeta, RevisionInfo, etc.)
├── lib/client.ts         # Axios 基礎客戶端
├── routes/__root.tsx     # 根路由 (AppShell + 導航)
├── generated/            # ⚡ 自動生成的程式碼
│   ├── types.ts          # 資源 TypeScript 型別
│   ├── resources.ts      # 資源註冊表
│   └── api/              # 每個資源的 API 客戶端
└── routes/               # ⚡ 自動生成的路由頁面
    ├── index.tsx          # Dashboard (資源總覽)
    └── {resource}/
        ├── index.tsx      # 列表頁 (搜尋/篩選/分頁)
        ├── create.tsx     # 新建頁 (自動表單)
        └── $resourceId.tsx # 詳情頁 (檢視/編輯/版本歷史)
```

## Generator 生成的內容

1. **TypeScript Types** - 從 OpenAPI Schema 自動轉換
2. **API Callers** - 每個資源的完整 CRUD + Search API (axios)
3. **Dashboard** - 所有資源的摘要首頁
4. **List Pages** - Mantine React Table + 伺服器端分頁/排序
5. **Detail Pages** - 完整資源檢視 + 編輯 Modal + 版本歷史
6. **Create Forms** - 根據 Schema 自動生成的表單

## 環境變數

```env
VITE_API_URL=http://0.0.0.0:8000
```
