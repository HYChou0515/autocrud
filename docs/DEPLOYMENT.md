# 📚 文件部署指南

本專案已經設定好了完整的文件系統，支援自動部署到 GitHub Pages 和 Read the Docs。

## 🚀 快速部署步驟

### 1. 推送到 GitHub

```bash
# 確保所有文件都已提交
git add .
git commit -m "docs: add comprehensive documentation system with Sphinx and MyST"
git push origin master
```

### 2. 啟用 GitHub Pages

1. 前往你的 GitHub 倉函式庫
2. 點擊 `Settings` 標籤
3. 滾動到 `Pages` 部分
4. 在 `Source` 下拉選單中選擇 `GitHub Actions`
5. 保存設定

### 3. 查看部署狀態

- 前往倉函式庫的 `Actions` 標籤查看構建狀態
- 文件將自動部署到：`https://HYChou0515.github.io/autocrud/`

## � GitHub Pages 部署

文件已自動部署到 GitHub Pages，提供：

- 自動化建置和部署
- 版本控制整合
- 自訂域名支援

### 設定步驟

1. **啟用 GitHub Pages**：
   - 前往 https://github.com/HYChou0515/autocrud/settings/pages
   - 在 'Source' 選擇 'GitHub Actions'

2. **自動部署**：
   - 每次 push 到 master branch 時自動觸發
   - GitHub Actions 會自動建置文件
   - 部署完成後可訪問：`https://HYChou0515.github.io/autocrud/`

3. **檢查部署狀態**：
   - 前往 Actions 頁面查看建置狀態
   - 綠色勾號表示部署成功
   - 紅色 X 表示需要檢查錯誤

4. **訪問文件**：
   - 主要文件：`https://HYChou0515.github.io/autocrud/`
   - 文件會自動更新當 master branch 有新的 commit

## 🔧 本地文件開發

### 構建文件

```bash
# 安裝 dependency
uv sync --dev

# 構建 HTML 文件
make html

# 啟動本地服務器
make serve

# 清理構建文件
make clean
```

### 實時預覽 (可選)

```bash
# 安裝 sphinx-autobuild
uv add --dev sphinx-autobuild

# 啟動實時預覽
make livehtml
```

## 📝 文件結構

```
docs/
├── source/
│   ├── conf.py              # Sphinx 設定
│   ├── index.md             # 主頁
│   ├── quickstart.md        # 快速入門
│   ├── installation.md     # 安裝指南
│   ├── user_guide.md       # 使用者指南
│   ├── api_reference.md    # API 參考
│   ├── examples.md         # 範例集合
│   ├── contributing.md     # 貢獻指南
│   └── changelog.md        # 變更日誌
└── build/
    └── html/               # 構建輸出
```

## 🛠️ 技術棧

- **Sphinx**: 文件產生引擎
- **MyST-Parser**: Markdown 支援
- **Furo**: 現代化主題
- **sphinx-autodoc-typehints**: 自動 API 文件
- **GitHub Actions**: 自動化 CI/CD

## 🔄 更新文件

每次推送到 master 分支時：

1. GitHub Actions 會自動觸發
2. 構建新的文件
3. 部署到 GitHub Pages
4. Read the Docs 也會自動更新 (如果有設定)

## 📊 監控和維護

### 檢查構建狀態

```bash
# 檢查文件連結
make linkcheck

# 執行文件測試
uv run sphinx-build -b doctest docs/source docs/build/doctest
```

### 常見問題

1. **構建失敗**：檢查 Actions 日誌
2. **連結失效**：執行 `make linkcheck`
3. **樣式問題**：清理緩存 `make clean && make html`

## 🎯 下一步

1. push 程式碼到 GitHub
2. 啟用 GitHub Pages
3. (可選) 設定 Read the Docs
4. 自訂域名 (如果需要)
5. 新增徽章到 README

## 📈 徽章範例

可以在 README.md 中新增這些徽章：

```markdown
[![GitHub Pages](https://img.shields.io/badge/docs-GitHub%20Pages-blue)](https://HYChou0515.github.io/autocrud/)
[![Build Status](https://github.com/HYChou0515/autocrud/actions/workflows/docs.yml/badge.svg)](https://github.com/HYChou0515/autocrud/actions/workflows/docs.yml)
```
