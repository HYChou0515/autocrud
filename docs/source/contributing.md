# 🤝 貢獻指南

感謝您對 AutoCRUD 項目的興趣！本指南將幫助您了解如何為項目做出貢獻。

## 🌟 貢獻方式

我們歡迎各種形式的貢獻：

- 🐛 **報告 Bug**：發現問題？請告訴我們！
- 💡 **功能建議**：有好想法？我們很樂意聽取！
- 📝 **文檔改進**：文檔總是可以更好
- 🔧 **代碼貢獻**：修復 Bug 或添加新功能
- 🧪 **測試改進**：增加測試覆蓋率
- 💬 **社區支持**：幫助其他用戶解決問題

## 🚀 快速開始

### 1. Fork 和克隆項目

```bash
# Fork 項目到您的 GitHub 帳戶
# 然後克隆您的 fork

git clone https://github.com/YOUR_USERNAME/autocrud.git
cd autocrud

# 添加上游倉庫
git remote add upstream https://github.com/HYChou0515/autocrud.git
```

### 2. 設置開發環境

我們推薦使用 `uv` 來管理依賴：

```bash
# 安裝 uv (如果尚未安裝)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 安裝項目依賴 (包括開發依賴)
uv sync --dev

# 激活虛擬環境
source .venv/bin/activate  # Linux/macOS
# 或
.venv\Scripts\activate     # Windows
```

### 3. 安裝 pre-commit 鈎子

```bash
# 安裝 pre-commit
uv add --dev pre-commit

# 設置鈎子
pre-commit install

# 測試鈎子 (可選)
pre-commit run --all-files
```

### 4. 運行測試

```bash
# 運行所有測試
uv run pytest

# 運行特定測試文件
uv run pytest tests/test_basic_crud.py

# 運行測試並生成覆蓋率報告
uv run pytest --cov=autocrud --cov-report=html

# 查看覆蓋率報告
open htmlcov/index.html
```

## 📋 開發工作流

### 創建分支

```bash
# 確保您在最新的 master 分支
git checkout master
git pull upstream master

# 創建新的功能分支
git checkout -b feature/awesome-new-feature

# 或者修復 bug 的分支
git checkout -b fix/issue-123
```

### 提交代碼

```bash
# 添加更改
git add .

# 提交 (pre-commit 會自動運行)
git commit -m "feat: add awesome new feature"

# 推送到您的 fork
git push origin feature/awesome-new-feature
```

### 提交 Pull Request

1. 前往 GitHub 上的原始倉庫
2. 點擊 "New Pull Request"
3. 選擇您的分支
4. 填寫 PR 描述
5. 等待代碼審查

## 📝 代碼規範

### 代碼風格

我們使用以下工具來保持代碼質量：

```bash
# 代碼格式化
uv run black autocrud tests

# 導入排序
uv run isort autocrud tests

# 類型檢查
uv run mypy autocrud

# 代碼質量檢查
uv run ruff check autocrud tests

# 自動修復一些問題
uv run ruff check --fix autocrud tests
```

### 提交信息規範

我們使用 [Conventional Commits](https://www.conventionalcommits.org/) 規範：

```
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

**類型 (type)**：
- `feat`: 新功能
- `fix`: Bug 修復
- `docs`: 文檔更新
- `style`: 代碼格式化 (不影響功能)
- `refactor`: 重構 (不是新功能也不是 Bug 修復)
- `test`: 添加或修改測試
- `chore`: 構建過程或輔助工具的變動

**示例**：
```
feat(crud): add support for soft delete

Add soft delete functionality to all CRUD operations.
This allows resources to be marked as deleted without
actually removing them from storage.

Closes #123
```

### 文檔字符串

我們使用 Google 風格的文檔字符串：

```python
def create_user(name: str, email: str) -> User:
    """創建新用戶。

    Args:
        name: 用戶姓名
        email: 用戶電子郵件地址

    Returns:
        創建的用戶對象

    Raises:
        ValidationError: 當輸入數據無效時
        EmailExistsError: 當電子郵件已存在時

    Example:
        >>> user = create_user("張三", "zhang@example.com")
        >>> print(user.name)
        張三
    """
```

## 🧪 測試指南

### 測試結構

```
tests/
├── conftest.py              # 共享測試配置
├── test_basic_crud.py       # 基本 CRUD 測試
├── test_multiple_data_types.py  # 多數據類型測試
├── test_advanced_features.py   # 高級功能測試
├── test_performance.py      # 性能測試
└── integration/
    ├── test_real_world_scenarios.py
    └── test_compatibility.py
```

### 編寫測試

```python
import pytest
from autocrud.crud.core import AutoCRUD
from pydantic import BaseModel

class TestUser(BaseModel):
    name: str
    email: str

class TestCRUDOperations:
    """測試 CRUD 操作"""
    
    @pytest.fixture
    def crud(self):
        """創建測試用的 CRUD 實例"""
        crud = AutoCRUD()
        # 添加必要的路由模板
        return crud
    
    def test_create_user(self, crud):
        """測試用戶創建"""
        user_data = {"name": "測試用戶", "email": "test@example.com"}
        # 測試邏輯
        assert True
    
    @pytest.mark.asyncio
    async def test_async_operation(self, crud):
        """測試異步操作"""
        # 異步測試邏輯
        assert True
    
    @pytest.mark.parametrize("name,email,expected", [
        ("張三", "zhang@example.com", True),
        ("", "invalid", False),
    ])
    def test_validation(self, name, email, expected):
        """參數化測試"""
        # 測試邏輯
        assert True
```

### 測試覆蓋率

我們目標是保持 90%+ 的測試覆蓋率：

```bash
# 查看覆蓋率
uv run pytest --cov=autocrud --cov-report=term-missing

# 生成 HTML 報告
uv run pytest --cov=autocrud --cov-report=html

# 失敗時停止
uv run pytest -x

# 詳細輸出
uv run pytest -v

# 運行特定標記的測試
uv run pytest -m "not slow"
```

## 📚 文檔貢獻

### 文檔結構

```
docs/
├── source/
│   ├── conf.py              # Sphinx 配置
│   ├── index.md             # 主頁
│   ├── quickstart.md        # 快速開始
│   ├── installation.md     # 安裝指南
│   ├── user_guide.md       # 用戶指南
│   ├── api_reference.md    # API 參考
│   ├── examples.md         # 示例集合
│   ├── contributing.md     # 貢獻指南
│   └── changelog.md        # 變更日誌
└── build/
    └── html/               # 構建輸出
```

### 構建文檔

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

### 編寫指南

- 使用清晰、簡潔的語言
- 提供實際可運行的代碼示例
- 包含必要的截圖或圖表
- 保持文檔與代碼同步更新

## 🔧 項目結構

```
autocrud/
├── autocrud/
│   ├── __init__.py
│   ├── crud/
│   │   ├── __init__.py
│   │   └── core.py           # 核心 CRUD 功能
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── memory.py         # 內存存儲
│   │   ├── file.py           # 文件存儲
│   │   └── database.py       # 數據庫存儲
│   ├── serializers/
│   │   ├── __init__.py
│   │   ├── json.py           # JSON 序列化
│   │   └── msgspec.py        # msgspec 序列化
│   ├── cache/
│   │   ├── __init__.py
│   │   ├── memory.py         # 內存緩存
│   │   └── redis.py          # Redis 緩存
│   └── exceptions.py         # 異常定義
├── tests/                    # 測試文件
├── docs/                     # 文檔
├── examples/                 # 示例代碼
├── scripts/                  # 工具腳本
├── pyproject.toml           # 項目配置
├── README.md                # 項目說明
└── CONTRIBUTING.md          # 貢獻指南
```

## 🚀 發布流程

### 版本號規範

我們使用 [Semantic Versioning](https://semver.org/)：

- `MAJOR.MINOR.PATCH` (例如 `1.2.3`)
- `MAJOR`: 不兼容的 API 變更
- `MINOR`: 向後兼容的功能添加
- `PATCH`: 向後兼容的 Bug 修復

### 創建發布

1. **更新版本號**：
   ```bash
   # 在 pyproject.toml 中更新版本
   version = "1.2.3"
   ```

2. **更新變更日誌**：
   ```markdown
   ## [1.2.3] - 2025-XX-XX
   
   ### Added
   - 新增功能 A
   - 新增功能 B
   
   ### Fixed
   - 修復 Bug X
   - 修復 Bug Y
   
   ### Changed
   - 改進功能 Z
   ```

3. **創建發布標籤**：
   ```bash
   git tag -a v1.2.3 -m "Release version 1.2.3"
   git push origin v1.2.3
   ```

4. **發布到 PyPI** (維護者操作)：
   ```bash
   uv build
   uv publish
   ```

## 🐛 報告問題

### Bug 報告

使用我們的 [Issue 模板](https://github.com/HYChou0515/autocrud/issues/new?template=bug_report.md)：

**必需信息**：
- AutoCRUD 版本
- Python 版本
- 操作系統
- 最小重現代碼
- 預期行為 vs 實際行為
- 錯誤消息或日誌

**示例**：
```markdown
### Bug 描述
在使用 TypedDict 時，列表查詢返回錯誤的數據格式。

### 重現步驟
1. 定義 TypedDict 模型
2. 創建幾個記錄
3. 調用 GET /model
4. 觀察響應格式

### 環境信息
- AutoCRUD: 1.0.0
- Python: 3.11.0
- OS: Ubuntu 22.04

### 最小重現代碼
\```python
from typing import TypedDict
# ... 重現代碼
\```
```

### 功能請求

使用我們的 [功能請求模板](https://github.com/HYChou0515/autocrud/issues/new?template=feature_request.md)：

**包含內容**：
- 功能描述
- 使用場景
- 建議的 API 設計
- 相關資源或參考

## 💬 社區

### 聯繫方式

- 📧 **電子郵件**：hychou0515@gmail.com
- 💬 **討論區**：[GitHub Discussions](https://github.com/HYChou0515/autocrud/discussions)
- 🐛 **問題追蹤**：[GitHub Issues](https://github.com/HYChou0515/autocrud/issues)

### 行為準則

我們承諾為所有人提供友好、安全和歡迎的環境。請：

- 使用友好和包容的語言
- 尊重不同的觀點和經驗
- 優雅地接受建設性批評
- 專注於對社區最有利的事情
- 對其他社區成員表現出同理心

## 🏆 貢獻者認可

我們感謝所有貢獻者的努力！您的貢獻將被記錄在：

- [Contributors 頁面](https://github.com/HYChou0515/autocrud/graphs/contributors)
- 發布說明中的特別感謝
- [CONTRIBUTORS.md](CONTRIBUTORS.md) 文件

### 貢獻類型

- 💻 **代碼貢獻**：修復 Bug、添加功能
- 📖 **文檔貢獻**：改進文檔、添加示例
- 🐛 **測試貢獻**：編寫測試、報告 Bug
- 💡 **設計貢獻**：API 設計、架構建議
- 🌍 **翻譯貢獻**：多語言支持
- 💬 **社區貢獻**：幫助其他用戶、組織活動

## 📋 檢查清單

在提交 PR 之前，請確保：

### 代碼質量
- [ ] 代碼風格檢查通過 (`pre-commit run --all-files`)
- [ ] 所有測試通過 (`uv run pytest`)
- [ ] 類型檢查通過 (`uv run mypy autocrud`)
- [ ] 測試覆蓋率不降低

### 文檔
- [ ] 添加了必要的文檔字符串
- [ ] 更新了相關文檔
- [ ] 添加了使用示例 (如適用)

### 測試
- [ ] 添加了新功能的測試
- [ ] 修復的 Bug 有對應的回歸測試
- [ ] 測試描述清晰明確

### 提交
- [ ] 提交信息遵循規範
- [ ] PR 描述清晰明確
- [ ] 相關的 Issue 已被引用

## 🎯 近期目標

我們正在尋求以下方面的貢獻：

### 高優先級
- 🔧 **性能優化**：提升大規模數據操作的性能
- 🧪 **測試覆蓋率**：達到 95% 的測試覆蓋率
- 📚 **文檔改進**：更多實際使用案例和最佳實踐

### 中優先級  
- 🌐 **國際化**：多語言支持
- 🔌 **插件系統**：可擴展的插件架構
- 📊 **監控集成**：與 Prometheus、Grafana 集成

### 低優先級
- 🎨 **CLI 工具**：命令行界面
- 🔄 **數據遷移**：版本升級工具
- 📱 **移動端 SDK**：移動應用集成

## 🎉 開始貢獻

準備好開始了嗎？

1. 🍴 Fork 項目
2. 🔧 設置開發環境
3. 🎯 選擇一個 [good first issue](https://github.com/HYChou0515/autocrud/labels/good%20first%20issue)
4. 💻 開始編碼
5. 📤 提交 Pull Request

感謝您的貢獻！每一個貢獻，無論大小，都讓 AutoCRUD 變得更好。 🚀
