"""
權限檢查系統使用範例
展示如何使用新的權限上下文模式來實現靈活的權限檢查
"""
from autocrud.resource_manager.permission_context import (
    IPermissionChecker,
    PermissionContext,
    PermissionResult,
    CompositePermissionChecker,
    DefaultPermissionChecker,
)
from autocrud.resource_manager.permission import PermissionResourceManager
from autocrud.resource_manager.core import ResourceManager
import datetime as dt


class CustomResourceAccessChecker(IPermissionChecker):
    """自定義資源存取檢查器 - 展示如何實現複雜的權限邏輯"""
    
    def __init__(self, permission_manager: PermissionResourceManager):
        self.permission_manager = permission_manager
        self.supported_actions = {"get", "update", "delete", "patch", "switch"}
    
    def supports_action(self, action: str) -> bool:
        return action in self.supported_actions
    
    def check_permission(self, context: PermissionContext) -> PermissionResult:
        """
        實現自定義權限檢查邏輯
        - 對於 get 操作：檢查具體的 resource_id
        - 對於 update/delete：除了檢查 resource_id，還要檢查 data 內容
        """
        if not context.resource_id:
            # 如果沒有 resource_id，嘗試從方法參數中提取
            if context.method_args:
                resource_id = context.method_args[0]
            else:
                return PermissionResult.DENY
        else:
            resource_id = context.resource_id
        
        # 基本權限檢查
        is_allowed = self.permission_manager.check_permission(
            context.user,
            context.action,
            resource_id
        )
        
        if not is_allowed:
            return PermissionResult.DENY
        
        # 特殊邏輯：對於 update 操作，檢查新資料內容
        if context.action == "update" and len(context.method_args) >= 2:
            new_data = context.method_args[1]
            
            # 範例：檢查敏感欄位
            if hasattr(new_data, 'sensitive_field'):
                # 只有管理員可以修改敏感欄位
                admin_check = self.permission_manager.check_permission(
                    context.user, "admin", "system"
                )
                if not admin_check:
                    return PermissionResult.DENY
        
        return PermissionResult.ALLOW


class DataFilterChecker(IPermissionChecker):
    """資料過濾檢查器 - 檢查搜尋查詢是否合理"""
    
    def supports_action(self, action: str) -> bool:
        return action == "search_resources"
    
    def check_permission(self, context: PermissionContext) -> PermissionResult:
        # 檢查查詢條件
        query = context.method_kwargs.get("query")
        if query and hasattr(query, 'data_conditions'):
            # 範例：限制查詢範圍
            for condition in query.data_conditions:
                if condition.field_path == "sensitive_data":
                    # 檢查用戶是否有查詢敏感資料的權限
                    return PermissionResult.DENY
        
        return PermissionResult.ALLOW


class TimeBasedChecker(IPermissionChecker):
    """時間基礎檢查器 - 在特定時間段限制某些操作"""
    
    def supports_action(self, action: str) -> bool:
        return action in {"update", "delete", "create"}
    
    def check_permission(self, context: PermissionContext) -> PermissionResult:
        now = dt.datetime.now()
        
        # 範例：在工作時間外限制修改操作
        if now.hour < 8 or now.hour > 18:
            if context.action in {"update", "delete"}:
                # 檢查是否有緊急操作權限
                emergency = context.extra_data.get("emergency", False)
                if not emergency:
                    return PermissionResult.DENY
        
        return PermissionResult.SKIP  # 讓其他檢查器決定


def setup_advanced_permission_checking(
    resource_manager: ResourceManager,
    permission_manager: PermissionResourceManager
) -> ResourceManager:
    """
    設定進階權限檢查系統
    
    這個函數展示如何組合多個權限檢查器來實現複雜的權限邏輯
    """
    
    # 建立組合權限檢查器
    composite_checker = CompositePermissionChecker()
    
    # 添加自定義檢查器（按優先順序）
    composite_checker.add_checker(TimeBasedChecker())
    composite_checker.add_checker(CustomResourceAccessChecker(permission_manager))
    composite_checker.add_checker(DataFilterChecker())
    
    # 添加預設檢查器作為最後的備用
    composite_checker.add_checker(DefaultPermissionChecker(permission_manager))
    
    # 設定到 resource_manager
    resource_manager.permission_checker = composite_checker
    
    return resource_manager


# === 使用範例 ===

def example_usage():
    """展示如何使用新的權限檢查系統"""
    
    # 假設你已經有了這些
    # permission_manager = PermissionResourceManager(...)
    # resource_manager = ResourceManager(...)
    
    # 方法 1: 使用預設檢查器（向後相容）
    # resource_manager.permission_checker = DefaultPermissionChecker(permission_manager)
    
    # 方法 2: 使用自定義檢查器
    # resource_manager.permission_checker = CustomResourceAccessChecker(permission_manager)
    
    # 方法 3: 使用組合檢查器（推薦）
    # resource_manager = setup_advanced_permission_checking(resource_manager, permission_manager)
    
    # 現在所有的 CRUD 操作都會使用新的權限檢查邏輯
    
    # 範例：帶緊急標記的更新操作
    # with resource_manager.meta_provide("user:alice", dt.datetime.now()):
    #     # 這個更新操作會被傳遞 extra_data 到權限檢查器
    #     # (需要在裝飾器中支援 extra_data 傳遞)
    #     resource_manager.update("resource:123", new_data)
    
    pass


if __name__ == "__main__":
    example_usage()
