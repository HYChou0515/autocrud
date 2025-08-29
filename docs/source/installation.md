# 🛠️ 安裝指南

## 📋 系統要求

- **Python**: 3.11+ (根據 pyproject.toml)
- **FastAPI**: 自動安裝為相依套件
- **存儲**: 約 20MB

## 🚀 安裝 AutoCRUD

### pip 安裝

```bash
pip install autocrud
```

### uv 安裝 (推薦)

```bash
# 安裝 uv (如果還沒有)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 安裝 AutoCRUD
uv add autocrud
```

### Poetry 安裝

```bash
poetry add autocrud
```

## ✅ 驗證安裝

創建 `test.py` 檔案：

```python
from autocrud import AutoCRUD
from fastapi import FastAPI
from fastapi.testclient import TestClient
from msgspec import Struct

class Todo(Struct):
    title: str
    completed: bool = False

def main():
    # 建立 AutoCRUD
    crud = AutoCRUD()
    crud.add_model(Todo)
    
    # 建立 FastAPI 應用
    app = FastAPI()
    crud.apply(app)
    
    # 測試 API
    client = TestClient(app)
    
    # 創建一個 todo
    response = client.post("/todo", json={"title": "測試安裝", "completed": False})
    print(f"創建 Todo: {response.status_code}")
    
    # 列出所有 todos
    response = client.get("/todo/data")
    print(f"Todo 列表: {response.json()}")
    
    print("✅ AutoCRUD 安裝成功！")

if __name__ == "__main__":
    main()
```

執行測試：

```bash
python test.py
```

如果看到 "✅ AutoCRUD 安裝成功！" 表示安裝完成。

## 🚀 快速開始開發服務器

使用 AutoCRUD 內建的範例：

```bash
# 運行基本範例
python -m fastapi dev examples/quick_start.py

# 或執行測試
python examples/quick_start.py

# 測試不同資料模型
python examples/quick_start.py dataclass
python examples/quick_start.py typeddict
```

訪問 http://localhost:8000/docs 查看自動生成的 API 文檔。

## 🧩 相依套件

AutoCRUD 會自動安裝：

- `fastapi` (>=0.116.1) - Web 框架
- `msgspec` (>=0.19.0) - 高速序列化
- `jsonpatch` (>=1.33) - JSON Patch 支援
- `dependency-injector` (>=4.48.1) - 相依注入
- `msgpack` (>=1.1.1) - 二進制序列化

## 🔧 開發環境設置

### 從源碼安裝

```bash
# 克隆專案
git clone https://github.com/HYChou0515/autocrud.git
cd autocrud

# 使用 uv 安裝開發環境
uv sync --group dev

# 或使用 pip
pip install -e ".[dev]"
```

### 執行測試

```bash
# 執行所有測試
make test

# 或直接使用 pytest
uv run pytest

# 執行特定測試
uv run pytest tests/test_resource_manager.py
```

### 代碼品質檢查

```bash
# 格式化代碼
make style

# 檢查代碼品質
make check

# 查看所有可用命令
make help
```

## � 建立你的第一個專案

### 基本專案結構

```
my-autocrud-project/
├── main.py          # FastAPI 應用入口
├── models.py        # 資料模型定義
├── requirements.txt # 或 pyproject.toml
└── data/           # 資料存儲目錄 (可選)
```

### main.py 範例

```python
from fastapi import FastAPI
from autocrud import AutoCRUD
from models import User, Product

# 建立 AutoCRUD 實例
crud = AutoCRUD()

# 註冊模型
crud.add_model(User)
crud.add_model(Product)

# 建立 FastAPI 應用
app = FastAPI(title="My AutoCRUD API")

# 應用 CRUD 路由
crud.apply(app)

# 可選：自訂路由
@app.get("/")
async def root():
    return {"message": "AutoCRUD API is running!"}
```

### models.py 範例

```python
from msgspec import Struct
from typing import Optional

class User(Struct):
    name: str
    email: str
    age: Optional[int] = None

class Product(Struct):
    name: str
    price: float
    description: Optional[str] = None
    in_stock: bool = True
```

### 啟動應用

```bash
# 開發模式
python -m fastapi dev main.py

# 生產模式
uvicorn main:app --host 0.0.0.0 --port 8000
```

## 🐛 故障排除

### Python 版本過舊

```bash
# 檢查版本
python --version

# 如果小於 3.11，請升級
pyenv install 3.11
pyenv global 3.11
```

### 相依套件問題

```bash
# 清理 pip 快取
pip cache purge

# 重新安裝
pip uninstall autocrud
pip install autocrud
```

### ImportError 問題

```bash
# 檢查安裝位置
python -c "import autocrud; print(autocrud.__file__)"

# 確認版本
python -c "import autocrud; print(autocrud.__version__)"
```

## � 下一步

安裝完成後，建議：

1. 閱讀 {doc}`quickstart` 學習基本用法
2. 查看 {doc}`examples` 了解進階功能
3. 參考 {doc}`user_guide` 深入了解配置選項
