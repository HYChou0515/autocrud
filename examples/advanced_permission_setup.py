"""
進階權限設定示例 - 組合多種檢查器
"""

from autocrud.resource_manager.permission_context import (
    DefaultPermissionChecker,
    FieldLevelPermissionChecker,
    ResourceOwnershipChecker,
    ConditionalPermissionChecker,
    CompositePermissionChecker,
    PermissionResult,
    create_default_permission_checker
)


def setup_advanced_permissions(permission_manager, resource_manager):
    """設定進階權限檢查"""
    
    # 方法 1: 使用便利函數
    simple_checker = create_default_permission_checker(
        permission_manager=permission_manager,
        resource_manager=resource_manager,
        enable_ownership_check=True,
        field_permissions={
            "user:alice": {"name", "email", "description"},
            "user:bob": {"description"},
            "user:admin": {"name", "email", "description", "status", "priority"},
        }
    )
    
    # 方法 2: 手動組合檢查器
    
    # 2.1 欄位級權限檢查器
    field_checker = FieldLevelPermissionChecker(
        allowed_fields_by_user={
            "user:alice": {"name", "email", "description"},
            "user:bob": {"description"},
            "user:admin": {"name", "email", "description", "status", "priority"},
        }
    )
    
    # 2.2 資源所有權檢查器
    ownership_checker = ResourceOwnershipChecker(
        resource_manager=resource_manager,
        allowed_actions={"update", "delete", "patch"}  # 只有這些操作需要檢查所有權
    )
    
    # 2.3 條件式檢查器
    conditional_checker = ConditionalPermissionChecker()
    
    # 添加條件：只有管理員可以刪除
    conditional_checker.add_condition(
        lambda ctx: PermissionResult.DENY 
        if ctx.action == "delete" and not ctx.user.endswith(":admin")
        else PermissionResult.NOT_APPLICABLE
    )
    
    # 添加條件：工作時間限制
    def work_hours_check(context):
        from datetime import datetime
        if context.action in {"delete", "update"}:
            hour = datetime.now().hour
            if hour < 9 or hour > 17:  # 非工作時間
                return PermissionResult.DENY
        return PermissionResult.NOT_APPLICABLE
    
    conditional_checker.add_condition(work_hours_check)
    
    # 2.4 基本的 ACL/RBAC 檢查器
    acl_checker = DefaultPermissionChecker(permission_manager)
    
    # 2.5 組合所有檢查器
    composite_checker = CompositePermissionChecker([
        conditional_checker,   # 最嚴格的條件檢查
        field_checker,        # 欄位權限檢查
        ownership_checker,    # 所有權檢查
        acl_checker,         # ACL/RBAC 檢查
    ])
    
    return composite_checker


# 使用示例
def main():
    # 假設你已經有了這些
    permission_manager = None  # 你的 PermissionResourceManager
    resource_manager = None    # 你的 ResourceManager
    
    # 設定權限檢查器
    permission_checker = setup_advanced_permissions(permission_manager, resource_manager)
    
    # 將檢查器設定到 ResourceManager
    resource_manager.permission_checker = permission_checker
    
    print("權限系統設定完成！")
