import asyncio
import logging

from fastapi import WebSocket


log = logging.getLogger("broadcast")


class Broadcaster:
    def __init__(self):
        self._clients: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, room_id: str, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self._clients.setdefault(room_id, set()).add(ws)
        log.info("ws connected room=%s total=%d", room_id, len(self._clients[room_id]))

    async def disconnect(self, room_id: str, ws: WebSocket):
        async with self._lock:
            self._clients.get(room_id, set()).discard(ws)
        log.info("ws disconnected room=%s", room_id)

    async def broadcast(self, room_id: str, payload: dict):
        async with self._lock:
            clients = list(self._clients.get(room_id, set()))
        dead = []
        for ws in clients:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(room_id, ws)


broadcaster = Broadcaster()