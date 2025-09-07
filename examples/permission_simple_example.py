#!/usr/bin/env python3
"""簡化權限管理系統使用範例

這個範例展示如何使用簡化的 Permission model 來管理 ACL 和 RBAC 權限。
設計特點：
- 使用 tag_field 自動處理類型識別
- 簡潔的欄位設計：subject, object, action
- 支援 ResourceAction 枚舉和自定義字符串
"""

import datetime as dt

from autocrud.permission.acl import Policy
from autocrud.types import PermissionResult
from autocrud.permission.rbac import (
    RBACPermission,
    RBACPermissionChecker,
    RBACPermissionEntry,
    RoleMembership,
)
from autocrud.types import (
    DataSearchCondition,
    PermissionContext,
    ResourceAction,
    ResourceMetaSearchQuery,
)
from autocrud.resource_manager.core import ResourceManager, SimpleStorage
from autocrud.resource_manager.meta_store.simple import MemoryMetaStore
from autocrud.resource_manager.resource_store.simple import MemoryResourceStore


def setup_permission_manager():
    """設置權限管理器"""
    meta_store = MemoryMetaStore()
    resource_store = MemoryResourceStore(RBACPermission)
    storage = SimpleStorage(meta_store, resource_store)

    return ResourceManager(RBACPermission, storage=storage)


def demo_acl_permissions(
    pm: ResourceManager[RBACPermission],
    user: str,
    now: dt.datetime,
):
    """示範 RBAC 權限條目管理"""
    print("=== RBAC 權限條目管理示範 ===")

    with pm.meta_provide(user, now):
        # 創建 RBAC 權限條目：用戶 alice 可以讀取文件
        acl1 = RBACPermissionEntry(
            subject="user:alice",
            object="file:/docs/secret.txt",
            action=ResourceAction.get,
        )
        info1 = pm.create(acl1)
        print(
            f"✓ 創建 RBAC 權限條目: {acl1.subject} 可以 {acl1.action} {acl1.object} (ID: {info1.resource_id})",
        )

        # 創建 RBAC 權限條目：用戶 bob 可以更新文件
        acl2 = RBACPermissionEntry(
            subject="user:bob",
            object="file:/docs/public.txt",
            action=ResourceAction.update,
        )
        info2 = pm.create(acl2)
        print(
            f"✓ 創建 RBAC 權限條目: {acl2.subject} 可以 {acl2.action} {acl2.object} (ID: {info2.resource_id})",
        )

        # 創建 RBAC 權限條目：服務帳戶可以管理資料庫（使用完整權限）
        acl3 = RBACPermissionEntry(
            subject="service:backup-service",
            object="database:users",
            action=ResourceAction.full,  # 使用 ResourceAction 枚舉
        )
        info3 = pm.create(acl3)
        print(
            f"✓ 創建 RBAC 權限條目: {acl3.subject} 可以 {acl3.action} {acl3.object} (ID: {info3.resource_id})",
        )


def demo_rbac_permissions(
    pm: ResourceManager[RBACPermission],
    user: str,
    now: dt.datetime,
):
    """示範 RBAC 權限管理"""
    print("\n=== RBAC 權限管理示範 ===")

    with pm.meta_provide(user, now):
        # 1. 創建角色成員關係：將用戶加入角色群組
        admin_membership = RoleMembership(subject="user:alice", group="group:admin")
        info1 = pm.create(admin_membership)
        print(
            f"✓ 創建角色成員關係: {admin_membership.subject} 加入群組 {admin_membership.group} (ID: {info1.resource_id})",
        )

        editor_membership = RoleMembership(subject="user:bob", group="group:editor")
        info2 = pm.create(editor_membership)
        print(
            f"✓ 創建角色成員關係: {editor_membership.subject} 加入群組 {editor_membership.group} (ID: {info2.resource_id})",
        )

        # 2. 一個用戶可以屬於多個群組
        multigroup_membership = RoleMembership(
            subject="user:charlie",
            group="group:editor",
        )
        info3 = pm.create(multigroup_membership)
        print(
            f"✓ 創建角色成員關係: {multigroup_membership.subject} 加入群組 {multigroup_membership.group} (ID: {info3.resource_id})",
        )

        multigroup_membership2 = RoleMembership(
            subject="user:charlie",
            group="group:reviewer",
        )
        info4 = pm.create(multigroup_membership2)
        print(
            f"✓ 創建角色成員關係: {multigroup_membership2.subject} 也加入群組 {multigroup_membership2.group} (ID: {info4.resource_id})",
        )

        # 3. 創建基於群組的權限：定義群組可以做什麼
        admin_group_perm = RBACPermissionEntry(
            subject="group:admin",
            object="system:*",
            action=ResourceAction.full,
        )
        info5 = pm.create(admin_group_perm)
        print(
            f"✓ 創建群組權限: {admin_group_perm.subject} 對 {admin_group_perm.object} 有 {admin_group_perm.action} (ID: {info5.resource_id})",
        )

        editor_group_perm = RBACPermissionEntry(
            subject="group:editor",
            object="content:*",
            action=ResourceAction.update,
        )
        info6 = pm.create(editor_group_perm)
        print(
            f"✓ 創建群組權限: {editor_group_perm.subject} 對 {editor_group_perm.object} 有 {editor_group_perm.action} (ID: {info6.resource_id})",
        )

        reviewer_group_perm = RBACPermissionEntry(
            subject="group:reviewer",
            object="content:*",
            action=ResourceAction.get,
        )
        info7 = pm.create(reviewer_group_perm)
        print(
            f"✓ 創建群組權限: {reviewer_group_perm.subject} 對 {reviewer_group_perm.object} 有 {reviewer_group_perm.action} (ID: {info7.resource_id})",
        )


def demo_search_permissions(pm: ResourceManager[RBACPermission]):
    """示範權限搜尋功能"""
    print("\n=== 權限搜尋示範 ===")

    from autocrud.types import (
        DataSearchOperator,
    )

    # 0. 先搜尋所有權限看看總數
    all_query = ResourceMetaSearchQuery(limit=100)
    all_results = pm.search_resources(all_query)
    print(f"✓ 總共有 {len(all_results)} 個權限")

    # 1. 搜尋所有 RBAC 權限條目
    acl_query = ResourceMetaSearchQuery(
        data_conditions=[
            DataSearchCondition(
                field_path="type",
                operator=DataSearchOperator.equals,
                value="RBACPermissionEntry",
            ),
        ],
        limit=20,
    )
    acl_results = pm.search_resources(acl_query)
    print(f"✓ 找到 {len(acl_results)} 個 RBAC 權限條目")

    # 2. 搜尋特定用戶的權限
    alice_query = ResourceMetaSearchQuery(
        data_conditions=[
            DataSearchCondition(
                field_path="subject",
                operator=DataSearchOperator.equals,
                value="user:alice",
            ),
        ],
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
            ),
        ],
    )
    role_membership_results = pm.search_resources(role_membership_query)
    print(f"✓ 找到 {len(role_membership_results)} 個角色成員關係")

    # 4. 搜尋所有群組權限（RBAC 權限條目中 subject 為 group: 開頭的）
    group_acl_query = ResourceMetaSearchQuery(
        data_conditions=[
            DataSearchCondition(
                field_path="type",
                operator=DataSearchOperator.equals,
                value="RBACPermissionEntry",
            ),
            DataSearchCondition(
                field_path="subject",
                operator=DataSearchOperator.starts_with,
                value="group:",
            ),
        ],
    )
    group_acl_results = pm.search_resources(group_acl_query)
    print(f"✓ 找到 {len(group_acl_results)} 個群組權限")

    # 5. 展示一些具體的權限內容
    if all_results:
        print("\n權限內容範例:")
        for i, meta in enumerate(all_results[:3]):  # 只顯示前3個
            try:
                resource = pm.get(meta.resource_id)
                data = resource.data
                if isinstance(data, RBACPermissionEntry):
                    print(
                        f"  {i + 1}. RBACPermissionEntry: {data.subject} -> {data.action} -> {data.object}",
                    )
                elif isinstance(data, RoleMembership):
                    print(
                        f"  {i + 1}. RoleMembership: {data.subject} 屬於群組 {data.group}",
                    )
            except Exception as e:
                print(f"  {i + 1}. 讀取權限失敗: {e}")


def demo_permission_lifecycle(
    pm: ResourceManager[RBACPermission],
    user: str,
    now: dt.datetime,
):
    """示範權限生命週期管理"""
    print("\n=== 權限生命週期管理示範 ===")

    with pm.meta_provide(user, now):
        # 創建一個角色成員關係（這個有正確的 tag）
        temp_membership = RoleMembership(subject="user:temp", group="group:temporary")
        info = pm.create(temp_membership)
        print(
            f"✓ 創建角色成員關係: {temp_membership.subject} -> {temp_membership.group}",
        )

        # 讀取權限
        try:
            retrieved = pm.get(info.resource_id)
            print(f"✓ 讀取權限: {type(retrieved.data).__name__}")
        except Exception as e:
            print(f"✗ 讀取權限失敗: {e}")
            return

        # 列出所有版本
        try:
            revisions = pm.list_revisions(info.resource_id)
            print(f"✓ 權限有 {len(revisions)} 個版本: {revisions}")
        except Exception as e:
            print(f"✗ 列出版本失敗: {e}")

        # 軟刪除權限
        try:
            deleted_meta = pm.delete(info.resource_id)
            print(f"✓ 軟刪除權限 (is_deleted: {deleted_meta.is_deleted})")
        except Exception as e:
            print(f"✗ 刪除權限失敗: {e}")

        # 恢復權限
        try:
            restored_meta = pm.restore(info.resource_id)
            print(f"✓ 恢復權限 (is_deleted: {restored_meta.is_deleted})")
        except Exception as e:
            print(f"✗ 恢復權限失敗: {e}")


def demo_type_checking(
    pm: ResourceManager[RBACPermission],
    user: str,
    now: dt.datetime,
):
    """示範類型檢查和處理"""
    print("\n=== 類型檢查示範 ===")

    with pm.meta_provide(user, now):
        # 創建不同類型的權限
        permissions = [
            RBACPermissionEntry(
                subject="user:test1",
                object="file:test1.txt",
                action=ResourceAction.get,
            ),
            RoleMembership(subject="user:test2", group="test_group_1"),
            RBACPermissionEntry(
                subject="group:test_group_1",
                object="resource:test",
                action=ResourceAction.update,
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
            try:
                resource = pm.get(rid)
                data = resource.data

                if isinstance(data, RBACPermissionEntry):
                    if data.subject.startswith("group:"):
                        print(
                            f"  - 群組權限: {data.subject} -> {data.action} -> {data.object}",
                        )
                    else:
                        print(
                            f"  - 用戶權限: {data.subject} -> {data.action} -> {data.object}",
                        )
                elif isinstance(data, RoleMembership):
                    print(f"  - 角色成員關係: {data.subject} 屬於群組 {data.group}")
                else:
                    print(f"  - 未知類型: {type(data)}")
            except Exception as e:
                print(f"  - 讀取權限 {rid} 失敗: {e}")


def demo_permission_checking(pm: ResourceManager[RBACPermission]):
    """示範權限檢查功能"""
    print("\n=== 權限檢查示範 ===")

    # 設置真正的權限檢查器
    permission_checker = RBACPermissionChecker(
        policy=Policy.strict,
        root_user="system_admin",
    )

    # 使用權限檢查器自己的資源管理器來創建權限
    with permission_checker.pm.meta_provide("system_admin", dt.datetime.now()):
        # 創建一些測試權限直接在權限檢查器中
        test_permissions = [
            RBACPermissionEntry(
                subject="user:alice",
                object="file:/docs/secret.txt",
                action=ResourceAction.get,
            ),
            RBACPermissionEntry(
                subject="user:bob",
                object="file:/docs/public.txt",
                action=ResourceAction.update,
            ),
            RBACPermissionEntry(
                subject="service:backup-service",
                object="database:users",
                action=ResourceAction.full,
            ),
            # 群組權限
            RBACPermissionEntry(
                subject="group:editor",
                object="content:*",
                action=ResourceAction.update,
            ),
            RBACPermissionEntry(
                subject="group:reviewer",
                object="content:*",
                action=ResourceAction.get,
            ),
            # 角色成員關係
            RoleMembership(subject="user:charlie", group="group:editor"),
            RoleMembership(subject="user:charlie", group="group:reviewer"),
        ]

        for perm in test_permissions:
            try:
                permission_checker.pm.create(perm)
            except Exception as e:
                print(f"創建權限失敗: {e}")

    print(f"在權限檢查器中創建了 {len(test_permissions)} 個權限條目")

    # 測試真正的權限檢查
    test_cases = [
        ("user:alice", ResourceAction.get, "file:/docs/secret.txt"),
        ("user:bob", ResourceAction.update, "file:/docs/public.txt"),
        ("service:backup-service", ResourceAction.full, "database:users"),
        ("user:charlie", ResourceAction.update, "content:*"),  # 透過 editor 群組
        ("user:charlie", ResourceAction.get, "content:*"),  # 透過 reviewer 群組
        ("user:unknown", ResourceAction.get, "file:test.txt"),  # 無權限用戶
    ]

    print("真實權限檢查結果:")
    for user, action, resource in test_cases:
        try:
            # 創建權限檢查上下文 - 使用完整的資源名稱作為 resource_name
            context = PermissionContext(
                user=user,
                action=action,
                resource_name=resource,  # 直接使用完整的資源名稱
                resource_id=None,  # 設為 None，讓權限檢查器根據 resource_name 匹配
                now=dt.datetime.now(),
            )
            result = permission_checker.check_permission(context)
            status = "✓ 允許" if result == PermissionResult.allow else "✗ 拒絕"
            print(f"  {status}: {user} -> {action.name} -> {resource}")
        except Exception as e:
            print(f"  ✗ 檢查失敗: {user} -> {action.name} -> {resource} (錯誤: {e})")


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
    print("✓ 簡潔結構：使用 RBACPermissionEntry 和 RoleMembership 兩種類型")
    print("✓ 自動標籤：使用 msgspec tag 自動處理類型識別")
    print("✓ 靈活動作：支援預定義動作和自定義字符串")
    print("✓ 角色成員關係：RoleMembership 記錄用戶屬於哪個群組")
    print(
        "✓ 群組權限：RBACPermissionEntry 可以直接定義群組級別的權限（subject 為 group:xxx）",
    )
    print("✓ 遞歸角色：支援角色繼承（群組可以屬於其他群組）")
    print("✓ 版本控制：基於 ResourceManager 的完整版本管理")
    print("✓ 高效搜尋：透過索引欄位支援快速查詢")
    print("✓ 類型安全：msgspec Union 類型的自動序列化/反序列化")


if __name__ == "__main__":
    main()
