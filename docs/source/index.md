# AutoCRUD 文檔

歡迎來到 AutoCRUD 的文檔！

**AutoCRUD 是一個 Python 函式庫，能夠從你的資料模型自動產生完整的、生產就緒的 REST API。**

只需定義資料模型，AutoCRUD 為你產生包含驗證、文檔、分頁、查詢的完整 FastAPI 應用。這正是核心技術價值 - 自動化 API 路由產生，而不只是簡單的程式化 CRUD 操作。

## 🎯 核心價值

**從資料模型到完整 REST API：**
```python
from autocrud import AutoCRUD
from dataclasses import dataclass

@dataclass
class User:
    id: str
    name: str
    email: str

crud = AutoCRUD()
crud.register_model(User)  # 完整 REST API 自動生成
app = crud.create_fastapi_app(title="我的 API")
```

**主要功能：**
- 🌐 **完整 REST API**: 所有 CRUD 端點 + 查詢/分頁/排序
- 📚 **自動 Swagger 文檔**: 訪問 `/docs` 查看交互式 API 文檔  
- ✅ **自動驗證**: 請求/響應驗證和錯誤處理
- 🚀 **快速部署**: 可部署到任何 FastAPI 支援的平台

## 🌟 主要特性

- 🎯 **自動 API 路由產生**: 從資料模型直接產生 REST API
- 🔄 **多模型支援**: 管理多個業務實體的 API 系統
- 📦 **多格式支援**: Pydantic、Dataclass、TypedDict 整合
- 💾 **持久化存儲**: 從原型到生產環境的儲存方案
- 🔧 **多種序列化**: JSON、Pickle、MessagePack 選擇
- ⚙️ **高度可配置**: 資源命名、ID 策略、路由設定
- 🧩 **插件系統**: 可擴展的路由插件架構
- ⚡ **進階查詢**: 複雜查詢、排序、分頁、時間篩選
- 🔄 **智能更新**: 原子操作和資料更新邏輯
- 📖 **自動文檔**: OpenAPI/Swagger 文檔自動同步
- 💻 **程式化控制**: 完整的程式化 CRUD 操作介面

## 🌟 主要特性

- 🎯 **自動 API 路由產生**: 這是核心技術價值！從資料模型直接產生生產級 REST API
- 🔄 **企業級多模型支援**: 一次管理多個業務實體的完整 API 生態系統
- 📦 **全格式支援**: Pydantic、Dataclass、TypedDict 無縫整合
- 💾 **生產級持久化**: 從原型到生產環境的儲存解決方案
- 🔧 **企業級序列化**: JSON、Pickle、MessagePack 多重選擇
- ⚙️ **高度可客製化**: 資源命名、ID 策略、路由配置完全可控
- 🧩 **可擴展插件系統**: 當自動生成不夠時的完整擴展能力
- ⚡ **進階查詢 API**: 複雜查詢、排序、分頁、時間範圍篩選
- 🔄 **智能更新機制**: 原子操作和複雜資料更新邏輯
- 📖 **零維護文檔**: 完整 OpenAPI/Swagger 文檔自動同步
- 💻 **程式化後備**: 當 API 不夠用時，完整的程式化 CRUD 控制到 AutoCRUD 的文檔！

AutoCRUD 是一個強大的 Python 函式庫，能夠自動為你的資料模型產生完整的 CRUD (建立、讀取、更新、刪除) API。支援多種資料模型格式、儲存後端、序列化方式和插件系統。

## 主要特性

- 🚀 **自動 API 產生**: 基於資料模型自動產生 FastAPI 路由
- 🔄 **多模型支援**: 支援在單個應用中管理多個不同的資料模型
- 📦 **多種資料格式**: 支援 Pydantic、Dataclass、TypedDict
- 💾 **彈性儲存**: 支援記憶體儲存和硬碟持久化
- 🔧 **多種序列化**: JSON、Pickle、MessagePack
- 🎯 **高度可設定**: 自訂資源名稱、ID 產生器、路由配置等
- 🧩 **插件系統**: 可擴展的路由插件系統，支援自定義端點
- ⚡ **高級功能**: 支援複雜查詢、排序、分頁、時間戳管理
- � **高級更新**: 支援原子操作和複雜的資料更新
- �📖 **自動文檔**: 自動產生 OpenAPI/Swagger 文檔

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

## 索引和表格

- {ref}`genindex`
- {ref}`modindex`
- {ref}`search`
