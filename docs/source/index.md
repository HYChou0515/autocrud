# AutoCRUD 文檔

```{include} ../../README.md
:start-after: # AutoCRUD
:end-before: ## 📖 文檔
```

## 快速導航

::::{grid} 2 2 2 3
:gutter: 2

:::{grid-item-card} 🚀 快速開始
:link: quickstart
:link-type: doc

立即開始使用 AutoCRUD，5 分鐘內建立您的第一個 CRUD API
:::

:::{grid-item-card} 📖 用戶指南
:link: user_guide
:link-type: doc

深入了解 AutoCRUD 的功能和最佳實踐
:::

:::{grid-item-card} 🔧 API 參考
:link: api_reference
:link-type: doc

完整的 API 文檔和類型定義
:::

:::{grid-item-card} 💡 示例集合
:link: examples
:link-type: doc

豐富的實際使用案例和代碼示例
:::

:::{grid-item-card} 🛠️ 安裝指南
:link: installation
:link-type: doc

詳細的安裝和配置說明
:::

:::{grid-item-card} 🤝 貢獻指南
:link: contributing
:link-type: doc

了解如何為 AutoCRUD 做出貢獻
:::

::::

## 主要特性

- 🎯 **多數據類型支持**: TypedDict、Pydantic BaseModel、dataclass、msgspec.Struct
- ⚡ **零配置**: 一行代碼生成完整 CRUD API
- 🔧 **高度可定制**: 靈活的路由模板和命名約定
- 📚 **自動文檔**: 集成 Swagger/OpenAPI 文檔
- 🏎️ **高性能**: 基於 FastAPI 和 msgspec
- 🔒 **類型安全**: 完整的 TypeScript 風格類型檢查
- 🧩 **插件系統**: 可擴展的路由插件系統，支援自定義端點
- ⚡ **高級功能**: 支援複雜查詢、排序、分頁、時間戳管理
- 🔄 **高級更新**: 支援原子操作和複雜的資料更新
- 📖 **自動文檔**: 自動產生 OpenAPI/Swagger 文檔

```{toctree}
:maxdepth: 2
:caption: 內容:

quickstart
installation
user_guide
api_reference
examples
contributing
changelog
```

## 快速示例

```python
from pydantic import BaseModel
from fastapi import FastAPI, APIRouter
from autocrud.crud.core import AutoCRUD, CreateRouteTemplate, ReadRouteTemplate

# 定義數據模型
class User(BaseModel):
    name: str
    email: str
    age: int = None

# 創建 AutoCRUD 實例
crud = AutoCRUD(model_naming="kebab")
crud.add_route_template(CreateRouteTemplate())
crud.add_route_template(ReadRouteTemplate())

# 註冊模型 - 就這麼簡單！
crud.add_model(User)

# 集成到 FastAPI
app = FastAPI(title="User API")
router = APIRouter()
crud.apply(router)
app.include_router(router)
```

現在您有了一個完整的 CRUD API：
- `POST /user` - 創建用戶
- `GET /user/{id}` - 獲取用戶

## 社區與支持

- 📖 [GitHub 倉庫](https://github.com/HYChou0515/autocrud)
- 🐛 [問題追蹤](https://github.com/HYChou0515/autocrud/issues)
- 💬 [討論區](https://github.com/HYChou0515/autocrud/discussions)
- 📧 [郵件支持](mailto:support@autocrud.dev)

## 許可證

AutoCRUD 在 MIT 許可證下發布。詳見 [LICENSE](https://github.com/HYChou0515/autocrud/blob/master/LICENSE)。
