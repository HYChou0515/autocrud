# 權限設定快速上手指南

## 📋 設定步驟總覽

### 1️⃣ 基本設定（3 步驟）

```python
# 步驟 1: 創建權限檢查器
from autocrud.resource_manager.permission_context import DefaultPermissionChecker
permission_checker = DefaultPermissionChecker(your_permission_manager)

# 步驟 2: 設定到 ResourceManager
your_resource_manager.permission_checker = permission_checker

# 步驟 3: 設定權限資料
with permission_manager.meta_provide("admin", datetime.now()):
    permission = ACLPermission(
        subject="user:alice",
        object=None,  # None = 任何資源
        action="create",
        effect=Effect.allow
    )
    permission_manager.create(permission)
```

### 2️⃣ 完整設定範例

```python
import datetime as dt
from autocrud.resource_manager.core import ResourceManager, SimpleStorage
from autocrud.resource_manager.permission import PermissionResourceManager, Permission, ACLPermission, Effect
from autocrud.resource_manager.permission_context import DefaultPermissionChecker
from autocrud.resource_manager.resource_store.simple import MemoryResourceStore
from autocrud.resource_manager.meta_store.simple import MemoryMetaStore

def setup_complete_system():
    # 1. 創建儲存
    meta_store = MemoryMetaStore()
    resource_store = MemoryResourceStore(resource_type=YourDataType)
    storage = SimpleStorage(meta_store, resource_store)
    
    # 2. 創建權限管理器
    permission_meta_store = MemoryMetaStore()
    permission_resource_store = MemoryResourceStore(resource_type=Permission)
    permission_storage = SimpleStorage(permission_meta_store, permission_resource_store)
    permission_manager = PermissionResourceManager(Permission, storage=permission_storage)
    
    # 3. 創建權限檢查器
    permission_checker = DefaultPermissionChecker(permission_manager)
    
    # 4. 創建 ResourceManager
    resource_manager = ResourceManager(
        resource_type=YourDataType,
        storage=storage,
        permission_checker=permission_checker  # 關鍵：設定權限檢查器
    )
    
    # 5. 設定初始權限
    admin_user = "admin"
    current_time = dt.datetime.now()
    
    with permission_manager.meta_provide(admin_user, current_time):
        # 給用戶基本權限
        permissions = [
            ACLPermission(subject="user:alice", object=None, action="create", effect=Effect.allow),
            ACLPermission(subject="user:alice", object=None, action="get", effect=Effect.allow),
            ACLPermission(subject="user:alice", object=None, action="get_meta", effect=Effect.allow),
            ACLPermission(subject="user:alice", object=None, action="get_resource_revision", effect=Effect.allow),
        ]
        
        for permission in permissions:
            permission_manager.create(permission)
    
    return resource_manager, permission_manager
```

### 3️⃣ 進階設定 - 組合多個檢查器

```python
from autocrud.resource_manager.permission_context import (
    CompositePermissionChecker,
    DefaultPermissionChecker,
    ResourceOwnershipChecker,
    FieldLevelPermissionChecker
)

def setup_advanced_permissions(permission_manager, resource_manager):
    # 創建各種檢查器
    acl_checker = DefaultPermissionChecker(permission_manager)
    ownership_checker = ResourceOwnershipChecker(resource_manager)
    field_checker = FieldLevelPermissionChecker(
        allowed_fields_by_user={
            "user:alice": {"name", "description"},
            "user:admin": {"name", "description", "status"}
        }
    )
    
    # 組合檢查器
    composite_checker = CompositePermissionChecker([
        field_checker,      # 欄位權限檢查
        ownership_checker,  # 所有權檢查  
        acl_checker,       # ACL/RBAC 檢查
    ])
    
    return composite_checker
```

## 🎯 常用權限模式

### 模式 1: 萬用權限（適合開發/測試）
```python
ACLPermission(subject="user:admin", object=None, action="*", effect=Effect.allow)
```

### 模式 2: 只有創建者可以修改
```python
# 使用 ResourceOwnershipChecker
ownership_checker = ResourceOwnershipChecker(
    resource_manager=your_resource_manager,
    allowed_actions={"update", "delete", "patch"}
)
```

### 模式 3: 欄位級權限
```python
field_checker = FieldLevelPermissionChecker(
    allowed_fields_by_user={
        "user:normal": {"name", "description"},
        "user:admin": {"name", "description", "status", "priority"}
    }
)
```

### 模式 4: 條件式權限
```python
from autocrud.resource_manager.permission_context import ConditionalPermissionChecker

conditional_checker = ConditionalPermissionChecker()
conditional_checker.add_condition(
    lambda ctx: PermissionResult.DENY 
    if ctx.action == "delete" and not ctx.user.endswith(":admin")
    else PermissionResult.NOT_APPLICABLE
)
```

## 🚀 快速開始

### 最簡單的設定（5 分鐘）

```python
# 1. 創建權限檢查器
from autocrud.resource_manager.permission_context import create_default_permission_checker

permission_checker = create_default_permission_checker(
    permission_manager=your_permission_manager,
    resource_manager=your_resource_manager,
    enable_ownership_check=True
)

# 2. 設定到 ResourceManager
your_resource_manager.permission_checker = permission_checker

# 3. 完成！現在所有操作都會自動檢查權限
```

## 🔧 除錯技巧

### 檢查權限設定是否正確
```python
def test_permissions():
    try:
        with resource_manager.meta_provide("user:alice", datetime.now()):
            result = resource_manager.create(your_data)
            print("✅ 創建成功")
    except PermissionDeniedError as e:
        print(f"❌ 權限被拒絕: {e}")
```

### 檢查現有權限
```python
# 查看用戶的所有權限
permissions = permission_manager.search_resources(
    ResourceMetaSearchQuery(
        data_conditions=[
            DataSearchCondition(
                field_path="subject",
                operator=DataSearchOperator.equals,
                value="user:alice"
            )
        ]
    )
)
for p in permissions:
    perm = permission_manager.get(p.resource_id)
    print(f"權限: {perm.data}")
```

## ⚠️ 常見問題

### Q: Permission denied 錯誤
**A:** 檢查是否設定了所有需要的權限：`create`, `get`, `get_meta`, `get_resource_revision`

### Q: 權限檢查器沒有執行
**A:** 確保在 ResourceManager 初始化時傳入了 `permission_checker` 參數

### Q: 欄位權限不生效
**A:** 確保檢查器順序正確，欄位檢查器應該在基本權限檢查器之前

### Q: 動態生成的 resource_id 權限問題
**A:** 使用 `object=None` 表示任何資源，或使用 `ResourceOwnershipChecker`

## 📚 更多資源

- 完整示例：`examples/complete_permission_example.py`
- 測試案例：`tests/test_permission_context.py`
- 系統設計：`docs/permission_system_guide.md`
