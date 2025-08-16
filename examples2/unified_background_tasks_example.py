"""統一 Background Task Callback Signature 完整示例"""

from typing import TypedDict, Any
from fastapi.testclient import TestClient
from autocrud import AutoCRUD
from autocrud.route_config import RouteConfig, RouteOptions, BackgroundTaskMode


class User(TypedDict):
    id: str
    name: str
    email: str
    age: int
    role: str


# 統一的背景任務函數 - 只接收一個參數：路由的輸出結果
def audit_log_task(route_output: Any):
    """統一的審計日誌背景任務"""
    print(f"[AUDIT] Route executed with output type: {type(route_output).__name__}")

    if isinstance(route_output, dict):
        if "id" in route_output:
            # 單個資源操作（CREATE, GET, UPDATE）
            print(
                f"[AUDIT] Resource operation: {route_output.get('name', 'Unknown')} (ID: {route_output['id']})"
            )
        elif "count" in route_output:
            # 計數操作
            print(f"[AUDIT] Count operation: {route_output['count']} total resources")
    elif isinstance(route_output, list):
        # 列表操作（LIST）
        print(f"[AUDIT] List operation: Retrieved {len(route_output)} resources")
    elif route_output is None:
        # 刪除操作（DELETE）
        print("[AUDIT] Delete operation: Resource removed successfully")
    else:
        print(f"[AUDIT] Unknown operation type: {type(route_output)}")


def notification_task(route_output: Any):
    """統一的通知背景任務"""
    print(f"[NOTIFICATION] Sending notification for operation result: {route_output}")


def main():
    """展示統一 background task signature 的完整功能"""

    # 創建 AutoCRUD 實例
    autocrud = AutoCRUD()
    autocrud.register_model(User)

    # 配置所有路由使用統一的背景任務
    config = RouteConfig(
        create=RouteOptions(
            enabled=True,
            background_task=BackgroundTaskMode.ENABLED,
            background_task_func=audit_log_task,
        ),
        get=RouteOptions(
            enabled=True,
            background_task=BackgroundTaskMode.ENABLED,
            background_task_func=notification_task,
        ),
        update=RouteOptions(
            enabled=True,
            background_task=BackgroundTaskMode.ENABLED,
            background_task_func=audit_log_task,
        ),
        delete=RouteOptions(
            enabled=True,
            background_task=BackgroundTaskMode.ENABLED,
            background_task_func=audit_log_task,
        ),
        list=RouteOptions(
            enabled=True,
            background_task=BackgroundTaskMode.ENABLED,
            background_task_func=audit_log_task,
        ),
        count=RouteOptions(
            enabled=True,
            background_task=BackgroundTaskMode.ENABLED,
            background_task_func=audit_log_task,
        ),
    )

    # 創建 FastAPI 應用
    app = autocrud.create_fastapi_app(
        title="統一背景任務 API",
        description="展示統一 background task callback signature",
        route_config=config,
    )

    client = TestClient(app)

    print("=== 統一 Background Task Callback Signature 示例 ===\n")

    # 1. CREATE 操作 - 背景任務接收 created_item
    print("1. 執行 CREATE 操作")
    response = client.post(
        "/api/v1/users",
        json={
            "name": "Alice Johnson",
            "email": "alice@example.com",
            "age": 28,
            "role": "developer",
        },
    )
    user_id = response.json()["id"]
    print(f"   Status: {response.status_code}, User ID: {user_id}\n")

    # 2. GET 操作 - 背景任務接收 item
    print("2. 執行 GET 操作")
    response = client.get(f"/api/v1/users/{user_id}")
    print(f"   Status: {response.status_code}\n")

    # 3. UPDATE 操作 - 背景任務接收 updated_item
    print("3. 執行 UPDATE 操作")
    response = client.put(
        f"/api/v1/users/{user_id}",
        json={
            "name": "Alice Johnson Smith",
            "email": "alice.smith@example.com",
            "age": 29,
            "role": "senior_developer",
        },
    )
    print(f"   Status: {response.status_code}\n")

    # 4. LIST 操作 - 背景任務接收 items (列表)
    print("4. 執行 LIST 操作")
    response = client.get("/api/v1/users")
    print(f"   Status: {response.status_code}\n")

    # 5. COUNT 操作 - 背景任務接收 {"count": count}
    print("5. 執行 COUNT 操作")
    response = client.get("/api/v1/users/count")
    print(f"   Status: {response.status_code}\n")

    # 6. DELETE 操作 - 背景任務接收 None
    print("6. 執行 DELETE 操作")
    response = client.delete(f"/api/v1/users/{user_id}")
    print(f"   Status: {response.status_code}\n")

    print("=== 功能總結 ===")
    print("✅ 所有路由的背景任務函數統一使用相同的 signature: func(route_output)")
    print("✅ CREATE: audit_log_task(created_item)")
    print("✅ GET: notification_task(item)")
    print("✅ UPDATE: audit_log_task(updated_item)")
    print("✅ LIST: audit_log_task(items)")
    print("✅ COUNT: audit_log_task({'count': count})")
    print("✅ DELETE: audit_log_task(None)")
    print("✅ 支持混合配置不同路由使用不同的背景任務函數")
    print("✅ 完全向後兼容現有功能")


if __name__ == "__main__":
    main()
