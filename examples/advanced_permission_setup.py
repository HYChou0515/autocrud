"""進階權限設定示例 - 組合多種檢查器"""

import datetime as dt

from autocrud.permission.acl import ACLPermissionChecker
from autocrud.types import PermissionResult
from autocrud.permission.composite import (
    CompositePermissionChecker,
    ConditionalPermissionChecker,
)
from autocrud.permission.data_based import FieldLevelPermissionChecker
from autocrud.permission.meta_based import ResourceOwnershipChecker
from autocrud.permission.simple import AllowAll
from autocrud.types import PermissionContext, ResourceAction


def setup_advanced_permissions(permission_manager=None, resource_manager=None):
    """設定進階權限檢查"""
    # 手動組合檢查器

    # 1. 欄位級權限檢查器
    field_checker = FieldLevelPermissionChecker(
        allowed_fields_by_user={
            "alice": {"name", "email", "description"},
            "bob": {"description"},
            "admin": {"name", "email", "description", "status", "priority"},
        },
    )

    # 2. 資源所有權檢查器 (如果有 resource_manager)
    ownership_checker = None
    if resource_manager:
        ownership_checker = ResourceOwnershipChecker(
            resource_manager=resource_manager,
            allowed_actions={
                ResourceAction.update,
                ResourceAction.delete,
                ResourceAction.patch,
            },  # 只有這些操作需要檢查所有權
        )

    # 3. 條件式檢查器
    conditional_checker = ConditionalPermissionChecker()

    # 添加條件：只有管理員可以刪除
    conditional_checker.add_condition(
        lambda ctx: PermissionResult.deny
        if ctx.action == ResourceAction.delete and not ctx.user.endswith("admin")
        else PermissionResult.not_applicable,
    )

    # 添加條件：工作時間限制
    def work_hours_check(context):
        if context.action in {ResourceAction.delete, ResourceAction.update}:
            hour = dt.datetime.now().hour
            if hour < 9 or hour > 17:  # 非工作時間
                return PermissionResult.deny
        return PermissionResult.not_applicable

    conditional_checker.add_condition(work_hours_check)

    # 4. 基本的 ACL/RBAC 檢查器 (如果有 permission_manager)
    acl_checker = None
    if permission_manager:
        acl_checker = ACLPermissionChecker(permission_manager)

    # 5. 組合所有檢查器
    checkers = [conditional_checker, field_checker]  # 最嚴格的條件檢查

    if ownership_checker:
        checkers.append(ownership_checker)  # 所有權檢查

    if acl_checker:
        checkers.append(acl_checker)  # ACL/RBAC 檢查
    else:
        checkers.append(AllowAll())  # 備用：允許所有操作

    composite_checker = CompositePermissionChecker(checkers)

    return composite_checker


# 使用示例
def main():
    """示範如何設定和使用進階權限系統"""
    # 設定權限檢查器（不需要實際的 managers）
    permission_checker = setup_advanced_permissions()

    print("權限系統設定完成！")
    print("組合權限檢查器包含以下檢查器：")
    print("1. 條件式檢查器 (工作時間限制、管理員刪除限制)")
    print("2. 欄位級權限檢查器")
    print("3. 備用允許所有檢查器")

    # 測試一些權限檢查
    test_cases = [
        ("alice", ResourceAction.get, "test_resource", "res_123", {}),
        ("admin", ResourceAction.delete, "test_resource", "res_456", {}),
        (
            "bob",
            ResourceAction.delete,
            "test_resource",
            "res_789",
            {},
        ),  # 應該被拒絕 (非管理員)
    ]

    print("\n=== 權限檢查測試 ===")
    for user, action, resource_name, resource_id, extra_data in test_cases:
        context = PermissionContext(
            user=user,
            now=dt.datetime.now().replace(hour=14),  # 下午2點 (工作時間)
            action=action,
            resource_name=resource_name,
            resource_id=resource_id,
            method_args=(resource_id,),
            method_kwargs={},
            extra_data=extra_data,
        )

        result = permission_checker.check_permission(context)
        print(f"{user} {action} {resource_name}:{resource_id} -> {result}")

    # 測試非工作時間的限制
    print("\n=== 非工作時間測試 ===")
    after_hours_context = PermissionContext(
        user="admin",
        now=dt.datetime.now().replace(hour=20),  # 晚上8點 (非工作時間)
        action=ResourceAction.update,
        resource_name="test_resource",
        resource_id="res_123",
        method_args=("res_123",),
        method_kwargs={},
        extra_data={},
    )

    result = permission_checker.check_permission(after_hours_context)
    print(f"admin update (after hours) -> {result}")


if __name__ == "__main__":
    main()
