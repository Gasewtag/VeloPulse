"""Tests for Strava CLI commands."""

from unittest.mock import AsyncMock, patch

import pytest

from velopulse.cli.strava import (
    cmd_delete_webhook,
    cmd_list_webhooks,
    cmd_register_webhook,
    cmd_simulate_event,
    main,
)
from velopulse.domain.strava import StravaSubscription
from velopulse.services.strava.client import StravaClient


@pytest.mark.asyncio
async def test_cmd_list_webhooks(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify list-webhooks prints active subscriptions."""
    client = StravaClient()
    mock_sub = StravaSubscription(
        id=555,
        application_id=123,
        callback_url="https://example.com/api/v1/webhooks/strava",
        created_at="2026-09-24T12:00:00Z",
        updated_at="2026-09-24T12:00:00Z",
    )
    with patch.object(client, "list_subscriptions", new_callable=AsyncMock) as mock_list:
        mock_list.return_value = [mock_sub]
        await cmd_list_webhooks(client)

    captured = capsys.readouterr()
    assert "Active Strava Webhook Subscriptions" in captured.out
    assert "ID: 555" in captured.out


@pytest.mark.asyncio
async def test_cmd_register_webhook(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify register-webhook prints created subscription details."""
    client = StravaClient()
    mock_sub = StravaSubscription(
        id=777,
        application_id=123,
        callback_url="https://example.com/api/v1/webhooks/strava",
        created_at="2026-09-24T12:00:00Z",
        updated_at="2026-09-24T12:00:00Z",
    )
    with patch.object(client, "create_subscription", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_sub
        await cmd_register_webhook(client, "https://example.com/api/v1/webhooks/strava", "my_token")

    captured = capsys.readouterr()
    assert "Subscription ID: 777" in captured.out
    assert "[SUCCESS]" in captured.out


@pytest.mark.asyncio
async def test_cmd_delete_webhook(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify delete-webhook issues delete call and prints success."""
    client = StravaClient()
    with patch.object(client, "delete_subscription", new_callable=AsyncMock) as mock_del:
        mock_del.return_value = None
        await cmd_delete_webhook(client, 999)

    captured = capsys.readouterr()
    assert "Successfully deleted webhook subscription ID 999" in captured.out


@pytest.mark.asyncio
async def test_cmd_simulate_event(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify simulate-event sends synthetic HTTP POST and reports latency."""
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_resp = AsyncMock()
        mock_resp.status_code = 204
        mock_post.return_value = mock_resp

        await cmd_simulate_event(
            api_url="http://testserver/api/v1/webhooks/strava",
            object_id=123456,
            object_type="activity",
            aspect_type="create",
            owner_id=789,
        )

    captured = capsys.readouterr()
    assert "HTTP 204" in captured.out
    assert "Event successfully ingested" in captured.out


def test_cli_main_entrypoint() -> None:
    """Verify CLI parser parses subcommands."""
    with patch("sys.argv", ["strava.py", "list-webhooks"]), patch(
        "velopulse.cli.strava.cmd_list_webhooks", new_callable=AsyncMock
    ) as mock_cmd:
        main()
        mock_cmd.assert_called_once()
