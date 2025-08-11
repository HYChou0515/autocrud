# AutoCRUD 文檔系統

## 概述

本文檔系統使用 Sphinx 和 MyST 解析器，支援 Markdown 格式編寫，並具有現代化的 Furo 主題和自定義樣式。

## 文檔結構

```
docs/
├── source/                     # 文檔源檔案
│   ├── index.md               # 主頁面
│   ├── quickstart.md          # 快速入門
│   ├── installation.md        # 安裝指南
│   ├── user_guide.md          # 使用指南
│   ├── api_reference.md       # API 參考
│   ├── examples.md            # 範例集
│   ├── contributing.md        # 貢獻指南
│   ├── changelog.md           # 版本更新
│   ├── conf.py               # Sphinx 配置
│   ├── _static/              # 靜態資源
│   │   └── custom.css        # 自定義樣式
│   └── _templates/           # 模板檔案
├── build/                     # 建置輸出
│   └── html/                 # HTML 檔案
└── README.md                 # 此檔案
```

## 快速開始

### 本地預覽

```bash
# 建置文檔
make html

# 清理並重新建置
make clean && make html

# 開啟本地伺服器預覽
cd docs/build/html && python -m http.server 8000
```

瀏覽器開啟 http://localhost:8000 查看文檔。

### 自動部署

文檔會自動通過 GitHub Actions 部署到 GitHub Pages：

1. 推送到 `master` 分支時觸發自動部署
2. 部署配置位於 `.github/workflows/docs.yml`
3. 部署後可在 GitHub Pages URL 查看

## 編輯指南

### 添加新頁面

1. 在 `docs/source/` 建立新的 `.md` 檔案
2. 在 `index.md` 的 toctree 中添加新頁面
3. 重新建置文檔

### 使用進階功能

#### 頁面網格

```markdown
::::{grid} 2
:::{grid-item-card} 標題
內容
:::
:::{grid-item-card} 標題
內容
:::
::::
```

#### 提示框

```markdown
:::{note}
這是一個提示框
:::

:::{warning}
這是一個警告框
:::
```

#### 程式碼區塊

```markdown
```python
# 程式碼範例
from autocrud import AutoCRUD
```

#### 交叉引用

```markdown
參見 [API 參考](api_reference.md) 了解更多詳情
```

## 樣式自定義

### 主要顏色

- 主色：#2563eb (AutoCRUD 藍)
- 次色：#1e40af
- 成功：#059669
- 警告：#d97706
- 錯誤：#dc2626

### 自定義 CSS

編輯 `docs/source/_static/custom.css` 來修改樣式：

- 響應式設計支援
- 程式碼語法高亮
- 自定義導航樣式
- API 文檔特殊樣式

## 維護檢查清單

### 定期更新

- [ ] 檢查 API 參考是否與程式碼同步
- [ ] 更新範例程式碼
- [ ] 檢查外部連結是否有效
- [ ] 更新版本資訊

### 品質保證

- [ ] 拼字檢查
- [ ] 程式碼範例測試
- [ ] 連結檢查
- [ ] 瀏覽器相容性測試

## 故障排除

### 常見問題

1. **建置失敗**
   ```bash
   # 檢查依賴項
   uv sync
   
   # 清理並重建
   make clean && make html
   ```

2. **樣式問題**
   - 檢查 `custom.css` 語法
   - 清除瀏覽器快取
   - 重新建置文檔

3. **交叉引用失敗**
   - 確認檔案路徑正確
   - 檢查標題錨點
   - 使用相對路徑

### 除錯技巧

```bash
# 啟用詳細輸出
make html SPHINXOPTS="-v"

# 檢查特定警告
make html 2>&1 | grep WARNING

# 檢查建置時間
time make html
```

## 文檔規範

### 檔案命名

- 使用小寫和底線：`user_guide.md`
- 避免空格和特殊字元
- 保持簡潔明確

### 內容結構

1. **標題層級**：使用 H1-H6，保持一致性
2. **程式碼範例**：提供完整可執行的範例
3. **交叉引用**：適當連結相關章節
4. **多語言**：主要使用繁體中文

### 寫作風格

- 清晰簡潔的表達
- 循序漸進的教學
- 實用的範例程式碼
- 適當的視覺元素

## 技術詳情

### 依賴項

- **Sphinx**: 文檔生成引擎
- **MyST Parser**: Markdown 支援
- **Furo**: 現代主題
- **sphinx-design**: 進階版面元素

### 配置亮點

- 中文搜尋支援
- 程式碼語法高亮
- 響應式設計
- 自動 API 文檔生成
- GitHub Pages 整合

---

如有任何問題或建議，請提交 Issue 或 Pull Request。
