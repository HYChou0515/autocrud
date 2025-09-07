#!/usr/bin/env python3
"""完整的權限系統測試

測試基於我們完整權限系統的所有 ResourceManager 操作，包括：
- 權限創建和管理
- Root 用戶權限
- 所有 CRUD 操作的權限檢查
- 錯誤情況處理
"""

import datetime as dt
from dataclasses import dataclass

import pytest

from autocrud.permission.acl import ACLPermission, ACLPermissionChecker, Policy
from autocrud.types import (
    BeforeCreate,
    BeforeDelete,
    BeforeGet,
    BeforeLoad,
    PermissionResult,
)
from autocrud.types import PermissionDeniedError
from autocrud.resource_manager.core import ResourceManager, SimpleStorage
from autocrud.resource_manager.meta_store.simple import MemoryMetaStore
from autocrud.resource_manager.resource_store.simple import MemoryResourceStore
from autocrud.resource_manager.storage_factory import MemoryStorageFactory
from autocrud.types import ResourceAction


@dataclass
class TestDocument:
    title: str
    content: str


class TestCaseUtil:
    @pytest.fixture(autouse=True)
    def setup_permission_system(self):
        """設置完整的權限系統"""
        # 設定基本組件
        resource_store = MemoryResourceStore(TestDocument)
        storage = SimpleStorage(
            meta_store=MemoryMetaStore(),
            resource_store=resource_store,
        )

        # 設定權限管理器
        permission_checker = ACLPermissionChecker(
            policy=Policy.deny_overrides,
            storage_factory=MemoryStorageFactory(),
        )

        # 建立 document manager
        document_manager = ResourceManager(
            TestDocument,
            storage=storage,
            permission_checker=permission_checker,
        )
        self.pc = permission_checker
        self.permission_manager = self.pc.pm
        self.document_manager = document_manager
        self.current_time = dt.datetime.now()


class TestPermissionCreationAndManagement(TestCaseUtil):
    """測試權限創建和管理"""

    def test_create_permissions(self):
        """測試創建權限"""
        pm = self.permission_manager
        current_time = self.current_time

        # 在 system context 中創建權限
        with pm.meta_provide("root", current_time):
            # 給 alice 完整權限
            alice_permissions = ACLPermission(
                subject="alice",
                object="test_document",
                action=ResourceAction.create
                | ResourceAction.read
                | ResourceAction.update
                | ResourceAction.delete,
                effect=PermissionResult.allow,
            )
            alice_resource_id = pm.create(alice_permissions).resource_id

            # 給 bob 只有讀取權限
            bob_permissions = ACLPermission(
                subject="bob",
                object="test_document",
                action=ResourceAction.read,
                effect=PermissionResult.allow,
            )
            bob_resource_id = pm.create(bob_permissions).resource_id

            # 驗證權限被正確創建
            assert alice_resource_id is not None
            assert bob_resource_id is not None
            assert len(pm.storage._meta_store) == 2  # 兩個權限記錄


class TestRootUserPermissions(TestCaseUtil):
    """測試 Root 用戶權限"""

    def test_root_user_has_all_permissions(self):
        """測試 root 用戶擁有所有權限"""
        assert (
            self.pc.check_permission(
                BeforeCreate(
                    user="root",
                    now=self.current_time,
                    resource_name="test_document",
                    data={"title": "Root's Doc", "content": "Content"},
                ),
            )
            is PermissionResult.allow
        )
        assert (
            self.pc.check_permission(
                BeforeGet(
                    user="root",
                    now=self.current_time,
                    resource_name="test_document",
                    resource_id="doc123",
                ),
            )
            is PermissionResult.allow
        )
        assert (
            self.pc.check_permission(
                BeforeCreate(
                    user="root",
                    now=self.current_time,
                    resource_name="test_document",
                    data={"title": "Root's Doc", "content": "Content"},
                ),
            )
            is PermissionResult.allow
        )
        assert (
            self.pc.check_permission(
                BeforeDelete(
                    user="root",
                    now=self.current_time,
                    resource_name="test_document",
                    resource_id="doc123",
                ),
            )
            is PermissionResult.allow
        )
        assert (
            self.pc.check_permission(
                BeforeLoad(
                    user="root",
                    now=self.current_time,
                    resource_name="test_document",
                    key="some_key",
                ),
            )
            is PermissionResult.allow
        )


class TestResourceManagerCRUDOperations(TestCaseUtil):
    """測試 ResourceManager 的所有 CRUD 操作"""

    def setup_permissions(self):
        """設置測試權限"""
        pm = self.permission_manager
        current_time = self.current_time

        with pm.meta_provide("root", current_time):
            # Alice: 完整權限
            alice_permissions = ACLPermission(
                subject="alice",
                object="test_document",
                action=ResourceAction.create
                | ResourceAction.read
                | ResourceAction.update
                | ResourceAction.delete
                | ResourceAction.read_list,
                effect=PermissionResult.allow,
            )
            pm.create(alice_permissions)

            # Bob: 只有讀取權限
            bob_permissions = ACLPermission(
                subject="bob",
                object="test_document",
                action=ResourceAction.read | ResourceAction.read_list,
                effect=PermissionResult.allow,
            )
            pm.create(bob_permissions)

            # Charlie: 只有創建權限
            charlie_permissions = ACLPermission(
                subject="charlie",
                object="test_document",
                action=ResourceAction.create,
                effect=PermissionResult.allow,
            )
            pm.create(charlie_permissions)

    def test_create_operation(self):
        """測試 create 操作的權限檢查"""
        self.setup_permissions()
        dm = self.document_manager
        current_time = self.current_time

        # Alice 可以創建
        with dm.meta_provide("alice", current_time):
            doc = TestDocument(title="Alice's Doc", content="Alice's Content")
            doc_info = dm.create(doc)
            assert doc_info.resource_id is not None

        # Charlie 可以創建
        with dm.meta_provide("charlie", current_time):
            doc = TestDocument(title="Charlie's Doc", content="Charlie's Content")
            doc_info = dm.create(doc)
            assert doc_info.resource_id is not None

        # Bob 不能創建
        with pytest.raises(PermissionDeniedError):
            with dm.meta_provide("bob", current_time):
                doc = TestDocument(title="Bob's Doc", content="Bob's Content")
                dm.create(doc)

    def test_get_operation(self):
        """測試 get 操作的權限檢查"""
        self.setup_permissions()
        dm = self.document_manager
        current_time = self.current_time

        # 先用 Alice 創建一個文檔
        with dm.meta_provide("alice", current_time):
            doc = TestDocument(title="Test Doc", content="Test Content")
            doc_info = dm.create(doc)
            doc_id = doc_info.resource_id

        # Alice 可以讀取
        with dm.meta_provide("alice", current_time):
            retrieved_doc = dm.get(doc_id)
            assert retrieved_doc.data.title == "Test Doc"

        # Bob 可以讀取
        with dm.meta_provide("bob", current_time):
            retrieved_doc = dm.get(doc_id)
            assert retrieved_doc.data.title == "Test Doc"

        # Charlie 不能讀取（只有 create 權限）
        with pytest.raises(PermissionDeniedError):
            with dm.meta_provide("charlie", current_time):
                dm.get(doc_id)

    def test_update_operation(self):
        """測試 update 操作的權限檢查"""
        self.setup_permissions()
        dm = self.document_manager
        current_time = self.current_time

        # 先用 Alice 創建一個文檔
        with dm.meta_provide("alice", current_time):
            doc = TestDocument(title="Original Title", content="Original Content")
            doc_info = dm.create(doc)
            doc_id = doc_info.resource_id

        # Alice 可以更新
        with dm.meta_provide("alice", current_time):
            updated_doc = TestDocument(title="Updated Title", content="Updated Content")
            update_info = dm.update(doc_id, updated_doc)
            assert update_info.resource_id == doc_id

        # Bob 不能更新（只有讀取權限）
        with pytest.raises(PermissionDeniedError):
            with dm.meta_provide("bob", current_time):
                updated_doc = TestDocument(
                    title="Bob's Update",
                    content="Bob's Content",
                )
                dm.update(doc_id, updated_doc)

        # Charlie 不能更新（只有創建權限）
        with pytest.raises(PermissionDeniedError):
            with dm.meta_provide("charlie", current_time):
                updated_doc = TestDocument(
                    title="Charlie's Update",
                    content="Charlie's Content",
                )
                dm.update(doc_id, updated_doc)

    def test_get_meta_operation(self):
        """測試 get_meta 操作的權限檢查"""
        self.setup_permissions()
        dm = self.document_manager
        current_time = self.current_time

        # 先用 Alice 創建一個文檔
        with dm.meta_provide("alice", current_time):
            doc = TestDocument(title="Meta Test Doc", content="Meta Test Content")
            doc_info = dm.create(doc)
            doc_id = doc_info.resource_id

        # Alice 可以獲取 metadata
        with dm.meta_provide("alice", current_time):
            meta = dm.get_meta(doc_id)
            assert meta.resource_id == doc_id

        # Bob 可以獲取 metadata（有讀取權限）
        with dm.meta_provide("bob", current_time):
            meta = dm.get_meta(doc_id)
            assert meta.resource_id == doc_id

        # Charlie 不能獲取 metadata（只有創建權限）
        with pytest.raises(PermissionDeniedError):
            with dm.meta_provide("charlie", current_time):
                dm.get_meta(doc_id)

    def test_search_resources_operation(self):
        """測試 search_resources 操作的權限檢查"""
        self.setup_permissions()
        dm = self.document_manager
        current_time = self.current_time

        # 先用 Alice 創建幾個文檔
        with dm.meta_provide("alice", current_time):
            for i in range(3):
                doc = TestDocument(title=f"Search Test Doc {i}", content=f"Content {i}")
                dm.create(doc)

        from autocrud.types import ResourceMetaSearchQuery

        # Alice 可以搜索
        with dm.meta_provide("alice", current_time):
            query = ResourceMetaSearchQuery(limit=10)
            results = dm.search_resources(query)
            assert len(results) == 3

        # Bob 可以搜索（有讀取權限）
        with dm.meta_provide("bob", current_time):
            query = ResourceMetaSearchQuery(limit=10)
            results = dm.search_resources(query)
            assert len(results) == 3

        # Charlie 不能搜索（只有創建權限）
        with pytest.raises(PermissionDeniedError):
            with dm.meta_provide("charlie", current_time):
                query = ResourceMetaSearchQuery(limit=10)
                dm.search_resources(query)


class TestRootUserOperations(TestCaseUtil):
    """測試 Root 用戶的實際操作"""

    def test_root_can_perform_all_operations(self):
        """測試 root 用戶可以執行所有操作"""
        dm = self.document_manager
        current_time = self.current_time

        # Root 用戶可以創建
        with dm.meta_provide("root", current_time):
            doc = TestDocument(title="Root's Doc", content="Root's Content")
            doc_info = dm.create(doc)
            doc_id = doc_info.resource_id

            # Root 可以讀取
            retrieved_doc = dm.get(doc_id)
            assert retrieved_doc.data.title == "Root's Doc"

            # Root 可以更新
            updated_doc = TestDocument(
                title="Root's Updated Doc",
                content="Root's Updated Content",
            )
            update_info = dm.update(doc_id, updated_doc)
            assert update_info.resource_id == doc_id

            # Root 可以獲取 metadata
            meta = dm.get_meta(doc_id)
            assert meta.resource_id == doc_id

            # Root 可以搜索
            from autocrud.types import ResourceMetaSearchQuery

            query = ResourceMetaSearchQuery(limit=10)
            results = dm.search_resources(query)
            assert len(results) >= 1


class TestPermissionDenialScenarios(TestCaseUtil):
    """測試權限拒絕場景"""

    def test_no_permissions_user(self):
        """測試沒有任何權限的用戶"""
        dm = self.document_manager
        current_time = self.current_time

        # 未授權用戶不能執行任何操作
        with pytest.raises(PermissionDeniedError):
            with dm.meta_provide("unauthorized", current_time):
                doc = TestDocument(
                    title="Unauthorized Doc",
                    content="Unauthorized Content",
                )
                dm.create(doc)

    def test_insufficient_permissions(self):
        """測試權限不足的場景"""
        pm = self.permission_manager
        dm = self.document_manager
        current_time = self.current_time

        # 設置一個只有創建權限的用戶
        with pm.meta_provide("root", current_time):
            create_only_permissions = ACLPermission(
                subject="create_only_user",
                object="test_document",
                action=ResourceAction.create,
                effect=PermissionResult.allow,
            )
            pm.create(create_only_permissions)

        # 先創建一個文檔
        with dm.meta_provide("create_only_user", current_time):
            doc = TestDocument(title="Create Only Doc", content="Create Only Content")
            doc_info = dm.create(doc)
            doc_id = doc_info.resource_id

        # 但不能讀取
        with pytest.raises(PermissionDeniedError):
            with dm.meta_provide("create_only_user", current_time):
                dm.get(doc_id)


class TestComplexPermissionScenarios(TestCaseUtil):
    """測試複雜權限場景"""

    def test_multiple_users_same_resource(self):
        """測試多用戶對同一資源的不同權限"""
        pm = self.permission_manager
        dm = self.document_manager
        current_time = self.current_time

        # 設置不同用戶的權限
        with pm.meta_provide("root", current_time):
            # Owner: 完整權限
            owner_permissions = ACLPermission(
                subject="owner",
                object="test_document",
                action=ResourceAction.create
                | ResourceAction.read
                | ResourceAction.update
                | ResourceAction.delete,
                effect=PermissionResult.allow,
            )
            pm.create(owner_permissions)

            # Editor: 創建和更新權限
            editor_permissions = ACLPermission(
                subject="editor",
                object="test_document",
                action=ResourceAction.create | ResourceAction.update,
                effect=PermissionResult.allow,
            )
            pm.create(editor_permissions)

            # Viewer: 只有讀取權限
            viewer_permissions = ACLPermission(
                subject="viewer",
                object="test_document",
                action=ResourceAction.read,
                effect=PermissionResult.allow,
            )
            pm.create(viewer_permissions)

        # Owner 創建文檔
        with dm.meta_provide("owner", current_time):
            doc = TestDocument(title="Shared Doc", content="Shared Content")
            doc_info = dm.create(doc)
            doc_id = doc_info.resource_id

        # Viewer 可以讀取
        with dm.meta_provide("viewer", current_time):
            retrieved_doc = dm.get(doc_id)
            assert retrieved_doc.data.title == "Shared Doc"

        # Editor 不能讀取（沒有讀取權限）
        with pytest.raises(PermissionDeniedError):
            with dm.meta_provide("editor", current_time):
                dm.get(doc_id)

        # Editor 可以創建自己的文檔
        with dm.meta_provide("editor", current_time):
            editor_doc = TestDocument(title="Editor's Doc", content="Editor's Content")
            editor_doc_info = dm.create(editor_doc)
            assert editor_doc_info.resource_id is not None

    def test_permission_isolation_between_resource_types(self):
        """測試不同資源類型之間的權限隔離"""
        pm = self.permission_manager
        current_time = self.current_time

        with pm.meta_provide("root", current_time):
            # 用戶只對 "other_resource" 有權限，對 "test_document" 沒有權限
            other_permissions = ACLPermission(
                subject="specialized_user",
                object="other_resource",
                action=ResourceAction.create | ResourceAction.read,
                effect=PermissionResult.allow,
            )
            pm.create(other_permissions)

        # 檢查權限隔離
        assert (
            self.pc.check_permission(
                BeforeCreate(
                    user="specialized_user",
                    now=current_time,
                    resource_name="other_resource",
                    data={"field": "value"},
                ),
            )
            is PermissionResult.allow
        )
        assert (
            self.pc.check_permission(
                BeforeGet(
                    user="specialized_user",
                    now=current_time,
                    resource_name="other_resource",
                    resource_id="doc123",
                ),
            )
            is PermissionResult.allow
        )

        # 對 test_document 沒有權限
        assert (
            self.pc.check_permission(
                BeforeCreate(
                    user="specialized_user",
                    now=current_time,
                    resource_name="test_document",
                    data={"field": "value"},
                ),
            )
            is PermissionResult.deny
        )
        assert (
            self.pc.check_permission(
                BeforeGet(
                    user="specialized_user",
                    now=current_time,
                    resource_name="test_document",
                    resource_id="doc123",
                ),
            )
            is PermissionResult.deny
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
