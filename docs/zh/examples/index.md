---
title: 範例集
description: AutoCRUD 的各種使用範例
---

# 範例集

這裡收集了 AutoCRUD 的各種使用範例，從基礎到進階應用。

## 快速導覽

<div class="grid cards" markdown>

-   :material-rocket-launch:{ .lg .middle } __基礎 CRUD__

    ---

    學習基本的建立、讀取、更新、刪除操作

    [:octicons-arrow-right-24: 基礎範例](basic-crud.md)

-   :material-shield-lock:{ .lg .middle } __權限控制__

    ---

    實作 RBAC、ACL 等權限系統

    [:octicons-arrow-right-24: 權限範例](permissions.md)

-   :material-history:{ .lg .middle } __版本控制__

    ---

    版本歷史、草稿、版本切換

    [:octicons-arrow-right-24: 版本範例](versioning.md)

-   :material-magnify:{ .lg .middle } __搜尋與過濾__

    ---

    複雜查詢、索引、分頁

    [:octicons-arrow-right-24: 搜尋範例](search.md)

</div>

## 實際應用範例

### CMS 內容管理系統

完整的部落格文章管理系統，包含：

- 文章版本控制
- 草稿/發布流程
- 分類與標籤
- 圖片上傳

[:octicons-arrow-right-24: 查看範例](cms-example.md)

### 電商訂單系統

訂單管理系統，展示：

- 複雜的資料關聯
- 狀態機管理
- 審計日誌
- 權限分層

[:octicons-arrow-right-24: 查看範例](ecommerce-example.md)

### IoT 設備管理

IoT 設備資料收集與管理：

- 時間序列資料
- 大量寫入優化
- 即時查詢
- 告警系統

[:octicons-arrow-right-24: 查看範例](iot-example.md)

## 程式碼片段

### 快速開始範本

最簡單的 AutoCRUD 應用：

```python
from fastapi import FastAPI
from autocrud import AutoCRUD
from msgspec import Struct

class Item(Struct):
    name: str
    price: float

crud = AutoCRUD()
crud.add_model(Item)

app = FastAPI()
crud.apply(app)
```

### 帶索引的模型

支援搜尋與過濾：

```python
crud.add_model(
    Item,
    indexed_fields=[
        ("price", float),
        ("category", str),
    ]
)
```

### 自定義權限

```python
from autocrud.permission import RBACPermissionChecker

permission_checker = RBACPermissionChecker({
    "admin": {"read", "create", "update", "delete"},
    "editor": {"read", "create", "update"},
    "viewer": {"read"}
})

crud = AutoCRUD(permission_checker=permission_checker)
```

### 事件處理

```python
from autocrud.types import IEventHandler, EventContext

class LoggingHandler(IEventHandler):
    def after_create(self, ctx: EventContext, resource):
        print(f"Created: {resource.resource_id}")
    
    def after_update(self, ctx: EventContext, resource):
        print(f"Updated: {resource.resource_id}")

crud = AutoCRUD(event_handlers=[LoggingHandler()])
```

## 專案範例庫

查看完整的專案範例：

- [GitHub - autocrud/examples](https://github.com/HYChou0515/autocrud/tree/master/examples)

## 進階範例

- [GraphQL 整合](../advanced/graphql.md#範例)
- [自定義儲存](../advanced/custom-storage.md#範例)
- [訊息佇列](../advanced/message-queue.md#範例)
- [效能優化](../advanced/performance.md#最佳實踐)