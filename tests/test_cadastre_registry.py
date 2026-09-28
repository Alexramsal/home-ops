"""Tests for multi-country cadastre registry."""

from home_ops.cadastre.registry import CADASTRE_REGISTRY, get_cadastre_provider


def test_cadastre_registry_contains_major_countries() -> None:
    expected_codes = {"ES", "DE", "FR", "HR", "UK", "US"}
    assert expected_codes.issubset(set(CADASTRE_REGISTRY.keys()))


def test_get_cadastre_provider_valid() -> None:
    provider_es = get_cadastre_provider("ES")
    assert provider_es is not None
    assert provider_es.country_code == "ES"
    assert provider_es.is_automated is True

    provider_de = get_cadastre_provider("de")
    assert provider_de is not None
    assert provider_de.country_code == "DE"
    assert provider_de.is_automated is False


def test_get_cadastre_provider_unknown() -> None:
    assert get_cadastre_provider("XX") is None
    assert get_cadastre_provider("") is None
