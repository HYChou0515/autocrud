# 添加到 basic.py
from abc import ABC, abstractmethod
from typing import Callable
import datetime as dt

from autocrud.types import ResourceAction
from msgspec import Raw, Struct


class ResourceEvent(Struct):
    """資源操作事件"""

    action: ResourceAction
    model_name: str
    event_by: str
    event_time: dt.datetime
    extra: Raw | None = None


class ITaskQueue(ABC):
    """簡單的任務隊列接口"""

    @abstractmethod
    def send_message(self, event: ResourceEvent) -> None:
        """發送事件消息到隊列"""
        pass

    @abstractmethod
    def start_worker(self, handler: Callable[[ResourceEvent], None]) -> None:
        """啟動工作進程處理消息"""
        pass


class IEventHandler(ABC):
    """事件處理器接口"""

    @abstractmethod
    def handle_event(self, event: ResourceEvent) -> None:
        """處理資源事件"""
        pass
