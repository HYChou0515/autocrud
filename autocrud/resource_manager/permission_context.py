# """權限檢查上下文和策略模式實現

# 這個模組提供了一個靈活的權限檢查框架：
# - PermissionContext：包含所有權限檢查所需的上下文資訊
# - PermissionChecker：可插拔的權限檢查器接口
# - DefaultPermissionChecker：預設實現，可以被繼承或組合
# """

# from collections.abc import Callable
# from typing import Dict
# from msgspec import UNSET
# import logging
# from autocrud.permission.basic import PermissionResult
# from autocrud.permission.basic import PermissionContext
# from autocrud.permission.basic import IPermissionChecker
# from autocrud.resource_manager.basic import ResourceAction


# from autocrud.resource_manager.core import ResourceManager

# logger = logging.getLogger(__name__)


# class CompositePermissionChecker(IPermissionChecker):
#     """組合權限檢查器 - 執行多個檢查器，任何 DENY 都會拒絕操作"""

#     def __init__(self, checkers: list[IPermissionChecker]):
#         self.checkers = checkers

#     def check_permission(self, context: PermissionContext) -> PermissionResult:
#         """執行所有檢查器，收集所有結果，任何 DENY 都會拒絕操作"""
#         has_allow = False

#         for checker in self.checkers:
#             result = checker.check_permission(context)

#             # 任何 DENY 立即拒絕
#             if result == PermissionResult.deny:
#                 return PermissionResult.deny

#             # 記錄是否有 ALLOW
#             if result == PermissionResult.allow:
#                 has_allow = True

#         # 如果有 ALLOW 且沒有 DENY，則允許
#         if has_allow:
#             return PermissionResult.allow

#         # 所有檢查器都不適用，預設拒絕
#         return PermissionResult.not_applicable


# class ActionBasedPermissionChecker(IPermissionChecker):
#     """基於 Action 的權限檢查器 - 為不同操作提供專門的檢查邏輯"""

#     def __init__(self):
#         self._action_handlers: Dict[str, callable] = {}

#     def register_action_handler(self, action: str, handler: callable) -> None:
#         """註冊 action 處理器

#         Args:
#             action: 動作名稱
#             handler: 處理函數，接受 PermissionContext，返回 PermissionResult
#         """
#         self._action_handlers[action] = handler

#     def check_permission(self, context: PermissionContext) -> PermissionResult:
#         """根據 action 分發到對應的處理器"""

#         handlers = [h for a, h in self._action_handlers.items() if context.action in a]
#         for handler in handlers:
#             result = handler(context)
#             if result != PermissionResult.not_applicable:
#                 return result

#         return PermissionResult.not_applicable

#     @classmethod
#     def from_dict(
#         cls,
#         handlers: dict[
#             ResourceAction | str, Callable[[PermissionContext], PermissionResult]
#         ],
#     ) -> "ActionBasedPermissionChecker":
#         """創建自定義 action 檢查器，並註冊常用的 action 處理器"""
#         checker = cls()

#         for action, handler in handlers.items():
#             if isinstance(action, str):
#                 action = ResourceAction[action]
#             checker.register_action_handler(action, handler)

#         return checker


# class ResourceOwnershipChecker(IPermissionChecker):
#     """資源所有權檢查器 - 檢查用戶是否為資源創建者"""

#     def __init__(
#         self,
#         resource_manager: ResourceManager,
#         allowed_actions: ResourceAction = ResourceAction.owner,
#     ):
#         self.resource_manager = resource_manager
#         self.allowed_actions = allowed_actions

#     def check_permission(self, context: PermissionContext) -> PermissionResult:
#         """檢查用戶是否為資源擁有者"""
#         # 只對特定 action 生效
#         if context.action not in self.allowed_actions:
#             return PermissionResult.not_applicable

#         # 需要有 resource_id
#         if context.resource_id is UNSET:
#             return PermissionResult.not_applicable

#         try:
#             # 獲取資源元資料
#             if context.resource_meta is UNSET:
#                 meta = self.resource_manager.get_meta(context.resource_id)
#                 context.resource_meta = meta
#             else:
#                 meta = context.resource_meta

#             # 檢查創建者
#             if meta.created_by == context.user:
#                 return PermissionResult.allow
#             else:
#                 return PermissionResult.deny

#         except Exception:
#             return PermissionResult.deny


# class FieldLevelPermissionChecker(IPermissionChecker):
#     """欄位級權限檢查器 - 檢查用戶是否可以修改特定欄位"""

#     def __init__(
#         self,
#         allowed_fields_by_user: Dict[str, set[str]] = None,
#         allowed_fields_by_role: Dict[str, set[str]] = None,
#     ):
#         self.allowed_fields_by_user = allowed_fields_by_user or {}
#         self.allowed_fields_by_role = allowed_fields_by_role or {}

#     def check_permission(self, context: PermissionContext) -> PermissionResult:
#         """檢查欄位級權限"""
#         # 只對 update/patch 操作生效
#         if not (context.action & (ResourceAction.update | ResourceAction.patch)):
#             return PermissionResult.not_applicable

#         # 從方法參數中提取要修改的欄位
#         modified_fields = self._extract_modified_fields(context)
#         if not modified_fields:
#             return PermissionResult.not_applicable

#         # 獲取用戶允許修改的欄位
#         allowed_fields = self._get_user_allowed_fields(context.user)

#         # 檢查是否所有修改的欄位都被允許
#         if modified_fields.issubset(allowed_fields):
#             return PermissionResult.allow
#         else:
#             return PermissionResult.deny

#     def _extract_modified_fields(self, context: PermissionContext) -> set[str]:
#         """從上下文中提取要修改的欄位"""
#         # 這裡可以根據實際的 update/patch 方法實現來提取
#         # 例如從 method_kwargs 中獲取 data 參數，然後分析要修改的欄位
#         modified_fields = set()

#         if "data" in context.method_kwargs:
#             data = context.method_kwargs["data"]
#             if hasattr(data, "__dict__"):
#                 modified_fields = set(data.__dict__.keys())
#             elif isinstance(data, dict):
#                 modified_fields = set(data.keys())

#         return modified_fields

#     def _get_user_allowed_fields(self, user: str) -> set[str]:
#         """獲取用戶允許修改的欄位"""
#         allowed = set()

#         # 直接用戶權限
#         if user in self.allowed_fields_by_user:
#             allowed.update(self.allowed_fields_by_user[user])

#         # TODO: 可以在這裡添加角色查詢邏輯
#         # 例如查詢用戶所屬角色，然後獲取角色的允許欄位

#         return allowed


# class ConditionalPermissionChecker(IPermissionChecker):
#     """條件式權限檢查器 - 基於資源內容的動態權限檢查"""

#     def __init__(self):
#         self._conditions: list[callable] = []

#     def add_condition(self, condition: callable) -> None:
#         """添加條件函數

#         Args:
#             condition: 條件函數，接受 PermissionContext，返回 PermissionResult
#         """
#         self._conditions.append(condition)

#     def check_permission(self, context: PermissionContext) -> PermissionResult:
#         """執行所有條件檢查"""
#         for condition in self._conditions:
#             result = condition(context)
#             if result != PermissionResult.not_applicable:
#                 return result

#         return PermissionResult.not_applicable
