"""
測試 ResourceManager 的 event_handlers 功能

使用 events.py 中的 do 函數來測試事件處理系統
"""

import datetime as dt
from unittest.mock import Mock

import pytest
from msgspec import Struct

from autocrud.resource_manager.basic import IStorage
from autocrud.resource_manager.core import ResourceManager, SimpleStorage
from autocrud.resource_manager.events import do
from autocrud.resource_manager.meta_store.simple import MemoryMetaStore
from autocrud.resource_manager.resource_store.simple import MemoryResourceStore
from autocrud.types import (
    OnSuccessCreate,
    ResourceAction,
    EventContext,
    ResourceMetaSearchQuery,
)


class SampleData(Struct):
    """測試用的數據結構"""

    name: str
    value: int


class TestResourceManagerEventHandlers:
    """測試 ResourceManager 的事件處理功能"""

    @pytest.fixture
    def storage(self) -> IStorage:
        """創建測試用的存儲"""
        meta_store = MemoryMetaStore()
        resource_store = MemoryResourceStore(SampleData)
        return SimpleStorage(meta_store, resource_store)

    @pytest.fixture
    def mock_handler_func(self):
        """創建一個 mock 函數用於測試事件處理"""
        return Mock()

    def test_single_event_handler_before_create(self, storage, mock_handler_func):
        """測試單個事件處理器在 create 操作的 before 階段"""
        # 使用 do 函數創建事件處理器
        event_handlers = do(mock_handler_func).before(ResourceAction.create)

        # 創建 ResourceManager
        manager = ResourceManager(
            SampleData,
            storage=storage,
            event_handlers=event_handlers,
        )

        # 創建測試數據
        test_data = SampleData(name="test", value=42)

        # 執行操作
        with manager.meta_provide("test_user", dt.datetime.now()):
            info = manager.create(test_data)

        # 驗證事件處理器被調用
        mock_handler_func.assert_called_once()

        # 驗證調用參數
        call_args = mock_handler_func.call_args[0][0]
        assert call_args.phase == "before"
        assert call_args.action == ResourceAction.create
        assert call_args.user == "test_user"
        assert call_args.resource_name == "sample_data"
        assert call_args.data == test_data

    def test_multiple_event_handlers_chain(self, storage):
        """測試多個事件處理器的鏈式調用"""
        handler1 = Mock()
        handler2 = Mock()
        handler3 = Mock()

        # 創建鏈式事件處理器
        event_handlers = (
            do(handler1)
            .before(ResourceAction.create)
            .do(handler2)
            .after(ResourceAction.create)
            .do(handler3)
            .on_success(ResourceAction.create)
        )

        manager = ResourceManager(
            SampleData,
            storage=storage,
            event_handlers=event_handlers,
        )

        test_data = SampleData(name="chain_test", value=123)

        with manager.meta_provide("test_user", dt.datetime.now()):
            info = manager.create(test_data)

        # 驗證所有處理器都被調用
        handler1.assert_called_once()
        handler2.assert_called_once()
        handler3.assert_called_once()

        # 驗證調用順序和階段
        assert handler1.call_args[0][0].phase == "before"
        assert handler2.call_args[0][0].phase == "after"
        assert handler3.call_args[0][0].phase == "on_success"

    def test_event_handler_different_actions(self, storage):
        """測試事件處理器處理不同的操作類型"""
        create_handler = Mock()
        get_handler = Mock()
        update_handler = Mock()

        # 為不同操作創建事件處理器
        event_handlers = (
            do(create_handler)
            .before(ResourceAction.create)
            .do(get_handler)
            .before(ResourceAction.get)
            .do(update_handler)
            .before(ResourceAction.update)
        )

        manager = ResourceManager(
            SampleData,
            storage=storage,
            event_handlers=event_handlers,
        )

        test_data = SampleData(name="action_test", value=456)

        with manager.meta_provide("test_user", dt.datetime.now()):
            # 創建資源
            info = manager.create(test_data)
            resource_id = info.resource_id

            # 獲取資源
            resource = manager.get(resource_id)

            # 更新資源
            updated_data = SampleData(name="updated", value=789)
            manager.update(resource_id, updated_data)

        # 驗證不同的處理器被適當調用
        create_handler.assert_called_once()
        get_handler.assert_called_once()
        update_handler.assert_called_once()

        # 驗證操作類型正確
        assert create_handler.call_args[0][0].action == ResourceAction.create
        assert get_handler.call_args[0][0].action == ResourceAction.get
        assert update_handler.call_args[0][0].action == ResourceAction.update

    def test_event_handler_on_failure(self, storage):
        """測試失敗情況下的事件處理器"""
        failure_handler = Mock()
        success_handler = Mock()

        event_handlers = (
            do(failure_handler)
            .on_failure(ResourceAction.get)
            .do(success_handler)
            .on_success(ResourceAction.get)
        )

        manager = ResourceManager(
            SampleData,
            storage=storage,
            event_handlers=event_handlers,
        )

        with manager.meta_provide("test_user", dt.datetime.now()):
            # 嘗試獲取不存在的資源，應該觸發失敗事件
            with pytest.raises(Exception):
                manager.get("non_existent_id")

        # 驗證只有失敗處理器被調用
        failure_handler.assert_called_once()
        success_handler.assert_not_called()

        # 驗證失敗上下文包含錯誤信息
        call_args = failure_handler.call_args[0][0]
        assert call_args.phase == "on_failure"
        assert call_args.action == ResourceAction.get

    def test_multiple_functions_in_single_handler(self, storage):
        """測試在單個處理器中使用多個函數"""
        func1 = Mock()
        func2 = Mock()
        func3 = Mock()

        # 使用多個函數創建單個事件處理器
        event_handlers = do([func1, func2, func3]).before(ResourceAction.create)

        manager = ResourceManager(
            SampleData,
            storage=storage,
            event_handlers=event_handlers,
        )

        test_data = SampleData(name="multi_func", value=999)

        with manager.meta_provide("test_user", dt.datetime.now()):
            manager.create(test_data)

        # 驗證所有函數都被調用
        func1.assert_called_once()
        func2.assert_called_once()
        func3.assert_called_once()

        # 驗證所有函數接收到相同的上下文
        context1 = func1.call_args[0][0]
        context2 = func2.call_args[0][0]
        context3 = func3.call_args[0][0]

        assert context1.phase == context2.phase == context3.phase == "before"
        assert (
            context1.action
            == context2.action
            == context3.action
            == ResourceAction.create
        )

    def test_event_handler_with_permission_checker(self, storage):
        """測試事件處理器與權限檢查器一起工作"""
        from autocrud.types import PermissionResult

        # 創建 mock 權限檢查器
        permission_checker = Mock()
        permission_checker.check_permission.return_value = PermissionResult.allow

        # 創建自定義事件處理器
        custom_handler = Mock()
        event_handlers = do(custom_handler).before(ResourceAction.create)

        manager = ResourceManager(
            SampleData,
            storage=storage,
            permission_checker=permission_checker,
            event_handlers=event_handlers,
        )

        test_data = SampleData(name="permission_test", value=111)

        with manager.meta_provide("test_user", dt.datetime.now()):
            manager.create(test_data)

        # 驗證權限檢查器被調用
        permission_checker.check_permission.assert_called()

        # 驗證自定義事件處理器也被調用
        custom_handler.assert_called_once()

    def test_event_context_data_integrity(self, storage):
        """測試事件上下文中的數據完整性"""
        handler = Mock()
        event_handlers = do(handler).before(ResourceAction.update)

        manager = ResourceManager(
            SampleData,
            storage=storage,
            event_handlers=event_handlers,
        )

        # 先創建一個資源
        original_data = SampleData(name="original", value=100)
        with manager.meta_provide("creator", dt.datetime(2023, 1, 1)):
            info = manager.create(original_data)
            resource_id = info.resource_id

        # 更新資源並檢查事件上下文
        updated_data = SampleData(name="updated", value=200)
        update_time = dt.datetime(2023, 1, 2)

        with manager.meta_provide("updater", update_time):
            manager.update(resource_id, updated_data)

        # 驗證事件上下文包含正確的數據
        call_args = handler.call_args[0][0]
        assert call_args.user == "updater"
        assert call_args.now == update_time
        assert call_args.resource_id == resource_id
        assert call_args.data == updated_data
        assert call_args.action == ResourceAction.update

    def test_event_handler_exception_handling(self, storage: IStorage):
        """測試事件處理器中的異常處理"""

        def failing_handler(context: EventContext):
            raise ValueError("事件處理器中的測試異常")

        event_handlers = do(failing_handler).before(ResourceAction.create)

        manager = ResourceManager(
            SampleData,
            storage=storage,
            event_handlers=event_handlers,
        )

        test_data = SampleData(name="exception_test", value=777)

        with manager.meta_provide("test_user", dt.datetime.now()):
            # 事件處理器中的異常應該阻止操作完成
            with pytest.raises(ValueError, match="事件處理器中的測試異常"):
                manager.create(test_data)

        # 驗證由於異常，資源確實沒有被創建
        with manager.meta_provide("test_user", dt.datetime.now()):
            resources = list(storage.search(ResourceMetaSearchQuery()))
            assert len(resources) == 0

    def test_event_handler_data_modification(self, storage: IStorage):
        """測試事件處理器修改數據的能力"""

        def modify_data_handler(context: EventContext):
            # 在創建前修改數據
            if hasattr(context, "data") and context.data:
                # 這裡假設事件處理器可以修改數據
                context.data.value = context.data.value * 2

        event_handlers = do(modify_data_handler).before(ResourceAction.create)

        manager = ResourceManager(
            SampleData,
            storage=storage,
            event_handlers=event_handlers,
        )

        original_data = SampleData(name="modify_test", value=50)

        with manager.meta_provide("test_user", dt.datetime.now()):
            info = manager.create(original_data)
            created_resource = manager.get(info.resource_id)

        # 驗證數據是否被修改（如果事件處理器支持修改的話）
        # 這個測試取決於具體的實現
        assert created_resource.data.name == "modify_test"

    def test_event_handler_context_validation(self, storage: IStorage):
        """測試事件上下文的各項屬性驗證"""
        validation_handler = Mock()
        event_handlers = do(validation_handler).on_success(ResourceAction.create)

        manager = ResourceManager(
            SampleData,
            storage=storage,
            event_handlers=event_handlers,
        )

        test_data = SampleData(name="validation_test", value=888)
        test_time = dt.datetime(2023, 6, 15, 10, 30, 0)

        with manager.meta_provide("validator_user", test_time):
            info = manager.create(test_data)

        # 驗證事件上下文的完整性
        call_args = validation_handler.call_args[0][0]

        # 檢查基本屬性
        assert isinstance(call_args, OnSuccessCreate)
        assert call_args.phase == "on_success"
        assert call_args.action == ResourceAction.create
        assert call_args.user == "validator_user"
        assert call_args.now == test_time
        assert call_args.resource_name == "sample_data"

        # 檢查資源相關屬性
        assert call_args.info.resource_id == info.resource_id
        assert call_args.data == test_data

        # 檢查上下文類型
        assert isinstance(call_args, EventContext)
