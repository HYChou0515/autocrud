# MyPy Type Checking Support

本專案已啟用 mypy 類型檢查支援，幫助開發者在編譯時期發現類型錯誤。

## 快速開始

### 執行類型檢查

```bash
# 使用 make 命令
make typecheck

# 或直接使用 uv
uv run mypy autocrud
```

### 整合到開發流程

```bash
# 完整的程式碼品質檢查（包含 mypy）
make quality

# CI/CD 流程（包含 mypy）
make ci
```

## 配置說明

mypy 的配置位於 [pyproject.toml](../pyproject.toml) 的 `[tool.mypy]` 區塊。

### 核心配置

- **Python 版本**: 3.11+
- **嚴格度**: 中等（逐步啟用嚴格檢查）
- **檢查範圍**: `autocrud/` 目錄下的所有 Python 檔案

### 特殊處理

由於使用了 `msgspec` 的動態特性（如 `defstruct`），某些模組啟用了較寬鬆的檢查：

- `autocrud.types`: 允許動態類型定義
- `autocrud.resource_manager.partial`: 允許動態欄位操作
- `autocrud.resource_manager.data_converter`: 允許泛型轉換

### 第三方套件

以下第三方套件缺少類型標註，已設定為忽略：

- msgpack
- jsonpatch
- jsonpointer
- xxhash
- more_itertools
- qqabc
- strawberry
- pika
- boto3
- botocore
- magic

## PEP 561 支援

本專案包含 `autocrud/py.typed` 標記檔案，符合 [PEP 561](https://www.python.org/dev/peps/pep-0561/) 規範，這表示：

1. **使用者可以進行類型檢查**: 安裝 autocrud 後，mypy 可以檢查使用者程式碼中對 autocrud 的使用
2. **IDE 支援**: VS Code、PyCharm 等 IDE 可以提供更好的自動完成和類型提示
3. **更好的文檔**: 類型標註本身就是很好的 API 文檔

## 當前狀態

截至目前（2026-01-14），專案有 **397 個 mypy 錯誤**，分布在 43 個檔案中。

### 錯誤分布

主要錯誤類型：

1. `no-untyped-def` (67): 缺少類型標註的函數定義
2. `assignment` (61): 賦值類型不匹配
3. `arg-type` (61): 參數類型不匹配
4. `attr-defined` (46): 屬性未定義
5. `valid-type` (36): 無效的類型定義

### 改進計畫

我們正在逐步改進類型標註：

1. ✅ 建立 mypy 配置和基礎設施
2. ✅ 標記套件為 typed package (PEP 561)
3. 🔄 逐步修復常見錯誤類型
4. 📅 啟用更嚴格的檢查選項
5. 📅 達到零錯誤目標

## 開發指南

### 撰寫類型安全的程式碼

```python
from msgspec import Struct
from typing import Generic, TypeVar

T = TypeVar('T')

class MyModel(Struct):
    name: str
    age: int
    tags: list[str] = []

def process_data(data: MyModel) -> dict[str, str]:
    return {"name": data.name, "age_str": str(data.age)}
```

### 使用 `msgspec.Struct` 而非 Pydantic

AutoCRUD 專為 `msgspec` 優化：

```python
# ✅ 正確
from msgspec import Struct, UNSET, UnsetType

class User(Struct):
    name: str
    email: str | None = None
    active: bool | UnsetType = UNSET

# ❌ 錯誤
from pydantic import BaseModel

class User(BaseModel):  # 不要使用 Pydantic
    name: str
```

### 忽略特定錯誤

如果某行程式碼因 mypy 限制而無法修復：

```python
result = complex_dynamic_operation()  # type: ignore[attr-defined]
```

但請盡量避免使用 `# type: ignore`，優先修改程式碼以符合類型檢查。

## 常見問題

### Q: 為什麼不啟用 `disallow_untyped_defs`？

A: 由於現有程式碼庫較大，我們採取漸進式策略。當前啟用了 `disallow_incomplete_defs`，確保有標註的函數必須完整標註所有參數和返回值。

### Q: msgspec 的動態特性如何處理？

A: 使用 `defstruct` 等動態特性的模組已在 `pyproject.toml` 中配置為允許特定錯誤類型，平衡了類型安全和程式碼靈活性。

### Q: 如何在 CI 中整合 mypy？

A: 使用 `make ci` 命令即可，它會執行 ruff check、mypy typecheck 和完整測試。

## 參考資源

- [mypy 官方文檔](https://mypy.readthedocs.io/)
- [PEP 561 -- Distributing and Packaging Type Information](https://www.python.org/dev/peps/pep-0561/)
- [msgspec 文檔](https://jcristharif.com/msgspec/)
- [Type Hints Cheat Sheet](https://mypy.readthedocs.io/en/stable/cheat_sheet_py3.html)
