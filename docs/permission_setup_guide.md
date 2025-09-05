# 權限設定快速指南

## 步驟 1: 選擇權限檢查策略

### 選項 A: 簡單設定（推薦新手）
```python
from autocrud.resource_manager.permission_context import DefaultPermissionChecker

# 只使用現有的 ACL/RBAC 系統
permission_checker = DefaultPermissionChecker(your_permission_manager)
```

### 選項 B: 便利函數設定（推薦一般使用）
```python
from autocrud.resource_manager.permission_context import create_default_permission_checker

permission_checker = create_default_permission_checker(
    permission_manager=your_permission_manager,
    resource_manager=your_resource_manager,
    enable_ownership_check=True,  # 啟用所有權檢查
    field_permissions={           # 設定欄位權限
        "user:alice": {"name", "email"},
        "user:admin": {"name", "email", "status"}
    }
)
```

### 選項 C: 完全自定義（推薦進階使用者）
```python
from autocrud.resource_manager.permission_context import CompositePermissionChecker

composite_checker = CompositePermissionChecker([
    YourCustomChecker(),
    FieldLevelPermissionChecker(...),
    ResourceOwnershipChecker(...),
    DefaultPermissionChecker(...)
])
```

## 步驟 2: 將權限檢查器設定到 ResourceManager

### 方法 A: 在初始化時設定
```python
resource_manager = ResourceManager(
    resource_type=YourDataType,
    storage=your_storage,
    permission_checker=permission_checker,  # 關鍵參數
    # ... 其他參數
)
```

### 方法 B: 後續設定
```python
resource_manager = ResourceManager(...)
resource_manager.permission_checker = permission_checker
```

## 步驟 3: 設定基本權限資料（如果使用 ACL/RBAC）

```python
# 在權限管理器中創建基本權限
with permission_manager.meta_provide("admin", datetime.now()):
    
    # 創建角色
    admin_role = RoleMembership(subject="user:alice", group="group:admin")
    permission_manager.create(admin_role)
    
    # 創建權限
    admin_permission = ACLPermission(
        subject="group:admin",
        object="documents", 
        action="*",  # 所有操作
        effect=Effect.allow
    )
    permission_manager.create(admin_permission)
```

## 常用權限模式

### 模式 1: 只有創建者可以修改
```python
ownership_checker = ResourceOwnershipChecker(
    resource_manager=your_resource_manager,
    allowed_actions={"update", "delete", "patch"}
)
```

### 模式 2: 欄位級權限控制
```python
field_checker = FieldLevelPermissionChecker(
    allowed_fields_by_user={
        "user:normal": {"name", "description"},
        "user:admin": {"name", "description", "status", "priority"}
    }
)
```

### 模式 3: 基於條件的動態權限
```python
conditional_checker = ConditionalPermissionChecker()

# 只有管理員可以刪除
conditional_checker.add_condition(
    lambda ctx: PermissionResult.DENY 
    if ctx.action == "delete" and not ctx.user.endswith(":admin")
    else PermissionResult.NOT_APPLICABLE
)

# 工作時間限制
def work_hours_only(context):
    if context.action in {"delete", "update"}:
        hour = datetime.now().hour
        if hour < 9 or hour > 17:
            return PermissionResult.DENY
    return PermissionResult.NOT_APPLICABLE

conditional_checker.add_condition(work_hours_only)
```

### 模式 4: 自定義業務邏輯
```python
class BusinessLogicChecker(PermissionChecker):
    def check_permission(self, context: PermissionContext) -> PermissionResult:
        # 檢查資源狀態
        if context.resource_data and hasattr(context.resource_data, 'status'):
            if context.resource_data.status == 'locked':
                return PermissionResult.DENY
        
        # 檢查用戶限額
        if context.action == "create":
            user_count = self.get_user_resource_count(context.user)
            if user_count >= MAX_RESOURCES:
                return PermissionResult.DENY
        
        return PermissionResult.NOT_APPLICABLE
```

## 除錯技巧

### 1. 檢查權限檢查器順序
檢查器按順序執行，任何 DENY 都會立即拒絕操作。將最嚴格的檢查器放在前面。

### 2. 使用日志記錄
```python
import logging

class LoggingPermissionChecker(PermissionChecker):
    def __init__(self, inner_checker):
        self.inner_checker = inner_checker
        self.logger = logging.getLogger(__name__)
    
    def check_permission(self, context):
        result = self.inner_checker.check_permission(context)
        self.logger.info(f"Permission check: {context.user} {context.action} {context.resource_name} -> {result}")
        return result
```

### 3. 測試權限邏輯
```python
def test_permission():
    context = PermissionContext(
        user="user:test",
        action="update", 
        resource_name="documents",
        resource_id="doc123",
        method_name="update"
    )
    
    result = your_checker.check_permission(context)
    print(f"Permission result: {result}")
```

## 性能考慮

1. **延遲載入資源資料**：只在需要時載入
2. **檢查器順序**：將快速檢查器放在前面
3. **快取權限結果**：對於複雜的權限邏輯可以考慮快取

## 安全最佳實踐

1. **預設拒絕**：當不確定時，選擇拒絕而不是允許
2. **最小權限原則**：只給予必要的權限
3. **定期審查**：定期檢查和更新權限設定
4. **日志記錄**：記錄所有權限檢查結果供審計
