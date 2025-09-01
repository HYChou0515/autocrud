"""
基本權限設定示例
"""

from autocrud.resource_manager.core import ResourceManager
from autocrud.resource_manager.permission import PermissionResourceManager
from autocrud.resource_manager.permission_context import DefaultPermissionChecker


# 步驟 1: 創建權限管理器（ACL/RBAC）
permission_manager = PermissionResourceManager(
    # ... storage 等其他參數
)

# 步驟 2: 創建簡單的權限檢查器
permission_checker = DefaultPermissionChecker(permission_manager)

# 步驟 3: 創建 ResourceManager 並傳入權限檢查器
resource_manager = ResourceManager(
    resource_type=YourDataType,
    storage=your_storage,
    permission_checker=permission_checker,  # 關鍵：傳入權限檢查器
    # ... 其他參數
)

# 現在所有 ResourceManager 的操作都會自動進行權限檢查
