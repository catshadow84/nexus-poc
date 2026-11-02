import asyncio
import os
import sys

from server.apaleo import ApaleoClient, ApaleoError, WEBHOOK_API


def mask(value, token: str) -> str:
    return str(value).replace(token, "***") if token else str(value)


async def main(args: list[str]) -> None:
    client = ApaleoClient()
    token = os.getenv("APALEO_WEBHOOK_TOKEN", "")
    command = args[0] if args else ""

    if command == "list":
        result = await client._request("GET", "/v1/subscriptions", base=WEBHOOK_API)
        print(mask(result, token))
    elif command == "create" and len(args) == 2:
        if not token:
            print("Set APALEO_WEBHOOK_TOKEN in .env first.")
            return
        body = {
            "endpointUrl": f"{args[1].rstrip('/')}/webhooks/apaleo/{token}",
            "events": ["reservation/*"],
            "propertyIds": [client.property_id],
        }
        result = await client._request("POST", "/v1/subscriptions", json=body, base=WEBHOOK_API)
        print("Created:", mask(result, token))
    elif command == "delete" and len(args) == 2:
        await client._request("DELETE", f"/v1/subscriptions/{args[1]}", base=WEBHOOK_API)
        print("Deleted", args[1])
    else:
        print("Usage:")
        print("  python -m server.apaleo_webhooks list")
        print("  python -m server.apaleo_webhooks create https://your-public-url")
        print("  python -m server.apaleo_webhooks delete SUBSCRIPTION_ID")


if __name__ == "__main__":
    try:
        asyncio.run(main(sys.argv[1:]))
    except ApaleoError as e:
        print("Apaleo error:", e)