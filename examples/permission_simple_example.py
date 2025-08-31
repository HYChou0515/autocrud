#!/usr/bin/env python3
"""
簡化權限管理系統使用範例

這個範例展示如何使用簡化的 Permission model 來管理 ACL 和 RBAC 權限。
設計特點：
- 使用 tag_field 自動處理類型識別
- 簡潔的欄位設計：subject, object, action
- 支援 ResourceAction 枚舉和自定義字符串
"""

import datetime as dt
from autocrud.resource_manager.permission import (
    PermissionResourceManager,
    Permission,
    ACLPermission,
    RoleMembership,
)
from autocrud.resource_manager.core import SimpleStorage
from autocrud.resource_manager.meta_store.simple import MemoryMetaStore
from autocrud.resource_manager.resource_store.simple import MemoryResourceStore


def setup_permission_manager():
    """設置權限管理器"""
    meta_store = MemoryMetaStore()
    resource_store = MemoryResourceStore(Permission)
    storage = SimpleStorage(meta_store, resource_store)

    return PermissionResourceManager(storage=storage)


def demo_acl_permissions(pm: PermissionResourceManager, user: str, now: dt.datetime):
    """示範 ACL 權限管理"""
    print("=== ACL 權限管理示範 ===")

    with pm.meta_provide(user, now):
        # 創建 ACL 權限：用戶 alice 可以讀取文件
        acl1 = ACLPermission(
            subject="user:alice", object="file:/docs/secret.txt", action="get"
        )
        info1 = pm.create(acl1)
        print(
            f"✓ 創建 ACL 權限: {acl1.subject} 可以 {acl1.action} {acl1.object} (ID: {info1.resource_id})"
        )

        # 創建 ACL 權限：用戶 bob 可以更新文件
        acl2 = ACLPermission(
            subject="user:bob", object="file:/docs/public.txt", action="update"
        )
        info2 = pm.create(acl2)
        print(
            f"✓ 創建 ACL 權限: {acl2.subject} 可以 {acl2.action} {acl2.object} (ID: {info2.resource_id})"
        )

        # 創建 ACL 權限：服務帳戶可以管理資料庫（使用自定義動作）
        acl3 = ACLPermission(
            subject="service:backup-service",
            object="database:users",
            action="full_access",  # 自定義字符串
        )
        info3 = pm.create(acl3)
        print(
            f"✓ 創建 ACL 權限: {acl3.subject} 可以 {acl3.action} {acl3.object} (ID: {info3.resource_id})"
        )


def demo_rbac_permissions(pm: PermissionResourceManager, user: str, now: dt.datetime):
    """示範 RBAC 權限管理"""
    print("\n=== RBAC 權限管理示範 ===")

    with pm.meta_provide(user, now):
        # 1. 創建角色成員關係：將用戶加入角色群組
        admin_membership = RoleMembership(subject="user:alice", group="group:admin")
        info1 = pm.create(admin_membership)
        print(
            f"✓ 創建角色成員關係: {admin_membership.subject} 加入群組 {admin_membership.group} (ID: {info1.resource_id})"
        )

        editor_membership = RoleMembership(subject="user:bob", group="group:editor")
        info2 = pm.create(editor_membership)
        print(
            f"✓ 創建角色成員關係: {editor_membership.subject} 加入群組 {editor_membership.group} (ID: {info2.resource_id})"
        )

        # 2. 一個用戶可以屬於多個群組
        multigroup_membership = RoleMembership(
            subject="user:charlie", group="group:editor"
        )
        info3 = pm.create(multigroup_membership)
        print(
            f"✓ 創建角色成員關係: {multigroup_membership.subject} 加入群組 {multigroup_membership.group} (ID: {info3.resource_id})"
        )

        multigroup_membership2 = RoleMembership(
            subject="user:charlie", group="group:reviewer"
        )
        info4 = pm.create(multigroup_membership2)
        print(
            f"✓ 創建角色成員關係: {multigroup_membership2.subject} 也加入群組 {multigroup_membership2.group} (ID: {info4.resource_id})"
        )

        # 3. 創建基於群組的權限：定義群組可以做什麼
        admin_group_perm = ACLPermission(
            subject="group:admin", object="system:*", action="full_access"
        )
        info5 = pm.create(admin_group_perm)
        print(
            f"✓ 創建群組權限: {admin_group_perm.subject} 對 {admin_group_perm.object} 有 {admin_group_perm.action} (ID: {info5.resource_id})"
        )

        editor_group_perm = ACLPermission(
            subject="group:editor", object="content:*", action="update"
        )
        info6 = pm.create(editor_group_perm)
        print(
            f"✓ 創建群組權限: {editor_group_perm.subject} 對 {editor_group_perm.object} 有 {editor_group_perm.action} (ID: {info6.resource_id})"
        )

        reviewer_group_perm = ACLPermission(
            subject="group:reviewer", object="content:*", action="get"
        )
        info7 = pm.create(reviewer_group_perm)
        print(
            f"✓ 創建群組權限: {reviewer_group_perm.subject} 對 {reviewer_group_perm.object} 有 {reviewer_group_perm.action} (ID: {info7.resource_id})"
        )


def demo_search_permissions(pm: PermissionResourceManager):
    """示範權限搜尋功能"""
    print("\n=== 權限搜尋示範 ===")

    from autocrud.resource_manager.basic import (
        ResourceMetaSearchQuery,
        DataSearchCondition,
        DataSearchOperator,
    )

    # 1. 搜尋所有 ACL 權限
    acl_query = ResourceMetaSearchQuery(
        data_conditions=[
            DataSearchCondition(
                field_path="type",
                operator=DataSearchOperator.equals,
                value="ACLPermission",
            )
        ],
        limit=20,
    )
    acl_results = pm.search_resources(acl_query)
    print(f"✓ 找到 {len(acl_results)} 個 ACL 權限")

    # 2. 搜尋特定用戶的權限
    alice_query = ResourceMetaSearchQuery(
        data_conditions=[
            DataSearchCondition(
                field_path="subject",
                operator=DataSearchOperator.equals,
                value="user:alice",
            )
        ]
    )
    alice_results = pm.search_resources(alice_query)
    print(f"✓ 找到 Alice 的 {len(alice_results)} 個權限")

    # 3. 搜尋所有角色成員關係
    role_membership_query = ResourceMetaSearchQuery(
        data_conditions=[
            DataSearchCondition(
                field_path="type",
                operator=DataSearchOperator.equals,
                value="RoleMembership",
            )
        ]
    )
    role_membership_results = pm.search_resources(role_membership_query)
    print(f"✓ 找到 {len(role_membership_results)} 個角色成員關係")

    # 4. 搜尋所有群組權限（ACL 權限中 subject 為 group: 開頭的）
    group_acl_query = ResourceMetaSearchQuery(
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
    group_acl_results = pm.search_resources(group_acl_query)
    print(f"✓ 找到 {len(group_acl_results)} 個群組權限")


def demo_permission_lifecycle(
    pm: PermissionResourceManager, user: str, now: dt.datetime
):
    """示範權限生命週期管理"""
    print("\n=== 權限生命週期管理示範 ===")

    with pm.meta_provide(user, now):
        # 創建一個權限
        temp_perm = ACLPermission(
            subject="user:temp", object="file:/temp/data.txt", action="get"
        )
        info = pm.create(temp_perm)
        print(
            f"✓ 創建權限: {temp_perm.subject} -> {temp_perm.action} -> {temp_perm.object}"
        )

        # 讀取權限
        retrieved = pm.get(info.resource_id)
        print(f"✓ 讀取權限: {type(retrieved.data).__name__}")

        # 更新權限 - 改變動作
        if isinstance(retrieved.data, ACLPermission):
            updated_perm = ACLPermission(
                subject=retrieved.data.subject,
                object=retrieved.data.object,
                action="update",  # 改變動作
            )

            pm.update(info.resource_id, updated_perm)
            print(f"✓ 更新權限: 動作從 {temp_perm.action} 改為 {updated_perm.action}")

        # 列出所有版本
        revisions = pm.list_revisions(info.resource_id)
        print(f"✓ 權限有 {len(revisions)} 個版本: {revisions}")

        # 軟刪除權限
        deleted_meta = pm.delete(info.resource_id)
        print(f"✓ 軟刪除權限 (is_deleted: {deleted_meta.is_deleted})")

        # 恢復權限
        restored_meta = pm.restore(info.resource_id)
        print(f"✓ 恢復權限 (is_deleted: {restored_meta.is_deleted})")


def demo_type_checking(pm: PermissionResourceManager, user: str, now: dt.datetime):
    """示範類型檢查和處理"""
    print("\n=== 類型檢查示範 ===")

    with pm.meta_provide(user, now):
        # 創建不同類型的權限
        permissions = [
            ACLPermission(subject="user:test1", object="file:test1.txt", action="get"),
            RoleMembership(subject="user:test2", group="test_group"),
            ACLPermission(
                subject="group:test_group", object="resource:test", action="update"
            ),
        ]

        resource_ids = []
        for perm in permissions:
            info = pm.create(perm)
            resource_ids.append(info.resource_id)
            print(f"✓ 創建 {type(perm).__name__}")

        # 讀取並檢查類型
        print("\n檢查權限類型:")
        for rid in resource_ids:
            resource = pm.get(rid)
            data = resource.data

            if isinstance(data, ACLPermission):
                if data.subject.startswith("group:"):
                    print(
                        f"  - Group ACL: {data.subject} -> {data.action} -> {data.object}"
                    )
                else:
                    print(
                        f"  - User ACL: {data.subject} -> {data.action} -> {data.object}"
                    )
            elif isinstance(data, RoleMembership):
                print(f"  - Role Membership: {data.subject} 屬於群組 {data.group}")
            else:
                print(f"  - Unknown type: {type(data)}")


def demo_permission_checking(pm: PermissionResourceManager):
    """示範權限檢查功能"""
    print("\n=== 權限檢查示範 ===")

    # 測試不同用戶的權限
    test_cases = [
        ("user:alice", "get", "file:/docs/secret.txt"),
        ("user:alice", "full_access", "system:*"),  # 透過 admin 群組
        ("user:bob", "update", "content:*"),  # 透過 editor 群組
        ("user:charlie", "get", "content:*"),  # 透過 reviewer 群組
        ("user:charlie", "update", "content:*"),  # 透過 editor 群組
        ("user:unknown", "get", "file:test.txt"),  # 無權限用戶
    ]

    for user, action, resource in test_cases:
        result = pm.check_permission(user, action, resource)
        status = "✓ 允許" if result else "✗ 拒絕"
        print(f"  {status}: {user} -> {action} -> {resource}")


def main():
    """主程式"""
    print("簡化權限管理系統示範")
    print("=" * 50)

    # 設置
    pm = setup_permission_manager()
    user = "system_admin"
    now = dt.datetime.now()

    # 示範各種權限模型
    demo_acl_permissions(pm, user, now)
    demo_rbac_permissions(pm, user, now)

    # 示範權限檢查
    demo_permission_checking(pm)

    # 示範搜尋功能
    demo_search_permissions(pm)

    # 示範權限生命週期
    demo_permission_lifecycle(pm, user, now)

    # 示範類型檢查
    demo_type_checking(pm, user, now)

    print("\n示範完成！")
    print("\n簡化設計的特色:")
    print("✓ 簡潔結構：只用 ACL 和 RoleMembership 兩種類型")
    print("✓ 自動標籤：使用 msgspec tag 自動處理類型識別")
    print("✓ 靈活動作：支援預定義動作和自定義字符串")
    print("✓ 角色成員關係：RoleMembership 記錄用戶屬於哪個群組")
    print("✓ 群組權限：ACL 可以直接定義群組級別的權限（subject 為 group:xxx）")
    print("✓ 遞歸角色：支援角色繼承（群組可以屬於其他群組）")
    print("✓ 版本控制：基於 ResourceManager 的完整版本管理")
    print("✓ 高效搜尋：透過索引欄位支援快速查詢")
    print("✓ 類型安全：msgspec Union 類型的自動序列化/反序列化")


if __name__ == "__main__":
    main()
