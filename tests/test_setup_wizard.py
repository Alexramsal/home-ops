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


@pytest.mark.asyncio
async def test_wizard_multiline_portals_saved_as_multiple_urls(tmp_path: Path) -> None:
    cfg = tmp_path / "user_profile.yml"
    cfg.write_text("portal:\n  urls: ['https://x']\n")
    env = tmp_path / ".env"
    env.write_text("TELEGRAM_BOT_TOKEN=tok\nTELEGRAM_CHAT_ID=1\n")

    app = SetupApp(cfg, env)
    async with app.run_test() as pilot:
        await pilot.pause()
        wizard = app.screen
        # Portal section is the third one in the nav list (index 2).
        from textual.widgets import ListView, TextArea

        lv = wizard.query_one(ListView)
        lv.index = 2
        await pilot.pause()

        ta = wizard.query_one("#portals", TextArea)
        ta.text = "https://a.example\nhttps://b.example\n https://c.example "
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        await pilot.pause()

    written = cfg.read_text()
    assert "https://a.example" in written
    assert "https://b.example" in written
    assert "https://c.example" in written


@pytest.mark.asyncio
async def test_wizard_saves_without_telegram_token(tmp_path: Path) -> None:
    cfg = tmp_path / "user_profile.yml"
    cfg.write_text("portal:\n  urls: ['https://x']\n")
    env = tmp_path / ".env"
    env.write_text("")  # no Telegram credentials at all

    app = SetupApp(cfg, env)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        await pilot.pause()

    assert "https://x" in cfg.read_text()
    # Telegram was optional: config persisted anyway (no exception raised).


@pytest.mark.asyncio
async def test_wizard_llm_enabled_is_switch(tmp_path: Path) -> None:
    cfg = tmp_path / "user_profile.yml"
    cfg.write_text("portal:\n  urls: ['https://x']\nllm:\n  enabled: false\n")
    env = tmp_path / ".env"
    env.write_text("TELEGRAM_BOT_TOKEN=tok\nTELEGRAM_CHAT_ID=1\n")

    app = SetupApp(cfg, env)
    async with app.run_test() as pilot:
        await pilot.pause()
        wizard = app.screen
        from textual.widgets import ListView, Switch

        lv = wizard.query_one(ListView)
        lv.index = 1  # LLM section
        await pilot.pause()
        sw = wizard.query_one("#llm_enabled", Switch)
        assert sw.value is False
        sw.value = True
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        await pilot.pause()

    assert "enabled: true" in cfg.read_text()
