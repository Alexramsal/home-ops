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
        assert len(lv.children) == 7
        assert "General" in str(wizard.query_one("#panel-title", Static).render())

        # Navigate to LLM section (index 2: General, Telegram, LLM).
        lv.index = 2
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
        # Portal section is index 3 (General, Telegram, LLM, Portal).
        from textual.widgets import ListView, TextArea

        lv = wizard.query_one(ListView)
        lv.index = 3
        await pilot.pause()

        ta = wizard.query_one("#portals", TextArea)
        ta.text = "https://a.example\nhttps://b.example\n https://c.example "
        await pilot.pause()
        await pilot.press("ctrl+s")
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
        lv.index = 2  # LLM section
        await pilot.pause()
        sw = wizard.query_one("#llm_enabled", Switch)
        assert sw.value is False
        sw.value = True
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()

    assert "enabled: true" in cfg.read_text()


@pytest.mark.asyncio
async def test_wizard_language_selector_and_persistence(tmp_path: Path) -> None:
    from textual.widgets import Select

    cfg = tmp_path / "user_profile.yml"
    cfg.write_text("portal:\n  urls: ['https://x']\n")
    env = tmp_path / ".env"
    env.write_text("HOME_OPS_LANG=en\n")

    app = SetupApp(cfg, env)
    async with app.run_test() as pilot:
        await pilot.pause()
        wizard = app.screen
        assert wizard._sections[0] == "General"
        sel = wizard.query_one("#language", Select)
        assert sel.value == "en"
        option_values = {option[1] for option in sel._options}
        assert {"es", "en"} <= option_values
        prompts = {option[0] for option in sel._options}
        assert {"Español", "English"} <= prompts
        sel.value = "en"
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()

    assert "HOME_OPS_LANG=en" in env.read_text()
    assert "HOME_OPS_LANG" not in cfg.read_text()


@pytest.mark.asyncio
async def test_wizard_invalid_language_falls_back_to_es(tmp_path: Path) -> None:
    from textual.widgets import Select

    cfg = tmp_path / "user_profile.yml"
    cfg.write_text("portal: {}\n")
    env = tmp_path / ".env"
    env.write_text("HOME_OPS_LANG=de\n")

    app = SetupApp(cfg, env)
    async with app.run_test() as pilot:
        await pilot.pause()
        wizard = app.screen
        assert wizard.query_one("#language", Select).value == "es"


@pytest.mark.asyncio
async def test_wizard_labels_localize(tmp_path: Path) -> None:
    from textual.widgets import ListView, Static

    cfg = tmp_path / "user_profile.yml"
    cfg.write_text("portal: {}\n")
    env = tmp_path / ".env"
    env.write_text("HOME_OPS_LANG=en\n")
    app = SetupApp(cfg, env)
    async with app.run_test() as pilot:
        await pilot.pause()
        wizard = app.screen
        lv = wizard.query_one(ListView)
        labels = " ".join(
            str(child.query_one(Static).render()) for child in lv.children
        )
        assert "Language" in labels
        assert "Buyer" in labels
        # Navigate to Buyer section (last) to check description
        lv.index = len(wizard._sections) - 1
        await pilot.pause()
        assert "Buyer Protection" in str(wizard.query_one("#panel-desc", Static).render())
        title = str(wizard.query_one("#panel-title", Static).render())
        assert "Buyer" in title


@pytest.mark.asyncio
async def test_wizard_label_text_localized_for_language_field(tmp_path: Path) -> None:
    from textual.widgets import Label, Select

    cfg = tmp_path / "user_profile.yml"
    cfg.write_text("portal: {}\n")
    env = tmp_path / ".env"
    env.write_text("HOME_OPS_LANG=en\n")
    app = SetupApp(cfg, env)
    async with app.run_test() as pilot:
        await pilot.pause()
        wizard = app.screen
        label = wizard.query_one("#section-general Label", Label)
        assert "Interface language (applies after restart)" in str(label.render())
        assert wizard.query_one("#language", Select)
