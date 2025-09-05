from abc import ABC, abstractmethod
import datetime as dt
from enum import StrEnum

from autocrud.resource_manager.basic import (
    IResourceManager,
    ResourceAction,
    ResourceMeta,
)

from msgspec import UNSET, Struct, UnsetType
from typing import Any, Dict, Generic, TypeVar

T = TypeVar("T")


class PermissionResult(StrEnum):
    """權限檢查結果"""

    allow = "allow"
    deny = "deny"
    not_applicable = "not_applicable"  # 這個檢查器不適用於此操作


class PermissionContext(Struct, kw_only=True):
    """權限檢查上下文 - 包含所有權限檢查所需的資訊"""

    # 基本資訊
    user: str
    now: dt.datetime
    action: ResourceAction
    resource_name: str

    # 方法調用資訊
    method_args: tuple = ()
    method_kwargs: Dict[str, Any] = {}

    # 額外上下文資料
    resource_id: str | UnsetType = UNSET
    resource_meta: ResourceMeta | UnsetType = UNSET
    resource_data: Any | UnsetType = UNSET
    extra_data: Dict[str, Any] = {}


class IPermissionChecker(ABC):
    """權限檢查器接口"""

    @abstractmethod
    def check_permission(self, context: PermissionContext) -> PermissionResult:
        """檢查權限

        Args:
            context: 權限檢查上下文

        Returns:
            PermissionResult: 檢查結果
        """


DEFAULT_ROOT_USER = "root"


class IPermissionCheckerWithStore(IPermissionChecker, Generic[T]):
    """帶有資源存儲的權限檢查器接口"""

    @property
    @abstractmethod
    def resource_manager(self) -> IResourceManager[T]: ...
