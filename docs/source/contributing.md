# 貢獻指南

感謝你對 AutoCRUD 項目的關注！我們歡迎各種形式的貢獻。

## 如何貢獻

### 1. 報告問題

如果你發現了 bug 或有功能請求，請：

1. 檢查 [GitHub Issues](https://github.com/your-repo/autocrud/issues) 確認問題未被報告
2. 創建新的 Issue，包含：
   - 清晰的問題描述
   - 重現步驟
   - 期望的行為
   - 系統環境信息

### 2. 提交代碼

#### 開發環境設置

```bash
# 克隆倉庫
git clone https://github.com/your-repo/autocrud.git
cd autocrud

# 安裝依賴 (使用 uv)
uv sync --dev

# 或使用 pip
pip install -e ".[dev]"
```

#### 開發流程

1. **創建分支**：
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **編寫代碼**：
   - 遵循項目的代碼風格
   - 添加適當的文檔字符串
   - 編寫測試用例

3. **運行測試**：
   ```bash
   # 運行所有測試
   pytest

   # 檢查測試覆蓋率
   coverage run -m pytest
   coverage report

   # 代碼風格檢查
   ruff check
   ruff format
   ```

4. **提交更改**：
   ```bash
   git add .
   git commit -m "feat: add your feature description"
   ```

5. **推送並創建 PR**：
   ```bash
   git push origin feature/your-feature-name
   ```

## 代碼規範

### 代碼風格

我們使用 Ruff 來維護代碼質量：

```bash
# 檢查代碼風格
ruff check

# 自動格式化
ruff format
```

### 提交消息規範

使用 [Conventional Commits](https://www.conventionalcommits.org/) 格式：

```
type(scope): description

- feat: 新功能
- fix: 修復 bug
- docs: 文檔更新
- style: 代碼格式化
- refactor: 代碼重構
- test: 測試相關
- chore: 構建或輔助工具更改
```

示例：
```
feat(multi-model): add URL plural choice support
fix(storage): handle file permission errors
docs: update installation guide
```

### 文檔字符串

使用 Google 風格的文檔字符串：

```python
def create_item(self, data: Dict[str, Any]) -> Dict[str, Any]:
    """創建新項目。

    Args:
        data: 要創建的項目數據

    Returns:
        創建的項目，包含生成的 ID

    Raises:
        ValidationError: 當數據驗證失敗時
        StorageError: 當存儲操作失敗時
    """
    pass
```

## 測試指南

### 編寫測試

1. **測試文件命名**：`test_*.py`
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
        """測試項目創建功能"""
        data = {"field1": "value1", "field2": "value2"}
        result = crud.create(data)
        
        assert result["field1"] == "value1"
        assert "id" in result
    
    def test_create_item_validation_error(self, crud):
        """測試無效數據的處理"""
        with pytest.raises(ValidationError):
            crud.create({"invalid": "data"})
```

### 測試覆蓋率

目標是保持 85% 以上的測試覆蓋率：

```bash
coverage run -m pytest
coverage report --show-missing
```

## 文檔貢獻

### 文檔構建

```bash
# 安裝文檔依賴
uv add --dev sphinx myst-parser furo sphinx-autodoc-typehints

# 構建文檔
sphinx-build -b html docs/source docs/build/html

# 查看文檔
open docs/build/html/index.html
```

### 文檔類型

1. **API 文檔**：自動從代碼生成
2. **用戶指南**：使用說明和最佳實踐
3. **示例**：實際使用案例
4. **變更日誌**：版本更新記錄

## 發布流程

### 版本號規範

使用 [語義化版本](https://semver.org/)：

- `MAJOR.MINOR.PATCH`
- `1.0.0`: 主要版本（不兼容的變更）
- `0.1.0`: 次要版本（新功能，向後兼容）
- `0.0.1`: 修復版本（bug 修復）

### 發布檢查清單

在發布新版本前：

- [ ] 所有測試通過
- [ ] 文檔更新完成
- [ ] 變更日誌更新
- [ ] 版本號更新
- [ ] 創建 Git 標籤

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
- **Pull Requests**：代碼審查和討論

## 常見問題

### Q: 我可以提交小的修復嗎？

A: 當然可以！任何改進都是歡迎的，包括：
- 修復拼寫錯誤
- 優化代碼
- 改進文檔

### Q: 如何建議新功能？

A: 請先創建 GitHub Issue 描述你的想法：
- 解釋功能的用途
- 提供使用案例
- 討論實現方法

### Q: 我不熟悉某個技術，還能貢獻嗎？

A: 絕對可以！我們歡迎：
- 文檔改進
- 測試用例
- 使用反饋
- 功能建議

### Q: 如何成為維護者？

A: 通過持續貢獻展現你的承諾：
- 定期提交高質量的代碼
- 幫助回答問題
- 參與代碼審查
- 維護文檔

感謝你考慮為 AutoCRUD 做出貢獻！每一個貢獻都讓這個項目變得更好。
