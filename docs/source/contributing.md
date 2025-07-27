# 貢獻指南

感謝你對 AutoCRUD 專案的關注！我們歡迎各種形式的貢獻。

## 如何貢獻

### 1. 報告問題

如果你發現了 bug 或有功能請求，請：

1. 檢查 [GitHub Issues](https://github.com/HYChou0515/autocrud/issues) 確認問題未被報告
2. 建立新的 Issue，包含：
   - 清晰的問題描述
   - 重現步驟
   - 期望的行為
   - 系統環境信息

### 2. 送出程式碼

#### 開發環境設定

```bash
# clone repository
git clone https://github.com/HYChou0515/autocrud.git
cd autocrud

# 安裝依賴套件 (使用 uv - 推薦)
uv sync --dev

# 或使用 pip
pip install -e ".[dev]"
```

#### 開發流程

1. **建立分支**：
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **編寫程式碼**：
   - 遵循專案的 coding style
   - 新增適當的文件字串
   - 編寫測試用例
   - 確保所有模型都包含必要的 `id` 欄位

3. **執行測試**：
   ```bash
   # 執行所有測試
   make test
   
   # 或單獨執行
   uv run pytest
   
   # 執行特定測試文件
   uv run pytest tests/test_specific.py
   ```

4. **代碼檢查**：
   ```bash
   # 執行代碼格式化
   make format
   
   # 執行代碼檢查
   make lint
   
   # 執行類型檢查
   make type-check
   ```

   # 檢查測試覆蓋率
   coverage run -m pytest
   coverage report

   # code style 檢查
   ruff check
   ruff format
   ```

4. **commit 更改**：
   ```bash
   git add .
   git commit -m "feat: add your feature description"
   ```

5. **push 並建立 PR**：
   ```bash
   git push origin feature/your-feature-name
   ```

## Coding 規範

### Code Style

我們使用 Ruff 來維護程式碼品質：

```bash
# 檢查 code style
ruff check

# 自動格式化
ruff format
```

### Commit Message 規範

使用 [Conventional Commits](https://www.conventionalcommits.org/) 格式：

```
type(scope): description

- feat: 新功能
- fix: 修復 bug
- docs: 檔案更新
- style: 程式碼格式化
- refactor: 程式碼重構
- test: 測試相關
- chore: build 或輔助工具更改
```

範例：
```
feat(multi-model): add URL plural choice support
fix(storage): handle file permission errors
docs: update installation guide
```

### 文件字串

使用 Google 風格的文件字串：

```python
def create_item(self, data: Dict[str, Any]) -> Dict[str, Any]:
    """建立新專案。

    Args:
        data: 要建立的專案資料

    Returns:
        建立的專案，包含產生的 ID

    Raises:
        ValidationError: 當資料驗證失敗時
        StorageError: 當儲存操作失敗時
    """
    pass
```

## 測試指南

### 編寫測試

1. **測試檔案命名**：`test_*.py`
2. **測試類命名**：`TestClassName`
3. **測試方法命名**：`test_method_name`

### 測試結構

```python
import pytest
from autocrud import AutoCRUD
from autocrud.storage import MemoryStorage

class TestAutoCRUD:
    @pytest.fixture
    def crud(self):
        storage = MemoryStorage()
        return AutoCRUD(model=YourModel, storage=storage)
    
    def test_create_item(self, crud):
        """測試專案建立功能"""
        data = {"field1": "value1", "field2": "value2"}
        result = crud.create(data)
        
        assert result["field1"] == "value1"
        assert "id" in result
    
    def test_create_item_validation_error(self, crud):
        """測試無效資料的處理"""
        with pytest.raises(ValidationError):
            crud.create({"invalid": "data"})
```

### 測試覆蓋率

目標是保持 85% 以上的測試覆蓋率：

```bash
coverage run -m pytest
coverage report --show-missing
```

## 檔案貢獻

### 檔案建置

```bash
# 安裝文件 dependency
uv add --dev sphinx myst-parser furo sphinx-autodoc-typehints

# 建置檔案
sphinx-build -b html docs/source docs/build/html

# 查看檔案
open docs/build/html/index.html
```

### 檔案類型

1. **API 檔案**：自動從程式碼產生
2. **使用者指南**：使用說明和最佳實踐
3. **範例**：實際使用案例
4. **變更日誌**：版本更新記錄

## 發布流程

### 版本號規範

使用 [語義化版本](https://semver.org/)：

- `MAJOR.MINOR.PATCH`
- `1.0.0`: 主要版本（不相容的變更）
- `0.1.0`: 次要版本（新功能，向後相容）
- `0.0.1`: 修復版本（bug 修復）

### 發布檢查清單

在發布新版本前：

- [ ] 所有測試通過
- [ ] 檔案更新完成
- [ ] 變更日誌更新
- [ ] 版本號更新
- [ ] 建立 Git 標籤

## 社群規範

### 行為準則

我們致力於為所有人提供友好、安全和歡迎的環境：

1. **尊重他人**：友善和專業的交流
2. **包容性**：歡迎不同背景的貢獻者
3. **建設性**：提供有用的反饋和建議
4. **耐心**：幫助新手和初學者

### 溝通渠道

- **GitHub Issues**：bug 報告和功能請求
- **GitHub Discussions**：一般討論和問答
- **Pull Requests**：code review 和討論

## 常見問題

### Q: 我可以提交小的修復嗎？

A: 當然可以！任何改進都是歡迎的，包括：
- 修復拼寫錯誤
- 優化程式碼
- 改進檔案

### Q: 如何建議新功能？

A: 請先建立 GitHub Issue 描述你的想法：
- 解釋功能的用途
- 提供使用案例
- 討論實作方法

### Q: 我不熟悉某個技術，還能貢獻嗎？

A: 絕對可以！我們歡迎：
- 檔案改進
- 測試用例
- 使用反饋
- 功能建議

### Q: 如何成為維護者？

A: 通過持續貢獻展現你的承諾：
- 定期送出高品質的程式碼
- 幫助回答問題
- 參與 code review
- 維護檔案

感謝你考慮為 AutoCRUD 做出貢獻！每一個貢獻都讓這個專案變得更好。
