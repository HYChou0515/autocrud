"""
Example: Using default_user as a function

This example demonstrates how to use a function as the default_user parameter,
which is useful for dynamic user identification scenarios like:
- Session-based user tracking
- Request context extraction
- Automated system users with timestamps
- UUID-based user identification
"""

import datetime as dt
import uuid

from msgspec import Struct

from autocrud import AutoCRUD


class Task(Struct):
    """簡單的任務模型"""

    title: str
    description: str
    priority: int = 1


def example_1_static_string():
    """範例 1: 使用靜態字串作為 default_user (傳統方式)"""
    print("\n=== 範例 1: 靜態字串 ===")

    crud = AutoCRUD(default_user="system")
    crud.add_model(Task)

    mgr = crud.get_resource_manager(Task)

    with mgr.meta_provide(now=dt.datetime.now()):
        result = mgr.create(Task(title="Task 1", description="First task"))

    print(f"Created by: {result.created_by}")  # 輸出: system


def example_2_dynamic_function():
    """範例 2: 使用動態函數產生 user ID"""
    print("\n=== 範例 2: 動態函數 ===")

    def get_current_user():
        """模擬從當前上下文獲取用戶"""
        # 在實際應用中，這可能從 request context 或 session 中取得
        return f"user_{uuid.uuid4().hex[:8]}"

    crud = AutoCRUD(default_user=get_current_user)
    crud.add_model(Task)

    mgr = crud.get_resource_manager(Task)

    with mgr.meta_provide(now=dt.datetime.now()):
        result1 = mgr.create(Task(title="Task 1", description="First task"))
        result2 = mgr.create(Task(title="Task 2", description="Second task"))

    print(f"Task 1 created by: {result1.created_by}")
    print(f"Task 2 created by: {result2.created_by}")
    # 每次都會呼叫 function，產生不同的 user ID


def example_3_timestamp_based_user():
    """範例 3: 基於時間戳的用戶識別"""
    print("\n=== 範例 3: 時間戳用戶 ===")

    def get_timestamped_user():
        """產生帶有時間戳的系統用戶 ID"""
        timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"system_{timestamp}"

    crud = AutoCRUD(default_user=get_timestamped_user)
    crud.add_model(Task)

    mgr = crud.get_resource_manager(Task)

    with mgr.meta_provide(now=dt.datetime.now()):
        result = mgr.create(Task(title="Automated Task", description="Auto-generated"))

    print(f"Created by: {result.created_by}")  # 例如: system_20260114_153045


def example_4_session_based():
    """範例 4: 模擬 session-based 用戶追蹤"""
    print("\n=== 範例 4: Session-based 用戶追蹤 ===")

    # 模擬 session storage
    current_session = {"user_id": None}

    def get_session_user():
        """從 session 取得當前用戶 ID"""
        if current_session["user_id"] is None:
            # 如果沒有 session，建立一個
            current_session["user_id"] = f"session_{uuid.uuid4().hex[:12]}"
        return current_session["user_id"]

    crud = AutoCRUD(default_user=get_session_user)
    crud.add_model(Task)

    mgr = crud.get_resource_manager(Task)

    with mgr.meta_provide(now=dt.datetime.now()):
        result1 = mgr.create(Task(title="Task 1", description="First task"))
        result2 = mgr.create(Task(title="Task 2", description="Second task"))

    print(f"Task 1 created by: {result1.created_by}")
    print(f"Task 2 created by: {result2.created_by}")
    # 同一個 session 內的 tasks 會有相同的 user ID


def example_5_override_default():
    """範例 5: 覆蓋預設用戶"""
    print("\n=== 範例 5: 覆蓋預設用戶 ===")

    def get_default_user():
        return "default_system_user"

    crud = AutoCRUD(default_user=get_default_user)
    crud.add_model(Task)

    mgr = crud.get_resource_manager(Task)

    # 使用預設用戶
    with mgr.meta_provide(now=dt.datetime.now()):
        result1 = mgr.create(Task(title="Task 1", description="Uses default"))

    # 明確指定用戶會覆蓋預設值
    with mgr.meta_provide(user="admin", now=dt.datetime.now()):
        result2 = mgr.create(Task(title="Task 2", description="Explicit user"))

    print(f"Task 1 created by: {result1.created_by}")  # default_system_user
    print(f"Task 2 created by: {result2.created_by}")  # admin


def example_6_per_model_default():
    """範例 6: 針對不同 model 設定不同的 default_user function"""
    print("\n=== 範例 6: 每個 model 不同的預設用戶 ===")

    class UserTask(Struct):
        title: str
        owner: str

    class SystemTask(Struct):
        title: str
        automated: bool = True

    def user_task_default():
        return f"web_user_{uuid.uuid4().hex[:6]}"

    def system_task_default():
        return "automated_system"

    crud = AutoCRUD()
    crud.add_model(UserTask, default_user=user_task_default)
    crud.add_model(SystemTask, default_user=system_task_default)

    user_mgr = crud.get_resource_manager(UserTask)
    system_mgr = crud.get_resource_manager(SystemTask)

    with user_mgr.meta_provide(now=dt.datetime.now()):
        user_task = user_mgr.create(UserTask(title="User Task", owner="alice"))

    with system_mgr.meta_provide(now=dt.datetime.now()):
        system_task = system_mgr.create(SystemTask(title="System Task"))

    print(f"UserTask created by: {user_task.created_by}")  # web_user_xxx
    print(f"SystemTask created by: {system_task.created_by}")  # automated_system


if __name__ == "__main__":
    example_1_static_string()
    example_2_dynamic_function()
    example_3_timestamp_based_user()
    example_4_session_based()
    example_5_override_default()
    example_6_per_model_default()

    print("\n✅ 所有範例執行完成！")
