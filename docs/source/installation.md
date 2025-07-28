# 安裝指南

# 安裝指南

## 🎯 快速開始

AutoCRUD 設計為開箱即用，讓你快速開始構建 REST API。

### 快速安裝

```bash
pip install autocrud
```

**開始使用：**

```python
from autocrud import AutoCRUD
from dataclasses import dataclass

@dataclass
class User:
    id: str
    name: str
    email: str

# 簡單設定
crud = AutoCRUD()
crud.register_model(User)
app = crud.create_fastapi_app(title="我的 API")

# 執行: uvicorn main:app --reload
# 訪問: http://localhost:8000/docs
```

## 系統需求

- **Python 3.11+** - 支援現代 Python 特性
- **pip** 或 **uv** (推薦) - 套件管理工具

## 🚀 推薦安裝方式

### 使用 uv (推薦)

uv 是快速的 Python 套件管理器，適合現代 Python 開發：

```bash
# 安裝 uv（如果還沒有）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 安裝 AutoCRUD
uv add autocrud
```

### 使用傳統 pip

```bash
pip install autocrud
```

## 可選功能安裝

AutoCRUD 採用模組化設計，你可以根據需求安裝額外功能：

### FastAPI 支援（預設已包含）

AutoCRUD 的核心功能是自動生成 REST API，FastAPI 支援已經內建：

```bash
# 如需要額外的 ASGI 伺服器功能
uv add uvicorn[standard]  # 包含額外的效能最佳化
```

### MessagePack 高效序列化

對於需要高效能資料序列化的場景：

```bash
uv add msgpack
```

### Pydantic 驗證

增強的資料驗證支援：

```bash
uv add pydantic[email]  # 包含 email 驗證
```

## 開發依賴套件

如果你想參與開發或執行測試，可以安裝開發依賴套件：

```bash
# 使用 uv (推薦)
git clone https://github.com/HYChou0515/autocrud.git
cd autocrud
uv sync --dev

# 使用 pip
git clone https://github.com/HYChou0515/autocrud.git
cd autocrud
pip install -e .[dev]
```

開發依賴包含：
- pytest (測試框架)
- pytest-asyncio (非同步測試)
- black (程式碼格式化)
- ruff (程式碼檢查)
- mypy (類型檢查)
- sphinx (文檔產生)

### 開發工具

用於測試和程式碼品質檢查：

```bash
uv add --dev pytest coverage ruff
```

### 文件產生

用於產生文件：

```bash
uv add --dev sphinx myst-parser furo sphinx-autodoc-typehints
```

## 驗證安裝

建立一個簡單的測試文件來驗證安裝：

```python
# test_installation.py
from autocrud import AutoCRUD
from autocrud.storage import MemoryStorage
from dataclasses import dataclass

@dataclass
class TestModel:
    id: str
    name: str
    value: int

def test_basic_functionality():
    # 測試多模型系統
    crud = AutoCRUD()
    crud.register_model(TestModel)
    
    # 測試建立
    user_id = crud.create("testmodels", {"name": "test", "value": 42})
    item = crud.get("testmodels", user_id)
    
    assert item["name"] == "test"
    assert item["value"] == 42
    
    print("✅ AutoCRUD 安裝成功！")

if __name__ == "__main__":
    test_basic_functionality()
```

執行測試：

```bash
python test_installation.py
```

如果看到 "✅ AutoCRUD 安裝成功！"，說明安裝正確。

## 故障排除

### 常見問題

**Q: 導入錯誤 "No module named 'autocrud'"**

A: 確保你在正確的 Python 環境中安裝了包：

```bash
# 檢查當前環境
python -c "import sys; print(sys.executable)"

# 重新安裝
uv add autocrud
```

**Q: FastAPI 相關錯誤**

A: 確保安裝了 FastAPI 和 Uvicorn：

```bash
uv add fastapi uvicorn
```

**Q: 序列化錯誤**

A: 根據需要安裝序列化 dependency：

```bash
# MessagePack 支援
uv add msgpack
```

### 取得幫助

如果遇到問題，可以：

1. 查看 [GitHub Issues](https://github.com/HYChou0515/autocrud/issues)
2. 閱讀 [使用者指南](user_guide.md) 取得更多信息
3. 查看 [範例](examples.md) 了解常見用法
