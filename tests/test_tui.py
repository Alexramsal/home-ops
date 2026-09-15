"""Smoke test: TUI control panel mounts, refreshes, approves — no crash."""

import pytest

pytest.importorskip("textual")

from home_ops.models.data_storage import get_connection  # noqa: E402
from home_ops.tui import HomeOpsTUI  # noqa: E402


@pytest.mark.asyncio
async def test_tui_mounts_and_refreshes() -> None:
    with get_connection(":memory:") as db:
        db.init_db()

    app = HomeOpsTUI(":memory:")
    async with app.run_test() as pilot:
        await pilot.pause()
        status = app.query_one("#status")
        assert "Listings: 0" in str(status.render())


@pytest.mark.asyncio
async def test_tui_approve_updates_pending_table(tmp_path) -> None:
    db_path = str(tmp_path / "home_ops.duckdb")
    with get_connection(db_path) as db:
        db.init_db()
        db.conn.execute(
            "INSERT INTO listings (content_hash, address) VALUES ('h1', 'Calle Falsa 123')"
        )
        listing_id = db.conn.execute(
            "SELECT id FROM listings WHERE content_hash = 'h1'"
        ).fetchone()[0]
        db.conn.execute(
            "INSERT INTO pending_approvals (listing_id, approved, score) VALUES (?, FALSE, 80.0)",
            [listing_id],
        )

    app = HomeOpsTUI(db_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        pending = app.query_one("#pending")
        assert pending.row_count == 1
        assert app._pending_ids == [listing_id]

        app.action_approve()
        await pilot.pause()
        pending = app.query_one("#pending")
        assert pending.row_count == 0


@pytest.mark.asyncio
async def test_tui_config_opens_setup_wizard(tmp_path) -> None:
    """Binding 'c' pushes the setup wizard modal without leaving the TUI."""
    from home_ops.setup.wizard import SetupWizard

    app = HomeOpsTUI(":memory:", config_path=tmp_path / "user_profile.yml")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("c")
        await pilot.pause()
        assert isinstance(app.screen, SetupWizard)

        # Escape dismisses back to the main TUI.
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, SetupWizard)


@pytest.mark.asyncio
async def test_tui_config_save_refreshes_and_returns(tmp_path) -> None:
    """Saving in the Config tab writes config, returns to the TUI, refreshes."""
    from home_ops.setup.wizard import SetupWizard

    cfg = tmp_path / "user_profile.yml"
    cfg.write_text("portal:\n  urls: ['https://x']\n")
    env = tmp_path / ".env"
    env.write_text("TELEGRAM_BOT_TOKEN=tok\nTELEGRAM_CHAT_ID=1\n")

    app = HomeOpsTUI(":memory:", config_path=cfg)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("c")
        await pilot.pause()
        wizard = app.screen
        assert isinstance(wizard, SetupWizard)

        wizard.query_one("#bot_token").value = "new_tok"
        await pilot.pause()
        await pilot.press("ctrl+s")  # dismiss(True) -> _config_closed -> refresh
        await pilot.pause()
        await pilot.pause()

        assert not isinstance(app.screen, SetupWizard)
        assert "TELEGRAM_BOT_TOKEN=new_tok" in env.read_text()
        assert "Listings: 0" in str(app.query_one("#status").render())
