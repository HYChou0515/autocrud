# 變更日誌

所有重要的項目變更都會記錄在此文件中。

格式基於 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，並且本項目遵循 [語義化版本](https://semver.org/lang/zh-CN/)。

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
  - `AutoCRUD` 類，支持基本的創建、讀取、更新、刪除操作
  - 自動 ID 生成（UUID4）
  - 數據驗證和轉換
- 📦 **多種數據模型支持**：
  - Python Dataclass
  - Pydantic 模型
  - TypedDict
- 💾 **存儲後端**：
  - `MemoryStorage`：內存存儲，適用於開發和測試
  - `DiskStorage`：磁碟持久化存儲
- 🔧 **多種序列化格式**：
  - JSON（默認）
  - Pickle
  - MessagePack
- 🚀 **FastAPI 集成**：
  - 自動生成 RESTful API 路由
  - OpenAPI/Swagger 文檔生成
  - 類型安全的請求/響應模型
- 🔄 **多模型支持**：
  - `MultiModelAutoCRUD` 類
  - 支持在單個應用中管理多個不同的數據模型
  - 自動資源名稱生成（複數化）
- 🎯 **API URL 自定義**：
  - 支持複數/單數形式選擇
  - 完全自定義資源名稱
  - 靈活的路由配置
- ✅ **全面測試覆蓋**：
  - 84 個測試用例
  - 89% 測試覆蓋率
  - 支持 pytest 測試框架
- 📚 **完整文檔**：
  - 用戶指南和 API 參考
  - 豐富的使用示例
  - 快速入門教程

### 技術特性
- **依賴注入**：使用 `dependency-injector` 進行組件管理
- **類型提示**：完整的 Python 類型註解支持
- **錯誤處理**：自定義異常類型和錯誤處理
- **代碼質量**：使用 Ruff 進行代碼檢查和格式化
- **靈活架構**：模塊化設計，易於擴展

### API 端點
每個註冊的模型自動生成以下 RESTful 端點：
- `GET /{resource}` - 列出所有項目
- `POST /{resource}` - 創建新項目
- `GET /{resource}/{id}` - 獲取特定項目
- `PUT /{resource}/{id}` - 更新項目
- `DELETE /{resource}/{id}` - 刪除項目

### 使用示例
```python
from autocrud import MultiModelAutoCRUD
from autocrud.storage import MemoryStorage

# 創建多模型 CRUD 系統
storage = MemoryStorage()
multi_crud = MultiModelAutoCRUD(storage)

# 註冊模型
multi_crud.register_model(User)  # /api/v1/users
multi_crud.register_model(Product, use_plural=False)  # /api/v1/product

# 生成 FastAPI 應用
app = multi_crud.create_fastapi_app()
```

### 支援的 Python 版本
- Python 3.8+

### 主要依賴
- FastAPI >= 0.100.0
- Pydantic >= 2.0.0
- dependency-injector >= 4.0.0

---

## 版本說明

### 版本號格式
- **主版本號**：不兼容的 API 變更
- **次版本號**：向後兼容的功能新增
- **修訂版本號**：向後兼容的問題修正

### 變更類型
- **新增**：新功能
- **變更**：現有功能的變更
- **棄用**：即將移除的功能
- **移除**：已移除的功能
- **修復**：錯誤修復
- **安全**：安全相關的變更
