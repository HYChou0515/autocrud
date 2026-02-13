# AutoCRUD Web Generator - 快速開始

## 專案結構

```
generator/
├── package.json          # npm 套件設定
├── tsconfig.json         # TypeScript 設定
├── README.md            # 英文說明文件
├── PUBLISH.md           # 發布指南
├── src/                 # TypeScript 原始碼
│   ├── cli.ts           # CLI 進入點
│   └── commands/
│       ├── init.ts      # init 命令實作
│       └── generate.ts  # generate 命令實作（主要邏輯）
├── dist/                # 編譯後的 JavaScript（pnpm build）
│   ├── cli.js
│   └── commands/
└── templates/
    └── base/            # 專案模板（不包含 generated 檔案）
        ├── package.json
        ├── vite.config.ts
        ├── tsconfig.json
        ├── index.html
        ├── .env
        └── src/
            ├── App.tsx
            ├── main.tsx
            ├── lib/client.ts
            ├── types/api.ts
            └── routes/__root.tsx
```

## 使用流程

### 1. 本地開發（尚未發布到 npm）

```bash
# 在 generator 目錄
cd generator
pnpm install
pnpm build

# 全域連結（用於本地測試）
npm link

# 現在可以在任何地方使用
cd /tmp
autocrud-web init my-app
cd my-app
pnpm install
pnpm generate --url http://localhost:8000
pnpm dev
```

### 2. 發布到 npm 後

使用者安裝：
```bash
npm install -g autocrud-web-generator
# 或使用 npx（不用安裝）
npx autocrud-web-generator init my-app
```

## 兩個主要命令

### `autocrud-web init <project-name>`

功能：
- 複製 `templates/base/` 到新目錄
- 更新 `package.json` 的 `name` 欄位
- 建立完整的專案結構

實作位置：`src/commands/init.ts`

### `autocrud-web generate [--url API_URL]`

功能：
- 從 AutoCRUD API 抓取 `/openapi.json`
- 解析 OpenAPI spec 找出所有 resources
- 生成以下檔案到 `src/` 目錄：
  - `generated/types.ts` - TypeScript 介面
  - `generated/resources.ts` - Resource 註冊表
  - `generated/api/*.ts` - 各 resource 的 API client
  - `routes/index.tsx` - Dashboard
  - `routes/{resource}/index.tsx` - List 頁面
  - `routes/{resource}/create.tsx` - Create 頁面
  - `routes/{resource}/$resourceId.tsx` - Detail 頁面

實作位置：`src/commands/generate.ts`（977 行，主要邏輯）

## 技術細節

### TypeScript 編譯
- 使用 `NodeNext` module resolution
- 輸出到 `dist/` 目錄
- 保留 `.js` import extensions

### CLI 框架
- 使用 `commander` 套件
- `#!/usr/bin/env node` shebang 自動保留

### 模板系統
- 模板位於 `templates/base/`
- `init` 命令直接複製整個目錄
- 不包含 `node_modules`、`dist`、`scripts`、`src/generated`、`src/routes/{resource}`

### 檔案生成
- 使用字串模板（template literals）
- `writeFileRecursive()` 自動建立目錄
- 所有生成的檔案都有 `// Auto-generated` 註解

## 維護指南

### 修改模板

編輯 `templates/base/` 中的檔案，然後重新測試 `init` 命令。

### 修改生成邏輯

編輯 `src/commands/generate.ts` 中的 generator 函數：
- `genTypes()` - 生成 TypeScript 介面
- `genApi()` - 生成 API client
- `genListPage()` - 生成列表頁面
- `genDetailPage()` - 生成詳細頁面
- `genCreatePage()` - 生成建立頁面
- `genDashboard()` - 生成儀表板

修改後記得：
```bash
pnpm build    # 重新編譯
pnpm test     # 測試（如果有寫測試）
```

### 測試流程

1. 修改程式碼
2. `pnpm build` 編譯
3. 在臨時目錄測試：
   ```bash
   cd /tmp
   rm -rf test-app
   autocrud-web init test-app
   cd test-app
   pnpm install
   autocrud-web generate --url http://localhost:8000
   pnpm dev
   ```
4. 確認所有頁面正常運作

## 常見問題

### Q: 為什麼 generate 命令要在專案目錄內執行？

A: 因為它會讀取 `process.cwd()` 來決定輸出位置。可以用 `-o` 參數指定其他目錄。

### Q: 如何更新已經生成的專案？

A: 直接再次執行 `pnpm generate`，會覆蓋 `src/generated/` 和 `src/routes/` 下的自動生成檔案。

### Q: 模板中的 package.json 為什麼不包含 autocrud-web-generator？

A: 因為使用者通常會全域安裝或用 npx，不需要加到專案 dependencies。但可以加入 `devDependencies`。

### Q: 如何支援新的 AutoCRUD 功能？

A: 修改 `src/commands/generate.ts` 中的相關 generator 函數，例如要支援新的 API endpoint 就修改 `genApi()`。
