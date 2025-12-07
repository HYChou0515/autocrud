# 🚦 Auto FastAPI Routes

當你在 AutoCRUD 註冊一個 resource（例如 TodoItem、User），系統會自動生成一組 RESTful API 路由。這些路由會以你提供的 resource 名稱為基礎，並自動處理該 resource 的各種操作。

## 路由格式說明

- `[resource]` 代表你註冊的資源名稱（如 todo-item、user）
- `{resource_id}` 代表該資源的唯一識別碼
- `{revision_id}` 代表版本識別碼

## 主要路由列表

| 方法 | 路徑 | 功能說明 |
|------|-------------------------------|-----------------------------|
| POST   | /[resource]                        | 新增一筆 [resource] |
| GET    | /[resource]/data                   | 取得所有 [resource] 的資料 |
| GET    | /[resource]/meta                   | 取得所有 [resource] 的 metadata |
| GET    | /[resource]/revision-info          | 取得所有 [resource] 的目前版本資訊 |
| GET    | /[resource]/full                   | 取得所有 [resource] 的完整資訊 |
| GET    | /[resource]/count                  | 取得 [resource] 的數量 |
| GET    | /[resource]/{resource_id}/meta     | 取得指定 [resource] 的 metadata |
| GET    | /[resource]/{resource_id}/revision-info | 取得指定 [resource] 的版本資訊 |
| GET    | /[resource]/{resource_id}/full     | 取得指定 [resource] 的完整資訊 |
| GET    | /[resource]/{resource_id}/revision-list | 取得指定 [resource] 的歷史版本 |
| GET    | /[resource]/{resource_id}/data     | 取得指定 [resource] 的資料 |
| PUT    | /[resource]/{resource_id}          | 更新指定 [resource]（全量更新）|
| PATCH  | /[resource]/{resource_id}          | 局部更新指定 [resource] |
| DELETE | /[resource]/{resource_id}          | 刪除指定 [resource]（軟刪除）|
| POST   | /[resource]/{resource_id}/switch/{revision_id} | 切換到指定版本 |
| POST   | /[resource]/{resource_id}/restore  | 還原指定 [resource] |

## 使用範例

假設你註冊的 resource 是 `todo-item`，則會自動生成如下路由：

- `POST /todo-item` 新增待辦事項
- `GET /todo-item/{id}/data` 取得指定待辦事項資料
- `PATCH /todo-item/{id}` 局部更新
- `DELETE /todo-item/{id}` 刪除
- ...等

你只需提供 resource 結構，AutoCRUD 會自動處理資料的 CRUD、版本、還原等操作，讓 API 開發更簡單。

---

