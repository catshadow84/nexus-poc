import asyncio
import os
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

TOKEN_URL = "https://identity.apaleo.com/connect/token"
API_URL = "https://api.apaleo.com"


class ApaleoError(Exception):
    pass


class ApaleoClient:
    def __init__(self) -> None:
        self.client_id = os.getenv("APALEO_CLIENT_ID")
        self.client_secret = os.getenv("APALEO_CLIENT_SECRET")
        if not self.client_id or not self.client_secret:
            raise ApaleoError("Set APALEO_CLIENT_ID and APALEO_CLIENT_SECRET in .env")
        self._token: str | None = None
        self._expires_at = 0.0

    async def _get_token(self, http: httpx.AsyncClient) -> str:
        # Reuse the token until 60 seconds before it expires.
        if self._token and time.time() < self._expires_at - 60:
            return self._token
        resp = await http.post(
            TOKEN_URL,
            data={"grant_type": "client_credentials"},
            auth=(self.client_id, self.client_secret),
        )
        if resp.status_code != 200:
            raise ApaleoError(f"Token request failed: {resp.status_code} {resp.text}")
        data = resp.json()
        self._token = data["access_token"]
        self._expires_at = time.time() + data["expires_in"]
        return self._token

    async def get(self, path: str, params: dict | None = None) -> dict:
        async with httpx.AsyncClient(timeout=20) as http:
            token = await self._get_token(http)
            resp = await http.get(
                API_URL + path,
                params=params,
                headers={"Authorization": f"Bearer {token}"},
            )
        if resp.status_code != 200:
            raise ApaleoError(f"GET {path} failed: {resp.status_code} {resp.text}")
        return resp.json()


async def _main() -> None:
    client = ApaleoClient()
    data = await client.get("/inventory/v1/properties")
    properties = data.get("properties", [])
    print(f"Found {len(properties)} propert(ies):")
    for p in properties:
        print(f"  id={p.get('id')}  name={p.get('name')}")


if __name__ == "__main__":
    asyncio.run(_main())