import asyncio
import os
import time
from datetime import date
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

    async def _request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        json: dict | None = None,
    ) -> dict:
        async with httpx.AsyncClient(timeout=30) as http:
            token = await self._get_token(http)
            resp = await http.request(
                method,
                API_URL + path,
                params=params,
                json=json,
                headers={"Authorization": f"Bearer {token}"},
            )
        if resp.status_code not in (200, 201, 202):
            raise ApaleoError(f"{method} {path} failed: {resp.status_code} {resp.text}")
        return resp.json() if resp.content else {}

    async def get(self, path: str, params: dict | None = None) -> dict:
        return await self._request("GET", path, params=params)

    async def post(self, path: str, json: dict) -> dict:
        return await self._request("POST", path, json=json)

    async def get_offers(
        self, property_id: str, arrival: str, departure: str, adults: int
    ) -> list[dict]:
        """Available room and rate combinations. Dates are YYYY-MM-DD."""
        data = await self.get(
            "/booking/v1/offers",
            params={
                "propertyId": property_id,
                "arrival": arrival,
                "departure": departure,
                "adults": adults,
                "channelCode": "Ibe",
            },
        )
        return data.get("offers", [])

    async def create_booking(
        self,
        offer: dict,
        arrival: str,
        departure: str,
        adults: int,
        first_name: str,
        last_name: str,
        email: str,
    ) -> dict:
        """Create one reservation from an offer. Returns Apaleo's raw response."""
        nights = (date.fromisoformat(departure) - date.fromisoformat(arrival)).days
        time_slices = [{"ratePlanId": offer["ratePlan"]["id"]} for _ in range(nights)]        
        guest = {"firstName": first_name, "lastName": last_name, "email": email}
        body = {
            "booker": guest,
            "reservations": [
                {
                    "arrival": arrival,
                    "departure": departure,
                    "adults": adults,
                    "channelCode": "Ibe",
                    "primaryGuest": guest,
                    "guaranteeType": offer["minGuaranteeType"],
                    "timeSlices": time_slices,
                }
            ],
        }
        return await self.post("/booking/v1/bookings", json=body)


async def _main() -> None:
    client = ApaleoClient()
    data = await client.get("/inventory/v1/properties")
    properties = data.get("properties", [])
    print(f"Found {len(properties)} propert(ies):")
    for p in properties:
        print(f"  id={p.get('id')}  name={p.get('name')}")


if __name__ == "__main__":
    asyncio.run(_main())