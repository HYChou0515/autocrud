# 發布到 npm

## 準備工作

1. **測試編譯**：
```bash
cd generator
pnpm build
```

2. **本地測試**：
```bash
# 測試 init 命令
cd /tmp
node /path/to/generator/dist/cli.js init test-project
cd test-project
pnpm install

# 測試 generate 命令（需要先啟動 AutoCRUD API）
node /path/to/generator/dist/cli.js generate --url http://localhost:8000
```

3. **設定 npm registry**（首次發布）：
```bash
npm login
```

## 發布步驟

1. **更新版本號**：
```bash
cd generator
npm version patch  # 或 minor / major
```

2. **發布到 npm**：
```bash
npm publish
```

3. **全域安裝測試**：
```bash
npm install -g autocrud-web-generator
autocrud-web --version
autocrud-web init test-app
```

## 本地測試（不發布）

使用 `npm link` 全域安裝本地版本：

```bash
cd generator
pnpm build
npm link
```

然後在任何地方使用：

```bash
cd /tmp
autocrud-web init my-test-app
```

取消連結：

```bash
npm unlink -g autocrud-web-generator
```

## 發布檢查清單

- [ ] README.md 完整且正確
- [ ] package.json 中的 version、description、keywords 正確
- [ ] `pnpm build` 沒有錯誤
- [ ] 本地測試 `init` 和 `generate` 命令都正常
- [ ] .npmignore 正確（不包含 src/）
- [ ] templates/base 目錄完整
