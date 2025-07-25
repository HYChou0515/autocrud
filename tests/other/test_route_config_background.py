"""測試 RouteConfig 與 Background Tasks 功能"""

from typing import TypedDict
from autocrud.route_config import RouteConfig, RouteOptions, BackgroundTaskMode


class User(TypedDict):
    id: str
    name: str
    email: str


# 模擬 background task 函數
executed_tasks = []


def send_welcome_email(user_data):
    """模擬發送歡迎郵件的 background task"""
    executed_tasks.append(f"Welcome email sent to {user_data['email']}")


def send_update_notification(user_data, user_id):
    """模擬發送更新通知的 background task"""
    executed_tasks.append(f"Update notification sent for user {user_id}")


def cleanup_user_data(user_data, user_id):
    """模擬清理用戶資料的 background task"""
    executed_tasks.append(f"Cleanup completed for user {user_id}")


def should_send_email(user_data):
    """條件函數：只對特定郵件域發送郵件"""
    return user_data.get("email", "").endswith("@example.com")


def test_basic_route_options():
    """測試基本的 RouteOptions 功能"""
    # 測試簡單啟用/停用
    enabled_option = RouteOptions.enabled_route()
    assert enabled_option.enabled is True
    assert enabled_option.background_task == BackgroundTaskMode.DISABLED

    disabled_option = RouteOptions.disabled_route()
    assert disabled_option.enabled is False

    # 測試 background task 選項
    bg_option = RouteOptions.background_route(send_welcome_email)
    assert bg_option.enabled is True
    assert bg_option.background_task == BackgroundTaskMode.ENABLED
    assert bg_option.background_task_func == send_welcome_email

    # 測試條件式 background task
    conditional_bg = RouteOptions.background_route(
        send_welcome_email, BackgroundTaskMode.CONDITIONAL, should_send_email
    )
    assert conditional_bg.background_task == BackgroundTaskMode.CONDITIONAL
    assert conditional_bg.background_task_condition == should_send_email


def test_route_config_compatibility():
    """測試 RouteConfig 的向後兼容性"""
    # 測試使用 bool 值（向後兼容）
    config = RouteConfig(create=True, get=False, update=True)

    assert config.is_route_enabled("create")
    assert not config.is_route_enabled("get")
    assert config.is_route_enabled("update")

    # 檢查自動轉換為 RouteOptions
    create_options = config.get_route_options("create")
    assert isinstance(create_options, RouteOptions)
    assert create_options.enabled is True
    assert create_options.background_task == BackgroundTaskMode.DISABLED


def test_route_config_with_background_tasks():
    """測試帶有 background tasks 的 RouteConfig"""
    config = RouteConfig.with_background_tasks(
        create_bg_func=send_welcome_email,
        update_bg_func=send_update_notification,
        delete_bg_func=cleanup_user_data,
    )

    # 檢查 create 路由有 background task
    create_options = config.get_route_options("create")
    assert create_options.background_task == BackgroundTaskMode.ENABLED
    assert create_options.background_task_func == send_welcome_email

    # 檢查 update 路由有 background task
    update_options = config.get_route_options("update")
    assert update_options.background_task == BackgroundTaskMode.ENABLED
    assert update_options.background_task_func == send_update_notification

    # 檢查 delete 路由有 background task
    delete_options = config.get_route_options("delete")
    assert delete_options.background_task == BackgroundTaskMode.ENABLED
    assert delete_options.background_task_func == cleanup_user_data

    # 檢查沒有指定 background task 的路由
    get_options = config.get_route_options("get")
    assert get_options.background_task == BackgroundTaskMode.DISABLED


def test_advanced_route_config():
    """測試進階 RouteConfig 配置"""
    # 創建自定義配置
    config = RouteConfig(
        create=RouteOptions.background_route(
            send_welcome_email, BackgroundTaskMode.CONDITIONAL, should_send_email
        ),
        update=RouteOptions(
            enabled=True,
            background_task=BackgroundTaskMode.ENABLED,
            background_task_func=send_update_notification,
            custom_status_code=202,
        ),
        delete=RouteOptions(enabled=True, custom_status_code=410),
        get=False,  # 混合使用 bool 和 RouteOptions
        list=True,
        count=True,
    )

    # 驗證配置
    create_opts = config.get_route_options("create")
    assert create_opts.background_task == BackgroundTaskMode.CONDITIONAL
    assert create_opts.background_task_condition == should_send_email

    update_opts = config.get_route_options("update")
    assert update_opts.custom_status_code == 202
    assert update_opts.background_task_func == send_update_notification

    delete_opts = config.get_route_options("delete")
    assert delete_opts.custom_status_code == 410
    assert delete_opts.background_task == BackgroundTaskMode.DISABLED

    # 檢查向後兼容的 bool 值
    assert not config.is_route_enabled("get")
    assert config.is_route_enabled("list")


def test_route_config_to_dict():
    """測試 RouteConfig 的序列化功能"""
    config = RouteConfig(
        create=RouteOptions.background_route(send_welcome_email),
        get=False,
        update=RouteOptions(enabled=True, custom_status_code=202),
    )

    config_dict = config.to_dict()

    # 檢查序列化結果
    assert isinstance(config_dict["create"], dict)
    assert config_dict["create"]["enabled"] is True
    assert config_dict["create"]["background_task"] == "enabled"
    assert config_dict["create"]["has_background_func"] is True

    assert isinstance(config_dict["update"], dict)
    assert config_dict["update"]["custom_status_code"] == 202

    # bool 值的路由（沒有進階功能時返回 bool）
    assert config_dict["get"] is False  # 直接是 bool 值
    assert config_dict["list"] is True  # 直接是 bool 值


def test_string_representation():
    """測試字串表示"""
    config = RouteConfig.with_background_tasks(
        create_bg_func=send_welcome_email, update_bg_func=send_update_notification
    )

    config_str = str(config)
    print(f"Config string: {config_str}")

    # 檢查字串包含相關資訊
    assert "enabled:" in config_str
    assert "background:" in config_str
    assert "create(bg)" in config_str
    assert "update(bg)" in config_str


if __name__ == "__main__":
    test_basic_route_options()
    print("✅ 基本 RouteOptions 測試通過")

    test_route_config_compatibility()
    print("✅ RouteConfig 向後兼容性測試通過")

    test_route_config_with_background_tasks()
    print("✅ Background tasks 配置測試通過")

    test_advanced_route_config()
    print("✅ 進階 RouteConfig 測試通過")

    test_route_config_to_dict()
    print("✅ 序列化測試通過")

    test_string_representation()
    print("✅ 字串表示測試通過")

    print("\n✅ 所有 RouteConfig 和 Background Tasks 測試通過！")
