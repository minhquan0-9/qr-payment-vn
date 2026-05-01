"""In-process pub/sub for order status changes.

Mỗi order_code có một danh sách asyncio.Queue subscriber. Khi có sự kiện mới
(order paid, expired, ...) ta đẩy vào tất cả queue tương ứng để SSE handler
flush về client.

Lưu ý: chỉ hoạt động trong 1 process. Nếu chạy nhiều worker uvicorn cần
chuyển sang Redis pub/sub.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any


class OrderEventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue[dict[str, Any]]]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def subscribe(self, order_code: str) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=32)
        async with self._lock:
            self._subscribers[order_code].append(queue)
        return queue

    async def unsubscribe(self, order_code: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        async with self._lock:
            if queue in self._subscribers.get(order_code, []):
                self._subscribers[order_code].remove(queue)
            if not self._subscribers.get(order_code):
                self._subscribers.pop(order_code, None)

    async def publish(self, order_code: str, event: dict[str, Any]) -> None:
        async with self._lock:
            queues = list(self._subscribers.get(order_code, []))
        for q in queues:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # Drop event if subscriber is slow; client có thể fallback poll
                pass


bus = OrderEventBus()
