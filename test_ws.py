import asyncio
import json
import websockets

async def main():
    async with websockets.connect("ws://localhost:8000/ws") as ws:
        print("connected")
        async for msg in ws:
            data = json.loads(msg)
            room = data.get("data", {})
            devs = room.get("devices", {})
            summary = {
                k: (v.get("reported") or {}).get("power")
                   or (v.get("reported") or {}).get("current_c")
                   or (v.get("reported") or {}).get("open_pct")
                for k, v in devs.items()
            }
            print("state:", summary)

asyncio.run(main())