"""Cache kết quả tool trong tiến trình (LRU + TTL).

Dữ liệu tàu là tĩnh trong phạm vi bài toán, nên cùng tool + cùng tham số cho cùng kết quả.
Chỉ cache kết quả không lỗi. Chạy nhiều bản API thì có thể thay bằng Redis cùng giao diện get/put.
"""

import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import replace

from .base import ToolResult


class ToolCache:
    def __init__(self, ttl_seconds: float, max_entries: int, clock: Callable[[], float] = time.monotonic):
        self.ttl = ttl_seconds
        self.max_entries = max_entries
        self.clock = clock
        self._items: OrderedDict[str, tuple[float, ToolResult]] = OrderedDict()

    def __len__(self) -> int:
        return len(self._items)

    @property
    def enabled(self) -> bool:
        return self.ttl > 0 and self.max_entries > 0

    def get(self, key: str) -> ToolResult | None:
        item = self._items.get(key)
        if item is None:
            return None
        expires, result = item
        if expires < self.clock():
            del self._items[key]
            return None
        self._items.move_to_end(key)
        # Bản sao nông: nơi gọi có thể thêm khoá vào content mà không làm bẩn cache
        return replace(result, content=dict(result.content), focus=dict(result.focus))

    def put(self, key: str, result: ToolResult) -> None:
        if not self.enabled:
            return
        self._items[key] = (self.clock() + self.ttl, result)
        self._items.move_to_end(key)
        while len(self._items) > self.max_entries:
            self._items.popitem(last=False)
