"""測試 FastAPI Background Tasks 集成"""

from typing import TypedDict
from autocrud import AutoCRUD
from autocrud.route_config import RouteConfig, RouteOptions, BackgroundTaskMode


class User(TypedDict):
    id: str
    name: str
    email: str


# 模擬 background task
executed_tasks = []


def log_user_creation(user_data):
    """記錄用戶創建事件"""
    executed_tasks.append(f"User created: {user_data['name']} ({user_data['email']})")


def log_user_update(user_data, user_id):
    """記錄用戶更新事件"""
    executed_tasks.append(f"User updated: {user_id} -> {user_data['name']}")


def cleanup_user_cache(user_data, user_id):
    """清理用戶快取"""
    executed_tasks.append(f"Cache cleared for user: {user_id}")


def should_log_creation(user_data):
    """條件：只記錄特定域的用戶創建"""
    return user_data.get("email", "").endswith("@company.com")


def test_fastapi_generator_with_background_tasks():
    """測試 FastAPI 生成器對 background tasks 的支援"""
    global executed_tasks
    executed_tasks.clear()

    # 創建 AutoCRUD 實例
    autocrud = AutoCRUD()

    # 註冊模型
    autocrud.register_model(User)

    # 創建帶有 background tasks 的配置
    config = RouteConfig(
        create=RouteOptions.background_route(
            log_user_creation, BackgroundTaskMode.CONDITIONAL, should_log_creation
        ),
        update=RouteOptions.background_route(log_user_update),
        delete=RouteOptions.background_route(cleanup_user_cache),
        get=True,
        list=True,
        count=True,
    )

    # 驗證配置
    assert config.is_route_enabled("create")
    assert config.is_route_enabled("update")
    assert config.is_route_enabled("delete")

    create_opts = config.get_route_options("create")
    assert create_opts.background_task == BackgroundTaskMode.CONDITIONAL
    assert create_opts.background_task_func == log_user_creation
    assert create_opts.background_task_condition == should_log_creation

    update_opts = config.get_route_options("update")
    assert update_opts.background_task == BackgroundTaskMode.ENABLED
    assert update_opts.background_task_func == log_user_update

    delete_opts = config.get_route_options("delete")
    assert delete_opts.background_task == BackgroundTaskMode.ENABLED
    assert delete_opts.background_task_func == cleanup_user_cache


def test_custom_status_codes():
    """測試自定義狀態碼"""
    config = RouteConfig(
        create=RouteOptions(
            enabled=True,
            custom_status_code=202,  # Accepted
            background_task=BackgroundTaskMode.ENABLED,
            background_task_func=log_user_creation,
        ),
        update=RouteOptions(
            enabled=True,
            custom_status_code=200,  # OK instead of default
        ),
        delete=RouteOptions(
            enabled=True,
            custom_status_code=410,  # Gone instead of 204
        ),
    )

    create_opts = config.get_route_options("create")
    assert create_opts.custom_status_code == 202
    assert create_opts.background_task == BackgroundTaskMode.ENABLED

    update_opts = config.get_route_options("update")
    assert update_opts.custom_status_code == 200

    delete_opts = config.get_route_options("delete")
    assert delete_opts.custom_status_code == 410


def test_mixed_configuration():
    """測試混合使用 bool 和 RouteOptions"""
    config = RouteConfig(
        create=RouteOptions.background_route(log_user_creation),
        get=True,  # 簡單的 bool
        update=False,  # 停用
        delete=RouteOptions(enabled=True, custom_status_code=204),
        list=RouteOptions.enabled_route(),
        count=True,
    )

    # 檢查混合類型正確處理
    assert config.is_route_enabled("create")
    assert config.is_route_enabled("get")
    assert not config.is_route_enabled("update")
    assert config.is_route_enabled("delete")
    assert config.is_route_enabled("list")
    assert config.is_route_enabled("count")

    # 檢查 RouteOptions 正確轉換
    get_opts = config.get_route_options("get")
    assert isinstance(get_opts, RouteOptions)
    assert get_opts.enabled is True
    assert get_opts.background_task == BackgroundTaskMode.DISABLED

    update_opts = config.get_route_options("update")
    assert isinstance(update_opts, RouteOptions)
    assert update_opts.enabled is False


def test_route_config_factory_methods():
    """測試 RouteConfig 的工廠方法與 background tasks 兼容性"""
    # 測試基本工廠方法仍然工作
    all_enabled = RouteConfig.all_enabled()
    assert all_enabled.is_route_enabled("create")
    assert all_enabled.is_route_enabled("get")
    assert all_enabled.is_route_enabled("update")
    assert all_enabled.is_route_enabled("delete")
    assert all_enabled.is_route_enabled("list")
    assert all_enabled.is_route_enabled("count")

    read_only = RouteConfig.read_only()
    assert not read_only.is_route_enabled("create")
    assert read_only.is_route_enabled("get")
    assert not read_only.is_route_enabled("update")
    assert not read_only.is_route_enabled("delete")
    assert read_only.is_route_enabled("list")
    assert read_only.is_route_enabled("count")

    # 測試 with_background_tasks 工廠方法
    bg_config = RouteConfig.with_background_tasks(
        create_bg_func=log_user_creation,
        delete_bg_func=cleanup_user_cache,
        # 其他參數使用預設值
        get=False,
        count=False,
    )

    assert bg_config.is_route_enabled("create")
    assert not bg_config.is_route_enabled("get")
    assert bg_config.is_route_enabled("update")  # 預設 True
    assert bg_config.is_route_enabled("delete")
    assert bg_config.is_route_enabled("list")  # 預設 True
    assert not bg_config.is_route_enabled("count")

    # 檢查 background tasks 配置
    create_opts = bg_config.get_route_options("create")
    assert create_opts.background_task == BackgroundTaskMode.ENABLED
    assert create_opts.background_task_func == log_user_creation

    delete_opts = bg_config.get_route_options("delete")
    assert delete_opts.background_task == BackgroundTaskMode.ENABLED
    assert delete_opts.background_task_func == cleanup_user_cache

    # update 沒有 background task 但仍啟用
    update_opts = bg_config.get_route_options("update")
    assert update_opts.background_task == BackgroundTaskMode.DISABLED


def test_serialization_and_deserialization():
    """測試序列化和反序列化（部分功能）"""
    original_config = RouteConfig(
        create=RouteOptions.background_route(log_user_creation),
        get=True,
        update=RouteOptions(enabled=True, custom_status_code=202),
        delete=False,
    )

    # 序列化
    config_dict = original_config.to_dict()

    # 驗證序列化結果
    assert config_dict["create"]["enabled"] is True
    assert config_dict["create"]["background_task"] == "enabled"
    assert config_dict["create"]["has_background_func"] is True

    assert config_dict["update"]["enabled"] is True
    assert config_dict["update"]["custom_status_code"] == 202

    # delete 是簡單的布爾值（沒有進階功能）
    assert config_dict["delete"] is False

    # 反序列化（注意：函數不會被恢復）
    restored_config = RouteConfig.from_dict(config_dict)

    # 檢查基本配置恢復
    assert restored_config.is_route_enabled("create")
    assert restored_config.is_route_enabled("get")
    assert restored_config.is_route_enabled("update")
    assert not restored_config.is_route_enabled("delete")

    # 檢查 background task 模式恢復（但函數不會恢復）
    create_opts = restored_config.get_route_options("create")
    assert create_opts.background_task == BackgroundTaskMode.ENABLED
    assert create_opts.background_task_func is None  # 函數不會被恢復

    update_opts = restored_config.get_route_options("update")
    assert update_opts.custom_status_code == 202


if __name__ == "__main__":
    test_fastapi_generator_with_background_tasks()
    print("✅ FastAPI 生成器 background tasks 測試通過")

    test_custom_status_codes()
    print("✅ 自定義狀態碼測試通過")

    test_mixed_configuration()
    print("✅ 混合配置測試通過")

    test_route_config_factory_methods()
    print("✅ 工廠方法測試通過")

    test_serialization_and_deserialization()
    print("✅ 序列化/反序列化測試通過")

    print("\n✅ 所有 FastAPI Background Tasks 集成測試通過！")
