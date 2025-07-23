# 安裝指南

## 系統要求

- Python 3.8+
- pip 或 uv (推薦)

## 使用 pip 安裝

```bash
pip install autocrud
```

## 使用 uv 安裝 (推薦)

```bash
uv add autocrud
```

## 開發依賴

如果你想參與開發或運行測試，可以安裝開發依賴：

```bash
# 使用 uv
uv add --dev autocrud[dev]

# 使用 pip
pip install autocrud[dev]
```

## 可選依賴

### FastAPI 支持

默認已包含 FastAPI 支持，用於自動生成 API：

```bash
uv add fastapi uvicorn
```

### MessagePack 序列化

如果需要使用 MessagePack 序列化：

```bash
uv add msgpack
```

### 開發工具

用於測試和代碼質量檢查：

```bash
uv add --dev pytest coverage ruff
```

### 文檔生成

用於生成文檔：

```bash
uv add --dev sphinx myst-parser furo sphinx-autodoc-typehints
```

## 驗證安裝

創建一個簡單的測試文件來驗證安裝：

```python
# test_installation.py
from autocrud import AutoCRUD, MultiModelAutoCRUD
from autocrud.storage import MemoryStorage
from dataclasses import dataclass

@dataclass
class TestModel:
    name: str
    value: int

def test_basic_functionality():
    storage = MemoryStorage()
    crud = AutoCRUD(model=TestModel, storage=storage)
    
    # 測試創建
    item = crud.create({"name": "test", "value": 42})
    assert item["name"] == "test"
    assert item["value"] == 42
    
    print("✅ AutoCRUD 安裝成功！")

if __name__ == "__main__":
    test_basic_functionality()
```

運行測試：

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

A: 根據需要安裝序列化依賴：

```bash
# MessagePack 支持
uv add msgpack
```

### 獲取幫助

如果遇到問題，可以：

1. 查看 [GitHub Issues](https://github.com/your-repo/autocrud/issues)
2. 閱讀 [用戶指南](user_guide.md) 獲取更多信息
3. 查看 [示例](examples.md) 了解常見用法
