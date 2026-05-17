import asyncio
from collections import defaultdict
from typing import AsyncIterator


class TranscriptBus:
    # Wildcard channel: any subscriber on this key receives EVERY published
    # message, regardless of its call_id. Lets the live-demo viewer attach
    # without needing to know the active call_id in advance.
    GLOBAL_KEY = "_all"

    def __init__(self) -> None:
        self._queues: dict[str, list[asyncio.Queue]] = defaultdict(list)

    async def publish(self, call_id: str, msg: dict) -> None:
        for q in self._queues[call_id]:
            await q.put(msg)
        if call_id != self.GLOBAL_KEY:
            for q in self._queues[self.GLOBAL_KEY]:
                await q.put(msg)

    async def subscribe(self, call_id: str) -> AsyncIterator[dict]:
        queue: asyncio.Queue = asyncio.Queue()
        self._queues[call_id].append(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            self._queues[call_id].remove(queue)


bus = TranscriptBus()
