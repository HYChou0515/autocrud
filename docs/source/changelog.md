# 變更日誌

所有重要的專案變更都會記錄在此檔案中。

格式基於 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，並且本專案遵循 [語義化版本](https://semver.org/lang/zh-CN/)。

## [0.2.0] - 2025-07-28

### 新增
- 🧩 **插件系統**：
  - `BaseRoutePlugin` 基類用於創建自訂路由
  - `PluginManager` 管理插件註冊和執行
  - 預設插件：create, get, update, delete, count, list
  - 支援插件優先級和路由覆蓋
- ⚡ **高級查詢功能**：
  - `ListQueryParams` 支援分頁、排序、時間範圍查詢
  - `ListResult` 包含分頁資訊的查詢結果
  - 支援 `created_by` 和 `updated_by` 用戶過濾
  - `DateTimeRange` 和 `SortOrder` 類型支援
- 🔧 **路由配置增強**：
  - `RouteOptions` 新增用於更細粒度的路由控制
  - 增強的路由配置系統

### 變更
- 🔄 **重要 API 變更**：
  - `list_all()` 方法現在支援 `ListQueryParams` 參數進行高級查詢
  - 新增 `list_with_params()` 方法提供分頁結果
  - `SingleModelCRUD` 建構函數新增 `default_values` 參數
  - `SchemaAnalyzer` 現在接受 `default_values` 參數
- 🎯 **資源名稱系統改進**：
  - 新增 `ResourceNameStyle` 枚舉支援不同命名風格
  - 更靈活的複數化選項
- 📝 **更好的類型支援**：
  - `SingleModelCRUD` 現在是泛型類 `SingleModelCRUD[T]`
  - 改進的類型註解和 IDE 支援

### 修復
- 🐛 修復 Pydantic v1/v2 相容性問題
- 🔧 改進錯誤處理和異常訊息
- 📦 修復序列化器的邊界情況
- 🎯 修復 FastAPI 路由生成的優先級問題

## [0.1.0] - 2025-07-23

### 新增
- 🎉 **初始版本發布**
- ✨ **核心 CRUD 功能**：
  - `SingleModelCRUD` 類，支援基本的建立、讀取、更新、刪除操作
  - 自動 ID 產生（UUID4）
  - 資料驗證和轉換
- 📦 **多種資料模型支援**：
  - Python Dataclass
  - Pydantic 模型
  - TypedDict
- 💾 **儲存後端**：
  - `MemoryStorage`：記憶體儲存，適用於開發和測試
  - `DiskStorage`：硬碟持久化儲存
- 🔧 **多種序列化格式**：
  - JSON（預設）
  - Pickle
  - MessagePack
- 🚀 **FastAPI 整合**：
  - 自動產生 RESTful API 路由
  - OpenAPI/Swagger 文件產生
  - 類型安全的請求/響應模型
- 🔄 **多模型支援**：
  - `MultiModelAutoCRUD` 類（後來重命名為 `AutoCRUD`）
  - 支援在單個應用中管理多個不同的資料模型
  - 自動資源名稱產生（複數化）
- 🎯 **API URL 自訂**：
  - 支援複數/單數形式選擇
  - 完全自訂資源名稱
  - 靈活的routing設定
- 📊 **元資料管理**：
  - `MetadataConfig` 配置自動時間戳和用戶追蹤
  - 自動添加 `created_time`, `updated_time`, `created_by`, `updated_by`
  - 可自訂欄位名稱
- 🔄 **高級更新系統**：
  - `AdvancedUpdater` 支援原子操作
  - 多種更新操作：`set_value`, `list_add`, `list_remove`, `dict_update`
  - 防止資料競爭和不一致狀態
- 🏭 **儲存工廠系統**：
  - `StorageFactory` 抽象工廠介面
  - `DefaultStorageFactory` 預設實作
  - 支援為不同資源創建獨立的儲存後端
- 🔧 **路由配置系統**：
  - `RouteConfig` 控制路由行為
  - 支援啟用/禁用特定 CRUD 操作
- 📋 **Schema 分析器**：
  - `SchemaAnalyzer` 自動分析模型結構
  - 支援預設值和必要欄位檢測
  - ID 欄位自動識別
- ✅ **全面測試覆蓋**：
  - 多個測試用例覆蓋核心功能
  - 支援 pytest 測試框架
- 📚 **完整文檔**：
  - 使用者指南和 API 參考
  - 豐富的使用範例
  - 快速入門教程

### 技術特性
- **dependency injection**：使用 `dependency-injector` 進行組件管理
- **類型提示**：完整的 Python 類型註解支援
- **錯誤處理**：自訂異常類型和錯誤處理
- **程式碼品質**：使用 Ruff 進行程式碼檢查和格式化
- **靈活架構**：模塊化設計，易於擴展

### API 端點
每個註冊的模型自動產生以下 RESTful 端點：
- `GET /{resource}` - 列出所有專案
- `POST /{resource}` - 建立新專案
- `GET /{resource}/{id}` - 取得特定專案
- `PUT /{resource}/{id}` - 更新專案
- `DELETE /{resource}/{id}` - 刪除專案

### 使用範例
```python
from autocrud import MultiModelAutoCRUD
from autocrud.storage import MemoryStorage

# 建立多模型 CRUD 系統
storage = MemoryStorage()
multi_crud = MultiModelAutoCRUD(storage)

# 註冊模型
multi_crud.register_model(User)  # /users
multi_crud.register_model(Product, use_plural=False)  # /product

# 產生 FastAPI 應用
app = multi_crud.create_fastapi_app()
```

### 支援的 Python 版本
- Python 3.11+

### 主要 dependency
- FastAPI >= 0.116.1
- Pydantic >= 2.11.7
- dependency-injector >= 4.48.1
- msgpack >= 1.1.1

---

## 版本說明

### 版本號格式
- **主版本號**：不相容的 API 變更
- **次版本號**：向後相容的功能新增
- **修訂版本號**：向後相容的問題修正

### 變更類型
- **新增**：新功能
- **變更**：現有功能的變更
- **棄用**：即將移除的功能
- **移除**：已移除的功能
- **修復**：錯誤修復
- **安全**：安全相關的變更
