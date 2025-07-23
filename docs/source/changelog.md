# 變更日誌

所有重要的專案變更都會記錄在此檔案中。

格式基於 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，並且本專案遵循 [語義化版本](https://semver.org/lang/zh-CN/)。

## [未發布]

### 新增
- 無

### 變更
- 無

### 修復
- 無

### 移除
- 無

## [0.1.0] - 2025-07-23

### 新增
- 🎉 **初始版本發布**
- ✨ **核心 CRUD 功能**：
  - `AutoCRUD` 類，支援基本的建立、讀取、更新、刪除操作
  - 自動 ID 產生（UUID4）
  - 資料驗證和轉換
- 📦 **多種資料模型支援**：
  - Python Dataclass
  - Pydantic 模型
  - TypedDict
- 💾 **儲存後端**：
  - `MemoryStorage`：內儲存存，適用於開發和測試
  - `DiskStorage`：磁碟持久化儲存
- 🔧 **多種序列化格式**：
  - JSON（預設）
  - Pickle
  - MessagePack
- 🚀 **FastAPI 整合**：
  - 自動產生 RESTful API routing
  - OpenAPI/Swagger 檔案產生
  - 類型安全的請求/響應模型
- 🔄 **多模型支援**：
  - `MultiModelAutoCRUD` 類
  - 支援在單個應用中管理多個不同的資料模型
  - 自動資源名稱產生（複數化）
- 🎯 **API URL 自訂**：
  - 支援複數/單數形式選擇
  - 完全自訂資源名稱
  - 靈活的routing設定
- ✅ **全面測試覆蓋**：
  - 84 個測試用例
  - 89% 測試覆蓋率
  - 支援 pytest 測試框架
- 📚 **完整檔案**：
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
multi_crud.register_model(User)  # /api/v1/users
multi_crud.register_model(Product, use_plural=False)  # /api/v1/product

# 產生 FastAPI 應用
app = multi_crud.create_fastapi_app()
```

### 支援的 Python 版本
- Python 3.8+

### 主要 dependency
- FastAPI >= 0.100.0
- Pydantic >= 2.0.0
- dependency-injector >= 4.0.0

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
