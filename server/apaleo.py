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
WEBHOOK_API = "https://webhook.apaleo.com"


class ApaleoError(Exception):
    pass


def validate_stay(arrival: date, departure: date, adults: int) -> None:
    """Raise ValueError if the requested stay makes no sense."""
    if arrival < date.today():
        raise ValueError("arrival is in the past")
    if departure <= arrival:
        raise ValueError("departure must be after arrival")
    if (departure - arrival).days > 30:
        raise ValueError("stays are limited to 30 nights")
    if not 1 <= adults <= 6:
        raise ValueError("adults must be between 1 and 6")


def split_name(full_name: str) -> tuple[str, str]:
    """Apaleo wants a first and last name; our guests have one name field."""
    first, _, last = full_name.strip().partition(" ")
    return first, (last.strip() or first)


def simplify_offer(offer: dict) -> dict:
    """Pick out the fields the app needs from an Apaleo offer."""
    total = offer.get("totalGrossAmount", {})
    guarantee = offer.get("minGuaranteeType")
    return {
        "rate_plan_id": offer["ratePlan"]["id"],
        "room_type": offer.get("unitGroup", {}).get("name"),
        "rate_plan": offer["ratePlan"].get("name"),
        "total_amount": total.get("amount", 0),
        "currency": total.get("currency", ""),
        "guarantee": guarantee,
        "available_units": offer.get("availableUnits"),
        "bookable": guarantee != "Prepayment",
    }


def extract_ids(response: dict) -> tuple[str, str]:
    """Return (booking_id, reservation_id) from Apaleo's create-booking response."""
    booking_id = response.get("id")
    reservations = response.get("reservationIds") or []
    first = reservations[0] if reservations else None
    reservation_id = first.get("id") if isinstance(first, dict) else None
    if not booking_id or not reservation_id:
        raise ApaleoError(f"Unexpected booking response: {response}")
    return booking_id, reservation_id


class ApaleoClient:
    def __init__(self) -> None:
        self.client_id = os.getenv("APALEO_CLIENT_ID")
        self.client_secret = os.getenv("APALEO_CLIENT_SECRET")
        self.property_id = os.getenv("APALEO_PROPERTY_ID")
        if not self.client_id or not self.client_secret:
            raise ApaleoError("Set APALEO_CLIENT_ID and APALEO_CLIENT_SECRET in .env")
        if not self.property_id:
            raise ApaleoError("Set APALEO_PROPERTY_ID in .env")
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
        base: str = API_URL,
    ) -> dict:
        try:
            async with httpx.AsyncClient(timeout=30) as http:
                token = await self._get_token(http)
                resp = await http.request(
                    method,
                    base + path,
                    params=params,
                    json=json,
                    headers={"Authorization": f"Bearer {token}"},
                )
        except httpx.HTTPError as e:
            raise ApaleoError(f"Network error talking to Apaleo: {e!r}") from e
        if resp.status_code not in (200, 201, 202, 204):
            raise ApaleoError(
                f"{method} {path} failed: {resp.status_code} {resp.text} "
                f"{resp.headers.get('www-authenticate', '')}"
            )
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


_client: ApaleoClient | None = None


def get_client() -> ApaleoClient:
    """One shared client, so the access token is reused between requests."""
    global _client
    if _client is None:
        _client = ApaleoClient()
    return _client


async def _main() -> None:
    client = ApaleoClient()
    data = await client.get("/inventory/v1/properties")
    properties = data.get("properties", [])
    print(f"Found {len(properties)} propert(ies):")
    for p in properties:
        print(f"  id={p.get('id')}  name={p.get('name')}")


if __name__ == "__main__":
    asyncio.run(_main())