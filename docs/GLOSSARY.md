# AutoCRUD Translation Glossary / 翻譯術語表

This glossary ensures consistent translation across all documentation.  
本術語表確保所有文檔翻譯的一致性。

---

## 🔧 Core Concepts / 核心概念

| 中文 | English | Notes |
|------|---------|-------|
| 模型驅動 | Model-driven | |
| 自動化 | Automated | |
| 版本控制 | Versioning | |
| 權限 | Permissions | |
| 搜尋 | Search | |
| 快速上手 | Quick Start | |
| 開始使用 | Getting Started | |
| 核心概念 | Core Concepts | |
| 架構概覽 | Architecture Overview | |
| 進階功能 | Advanced Features | |
| 效能測試 | Benchmarks / Performance Tests | |
| 範例 | Examples | |
| 安裝 | Installation | |

---

## 🏗️ Architecture / 架構

| 中文 | English | Notes |
|------|---------|-------|
| 分層式架構 | Layered Architecture | |
| 存取層 | Interface Layer | |
| 邏輯層 | Service Layer | |
| 儲存層 | Persistence Layer | |
| 系統總入口 | Main Entry Point | |
| 混合儲存 | Hybrid Storage | |
| 儲存後端 | Storage Backend | |
| 儲存機制 | Storage Mechanism | |
| 儲存適配器 | Storage Adapter | |
| 資料編解碼 | Data Encoding/Decoding | |
| 去重機制 | Deduplication | |

---

## 📦 Resource Management / 資源管理

| 中文 | English | Notes |
|------|---------|-------|
| 資源 | Resource | |
| 資源管理器 | Resource Manager | Keep as `ResourceManager` in code |
| 資料模型 | Data Model | |
| 資料本體 | Resource Payload / Data Payload | |
| 元資料/中繼資料 | Metadata | |
| 註冊 | Register | |
| 建立 | Create | |
| 讀取 | Read | |
| 更新 | Update | |
| 刪除 | Delete | |
| 軟刪除 | Soft Delete | |
| 硬刪除 | Hard Delete | |
| 還原 | Restore | |
| 備份 | Backup | |

---

## 📜 Versioning / 版本控制

| 中文 | English | Notes |
|------|---------|-------|
| 版本 | Version | |
| 修訂版/版本號 | Revision | |
| 草稿 | Draft | |
| 正式/穩定版 | Stable | |
| 版本歷史 | Revision History | |
| 版本切換 | Switch Revision | |
| 不進版編輯 | In-place Modification (without creating new revision) | |
| 進版 | Create New Revision | |
| 回溯 | Rollback / Revert | |
| 父版本 | Parent Revision | |
| 版本鏈 | Revision Chain | |

---

## 🔄 Migration / 遷移

| 中文 | English | Notes |
|------|---------|-------|
| 遷移 | Migration | |
| 結構變更 | Schema Change | |
| 資料遷移 | Data Migration | |
| 搬遷邏輯 | Migration Logic | |
| 自動升級 | Auto Upgrade | |
| 延遲升級 | Lazy Upgrade | |
| Schema 版本 | Schema Version | |

---

## 🔒 Permissions / 權限

| 中文 | English | Notes |
|------|---------|-------|
| 權限控制 | Permission Control | |
| 權限檢查 | Permission Check | |
| 權限檢查器 | Permission Checker | |
| 權限驗證框架 | Permission Validation Framework | |
| 三層 RBAC | Three-tier RBAC | Global/Model/Resource |
| 全域權限 | Global Permission | |
| 模型權限 | Model Permission | |
| 資源權限 | Resource Permission | |
| 角色 | Role | |
| 存取控制 | Access Control | |
| 自定義檢查器 | Custom Checker | |

---

## 🔔 Events / 事件

| 中文 | English | Notes |
|------|---------|-------|
| 事件 | Event | |
| 事件驅動 | Event-driven | |
| 事件處理器 | Event Handler | |
| 事件管線 | Event Pipeline | |
| 事件廣播器 | Event Broadcaster | |
| 同步 | Synchronous (Sync) | |
| 非同步 | Asynchronous (Async) | |
| 前置處理 | Before Hook / Pre-processing | |
| 後置處理 | After Hook / Post-processing | |
| 成功回調 | OnSuccess Callback | |
| 錯誤回調 | OnError Callback | |

---

## 🛣️ Routes & API / 路由與 API

| 中文 | English | Notes |
|------|---------|-------|
| 路由 | Route | |
| 端點 | Endpoint | |
| 路由模板 | Route Template | |
| 自動生成路由 | Auto-generated Routes | |
| 業務端點 | Business Endpoint | |
| 自定義端點 | Custom Endpoint | |
| 全量更新 | Full Update | PUT |
| 部分更新 | Partial Update | PATCH |
| 列表查詢 | List Query | |
| 分頁 | Pagination | |

---

## 🗄️ Storage / 儲存

| 中文 | English | Notes |
|------|---------|-------|
| 記憶體儲存 | Memory Storage | |
| 磁碟儲存 | Disk Storage | |
| 物件儲存 | Object Storage | S3, etc. |
| 索引 | Index | |
| 索引欄位 | Indexed Field | |
| 元資料儲存 | Meta Store | |
| 資源儲存 | Resource Store | |
| Blob 儲存 | Blob Store | |
| 資料持久化 | Data Persistence | |

---

## 🔍 Query & Search / 查詢與搜尋

| 中文 | English | Notes |
|------|---------|-------|
| 查詢 | Query | |
| 搜尋 | Search | |
| 查詢建構器 | Query Builder | |
| 篩選 | Filter | |
| 排序 | Sort | |
| 條件 | Condition | |
| 運算符 | Operator | |
| 欄位 | Field | |
| 組合條件 | Combined Conditions | |
| 鏈式語法 | Chaining Syntax | |

---

## 🎯 Types & Data / 型別與資料

| 中文 | English | Notes |
|------|---------|-------|
| 型別 | Type | |
| 型別檢查 | Type Checking | |
| 序列化 | Serialization | |
| 反序列化 | Deserialization | |
| 編碼 | Encoding | |
| 解碼 | Decoding | |
| 局部讀取 | Partial Read | |
| 局部更新 | Partial Update | |
| 欄位 | Field | |
| 屬性 | Attribute / Property | |

---

## 📋 UI & Navigation / 介面與導航

| 中文 | English | Notes |
|------|---------|-------|
| 首頁 | Home | |
| 下一步 | Next Steps | |
| 參閱 | See Also | |
| 提示 | Tip | |
| 注意 | Note | |
| 警告 | Warning | |
| 範例 | Example | |
| 說明 | Description | |
| 功能概覽 | Feature Overview | |
| 快速範例 | Quick Example | |

---

## 🔧 Technical Terms / 技術術語 (Keep in English)

These terms should remain in English or be used as-is:

| Term | 中文說明 |
|------|---------|
| `AutoCRUD` | 框架名稱，保持原樣 |
| `ResourceManager` | 類別名稱，保持原樣 |
| `msgspec.Struct` | 類別名稱，保持原樣 |
| `FastAPI` | 框架名稱，保持原樣 |
| `CRUD` | Create/Read/Update/Delete 縮寫 |
| `RESTful` | REST 架構風格 |
| `GraphQL` | 查詢語言 |
| `API` | Application Programming Interface |
| `JSON` | JavaScript Object Notation |
| `JSON Patch` | RFC 6902 標準 |
| `MessagePack` / `msgpack` | 二進位序列化格式 |
| `S3` | Amazon Simple Storage Service |
| `Redis` | 內存資料庫 |
| `PostgreSQL` | 關聯式資料庫 |
| `SQLite` | 輕量級資料庫 |
| `OpenAPI` / `Swagger` | API 規範 |
| `RBAC` | Role-Based Access Control |
| `ACL` | Access Control List |
| `Hook` | 鉤子函數 |
| `Handler` | 處理器 |
| `Factory` | 工廠模式 |
| `Schema` | 結構定義 |
| `Blob` | Binary Large Object |
| `UUID` | Universally Unique Identifier |
| `Draft` / `Stable` | 狀態名稱，可保持英文 |

---

## 📝 Common Phrases / 常用片語

| 中文 | English |
|------|---------|
| 只需幾行程式碼 | With just a few lines of code |
| 自動產生 | Automatically generated |
| 零樣板 | Zero boilerplate |
| 高效能 | High performance |
| 低延遲 | Low latency |
| 高吞吐 | High throughput |
| 所見即所得 | What you see is what you get |
| 開發者只需專注 | Developers only need to focus on |
| 由框架自動處理 | Automatically handled by the framework |
| 一行代碼 | One line of code |
| 完整的 CRUD API | Complete CRUD API |
| 內建支援 | Built-in support |
| 原生支援 | Native support |
| 適合快速原型開發 | Suitable for rapid prototyping |
| 適合生產環境 | Suitable for production |

---

## 💡 Usage Tips / 使用提示

1. **Keep code identifiers in English**: Class names, function names, and variable names should remain in their original form.

2. **Translate comments in code blocks**: Comments within code examples should be translated.

3. **Preserve Markdown formatting**: Keep all Markdown syntax, links, and code blocks intact.

4. **Maintain technical accuracy**: When in doubt, keep the original term with a translation in parentheses.

5. **Consistent capitalization**: 
   - `ResourceManager` (not `Resource Manager` or `resourcemanager`)
   - `AutoCRUD` (not `Autocrud` or `Auto CRUD`)
