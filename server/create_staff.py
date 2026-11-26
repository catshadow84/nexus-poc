"""Create a staff account from the terminal. Use it for the first manager.

Run from the project folder:  python -m server.create_staff
"""

import asyncio
import getpass

from .db import SessionLocal
from .staff import ROLES, create_staff


async def main() -> None:
    username = input("Username (letters and digits, 3-32 characters): ").strip()
    name = input("Full name: ").strip()
    role = input(f"Role ({', '.join(ROLES)}) [manager]: ").strip() or "manager"
    password = getpass.getpass("Password (at least 10 characters, nothing shows as you type): ")
    if password != getpass.getpass("Type the password again: "):
        print("FAILED: the two passwords are different")
        return
    async with SessionLocal() as session:
        try:
            user = await create_staff(session, username, name, role, password)
        except ValueError as e:
            print(f"FAILED: {e}")
            return
    print(f"OK: created the {user.role} account '{user.username}'")


if __name__ == "__main__":
    asyncio.run(main())