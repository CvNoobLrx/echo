"""按 asyncio 事件循环隔离异步客户端。"""
from asyncio import AbstractEventLoop, get_running_loop
from collections.abc import Callable
from threading import Lock
from typing import Generic, TypeVar
from weakref import WeakKeyDictionary

T = TypeVar("T")


class LoopLocal(Generic[T]):
    """为每个事件循环保存一个资源，适配 Celery threads + asyncio.run。"""

    def __init__(self) -> None:
        self._items: WeakKeyDictionary[AbstractEventLoop, T] = WeakKeyDictionary()
        self._lock = Lock()

    def get_or_create(self, factory: Callable[[], T]) -> T:
        loop = get_running_loop()
        with self._lock:
            item = self._items.get(loop)
            if item is None:
                item = factory()
                self._items[loop] = item
            return item

    def pop_current(self) -> T | None:
        loop = get_running_loop()
        with self._lock:
            return self._items.pop(loop, None)
