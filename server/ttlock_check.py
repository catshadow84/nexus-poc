"""Check that the TT Lock credentials in .env work. Only logs in; changes nothing.

Run from the project folder:  python -m server.ttlock_check
"""

import asyncio

from .ttlock import TTLockClient, TTLockError


async def main() -> None:
    try:
        info = await TTLockClient().login()
    except TTLockError as e:
        print(f"FAILED: {e}")
        return
    days = info["expires_in"] // 86400
    print(f"OK: logged in to TT Lock (user id {info['uid']}, token valid for about {days} days)")


if __name__ == "__main__":
    asyncio.run(main())