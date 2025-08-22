# ✅ 已完成
- [x] **Resource CRUD**（含 metadata 自動注入：resource id / revision id / created/updated time/by）
- [x] **Automatic FastAPI CRUD Routes**（自動產生 CRUD 與 **metadata search** 的 API 路由）
- [x] **Search & Filter**（依 metadata 查詢：時間、作者、revision …）
- [x] **Dump/Load for backup**
- [x] **Schema Migration**（user-defined migration handler）

# 🔜 待辦 / 缺少的核心
- [ ] **Revision diff**（計算不同版本之間的差異）

# 📝 TODO（進階功能，未來可考慮）
- [ ] **Access Control (ACL / RBAC)**：依 user/role 限制 CRUD 權限
- [ ] **Dependency Tracking**：記錄 resource 之間的引用關係，避免 dangling reference
- [ ] **Validation / Policy Hooks**：CRUD 前後的檢查與規則限制
- [ ] **Event Hooks / Pub-Sub**：CRUD 後觸發事件，支援外部通知或 workflow
- [ ] **Bulk Operations**：一次建立/更新/刪除多筆 resource
- [ ] **Resource Lifecycle**：支援狀態機（例如 草稿 → 已發布 → 停用）
- [ ] **Audit Log & Metrics**：操作紀錄、使用統計與錯誤率監控
- [ ] **Partial Update (PATCH)**：支援 JSONPatch 或類似的局部更新
- [ ] **Multi-tenancy 支援**：不同 user/tenant 的資源隔離
