#!/usr/bin/env python3
"""
權限管理系統測試

測試 ACL 和 RBAC 權限系統的各種功能，包括：
- ACL 權限管理
- RBAC 角色成員關係
- 權限檢查邏輯
- 搜尋功能
- 生命週期管理
"""

import datetime as dt
import pytest
from autocrud.resource_manager.permission import (
    PermissionResourceManager,
    Permission,
    ACLPermission,
    RoleMembership,
    Policy,
    Effect,
)
from autocrud.resource_manager.core import SimpleStorage
from autocrud.resource_manager.meta_store.simple import MemoryMetaStore
from autocrud.resource_manager.resource_store.simple import MemoryResourceStore
from autocrud.resource_manager.basic import (
    ResourceMetaSearchQuery,
    DataSearchCondition,
    DataSearchOperator,
)


@pytest.fixture
def permission_manager():
    """設置權限管理器"""
    meta_store = MemoryMetaStore()
    resource_store = MemoryResourceStore(Permission)
    storage = SimpleStorage(meta_store, resource_store)
    return PermissionResourceManager(storage=storage)


@pytest.fixture
def admin_user():
    """測試用管理員用戶"""
    return "system_admin"


@pytest.fixture
def current_time():
    """當前時間"""
    return dt.datetime.now()


class TestACLPermissions:
    """測試 ACL 權限管理"""

    def test_create_user_acl_permission(
        self, permission_manager, admin_user, current_time
    ):
        """測試創建用戶 ACL 權限"""
        pm = permission_manager

        with pm.meta_provide(admin_user, current_time):
            acl = ACLPermission(
                subject="user:alice", object="file:/docs/secret.txt", action="get"
            )
            info = pm.create(acl)

            assert info.resource_id is not None

            # 驗證創建的權限
            retrieved = pm.get(info.resource_id)
            assert isinstance(retrieved.data, ACLPermission)
            assert retrieved.data.subject == "user:alice"
            assert retrieved.data.object == "file:/docs/secret.txt"
            assert retrieved.data.action == "get"
            assert retrieved.data.effect == Effect.allow

    def test_create_service_acl_permission(
        self, permission_manager, admin_user, current_time
    ):
        """測試創建服務 ACL 權限"""
        pm = permission_manager

        with pm.meta_provide(admin_user, current_time):
            acl = ACLPermission(
                subject="service:backup-service",
                object="database:users",
                action="full_access",
                effect=Effect.allow,
            )
            info = pm.create(acl)

            retrieved = pm.get(info.resource_id)
            assert retrieved.data.subject == "service:backup-service"
            assert retrieved.data.action == "full_access"

    def test_create_deny_acl_permission(
        self, permission_manager, admin_user, current_time
    ):
        """測試創建拒絕 ACL 權限"""
        pm = permission_manager

        with pm.meta_provide(admin_user, current_time):
            acl = ACLPermission(
                subject="user:blocked",
                object="file:/sensitive.txt",
                action="get",
                effect=Effect.deny,
            )
            info = pm.create(acl)

            retrieved = pm.get(info.resource_id)
            assert retrieved.data.effect == Effect.deny


class TestRBACPermissions:
    """測試 RBAC 權限管理"""

    def test_create_role_membership(self, permission_manager, admin_user, current_time):
        """測試創建角色成員關係"""
        pm = permission_manager

        with pm.meta_provide(admin_user, current_time):
            membership = RoleMembership(subject="user:alice", group="group:admin")
            info = pm.create(membership)

            retrieved = pm.get(info.resource_id)
            assert isinstance(retrieved.data, RoleMembership)
            assert retrieved.data.subject == "user:alice"
            assert retrieved.data.group == "group:admin"

    def test_multiple_group_membership(
        self, permission_manager, admin_user, current_time
    ):
        """測試用戶屬於多個群組"""
        pm = permission_manager

        with pm.meta_provide(admin_user, current_time):
            # 用戶加入編輯者群組
            membership1 = RoleMembership(subject="user:charlie", group="group:editor")
            info1 = pm.create(membership1)

            # 用戶加入審查者群組
            membership2 = RoleMembership(subject="user:charlie", group="group:reviewer")
            info2 = pm.create(membership2)

            # 驗證兩個成員關係都存在
            retrieved1 = pm.get(info1.resource_id)
            retrieved2 = pm.get(info2.resource_id)

            assert retrieved1.data.group == "group:editor"
            assert retrieved2.data.group == "group:reviewer"

    def test_group_acl_permissions(self, permission_manager, admin_user, current_time):
        """測試群組 ACL 權限"""
        pm = permission_manager

        with pm.meta_provide(admin_user, current_time):
            # 創建群組權限
            group_perm = ACLPermission(
                subject="group:admin", object="system:*", action="full_access"
            )
            info = pm.create(group_perm)

            retrieved = pm.get(info.resource_id)
            assert retrieved.data.subject == "group:admin"
            assert retrieved.data.object == "system:*"
            assert retrieved.data.action == "full_access"


class TestPermissionChecking:
    """測試權限檢查邏輯"""

    def setup_test_permissions(self, pm, admin_user, current_time):
        """設置測試用權限"""
        with pm.meta_provide(admin_user, current_time):
            # 創建直接 ACL 權限
            acl1 = ACLPermission(
                subject="user:alice", object="file:/docs/secret.txt", action="get"
            )
            pm.create(acl1)

            # 創建角色成員關係
            membership = RoleMembership(subject="user:alice", group="group:admin")
            pm.create(membership)

            # 創建群組權限
            group_perm = ACLPermission(
                subject="group:admin", object="system:*", action="full_access"
            )
            pm.create(group_perm)

    def test_direct_acl_permission_check(
        self, permission_manager, admin_user, current_time
    ):
        """測試直接 ACL 權限檢查"""
        pm = permission_manager
        self.setup_test_permissions(pm, admin_user, current_time)

        # 測試直接權限
        result = pm.check_permission("user:alice", "get", "file:/docs/secret.txt")
        assert result is True

    def test_rbac_permission_check(self, permission_manager, admin_user, current_time):
        """測試 RBAC 權限檢查"""
        pm = permission_manager
        self.setup_test_permissions(pm, admin_user, current_time)

        # 測試通過群組的權限
        result = pm.check_permission("user:alice", "full_access", "system:*")
        assert result is True

    def test_no_permission_check(self, permission_manager, admin_user, current_time):
        """測試無權限情況"""
        pm = permission_manager
        self.setup_test_permissions(pm, admin_user, current_time)

        # 測試無權限用戶
        result = pm.check_permission("user:unknown", "get", "file:test.txt")
        assert result is False

    def test_deny_permission_check(self, permission_manager, admin_user, current_time):
        """測試拒絕權限"""
        pm = permission_manager

        with pm.meta_provide(admin_user, current_time):
            # 創建拒絕權限
            deny_acl = ACLPermission(
                subject="user:blocked",
                object="file:/sensitive.txt",
                action="get",
                effect=Effect.deny,
            )
            pm.create(deny_acl)

        result = pm.check_permission("user:blocked", "get", "file:/sensitive.txt")
        assert result is False


class TestPermissionSearch:
    """測試權限搜尋功能"""

    def setup_search_test_data(self, pm, admin_user, current_time):
        """設置搜尋測試數據"""
        with pm.meta_provide(admin_user, current_time):
            # 創建多個 ACL 權限
            acl1 = ACLPermission(
                subject="user:alice", object="file:1.txt", action="get"
            )
            acl2 = ACLPermission(
                subject="user:bob", object="file:2.txt", action="update"
            )
            acl3 = ACLPermission(
                subject="group:admin", object="system:*", action="full_access"
            )

            pm.create(acl1)
            pm.create(acl2)
            pm.create(acl3)

            # 創建角色成員關係
            membership = RoleMembership(subject="user:alice", group="group:admin")
            pm.create(membership)

    def test_search_all_acl_permissions(
        self, permission_manager, admin_user, current_time
    ):
        """測試搜尋所有 ACL 權限"""
        pm = permission_manager
        self.setup_search_test_data(pm, admin_user, current_time)

        query = ResourceMetaSearchQuery(
            data_conditions=[
                DataSearchCondition(
                    field_path="type",
                    operator=DataSearchOperator.equals,
                    value="ACLPermission",
                )
            ]
        )
        results = pm.search_resources(query)
        assert len(results) == 3

    def test_search_user_permissions(
        self, permission_manager, admin_user, current_time
    ):
        """測試搜尋特定用戶權限"""
        pm = permission_manager
        self.setup_search_test_data(pm, admin_user, current_time)

        query = ResourceMetaSearchQuery(
            data_conditions=[
                DataSearchCondition(
                    field_path="subject",
                    operator=DataSearchOperator.equals,
                    value="user:alice",
                )
            ]
        )
        results = pm.search_resources(query)
        assert len(results) == 2  # 1 ACL + 1 RoleMembership

    def test_search_group_permissions(
        self, permission_manager, admin_user, current_time
    ):
        """測試搜尋群組權限"""
        pm = permission_manager
        self.setup_search_test_data(pm, admin_user, current_time)

        query = ResourceMetaSearchQuery(
            data_conditions=[
                DataSearchCondition(
                    field_path="type",
                    operator=DataSearchOperator.equals,
                    value="ACLPermission",
                ),
                DataSearchCondition(
                    field_path="subject",
                    operator=DataSearchOperator.starts_with,
                    value="group:",
                ),
            ]
        )
        results = pm.search_resources(query)
        assert len(results) == 1


class TestPermissionLifecycle:
    """測試權限生命週期管理"""

    def test_permission_crud_operations(
        self, permission_manager, admin_user, current_time
    ):
        """測試權限 CRUD 操作"""
        pm = permission_manager

        with pm.meta_provide(admin_user, current_time):
            # 創建
            acl = ACLPermission(
                subject="user:temp", object="file:/temp/data.txt", action="get"
            )
            info = pm.create(acl)

            # 讀取
            retrieved = pm.get(info.resource_id)
            assert retrieved.data.action == "get"

            # 更新
            updated_acl = ACLPermission(
                subject="user:temp",
                object="file:/temp/data.txt",
                action="update",  # 改變動作
            )
            update_info = pm.update(info.resource_id, updated_acl)

            # 驗證更新
            updated_retrieved = pm.get(info.resource_id)
            assert updated_retrieved.data.action == "update"

            # 檢查版本
            revisions = pm.list_revisions(info.resource_id)
            assert len(revisions) == 2

    def test_permission_soft_delete_restore(
        self, permission_manager, admin_user, current_time
    ):
        """測試權限軟刪除和恢復"""
        pm = permission_manager

        with pm.meta_provide(admin_user, current_time):
            # 創建權限
            acl = ACLPermission(
                subject="user:temp", object="file:test.txt", action="get"
            )
            info = pm.create(acl)

            # 軟刪除
            deleted_meta = pm.delete(info.resource_id)
            assert deleted_meta.is_deleted is True

            # 恢復
            restored_meta = pm.restore(info.resource_id)
            assert restored_meta.is_deleted is False


class TestPolicyBehavior:
    """測試策略行為"""

    def test_strict_policy(self):
        """測試嚴格策略"""
        meta_store = MemoryMetaStore()
        resource_store = MemoryResourceStore(Permission)
        storage = SimpleStorage(meta_store, resource_store)
        pm = PermissionResourceManager(storage=storage, policy=Policy.strict)

        user = "test_admin"
        now = dt.datetime.now()

        with pm.meta_provide(user, now):
            # 創建 allow 權限
            acl = ACLPermission(
                subject="user:test", object="file:test.txt", action="get"
            )
            pm.create(acl)

        # 嚴格策略下，有 allow 應該允許
        result = pm.check_permission("user:test", "get", "file:test.txt")
        assert result is True

        # 沒有權限應該拒絕
        result = pm.check_permission("user:unknown", "get", "file:test.txt")
        assert result is False

    def test_permissive_policy(self):
        """測試寬鬆策略"""
        meta_store = MemoryMetaStore()
        resource_store = MemoryResourceStore(Permission)
        storage = SimpleStorage(meta_store, resource_store)
        pm = PermissionResourceManager(storage=storage, policy=Policy.permissive)

        user = "test_admin"
        now = dt.datetime.now()

        with pm.meta_provide(user, now):
            # 創建 allow 權限
            acl = ACLPermission(
                subject="user:test", object="file:test.txt", action="get"
            )
            pm.create(acl)

        # 寬鬆策略下，有 allow 應該允許
        result = pm.check_permission("user:test", "get", "file:test.txt")
        assert result is True


class TestComplexScenarios:
    """測試複雜場景"""

    def test_hierarchical_roles(self, permission_manager, admin_user, current_time):
        """測試層級角色"""
        pm = permission_manager

        with pm.meta_provide(admin_user, current_time):
            # 設置用戶 -> 編輯者 -> 管理員的層級關係

            # 用戶屬於編輯者群組
            membership1 = RoleMembership(subject="user:editor1", group="group:editor")
            pm.create(membership1)

            # 編輯者群組屬於管理員群組
            membership2 = RoleMembership(subject="group:editor", group="group:admin")
            pm.create(membership2)

            # 管理員群組有系統權限
            admin_perm = ACLPermission(
                subject="group:admin", object="system:*", action="full_access"
            )
            pm.create(admin_perm)

        # 用戶應該能通過層級關係獲得管理員權限
        result = pm.check_permission("user:editor1", "full_access", "system:*")
        assert result is True

    def test_mixed_allow_deny_permissions(
        self, permission_manager, admin_user, current_time
    ):
        """測試混合允許和拒絕權限"""
        pm = permission_manager

        with pm.meta_provide(admin_user, current_time):
            # 創建 allow 權限
            allow_acl = ACLPermission(
                subject="user:mixed",
                object="file:test.txt",
                action="get",
                effect=Effect.allow,
                order=1,
            )
            pm.create(allow_acl)

            # 創建 deny 權限（更高優先級）
            deny_acl = ACLPermission(
                subject="user:mixed",
                object="file:test.txt",
                action="get",
                effect=Effect.deny,
                order=0,
            )
            pm.create(deny_acl)

        # 在嚴格策略下，有 deny 應該拒絕
        result = pm.check_permission("user:mixed", "get", "file:test.txt")
        assert result is False

    def test_wildcard_patterns(self, permission_manager, admin_user, current_time):
        """測試通配符模式匹配"""
        pm = permission_manager

        with pm.meta_provide(admin_user, current_time):
            # 創建通配符權限
            wildcard_acl = ACLPermission(
                subject="user:admin", object="file:/*", action="*"
            )
            pm.create(wildcard_acl)

        # 測試通配符匹配 (這需要 ResourceManager 支援模式匹配)
        # 注意：此測試顯示了設計意圖，實際實現可能需要額外邏輯
        result = pm.check_permission("user:admin", "get", "file:/docs/test.txt")
        # 現在的實現是精確匹配，所以會失敗
        assert result is False

        # 但精確匹配應該成功
        result = pm.check_permission("user:admin", "*", "file:/*")
        assert result is True

    def test_large_permission_set_performance(
        self, permission_manager, admin_user, current_time
    ):
        """測試大量權限的性能"""
        pm = permission_manager

        with pm.meta_provide(admin_user, current_time):
            # 創建大量權限（模擬實際使用場景）
            for i in range(100):
                # 創建用戶權限
                acl = ACLPermission(
                    subject=f"user:user{i}", object=f"resource:{i}", action="get"
                )
                pm.create(acl)

                # 創建群組成員關係
                if i % 10 == 0:  # 每10個用戶建一個群組
                    membership = RoleMembership(
                        subject=f"user:user{i}", group=f"group:team{i // 10}"
                    )
                    pm.create(membership)

        # 測試查詢性能
        import time

        start_time = time.time()

        # 執行權限檢查
        result = pm.check_permission("user:user50", "get", "resource:50")
        assert result is True

        # 執行搜尋
        query = ResourceMetaSearchQuery(
            data_conditions=[
                DataSearchCondition(
                    field_path="type",
                    operator=DataSearchOperator.equals,
                    value="ACLPermission",
                )
            ],
            limit=200,  # 增加限制以獲得所有結果
        )
        results = pm.search_resources(query)

        end_time = time.time()
        execution_time = end_time - start_time

        # 驗證結果
        assert len(results) == 100
        assert execution_time < 1.0  # 應該在 1 秒內完成

        print(
            f"Performance test: {len(results)} permissions processed in {execution_time:.4f} seconds"
        )


class TestEdgeCases:
    """測試邊界情況"""

    def test_empty_subject_object_action(
        self, permission_manager, admin_user, current_time
    ):
        """測試空的 subject, object, action"""
        pm = permission_manager

        with pm.meta_provide(admin_user, current_time):
            # 空字符串不應該導致錯誤
            acl = ACLPermission(subject="", object="", action="")
            info = pm.create(acl)

            retrieved = pm.get(info.resource_id)
            assert retrieved.data.subject == ""
            assert retrieved.data.object == ""
            assert retrieved.data.action == ""

    def test_circular_role_membership(
        self, permission_manager, admin_user, current_time
    ):
        """測試循環角色成員關係"""
        pm = permission_manager

        with pm.meta_provide(admin_user, current_time):
            # 創建循環關係: A -> B -> C -> A
            membership1 = RoleMembership(subject="group:A", group="group:B")
            pm.create(membership1)

            membership2 = RoleMembership(subject="group:B", group="group:C")
            pm.create(membership2)

            membership3 = RoleMembership(subject="group:C", group="group:A")
            pm.create(membership3)

            # 給 A 群組設置權限
            acl = ACLPermission(subject="group:A", object="resource:test", action="get")
            pm.create(acl)

        # 檢查是否能處理循環關係 (應該不會無限循環)
        result = pm.check_permission("group:B", "get", "resource:test")
        # 由於有循環檢測，應該能找到權限
        assert result is True

    def test_special_characters_in_names(
        self, permission_manager, admin_user, current_time
    ):
        """測試名稱中的特殊字符"""
        pm = permission_manager

        with pm.meta_provide(admin_user, current_time):
            # 包含特殊字符的名稱
            acl = ACLPermission(
                subject="user:test@example.com",
                object="file://server/path with spaces/檔案.txt",
                action="read/write",
            )
            info = pm.create(acl)

            retrieved = pm.get(info.resource_id)
            assert retrieved.data.subject == "user:test@example.com"
            assert retrieved.data.object == "file://server/path with spaces/檔案.txt"
            assert retrieved.data.action == "read/write"

        # 權限檢查也應該正常工作
        result = pm.check_permission(
            "user:test@example.com",
            "read/write",
            "file://server/path with spaces/檔案.txt",
        )
        assert result is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
