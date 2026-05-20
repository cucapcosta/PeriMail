from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from perimail.calendar import CalendarEvent
import main as main_module


async def test_main_appends_calendar_section(mocker):
    mock_event = CalendarEvent(
        id="e1", calendar_id="primary", title="Dentist",
        start=datetime(2026, 5, 20, 9, 0, tzinfo=timezone.utc),
        end=datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc),
    )
    mocker.patch.dict("os.environ", {
        "GEMINI_API_KEY": "fake",
        "ENCRYPTION_KEY": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
        "DISCORD_BOT_TOKEN": "fake",
        "DISCORD_USER_ID": "123",
    })
    mock_db = AsyncMock()
    mock_db.get_account.return_value = MagicMock(encrypted_tokens="tok")
    mocker.patch("main.Database", return_value=mock_db)
    mocker.patch("main.run_all", return_value={"user@gmail.com": MagicMock(
        category_counts={}, rules_count=0, gemini_count=0, failed_count=0
    )})
    mocker.patch("main.get_credentials", return_value=MagicMock())
    mocker.patch("main.get_calendar_service", return_value=MagicMock())
    mocker.patch("main.list_events", return_value=[mock_event])
    mocker.patch("main.decrypt", return_value=(
        '{"token":"t","refresh_token":"r","token_uri":"u",'
        '"client_id":"c","client_secret":"s","scopes":[]}'
    ))
    sent = []
    mocker.patch("main.send_discord_dm", new=AsyncMock(side_effect=lambda r, *a: sent.append(r)))

    await main_module.main()

    assert sent, "send_discord_dm was never called"
    assert any("Calendar" in r for r in sent), "Calendar section missing from report"
    assert any("Dentist" in r for r in sent), "Event title missing from report"


async def test_main_skips_calendar_on_error(mocker):
    mocker.patch.dict("os.environ", {
        "GEMINI_API_KEY": "fake",
        "ENCRYPTION_KEY": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
        "DISCORD_BOT_TOKEN": "fake",
        "DISCORD_USER_ID": "123",
    })
    mock_db = AsyncMock()
    mock_db.get_account.return_value = MagicMock(encrypted_tokens="tok")
    mocker.patch("main.Database", return_value=mock_db)
    mocker.patch("main.run_all", return_value={"user@gmail.com": MagicMock(
        category_counts={}, rules_count=0, gemini_count=0, failed_count=0
    )})
    mocker.patch("main.get_credentials", side_effect=Exception("no calendar scope"))
    sent = []
    mocker.patch("main.send_discord_dm", new=AsyncMock(side_effect=lambda r, *a: sent.append(r)))

    await main_module.main()

    assert sent, "send_discord_dm was never called"
    assert not any("Calendar" in r for r in sent), "Calendar section should be absent on error"
