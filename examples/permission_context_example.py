"""權限檢查系統使用示例

這個示例展示如何使用新的基於 Context 的權限檢查系統：
1. 使用預設檢查器
2. 創建自定義檢查器
3. 組合多個檢查器
4. 處理複雜的業務邏輯
"""

import datetime as dt

from autocrud.permission.acl import ACLPermissionChecker
from autocrud.types import (
    PermissionResult,
)
from autocrud.permission.composite import (
    CompositePermissionChecker,
    ConditionalPermissionChecker,
)
from autocrud.permission.data_based import FieldLevelPermissionChecker
from autocrud.permission.meta_based import ResourceOwnershipChecker
from autocrud.types import IPermissionChecker, PermissionContext, ResourceAction


# 示例 1: 基本使用 - 結合現有的 ACL/RBAC 系統
def setup_basic_permission_checker(
    permission_checker: ACLPermissionChecker,
    resource_manager,
) -> CompositePermissionChecker:
    """設置基本的權限檢查器"""
    return CompositePermissionChecker(
        [
            permission_checker,
            ResourceOwnershipChecker(
                resource_manager=resource_manager,
                allowed_actions={
                    ResourceAction.update,
                    ResourceAction.delete,
                    ResourceAction.patch,
                },
            ),
        ],
    )


# 示例 2: 自定義業務邏輯檢查器
class BusinessLogicChecker(IPermissionChecker):
    """業務邏輯檢查器 - 實現複雜的業務規則"""

    def check_permission(self, context: PermissionContext) -> PermissionResult:
        """實現自定義業務邏輯"""
        # 示例：只允許在工作時間進行某些操作
        if (
            context.action in {ResourceAction.delete, ResourceAction.update}
            and not self._is_work_hours()
        ):
            return PermissionResult.deny

        # 示例：根據資源狀態決定權限
        if context.resource_id and context.action == ResourceAction.update:
            return self._check_resource_status(context)

        # 示例：創建操作的特殊邏輯
        if context.action == ResourceAction.create:
            return self._check_create_permission(context)

        return PermissionResult.not_applicable

    def _is_work_hours(self) -> bool:
        """檢查是否在工作時間"""
        now = dt.datetime.now()
        return 9 <= now.hour <= 17  # 簡單示例：9-17點

    def _check_resource_status(self, context: PermissionContext) -> PermissionResult:
        """檢查資源狀態是否允許修改"""
        # 如果資源資料還沒載入，嘗試載入
        if context.resource_data is None:
            try:
                # 假設我們有方法可以載入資源資料
                # 在實際使用中，這可能需要傳入 resource_manager
                pass  # resource = resource_manager.get(context.resource_id)
                # context.set_resource_data(resource.data)
            except Exception:
                return PermissionResult.deny

        # 檢查資源狀態（示例邏輯）
        if hasattr(context.resource_data, "status"):
            if context.resource_data.status == "locked":
                return PermissionResult.deny

        return PermissionResult.not_applicable

    def _check_create_permission(self, context: PermissionContext) -> PermissionResult:
        """檢查創建權限"""
        # 示例：檢查用戶創建的資源數量限制
        user_prefix = f"user:{context.user}"

        # 在實際實現中，你可能需要查詢用戶已創建的資源數量
        # created_count = count_user_resources(context.user)
        # if created_count >= MAX_RESOURCES_PER_USER:
        #     return PermissionResult.DENY

        return PermissionResult.not_applicable


# 示例 3: 欄位級權限檢查
def setup_field_level_permissions() -> FieldLevelPermissionChecker:
    """設置欄位級權限"""
    field_permissions = {
        "user:alice": {"name", "email", "description"},  # alice 只能修改這些欄位
        "user:bob": {"description"},  # bob 只能修改描述
        "user:admin": {
            "name",
            "email",
            "description",
            "status",
            "priority",
        },  # admin 可以修改更多
    }

    return FieldLevelPermissionChecker(allowed_fields_by_user=field_permissions)


# 示例 4: 條件式權限檢查
def setup_conditional_checker() -> ConditionalPermissionChecker:
    """設置條件式權限檢查"""
    checker = ConditionalPermissionChecker()

    # 添加條件：只有週一到週五可以刪除資源
    def weekday_only_delete(context: PermissionContext) -> PermissionResult:
        if context.action == ResourceAction.delete:
            if dt.datetime.now().weekday() >= 5:  # 週末
                return PermissionResult.deny
        return PermissionResult.not_applicable

    # 添加條件：VIP 用戶可以跳過某些限制
    def vip_user_bypass(context: PermissionContext) -> PermissionResult:
        if context.user.startswith("vip:"):
            # VIP 用戶在某些情況下可以繞過限制
            if context.action in {ResourceAction.update, ResourceAction.delete}:
                return PermissionResult.allow
        return PermissionResult.not_applicable

    checker.add_condition(weekday_only_delete)
    checker.add_condition(vip_user_bypass)

    return checker


# 示例 5: 完整的權限檢查器設置
def setup_complete_permission_system(
    permission_checker: ACLPermissionChecker,
    resource_manager,
) -> CompositePermissionChecker:
    """設置完整的權限檢查系統"""
    checkers = [
        # 1. 首先檢查基本的 ACL/RBAC 權限
        permission_checker,
        # 2. 檢查資源所有權
        ResourceOwnershipChecker(
            resource_manager=resource_manager,
            allowed_actions={
                ResourceAction.update,
                ResourceAction.delete,
                ResourceAction.patch,
            },
        ),
        # 3. 檢查欄位級權限
        setup_field_level_permissions(),
        # 4. 檢查業務邏輯
        BusinessLogicChecker(),
        # 5. 檢查條件式規則
        setup_conditional_checker(),
    ]

    return CompositePermissionChecker(checkers)


# 示例 7: 動態權限配置
class DynamicPermissionChecker(IPermissionChecker):
    """動態權限檢查器 - 可以在運行時修改權限規則"""

    def __init__(self):
        self.rules = {}  # 存储動態規則

    def add_rule(self, rule_name: str, condition: callable):
        """添加動態規則"""
        self.rules[rule_name] = condition

    def remove_rule(self, rule_name: str):
        """移除動態規則"""
        self.rules.pop(rule_name, None)

    def check_permission(self, context: PermissionContext) -> PermissionResult:
        """執行所有動態規則"""
        for rule_name, condition in self.rules.items():
            try:
                result = condition(context)
                if result == PermissionResult.deny:
                    return PermissionResult.deny
            except Exception:
                # 規則執行失敗，記錄但不影響其他規則
                pass

        return PermissionResult.not_applicable


# 使用示例
def usage_example():
    """使用示例"""
    # 假設你已經有了 permission_checker 和 resource_manager
    permission_checker = ACLPermissionChecker()  # 你的 ACLPermissionChecker 實例
    resource_manager = None  # 你的 ResourceManager 實例

    # 方法 1: 使用基本設置
    simple_checker = setup_basic_permission_checker(
        permission_checker=permission_checker,
        resource_manager=resource_manager,
    )

    # 方法 2: 手動組裝複雜的檢查器
    complex_checker = CompositePermissionChecker(
        [
            permission_checker,
            BusinessLogicChecker(),
            setup_conditional_checker(),
        ],
    )

    # 方法 3: 使用動態檢查器
    dynamic_checker = DynamicPermissionChecker()
    dynamic_checker.add_rule(
        "no_weekend_delete",
        lambda ctx: PermissionResult.deny
        if ctx.action == ResourceAction.delete and dt.datetime.now().weekday() >= 5
        else PermissionResult.not_applicable,
    )

    print("✅ 權限檢查器設置完成")

    # 將檢查器傳入 ResourceManager
    # resource_manager = ResourceManager(
    #     resource_type=YourDataType,
    #     storage=your_storage,
    #     permission_checker=complex_checker,  # 使用新的檢查器
    #     # ... 其他參數
    # )


if __name__ == "__main__":
    print("=== 權限檢查系統使用示例 ===")
    usage_example()

    print("\n=== 權限檢查器類型說明 ===")
    print("1. ACLPermissionChecker: 基本的 ACL/RBAC 權限檢查")
    print("2. ResourceOwnershipChecker: 資源所有權檢查")
    print("3. FieldLevelPermissionChecker: 欄位級權限檢查")
    print("4. BusinessLogicChecker: 自定義業務邏輯檢查")
    print("5. ConditionalPermissionChecker: 條件式權限檢查")
    print("6. DynamicPermissionChecker: 動態權限檢查")
    print("7. CompositePermissionChecker: 組合多個檢查器")
