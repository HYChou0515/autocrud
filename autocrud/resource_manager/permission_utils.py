"""
權限設定便利函數

提供更安全、更語義化的權限設定方式，避免直接使用 object=None
"""

from autocrud.resource_manager.basic import ResourceAction
from autocrud.resource_manager.permission import ACLPermission, RoleMembership, Effect
from typing import Literal


class PermissionBuilder:
    """權限建構器 - 提供安全的權限設定方式"""
    
    @staticmethod
    def allow_user_on_resource_type(
        user: str, 
        resource_type: str, 
        action: ResourceAction,
        order: int | None = None
    ) -> ACLPermission:
        """允許用戶對特定資源類型執行操作
        
        Args:
            user: 用戶名稱 (會自動加上 'user:' 前綴)
            resource_type: 資源類型名稱 (例如 'document', 'file')
            action: 動作名稱
            order: 權限優先級
            
        Example:
            # 允許 alice 創建文檔
            PermissionBuilder.allow_user_on_resource_type("alice", "document", "create")
        """
        subject = user if user.startswith(('user:', 'group:', 'service:')) else f"user:{user}"
        
        return ACLPermission(
            subject=user,
            object=resource_type,
            action=action,
            effect=Effect.allow,
            order=order
        )
    
    @staticmethod
    def allow_user_on_specific_resource(
        user: str,
        resource_id: str,
        action: str,
        order: int | None = None
    ) -> ACLPermission:
        """允許用戶對特定資源執行操作
        
        Args:
            user: 用戶名稱
            resource_id: 完整的資源 ID
            action: 動作名稱
            order: 權限優先級
            
        Example:
            # 允許 alice 讀取特定文檔
            PermissionBuilder.allow_user_on_specific_resource(
                "alice", "document:123e4567-e89b-12d3-a456-426614174000", "get"
            )
        """
        subject = user if user.startswith(('user:', 'group:', 'service:')) else f"user:{user}"
        
        return ACLPermission(
            subject=subject,
            object=resource_id,
            action=action,
            effect=Effect.allow,
            order=order
        )
    
    @staticmethod
    def allow_group_on_resource_type(
        group: str,
        resource_type: str,
        action: str,
        order: int | None = None
    ) -> ACLPermission:
        """允許群組對特定資源類型執行操作
        
        Args:
            group: 群組名稱 (會自動加上 'group:' 前綴)
            resource_type: 資源類型名稱
            action: 動作名稱
            order: 權限優先級
            
        Example:
            # 允許 admin 群組對所有文檔執行所有操作
            PermissionBuilder.allow_group_on_resource_type("admin", "document", "*")
        """
        subject = group if group.startswith('group:') else f"group:{group}"
        
        return ACLPermission(
            subject=subject,
            object=resource_type,
            action=action,
            effect=Effect.allow,
            order=order
        )
    
    @staticmethod
    def deny_user_action(
        user: str,
        resource_type_or_id: str,
        action: str,
        order: int = 0  # deny 通常需要高優先級
    ) -> ACLPermission:
        """拒絕用戶執行特定操作
        
        Args:
            user: 用戶名稱
            resource_type_or_id: 資源類型或具體資源 ID
            action: 動作名稱
            order: 權限優先級 (deny 通常應該有高優先級)
            
        Example:
            # 拒絕 bob 刪除任何文檔
            PermissionBuilder.deny_user_action("bob", "document", "delete")
        """
        subject = user if user.startswith(('user:', 'group:', 'service:')) else f"user:{user}"
        
        return ACLPermission(
            subject=subject,
            object=resource_type_or_id,
            action=action,
            effect=Effect.deny,
            order=order
        )
    
    @staticmethod
    def create_role_membership(
        user: str,
        group: str,
        order: int | None = None
    ) -> RoleMembership:
        """創建角色成員關係
        
        Args:
            user: 用戶名稱 (會自動加上 'user:' 前綴)
            group: 群組名稱 (會自動加上 'group:' 前綴)
            order: 優先級
            
        Example:
            # 將 alice 加入 admin 群組
            PermissionBuilder.create_role_membership("alice", "admin")
        """
        subject = user if user.startswith(('user:', 'group:', 'service:')) else f"user:{user}"
        group_name = group if group.startswith('group:') else f"group:{group}"
        
        return RoleMembership(
            subject=subject,
            group=group_name,
            order=order
        )


class CommonPermissions:
    """常用權限模式"""
    
    @staticmethod
    def full_access_for_user(user: str, resource_type: str) -> list[ACLPermission]:
        """為用戶提供對資源類型的完整權限
        
        Returns:
            包含所有標準操作權限的列表
        """
        actions = ["create", "get", "get_meta", "get_resource_revision", "update", "patch", "delete", "search_resources"]
        subject = user if user.startswith(('user:', 'group:', 'service:')) else f"user:{user}"
        
        return [
            ACLPermission(
                subject=subject,
                object=resource_type,
                action=action,
                effect=Effect.allow
            )
            for action in actions
        ]
    
    @staticmethod
    def read_only_for_user(user: str, resource_type: str) -> list[ACLPermission]:
        """為用戶提供對資源類型的唯讀權限"""
        read_actions = ["get", "get_meta", "get_resource_revision", "search_resources"]
        subject = user if user.startswith(('user:', 'group:', 'service:')) else f"user:{user}"
        
        return [
            ACLPermission(
                subject=subject,
                object=resource_type,
                action=action,
                effect=Effect.allow
            )
            for action in read_actions
        ]
    
    @staticmethod
    def owner_permissions_for_user(user: str, resource_type: str) -> list[ACLPermission]:
        """為用戶提供擁有者權限（創建 + 對自己創建的資源的完整權限）
        
        注意：這需要配合 ResourceOwnershipChecker 使用
        """
        return [
            # 可以創建新資源
            ACLPermission(
                subject=user if user.startswith(('user:', 'group:', 'service:')) else f"user:{user}",
                object=resource_type,
                action="create",
                effect=Effect.allow
            ),
            # 可以查看資源列表
            ACLPermission(
                subject=user if user.startswith(('user:', 'group:', 'service:')) else f"user:{user}",
                object=resource_type,
                action="search_resources",
                effect=Effect.allow
            )
        ]


# 使用示例
def permission_setup_examples():
    """權限設定示例"""
    
    permissions = []
    
    # 方法 1: 使用 PermissionBuilder
    permissions.extend([
        # 基本用戶權限
        PermissionBuilder.allow_user_on_resource_type("alice", "document", "create"),
        PermissionBuilder.allow_user_on_resource_type("alice", "document", "get"),
        PermissionBuilder.allow_user_on_resource_type("alice", "document", "search_resources"),
        
        # 管理員群組權限
        PermissionBuilder.allow_group_on_resource_type("admin", "document", "*"),
        PermissionBuilder.allow_group_on_resource_type("admin", "*", "*"),  # 超級管理員
        
        # 角色成員關係
        PermissionBuilder.create_role_membership("alice", "editor"),
        PermissionBuilder.create_role_membership("bob", "viewer"),
        
        # 拒絕權限
        PermissionBuilder.deny_user_action("guest", "document", "delete"),
    ])
    
    # 方法 2: 使用 CommonPermissions
    permissions.extend(CommonPermissions.full_access_for_user("admin", "document"))
    permissions.extend(CommonPermissions.read_only_for_user("viewer", "document"))
    permissions.extend(CommonPermissions.owner_permissions_for_user("author", "document"))
    
    return permissions


def deprecated_patterns():
    """不推薦的權限設定模式（僅供參考）"""
    
    # ❌ 不推薦：使用 object=None
    dangerous_permission = ACLPermission(
        subject="user:alice",
        object=None,  # 危險：可能給予意外的權限
        action="delete",
        effect=Effect.allow
    )
    
    # ✅ 推薦：使用明確的資源類型
    safe_permission = PermissionBuilder.allow_user_on_resource_type(
        "alice", "document", "delete"
    )
    
    return [dangerous_permission, safe_permission]
