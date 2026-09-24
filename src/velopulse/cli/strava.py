"""Strava administrative CLI commands for webhook lifecycle and event simulation."""

import argparse
import asyncio
import json
import logging
import sys
import time

import httpx

from velopulse.core.config import get_settings
from velopulse.services.strava.client import StravaAPIError, StravaClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("velopulse.cli.strava")


async def cmd_list_webhooks(client: StravaClient) -> None:
    """List active Strava webhook push subscriptions."""
    try:
        subscriptions = await client.list_subscriptions()
        if not subscriptions:
            print("No active Strava webhook subscriptions found.")
            return

        print("\n--- Active Strava Webhook Subscriptions ---")
        for sub in subscriptions:
            print(
                f"ID: {sub.id} | App ID: {sub.application_id} | "
                f"Callback: {sub.callback_url} | Created: {sub.created_at}"
            )
        print("-------------------------------------------\n")
    except StravaAPIError as exc:
        logger.error("Failed to query subscriptions: %s", exc)
        sys.exit(1)


async def cmd_register_webhook(
    client: StravaClient, callback_url: str | None, verify_token: str | None
) -> None:
    """Register a new webhook subscription with Strava API."""
    try:
        sub = await client.create_subscription(callback_url=callback_url, verify_token=verify_token)
        print("\n[SUCCESS] Successfully registered Strava Webhook Subscription!")
        print(f"Subscription ID: {sub.id}")
        print(f"Callback URL:    {sub.callback_url}")
        print(f"Created At:      {sub.created_at}\n")
    except StravaAPIError as exc:
        logger.error("Failed to register webhook subscription: %s", exc)
        sys.exit(1)


async def cmd_delete_webhook(client: StravaClient, subscription_id: int) -> None:
    """Delete a webhook subscription from Strava API."""
    try:
        await client.delete_subscription(subscription_id=subscription_id)
        print(f"\n[SUCCESS] Successfully deleted webhook subscription ID {subscription_id}.\n")
    except StravaAPIError as exc:
        logger.error("Failed to delete subscription: %s", exc)
        sys.exit(1)


async def cmd_simulate_event(
    api_url: str,
    object_id: int,
    object_type: str,
    aspect_type: str,
    owner_id: int,
) -> None:
    """Simulate Strava sending a real-time event to local VeloPulse webhook gateway."""
    payload = {
        "object_type": object_type,
        "object_id": object_id,
        "aspect_type": aspect_type,
        "owner_id": owner_id,
        "subscription_id": 9999,
        "event_time": int(time.time()),
        "updates": {},
    }

    print(f"\nDispatching simulated webhook event to: {api_url}")
    print(json.dumps(payload, indent=2))

    start = time.perf_counter()
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(api_url, json=payload, timeout=5.0)
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            print(f"\n[STATUS] HTTP {response.status_code}")
            print(
                f"[LATENCY] {elapsed_ms:.2f} ms (Strava SLA target: < 2000 ms, VeloPulse target: < 50 ms)"
            )
            if response.status_code == 204:
                print("[SUCCESS] Event successfully ingested and queued in Redis!\n")
            else:
                print(f"[FAIL] Unexpected response: {response.text}\n")
        except Exception as exc:
            logger.error("Simulation request failed: %s", exc)
            sys.exit(1)


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(
        prog="python -m velopulse.cli.strava",
        description="VeloPulse Strava Webhook and Integration CLI Management Tool",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # 1. list-webhooks
    subparsers.add_parser("list-webhooks", help="List registered Strava webhook subscriptions")

    # 2. register-webhook
    reg_parser = subparsers.add_parser(
        "register-webhook", help="Register a webhook subscription with Strava"
    )
    reg_parser.add_argument(
        "--callback-url", type=str, default=None, help="Public HTTPS callback URL"
    )
    reg_parser.add_argument(
        "--verify-token", type=str, default=None, help="Custom secret verification token"
    )

    # 3. delete-webhook
    del_parser = subparsers.add_parser(
        "delete-webhook", help="Delete a webhook subscription from Strava"
    )
    del_parser.add_argument(
        "--subscription-id", type=int, required=True, help="Subscription ID to delete"
    )

    # 4. simulate-event
    sim_parser = subparsers.add_parser(
        "simulate-event", help="Simulate a webhook event delivery to local gateway"
    )
    sim_parser.add_argument(
        "--api-url", type=str, default="http://localhost:8000/api/v1/webhooks/strava"
    )
    sim_parser.add_argument("--object-id", type=int, default=123456789, help="Strava activity ID")
    sim_parser.add_argument(
        "--object-type", type=str, default="activity", choices=["activity", "athlete"]
    )
    sim_parser.add_argument(
        "--aspect-type", type=str, default="create", choices=["create", "update", "delete"]
    )
    sim_parser.add_argument("--owner-id", type=int, default=987654321, help="Strava athlete ID")

    args = parser.parse_args()
    settings = get_settings()
    client = StravaClient(settings=settings)

    if args.command == "list-webhooks":
        asyncio.run(cmd_list_webhooks(client))
    elif args.command == "register-webhook":
        asyncio.run(cmd_register_webhook(client, args.callback_url, args.verify_token))
    elif args.command == "delete-webhook":
        asyncio.run(cmd_delete_webhook(client, args.subscription_id))
    elif args.command == "simulate-event":
        asyncio.run(
            cmd_simulate_event(
                api_url=args.api_url,
                object_id=args.object_id,
                object_type=args.object_type,
                aspect_type=args.aspect_type,
                owner_id=args.owner_id,
            )
        )


if __name__ == "__main__":
    main()
