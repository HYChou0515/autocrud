
## 功能概覽

| 功能 | 說明 |
| :--- | :--- |
| ✅ 自動生成 (Schema → API/Storage) | `Schema as Infrastructure`：自動產生路由、邏輯綁定與儲存映射 |
| ✅ 版本控制 (Revision History) | Draft→Update / Stable→Append、完整 parent revision 鏈 |
| ✅ 遷移 (Migration) | Functional Converter，Lazy Upgrade on Read + Save |
| ✅ 儲存架構 (Storage) | Hybrid：Meta (SQL/Redis) + Payload (Object Store) + Blob |
| ✅ 可擴展性 (Scale Out) | 使用 Object Storage 與索引分離，便於水平擴展 |
| ✅ 局部更新 (Partial Update / PATCH) | JSON Patch精準更新, 提速省頻寬 |
| ✅ 局部讀取 (Partial Read) | msgspec 解碼階段跳過不必要欄位, 提速省頻寬 |
| ✅ GraphQL 整合 | 自動產生 Strawberry GraphQL Endpoint |
| ✅ Blob優化 | BlobStore 去重、延遲載入 |
| ✅ 權限控制 (Permissions) | Global / Model / Resource 三層 RBAC 與自定義檢查器 |
| ✅ Event Hooks | 每種操作都可以自訂 Before / After / OnSuccess / OnError |
| ✅ Route Templates | 標準 CRUD 與plug-in自定義端點 |
| ✅ 搜尋與索引 (Search / Index) | Meta Store 提供高效篩選、排序、分頁與複雜查詢 |
| ✅ 審計 / 日誌 (Audit / Logging) | 支援事件後的審計紀錄與審查流程 |
| ✅ 訊息佇列 (Message Queue) | 內建非同步任務處理，將 Job 視為資源進行版本與狀態管理 |