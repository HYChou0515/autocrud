"""權限檢查系統使用範例
展示如何使用新的權限上下文模式來實現靈活的權限檢查
"""

import datetime as dt

from autocrud.types import (
    PermissionResult,
)
from autocrud.permission.composite import CompositePermissionChecker
from autocrud.permission.simple import AllowAll
from autocrud.types import IPermissionChecker, PermissionContext


class SimplePermissionManager:
    """簡化的權限管理器 - 用於示範"""

    def __init__(self):
        self.permissions = {
            "alice": {"get": ["resource:123"], "update": ["resource:123"]},
            "bob": {"get": ["resource:456"]},
            "admin": {"admin": ["system"]},
        }

    def check_permission(self, user: str, action: str, resource_id: str) -> bool:
        """檢查用戶是否有對特定資源的操作權限"""
        user_perms = self.permissions.get(user, {})
        allowed_resources = user_perms.get(action, [])
        return resource_id in allowed_resources


class CustomResourceAccessChecker(IPermissionChecker):
    """自定義資源存取檢查器 - 展示如何實現複雜的權限邏輯"""

    def __init__(self, permission_manager: SimplePermissionManager):
        self.permission_manager = permission_manager
        self.supported_actions = {"get", "update", "delete", "patch", "switch"}

    def check_permission(self, context: PermissionContext) -> PermissionResult:
        """實現自定義權限檢查邏輯
        - 對於 get 操作：檢查具體的 resource_id
        - 對於 update/delete：除了檢查 resource_id，還要檢查 data 內容
        """
        if not context.resource_id:
            # 如果沒有 resource_id，嘗試從方法參數中提取
            if context.method_args:
                resource_id = context.method_args[0]
            else:
                return PermissionResult.deny
        else:
            resource_id = context.resource_id

        # 基本權限檢查
        is_allowed = self.permission_manager.check_permission(
            context.user,
            context.action,
            resource_id,
        )

        if not is_allowed:
            return PermissionResult.deny

        # 特殊邏輯：對於 update 操作，檢查新資料內容
        if context.action == "update" and len(context.method_args) >= 2:
            new_data = context.method_args[1]

            # 範例：檢查敏感欄位
            if hasattr(new_data, "sensitive_field"):
                # 只有管理員可以修改敏感欄位
                admin_check = self.permission_manager.check_permission(
                    context.user,
                    "admin",
                    "system",
                )
                if not admin_check:
                    return PermissionResult.deny

        return PermissionResult.allow


class DataFilterChecker(IPermissionChecker):
    """資料過濾檢查器 - 檢查搜尋查詢是否合理"""

    def check_permission(self, context: PermissionContext) -> PermissionResult:
        # 檢查查詢條件
        query = context.method_kwargs.get("query")
        if query and hasattr(query, "data_conditions"):
            # 範例：限制查詢範圍
            for condition in query.data_conditions:
                if condition.field_path == "sensitive_data":
                    # 檢查用戶是否有查詢敏感資料的權限
                    return PermissionResult.deny

        return PermissionResult.allow


class TimeBasedChecker(IPermissionChecker):
    """時間基礎檢查器 - 在特定時間段限制某些操作"""

    def check_permission(self, context: PermissionContext) -> PermissionResult:
        now = dt.datetime.now()

        # 範例：在工作時間外限制修改操作
        if now.hour < 8 or now.hour > 18:
            if context.action in {"update", "delete"}:
                # 檢查是否有緊急操作權限
                emergency = context.extra_data.get("emergency", False)
                if not emergency:
                    return PermissionResult.deny

        return PermissionResult.not_applicable  # 讓其他檢查器決定


def setup_advanced_permission_checking() -> CompositePermissionChecker:
    """設定進階權限檢查系統

    這個函數展示如何組合多個權限檢查器來實現複雜的權限邏輯

    Returns:
        CompositePermissionChecker: 組合的權限檢查器
    """
    # 創建簡單的 permission manager
    permission_manager = SimplePermissionManager()

    # 建立組合權限檢查器
    composite_checker = CompositePermissionChecker(
        [
            TimeBasedChecker(),
            CustomResourceAccessChecker(permission_manager),
            DataFilterChecker(),
            # 可以添加更多檢查器
            AllowAll(),  # 作為最後的備用（允許所有操作）
        ],
    )

    return composite_checker


# === 使用範例 ===


def example_usage():
    """展示如何使用新的權限檢查系統"""
    # 創建進階權限檢查器
    permission_checker = setup_advanced_permission_checking()

    # 測試權限檢查
    context = PermissionContext(
        user="alice",
        now=dt.datetime.now(),
        action="get",
        resource_name="test_resource",
        resource_id="resource:123",
    )

    result = permission_checker.check_permission(context)
    print(f"Permission check result: {result}")

    # 測試時間基礎的權限檢查
    update_context = PermissionContext(
        user="alice",
        now=dt.datetime.now().replace(hour=22),  # 晚上10點
        action="update",
        resource_name="test_resource",
        resource_id="resource:123",
        extra_data={"emergency": False},
    )

    result = permission_checker.check_permission(update_context)
    print(f"After-hours update result (no emergency): {result}")

    # 測試緊急更新
    emergency_context = PermissionContext(
        user="alice",
        now=dt.datetime.now().replace(hour=22),
        action="update",
        resource_name="test_resource",
        resource_id="resource:123",
        extra_data={"emergency": True},
    )

    result = permission_checker.check_permission(emergency_context)
    print(f"After-hours update result (with emergency): {result}")


def demo_permission_checking():
    """展示更多權限檢查的範例"""
    permission_checker = setup_advanced_permission_checking()

    # 測試不同用戶和資源的權限
    test_cases = [
        ("alice", "get", "resource:123"),
        ("alice", "update", "resource:123"),
        ("bob", "get", "resource:456"),
        ("bob", "update", "resource:456"),  # 應該失敗
        ("charlie", "get", "resource:123"),  # 應該失敗
    ]

    for user, action, resource_id in test_cases:
        context = PermissionContext(
            user=user,
            now=dt.datetime.now().replace(hour=14),  # 下午2點
            action=action,
            resource_name="test_resource",
            resource_id=resource_id,
            method_args=(resource_id,),
            method_kwargs={},
        )

        result = permission_checker.check_permission(context)
        print(f"{user} {action} {resource_id}: {result}")


if __name__ == "__main__":
    print("=== 基本權限檢查範例 ===")
    example_usage()

    print("\n=== 進階權限檢查範例 ===")
    demo_permission_checking()
