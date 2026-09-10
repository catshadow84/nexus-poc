import asyncio
import logging
from fastapi import WebSocket

log = logging.getLogger("broadcast")


class Broadcaster:
    def __init__(self):
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)
        log.info("ws client connected, total=%d", len(self._clients))

    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            self._clients.discard(ws)
        log.info("ws client disconnected, total=%d", len(self._clients))

    async def broadcast(self, payload: dict):
        async with self._lock:
            clients = list(self._clients)
        dead = []
        for ws in clients:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)


broadcaster = Broadcaster()