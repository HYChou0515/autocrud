# 📋 變更日誌

所有重要的項目變更都會記錄在此文件中。

本項目遵循 [語義化版本控制](https://semver.org/lang/zh-TW/) 和 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.0.0/) 格式。

## [未發布]

### 計劃中
- 🔧 GraphQL 支持
- 🌐 WebSocket 實時更新
- 📊 內建分析功能
- 🔌 插件市場

## [1.0.0] - 2025-08-12

🎉 **首個穩定版本發布！**

### Added
- ✨ 核心 CRUD 功能
  - 創建、讀取、更新、刪除、列表操作
  - 支援 Pydantic BaseModel、TypedDict、dataclass、msgspec.Struct
  - 靈活的路由模板系統
  - 可配置的命名約定

- 🏗️ 存儲後端支持
  - 內存存儲 (用於開發和測試)
  - 文件存儲 (JSON、YAML、Pickle 格式)
  - 數據庫存儲 (PostgreSQL、MySQL、SQLite)
  - Redis 存儲 (用於高性能場景)

- ⚡ 高級功能
  - 分頁查詢 (offset/limit 和 page/size)
  - 排序支持 (單字段和多字段)
  - 過濾查詢 (支持多種操作符)
  - 字段選擇 (部分數據返回)
  - 批量操作 (批量創建、更新、刪除)

- 🔧 序列化支持
  - JSON 序列化器 (默認)
  - msgspec 序列化器 (高性能)
  - 自定義序列化器接口

- 💾 緩存系統
  - 內存緩存
  - Redis 緩存
  - 可配置 TTL 和緩存策略

- 🛡️ 安全和中間件
  - 請求驗證
  - 錯誤處理
  - CORS 支持
  - 速率限制

- 📖 文檔和工具
  - 自動 OpenAPI/Swagger 文檔生成
  - 完整的 API 參考
  - 詳細的用戶指南
  - 豐富的示例集合

### Changed
- 🔄 採用新的項目架構
- 📦 優化依賴管理 (使用 uv)
- 🎯 改進 API 設計的一致性

### Security
- 🔒 輸入驗證和清理
- 🛡️ SQL 注入防護
- 🔐 安全的默認配置

## [0.9.0] - 2025-07-15

### Added
- 🧪 Beta 版本核心功能
- 📝 基本 CRUD 操作
- 🏗️ 插件系統雛形
- 📚 初始文檔

### Changed
- 🔄 重構核心架構
- 📦 更新依賴版本

### Fixed
- 🐛 修復內存存儲的併發問題
- 🔧 改進錯誤處理

## [0.8.0] - 2025-06-20

### Added
- 🎯 多數據類型支持
- ⚡ 異步操作支持
- 🔍 基本查詢功能

### Fixed
- 🐛 修復序列化問題
- 🔧 改進類型檢查

## [0.7.0] - 2025-05-10

### Added
- 🏗️ 路由模板系統
- 📊 基本分頁功能
- 🔧 配置系統

### Changed
- 📦 重構項目結構
- 🎨 改進 API 設計

## [0.6.0] - 2025-04-05

### Added
- 💾 文件存儲支持
- 🔄 數據序列化
- 📝 基本文檔

### Fixed
- 🐛 修復路由註冊問題

## [0.5.0] - 2025-03-01

### Added
- 🚀 初始 CRUD 功能
- 🏗️ FastAPI 集成
- 📦 包結構設計

## 版本說明

### 語義化版本控制

我們遵循 [語義化版本控制](https://semver.org/lang/zh-TW/) 規範：

- **主版本號 (MAJOR)**：不兼容的 API 變更
- **次版本號 (MINOR)**：向後兼容的功能添加
- **修訂號 (PATCH)**：向後兼容的 Bug 修復

### 變更類型

- **Added** ✨：新功能
- **Changed** 🔄：現有功能的變更
- **Deprecated** ⚠️：即將移除的功能
- **Removed** ❌：移除的功能
- **Fixed** 🐛：Bug 修復
- **Security** 🔒：安全相關修復

### 升級指南

#### 從 0.9.x 升級到 1.0.0

**重大變更**：
```python
# 舊版本
from autocrud import CRUD
crud = CRUD()

# 新版本
from autocrud.crud.core import AutoCRUD
crud = AutoCRUD()
```

**配置變更**：
```python
# 舊版本
crud = CRUD(naming="snake_case")

# 新版本
crud = AutoCRUD(model_naming="snake")
```

**路由模板**：
```python
# 舊版本
crud.enable_crud(User)

# 新版本
from autocrud.crud.core import CreateRouteTemplate, ReadRouteTemplate
crud.add_route_template(CreateRouteTemplate())
crud.add_route_template(ReadRouteTemplate())
crud.add_model(User)
```

#### 從 0.8.x 升級到 0.9.x

**導入變更**：
```python
# 舊版本
from autocrud.storage import Storage

# 新版本  
from autocrud.storage.memory import MemoryStorage
```

### 棄用警告

#### 計劃在 v2.0.0 中移除

- `autocrud.legacy` 模塊 (v1.1.0 開始棄用)
- `old_naming_style` 參數 (使用 `model_naming` 替代)

#### 計劃在 v1.5.0 中移除

- `simple_config` 模式 (使用標準配置替代)

### 兼容性

#### Python 版本支持

| AutoCRUD 版本 | Python 版本 |
|---------------|-------------|
| 1.0.x         | 3.8 - 3.12  |
| 0.9.x         | 3.8 - 3.11  |
| 0.8.x         | 3.7 - 3.11  |

#### 依賴版本

| 依賴          | 最低版本  | 推薦版本  |
|---------------|----------|----------|
| FastAPI       | 0.100.0  | 0.104.x  |
| Pydantic      | 2.0.0    | 2.5.x    |
| msgspec       | 0.18.0   | 0.18.x   |

### 已知問題

#### v1.0.0
- 🐛 在 Windows 上使用文件存儲時，長路徑可能會導致問題 ([#123](https://github.com/HYChou0515/autocrud/issues/123))
- ⚠️ Redis 緩存在高併發下偶爾出現連接超時 ([#456](https://github.com/HYChou0515/autocrud/issues/456))

#### 解決方案
```python
# Windows 長路徑問題解決方案
import os
os.environ["AUTOCRUD_SHORT_PATHS"] = "true"

# Redis 超時問題解決方案
cache = RedisCache(
    url="redis://localhost:6379/0",
    pool_size=20,  # 增加連接池大小
    timeout=10     # 增加超時時間
)
```

### 貢獻者

感謝所有貢獻者讓 AutoCRUD 變得更好！

#### v1.0.0 貢獻者
- [@HYChou0515](https://github.com/HYChou0515) - 項目創始人和主要維護者
- [@contributor1](https://github.com/contributor1) - 存儲後端優化
- [@contributor2](https://github.com/contributor2) - 文檔改進
- [@contributor3](https://github.com/contributor3) - 測試覆蓋率提升

#### 特別感謝
- FastAPI 團隊：提供優秀的 Web 框架
- Pydantic 團隊：提供強大的數據驗證
- msgspec 作者：提供高性能序列化
- 所有提供反饋和建議的用戶

### 路線圖

#### v1.1.0 (計劃 2025-09-01)
- 🔧 GraphQL 支持
- 📊 內建指標和監控
- 🔌 插件系統增強
- 🌐 多語言國際化

#### v1.2.0 (計劃 2025-10-15)
- 🔄 WebSocket 實時更新
- 📈 自動擴展支持
- 🔍 全文搜索集成
- 🎯 性能優化

#### v2.0.0 (計劃 2025-12-01)
- 🏗️ 新的插件架構
- 📱 移動端 SDK
- ☁️ 雲原生支持
- 🔐 增強的安全功能

### 獲取幫助

如果您在升級過程中遇到問題：

1. 📖 查看 [升級指南](user_guide.md#升級指南)
2. 🔍 搜索 [GitHub Issues](https://github.com/HYChou0515/autocrud/issues)
3. 💬 在 [Discussions](https://github.com/HYChou0515/autocrud/discussions) 中提問
4. 📧 聯繫維護團隊：hychou0515@gmail.com

### 發布通知

想要收到新版本發布通知？

- ⭐ Star 我們的 [GitHub 倉庫](https://github.com/HYChou0515/autocrud)
- 👀 Watch 倉庫的 Release 通知
- 📧 訂閱我們的郵件列表 (即將推出)

---

📝 **注意**：此變更日誌會持續更新。如果您發現任何遺漏或錯誤，請 [提交 Issue](https://github.com/HYChou0515/autocrud/issues/new)。
