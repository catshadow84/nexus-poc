import asyncio
import sys
from datetime import date, timedelta

from server.apaleo import ApaleoClient, ApaleoError


async def main(book: bool) -> None:
    client = ApaleoClient()

    properties = (await client.get("/inventory/v1/properties")).get("properties", [])
    if not properties:
        print("No properties found.")
        return
    prop = properties[0]
    print(f"Property: {prop.get('id')} - {prop.get('name')}")

    arrival = (date.today() + timedelta(days=30)).isoformat()
    departure = (date.today() + timedelta(days=32)).isoformat()
    adults = 2
    print(f"Searching {arrival} to {departure}, {adults} adults\n")

    offers = await client.get_offers(prop["id"], arrival, departure, adults)
    if not offers:
        print("No offers returned (no availability, or no rates for these dates).")
        return

    for i, o in enumerate(offers):
        total = o.get("totalGrossAmount", {})
        print(
            f"[{i}] {o['unitGroup'].get('name')} | {o['ratePlan'].get('name')} | "
            f"{total.get('amount')} {total.get('currency')} | "
            f"units={o.get('availableUnits')} | guarantee={o.get('minGuaranteeType')}"
        )

    if not book:
        print("\nLook-only run. Add --book to create a test reservation.")
        return

    chosen = next((o for o in offers if o.get("minGuaranteeType") != "Prepayment"), None)
    if chosen is None:
        print("\nEvery offer needs Prepayment. Not booking.")
        return
    print(f"\nGuarantee type: {chosen.get('minGuaranteeType')}")

    print(f"\nBooking: {chosen['unitGroup'].get('name')} / {chosen['ratePlan'].get('name')}")
    result = await client.create_booking(
        chosen, arrival, departure, adults,
        first_name="Nexus", last_name="TestGuest", email="nexus.test@example.com",
    )
    print("Apaleo response:", result)


if __name__ == "__main__":
    try:
        asyncio.run(main(book="--book" in sys.argv))
    except ApaleoError as e:
        print("Apaleo error:", e)