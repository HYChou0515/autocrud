"""User and clock dependency wiring for route templates.

:class:`DependencyProvider` produces the FastAPI ``Depends`` callables that
route handlers use to obtain the *current user* and *current time*.  Both
default to safe values (``"anonymous"`` and timezone-aware UTC ``now``)
when not customised; :class:`AutoCRUD` swaps in its configured
``default_user`` automatically via :meth:`with_default_user`.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable


class DependencyProvider:
    """依賴提供者，統一管理用戶和時間的依賴函數

    When ``get_user`` is not provided, the provider returns ``"anonymous"``
    by default.  If the owning :class:`AutoCRUD` instance has a
    ``default_user`` configured, it will replace that default automatically
    via :meth:`with_default_user` so that route handlers use the configured
    user instead of ``"anonymous"``.
    """

    def __init__(
        self,
        get_user: Callable = None,  # ty:ignore[invalid-parameter-default]
        get_now: Callable = None,  # ty:ignore[invalid-parameter-default]
        *,
        default_user: str = "anonymous",
    ):
        """初始化依賴提供者

        Args:
            get_user: 獲取當前用戶的 dependency 函數，如果為 None 則創建預設函數
            get_now: 獲取當前時間的 dependency 函數，如果為 None 則創建預設函數
            default_user: 當 ``get_user`` 未提供時，預設的用戶名稱。
                AutoCRUD 會在設定 ``default_user`` 時自動傳入此值。
        """
        # 記錄 get_user 是否為使用者自訂的
        self._user_is_default: bool = get_user is None
        # 如果沒有提供 get_user，創建一個預設的 dependency 函數
        self.get_user = get_user or self._create_default_user_dependency(default_user)
        # 如果沒有提供 get_now，創建一個預設的 dependency 函數
        self.get_now = get_now or self._create_default_now_dependency()

    def with_default_user(
        self, default_user: "str | Callable[[], str]"
    ) -> "DependencyProvider":
        """Return a (possibly new) provider with the given default user.

        If ``get_user`` was explicitly provided by the caller, the provider
        is returned unchanged — a custom authentication dependency always
        takes priority over ``default_user``.

        Args:
            default_user: A string or zero-arg callable that returns the
                default user name.

        Returns:
            A ``DependencyProvider`` whose ``get_user`` returns
            *default_user* (when the original ``get_user`` was the built-in
            default), or ``self`` unchanged when a custom ``get_user`` was
            already configured.
        """
        if not self._user_is_default:
            return self  # Custom get_user — never override
        if callable(default_user):
            return DependencyProvider(get_user=default_user, get_now=self.get_now)
        return DependencyProvider(get_now=self.get_now, default_user=default_user)

    def _create_default_user_dependency(
        self, default_user: str = "anonymous"
    ) -> Callable:
        """創建預設的用戶 dependency 函數"""

        def default_get_user() -> str:
            return default_user

        return default_get_user

    def _create_default_now_dependency(self) -> Callable:
        """創建預設的時間 dependency 函數

        Returns a callable that produces a **timezone-aware** UTC
        ``datetime``.  This avoids ``TypeError`` when comparing naive
        and aware datetimes (e.g. after a msgpack round-trip).
        """

        def default_get_now() -> dt.datetime:
            return dt.datetime.now(dt.timezone.utc)

        return default_get_now
