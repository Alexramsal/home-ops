"""Smoke test: setup wizard mounts, navigates sections, saves config."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("textual")

from home_ops.setup.wizard import SetupApp, SetupWizard  # noqa: E402


@pytest.mark.asyncio
async def test_wizard_mounts_and_renders_sections(tmp_path: Path) -> None:
    cfg = tmp_path / "user_profile.yml"
    cfg.write_text("portal:\n  urls: ['https://x']\n")
    env = tmp_path / ".env"
    env.write_text("TELEGRAM_BOT_TOKEN=tok\nTELEGRAM_CHAT_ID=1\n")

    app = SetupApp(cfg, env)
    async with app.run_test() as pilot:
        await pilot.pause()
        from textual.widgets import Input, ListView, Static

        wizard = app.screen
        assert isinstance(wizard, SetupWizard)

        lv = wizard.query_one(ListView)
        assert len(lv.children) == 6
        assert "Telegram" in str(wizard.query_one("#panel-title", Static).render())

        # Navigate to LLM section.
        lv.index = 1
        await pilot.pause()
        assert "LLM" in str(wizard.query_one("#panel-title", Static).render())

        # Inputs are pre-filled from state.
        token_input = wizard.query_one("#bot_token", Input)
        assert token_input.value == "tok"


@pytest.mark.asyncio
async def test_wizard_save_writes_config(tmp_path: Path) -> None:
    cfg = tmp_path / "user_profile.yml"
    cfg.write_text("portal:\n  urls: ['https://x']\ncustom: 1\n")
    env = tmp_path / ".env"
    env.write_text("TELEGRAM_BOT_TOKEN=tok\nTELEGRAM_CHAT_ID=1\n")

    app = SetupApp(cfg, env)
    async with app.run_test() as pilot:
        await pilot.pause()
        wizard = app.screen
        # Change the token and save (via the ctrl+s binding so the save runs
        # inside the message loop, as in real usage).
        wizard.query_one("#bot_token").value = "new_tok"
        await pilot.pause()
        await pilot.press("ctrl+s")  # action_save -> dismiss(True)
        await pilot.pause()
        await pilot.pause()

    written = env.read_text()
    assert "TELEGRAM_BOT_TOKEN=new_tok" in written
    assert "TELEGRAM_CHAT_ID=1" in written  # untouched
    # YAML custom section survives.
    assert "custom" in cfg.read_text()
