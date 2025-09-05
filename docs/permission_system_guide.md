# 權限檢查系統使用指南

## 概述

這個新的權限檢查系統解決了你提到的所有問題：

1. **靈活處理不同 action 的參數** - 通過 `PermissionContext` 提供完整的上下文資訊
2. **支援用戶自定義權限邏輯** - 可插拔的檢查器架構
3. **提供合理的預設實現** - `DefaultPermissionChecker` 整合現有的 ACL/RBAC 系統
4. **支援複雜的業務邏輯** - 可以基於資源內容、用戶角色、時間等進行檢查

## 核心概念

### 1. PermissionContext
包含權限檢查所需的所有資訊：
- 基本資訊：user, action, resource_name, resource_id
- 方法調用資訊：method_name, method_args, method_kwargs
- 資源資料：可延遲加載的 resource_data 和 resource_meta

### 2. PermissionChecker
可插拔的權限檢查器接口，返回三種結果：
- `ALLOW`: 允許操作
- `DENY`: 拒絕操作
- `NOT_APPLICABLE`: 此檢查器不適用於這個操作

### 3. CompositePermissionChecker
組合多個檢查器，採用 "任何 DENY 都拒絕" 的策略

## 使用場景

### 場景 1: 基本使用 - 整合現有 ACL/RBAC
```python
from autocrud.resource_manager.permission_context import DefaultPermissionChecker

# 使用現有的 PermissionResourceManager
permission_checker = DefaultPermissionChecker(your_permission_manager)

# 在 ResourceManager 中使用
resource_manager = ResourceManager(
    resource_type=YourDataType,
    storage=your_storage,
    permission_checker=permission_checker,
    # ... 其他參數
)
```

### 場景 2: 欄位級權限檢查
```python
from autocrud.resource_manager.permission_context import FieldLevelPermissionChecker

field_checker = FieldLevelPermissionChecker(
    allowed_fields_by_user={
        "user:alice": {"name", "email", "description"},
        "user:bob": {"description"},
        "user:admin": {"name", "email", "description", "status", "priority"},
    }
)
```

### 場景 3: 資源所有權檢查
```python
from autocrud.resource_manager.permission_context import ResourceOwnershipChecker

# 只有資源創建者可以進行 update/delete 操作
ownership_checker = ResourceOwnershipChecker(
    resource_manager=your_resource_manager,
    allowed_actions={"update", "delete", "patch"}
)
```

### 場景 4: 自定義業務邏輯
```python
class BusinessLogicChecker(PermissionChecker):
    def check_permission(self, context: PermissionContext) -> PermissionResult:
        # 例如：只有工作時間可以執行某些操作
        if context.action in {"delete", "update"} and not self._is_work_hours():
            return PermissionResult.DENY
        
        # 例如：根據資源狀態決定權限
        if context.has_resource_id and context.resource_data:
            if hasattr(context.resource_data, 'status'):
                if context.resource_data.status == 'locked':
                    return PermissionResult.DENY
        
        return PermissionResult.NOT_APPLICABLE
```

### 場景 5: 完整的權限系統
```python
from autocrud.resource_manager.permission_context import CompositePermissionChecker

# 組合多個檢查器
composite_checker = CompositePermissionChecker([
    # 1. 條件式檢查（最嚴格的規則）
    conditional_checker,
    
    # 2. 欄位級權限檢查
    field_checker,
    
    # 3. 資源所有權檢查
    ownership_checker,
    
    # 4. 基本的 ACL/RBAC 檢查
    DefaultPermissionChecker(permission_manager),
    
    # 5. 自定義業務邏輯
    BusinessLogicChecker(),
])
```

## 解決你提到的具體問題

### 1. 不同 action 的參數問題
```python
# create: 沒有 resource_id
context = PermissionContext(
    user="user:alice",
    action="create",
    resource_name="documents",
    method_name="create",
    method_kwargs={"data": document_data}
)

# update: 有 resource_id，可以檢查修改的欄位
context = PermissionContext(
    user="user:alice", 
    action="update",
    resource_name="documents",
    resource_id="doc123",
    method_name="update",
    method_kwargs={"data": updated_data}
)

# list/search: 沒有 resource_id
context = PermissionContext(
    user="user:alice",
    action="search_resources", 
    resource_name="documents",
    method_name="search_resources",
    method_kwargs={"query": search_query}
)
```

### 2. 檢查用戶可修改的欄位
```python
class CustomFieldChecker(PermissionChecker):
    def check_permission(self, context: PermissionContext) -> PermissionResult:
        if context.action not in {"update", "patch"}:
            return PermissionResult.NOT_APPLICABLE
            
        # 從 method_kwargs 中獲取要修改的資料
        if "data" in context.method_kwargs:
            data = context.method_kwargs["data"]
            modified_fields = set(data.__dict__.keys() if hasattr(data, "__dict__") else data.keys())
            
            # 檢查用戶是否有權限修改這些欄位
            allowed_fields = self._get_user_allowed_fields(context.user)
            
            if not modified_fields.issubset(allowed_fields):
                return PermissionResult.DENY
                
        return PermissionResult.ALLOW
```

### 3. 基於資源內容的動態權限
```python
class ContentBasedChecker(PermissionChecker):
    def check_permission(self, context: PermissionContext) -> PermissionResult:
        if not context.has_resource_id:
            return PermissionResult.NOT_APPLICABLE
            
        # 載入資源資料（如果還沒載入）
        if context.resource_data is None:
            try:
                resource = self.resource_manager.get(context.resource_id)
                context.set_resource_data(resource.data)
                context.set_resource_meta(resource.meta)
            except Exception:
                return PermissionResult.DENY
        
        # 檢查用戶是否為創建者
        if context.resource_meta.created_by == context.user:
            return PermissionResult.ALLOW
            
        # 檢查其他業務邏輯
        if hasattr(context.resource_data, 'visibility'):
            if context.resource_data.visibility == 'private' and context.action == 'get':
                return PermissionResult.DENY
                
        return PermissionResult.NOT_APPLICABLE
```

## 優勢

1. **簡潔且不囉嗦**：每個檢查器專注於單一職責
2. **高度可擴展**：可以輕鬆添加新的檢查器
3. **向後兼容**：可以與現有的 ACL/RBAC 系統無縫整合
4. **靈活的組合**：可以根據需要組合不同的檢查器
5. **完整的上下文**：`PermissionContext` 提供所有需要的資訊
6. **性能考慮**：支援延遲載入資源資料

## 最佳實踐

1. **檢查器順序**：將最嚴格的檢查器放在前面
2. **返回 NOT_APPLICABLE**：當檢查器不適用時，返回 NOT_APPLICABLE 而不是 ALLOW
3. **延遲載入**：只在需要時載入資源資料
4. **異常處理**：在檢查器中妥善處理異常
5. **測試**：為每個自定義檢查器編寫測試

這個系統給了你最大的靈活性來實現複雜的權限邏輯，同時保持代碼的清晰和可維護性。
