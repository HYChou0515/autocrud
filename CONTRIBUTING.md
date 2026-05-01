# 貢獻指南

感謝你對 SpecStar 的關注！我們歡迎各種形式的貢獻。

## 貢獻方式

### 回報問題

如果你發現 bug 或有功能建議，請在 [GitHub Issues](https://github.com/HYChou0515/specstar/issues) 提出。

提交 issue 時請包含：

- **問題描述**：清楚描述問題或建議
- **重現步驟**：如何重現問題（若是 bug）
- **預期行為**：你期望發生什麼
- **實際行為**：實際發生了什麼
- **環境資訊**：Python 版本、SpecStar 版本、作業系統

### 提交程式碼

1. **Fork 專案**

   Fork [specstar](https://github.com/HYChou0515/specstar) 到你的 GitHub 帳號

2. **Clone 到本地**

   ```bash
   git clone https://github.com/YOUR_USERNAME/specstar.git
   cd specstar
   ```

3. **安裝開發環境**

   ```bash
   # 使用 uv 安裝依賴
   uv sync
   
   # 或使用 pip
   pip install -e ".[dev]"
   ```

4. **創建分支**

   ```bash
   git checkout -b feature/your-feature-name
   ```

5. **開發與測試**

   ```bash
   # 自動格式化程式碼
   make style
   
   # 執行測試
   make test
   ```

6. **提交變更**

   ```bash
   git add .
   git commit -m "描述你的變更"
   ```

7. **推送到 GitHub**

   ```bash
   git push origin feature/your-feature-name
   ```

8. **創建 Pull Request**

   在 GitHub 上創建 Pull Request，描述你的變更內容

## 開發規範

### 程式碼風格

- 使用 **ruff** 進行程式碼格式化和檢查
- 執行 `make style` 自動格式化程式碼
- 執行 `make check` 檢查程式碼品質

### 資料模型

- **必須使用 `msgspec.Struct`**，不使用 Pydantic
- 所有欄位都需要類型標註
- 範例：

  ```python
  from msgspec import Struct
  
  class User(Struct):
      name: str
      age: int
      email: str | None = None
  ```

### 測試要求

- **所有新功能必須包含測試**
- 目標：**90% 以上的程式碼覆蓋率**
- 測試檔案放在 `tests/` 目錄
- 執行測試：`make test`
- 查看覆蓋率：`make test`

### Commit 訊息

使用清楚的 commit 訊息：

```
feat: 新增 XXX 功能
fix: 修復 XXX 問題
docs: 更新文檔
test: 新增測試
refactor: 重構程式碼
perf: 效能優化
```

### 文檔

- 更新相關文檔（`docs/` 目錄）
- 為新功能添加範例
- 更新 API 參考文檔

## 開發工作流程

### 本地測試

```bash
# 快速開發循環（格式化 + 測試）
make dev

# 完整 CI 流程（檢查 + 測試 + 覆蓋率）
make ci

# 查看 HTML 覆蓋率報告
make cov-html
# 然後開啟 htmlcov/index.html
```

### 文檔預覽

```bash
# 啟動文檔伺服器
make serve

# 訪問 http://localhost:8000
```

### 效能測試

```bash
# 執行基準測試
make test-benchmark
```

## 專案結構

```
specstar/
├── specstar/           # 核心程式碼
│   ├── crud/          # SpecStar 主要邏輯
│   ├── resource_manager/  # 資源管理
│   ├── permission/    # 權限系統
│   ├── message_queue/ # 訊息佇列
│   └── util/          # 工具函數
├── tests/             # 測試檔案
├── examples/          # 範例程式
├── docs/              # 文檔
│   ├── en/           # 英文文檔
│   └── zh/           # 中文文檔
└── scripts/           # 工具腳本
```

## 貢獻範例

### 新增功能範例

如果你實作了一個有趣的應用範例：

1. 在 `examples/` 目錄下創建新檔案
2. 確保範例可以執行
3. 在 `docs/zh/examples/index.md` 添加說明
4. 提交 Pull Request

範例應該：

- 使用 `msgspec.Struct` 定義模型
- 包含完整的註解
- 可以直接執行
- 展示特定功能或應用場景

### 報告 Bug

提交 bug 報告時，請使用以下範本：

```markdown
**問題描述**
簡短描述問題

**重現步驟**
1. 執行 '...'
2. 訪問 '...'
3. 觀察錯誤

**預期行為**
應該要...

**實際行為**
實際上...

**環境**
- OS: [e.g. Ubuntu 22.04]
- Python: [e.g. 3.11.5]
- SpecStar: [e.g. 0.1.0]

**額外資訊**
其他相關資訊、截圖、錯誤訊息等
```

## 發布流程

（僅供維護者參考）

```bash
# 更新版本號
# 編輯 pyproject.toml

# 建立並上傳套件
uv run python scripts/publish.py

# 標記版本
git tag v0.x.x
git push origin v0.x.x
```

## 授權

提交貢獻即表示你同意將你的貢獻以與本專案相同的授權條款（MIT License）釋出。

## 需要幫助？

- 查看 [文檔](https://hychou0515.github.io/specstar/)
- 提出 [Issue](https://github.com/HYChou0515/specstar/issues)
- 查看現有的 [Pull Requests](https://github.com/HYChou0515/specstar/pulls)

感謝你的貢獻！🚀
