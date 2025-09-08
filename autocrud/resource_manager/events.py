"""
do(callable).{phase}(ResourceAction)
.do(callable).{phase}(ResourceAction) # chanainable
.notify(callable).{phase}(ResourceAction) # do async by task queue
"""

from collections.abc import Callable
from typing import Self, Sequence
from autocrud.types import EventContext, ResourceAction, IEventHandler


class SimpleEventHandler(IEventHandler):
    def __init__(self, func, phase: str, action: ResourceAction):
        self.func = func
        self.phase = phase
        self.action = action

    def is_supported(self, context: EventContext) -> bool:
        return context.phase == self.phase and context.action in self.action

    def handle_event(self, context: EventContext) -> None:
        self.func(context)


ContextFunc = Callable[[EventContext], None]


class SimpleEventHandlerBuilder(Sequence[SimpleEventHandler]):
    def __init__(
        self,
        func: ContextFunc | list[ContextFunc],
    ):
        self._ehs: list[SimpleEventHandler] = []
        self.func = None
        self._set_func(func)

    def __len__(self) -> int:
        return len(self._ehs)

    def __getitem__(self, index: int) -> SimpleEventHandler:
        return self._ehs[index]

    def _set_func(self, func: ContextFunc | list[ContextFunc]) -> None:
        if self.func is None:
            self.func = []
        if not isinstance(func, list):
            self.func.append(func)
        else:
            self.func.extend(func)

    def _build_phase(self, phase: str, action: ResourceAction) -> Self:
        if phase not in {"before", "after", "on_success", "on_failure"}:
            raise ValueError(f"Invalid phase: {phase}")
        if self.func is None:
            raise ValueError("Function must be provided before setting phase")
        for f in self.func:
            self._ehs.append(SimpleEventHandler(f, phase, action))
        self.func = None  # 清空當前函數列表，為下一次鏈式調用準備
        return self

    def do(self, func: ContextFunc | list[ContextFunc]) -> Self:
        self._set_func(func)
        return self

    def before(self, action: ResourceAction) -> Self:
        return self._build_phase("before", action)

    def after(self, action: ResourceAction) -> Self:
        return self._build_phase("after", action)

    def on_success(self, action: ResourceAction) -> Self:
        return self._build_phase("on_success", action)

    def on_failure(self, action: ResourceAction) -> Self:
        return self._build_phase("on_failure", action)


def do(func: ContextFunc | list[ContextFunc]) -> SimpleEventHandlerBuilder:
    return SimpleEventHandlerBuilder(func)
