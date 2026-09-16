"""i18n resolution, catalog parity and safe interpolation."""

import pytest

from home_ops import i18n


def test_resolve_explicit_wins(monkeypatch) -> None:
    monkeypatch.setenv("HOME_OPS_LANG", "es")
    assert i18n.resolve_locale("en", "es-ES,es;q=0.9") == "en"


def test_resolve_explicit_regional_value() -> None:
    assert i18n.resolve_locale("en-US") == "en"
    assert i18n.resolve_locale("es-ES") == "es"


def test_resolve_explicit_invalid_falls_through(monkeypatch) -> None:
    monkeypatch.setenv("HOME_OPS_LANG", "en")
    assert i18n.resolve_locale("fr", "es") == "en"


def test_resolve_env_wins_over_header(monkeypatch) -> None:
    monkeypatch.setenv("HOME_OPS_LANG", "en")
    assert i18n.resolve_locale(None, "es-ES,es;q=0.9") == "en"


def test_resolve_env_invalid_ignored(monkeypatch) -> None:
    monkeypatch.setenv("HOME_OPS_LANG", "de")
    assert i18n.resolve_locale(None, "en-US,en;q=0.9") == "en"


def test_resolve_header_first_supported(monkeypatch) -> None:
    monkeypatch.delenv("HOME_OPS_LANG", raising=False)
    assert i18n.resolve_locale(None, "fr-FR,en-US;q=0.8,es;q=0.7") == "en"
    assert i18n.resolve_locale(None, "es-ES,es;q=0.9,en;q=0.8") == "es"


def test_resolve_default_es(monkeypatch) -> None:
    monkeypatch.delenv("HOME_OPS_LANG", raising=False)
    assert i18n.resolve_locale() == "es"
    assert i18n.resolve_locale(None, None) == "es"
    assert i18n.resolve_locale(None, "fr-FR,de;q=0.9") == "es"
    assert i18n.resolve_locale(None, "*") == "es"


def test_catalog_parity() -> None:
    assert set(i18n.CATALOGS["es"]) == set(i18n.CATALOGS["en"])


def test_t_interpolates_es_and_en() -> None:
    assert i18n.t("kpi.obs.desc", "es") == "Capturas brutas registradas"
    assert i18n.t("kpi.obs.desc", "en") == "Raw captures recorded"
    assert i18n.t("step1.stat", "es", n=3) == "3 observaciones brutas"
    assert i18n.t("step1.stat", "en", n=3) == "3 raw observations"


def test_t_fallback_to_es_and_unknown_key() -> None:
    assert i18n.t("kpi.obs.desc", "fr") == "Capturas brutas registradas"
    assert i18n.t("does.not.exist", "en") == "does.not.exist"


def test_t_missing_var_is_safe() -> None:
    # No KeyError/IndexError: placeholder stays visible.
    assert i18n.t("step1.stat", "es") == "{n} observaciones brutas"


@pytest.mark.parametrize("key", sorted(i18n.CATALOGS["es"]))
def test_every_catalog_entry_renders(key: str) -> None:
    assert isinstance(i18n.t(key, "es"), str)
    assert isinstance(i18n.t(key, "en"), str)


def test_tui_default_spanish_exact() -> None:
    assert i18n.t("tui.subtitle", "es") == "Radar inmobiliario"
    assert i18n.t("tui.status.idle", "es") == "En reposo"
    assert i18n.t("tui.tab.summary", "es") == "Resumen"
    assert i18n.t("tui.col.address", "es") == "Dirección"
    assert i18n.t("tui.llm.none", "es") == "IA: sin analizar"
    assert i18n.t("tui.llm.prefix", "es") == "IA: "
    assert i18n.t("tui.flags.prefix", "es") == "Flags: "


def test_tui_english_translations() -> None:
    assert i18n.t("tui.subtitle", "en") == "Real estate radar"
    assert i18n.t("tui.tab.summary", "en") == "Summary"
    assert i18n.t("tui.tab.pending", "en") == "Pending"
    assert i18n.t("tui.col.address", "en") == "Address"
    assert i18n.t("tui.llm.none", "en") == "AI: not analyzed"
    assert i18n.t("tui.status.idle", "en") == "Idle"


def test_wizard_labels_translated() -> None:
    assert i18n.t("setup.section.general", "es") == "General"
    assert i18n.t("setup.section.general", "en") == "Language"
    assert i18n.t("setup.field.language", "es") == "Idioma de la interfaz (se aplica al reiniciar)"
    assert i18n.t("setup.field.language", "en") == "Interface language (applies after restart)"
    assert i18n.t("setup.section.buyer", "en") == "Buyer"
