import asyncio
import json
import logging
from typing import Awaitable, Callable

import asyncio_mqtt as aiomqtt

log = logging.getLogger("mqtt")

BROKER_HOST = "localhost"
BROKER_PORT = 1883


def _topic_matches(pattern: str, topic: str) -> bool:
    """MQTT level-based wildcard matcher.

    `+` matches a single level, `#` matches the remainder.
    """
    p = pattern.split("/")
    t = topic.split("/")
    i = 0
    while i < len(p):
        if p[i] == "#":
            return True
        if i >= len(t):
            return False
        if p[i] != "+" and p[i] != t[i]:
            return False
        i += 1
    return i == len(t)


class MqttBus:
    def __init__(self, host: str = BROKER_HOST, port: int = BROKER_PORT):
        self.host = host
        self.port = port
        self._client: aiomqtt.Client | None = None
        self._handlers: dict[str, Callable[[str, dict], Awaitable[None]]] = {}
        self._task: asyncio.Task | None = None

    async def start(self):
        self._client = aiomqtt.Client(hostname=self.host, port=self.port)
        await self._client.__aenter__()
        log.info("MQTT connected to %s:%s", self.host, self.port)
        self._task = asyncio.create_task(self._listen())

    async def stop(self):
        if self._task:
            self._task.cancel()
        if self._client:
            await self._client.__aexit__(None, None, None)

    async def subscribe(
        self,
        topic: str,
        handler: Callable[[str, dict], Awaitable[None]],
    ):
        self._handlers[topic] = handler
        if self._client:
            await self._client.subscribe(topic)

    async def publish(self, topic: str, payload: dict):
        if not self._client:
            raise RuntimeError("MQTT bus not started")
        await self._client.publish(topic, json.dumps(payload, default=str))

    async def _listen(self):
        assert self._client is not None
        async with self._client.messages() as messages:
            async for message in messages:
                topic = str(message.topic)
                try:
                    payload = json.loads(message.payload)
                except Exception:
                    log.warning("Bad payload on %s", topic)
                    continue

                for pattern, handler in self._handlers.items():
                    if _topic_matches(pattern, topic):
                        try:
                            await handler(topic, payload)
                        except Exception:
                            log.exception("handler failed for topic %s", topic)
                        break


bus = MqttBus()