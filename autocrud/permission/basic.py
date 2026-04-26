from abc import abstractmethod
from typing import Generic, TypeVar

from autocrud.permission.checker import IPermissionChecker
from autocrud.types import IResourceManager

T = TypeVar("T")


DEFAULT_ROOT_USER = "root"


class IPermissionCheckerWithStore(IPermissionChecker, Generic[T]):
    """帶有資源存儲的權限檢查器接口"""

    @property
    @abstractmethod
    def resource_manager(self) -> IResourceManager[T]: ...
