"""Tests for multi-country cadastre registry."""

from home_ops.cadastre.registry import CADASTRE_REGISTRY, get_cadastre_provider

EXPECTED_CODES = {
    "ES", "US", "DE", "HR", "FR", "GB", "IT", "PT", "NL", "BE", "AT", "PL", "CZ", "IE", "SE", "GR",
}


def test_registry_contains_all_supported_countries() -> None:
    assert set(CADASTRE_REGISTRY) >= EXPECTED_CODES


def test_providers_are_official_https_and_conservative() -> None:
    for code in EXPECTED_CODES:
        provider = get_cadastre_provider(code)
        assert provider is not None
        assert provider.portal_url.startswith("https://")
        assert provider.authority_name
        assert provider.description
        if code != "ES":
            assert provider.is_automated is False
        if provider.api_url:
            assert provider.api_url.startswith("https://")


def test_us_provider_is_decentralized_manual_source() -> None:
    provider = get_cadastre_provider("US")
    assert provider is not None
    assert provider.portal_url == "https://www.usa.gov/state-local-governments"
    assert "decentralized" in provider.authority_name.lower()
    assert "census" not in provider.description.lower()
    assert "tiger" not in provider.description.lower()
    assert provider.api_url is None
    assert provider.is_automated is False


def test_italy_and_austria_use_verified_official_root_portals() -> None:
    assert get_cadastre_provider("IT").portal_url == "https://www.agenziaentrate.gov.it/portale/"
    assert get_cadastre_provider("AT").portal_url == "https://www.justiz.gv.at/"


def test_spain_uses_ovc_runtime_integration() -> None:
    provider = get_cadastre_provider("ES")
    assert provider is not None
    assert provider.api_url == (
        "https://ovc.catastro.meh.es/ovcservweb/OVCSWLocalizacionRC/"
        "OVCCallejero.asmx/Consulta_DNPLOC"
    )
    assert provider.is_automated is True


def test_spain_url_and_legal_distinction() -> None:
    provider = get_cadastre_provider("es")
    assert provider is not None
    assert provider.portal_url == "https://www.sedecatastro.gob.es/"
    assert "catastr" in provider.description.lower()


def test_gb_alias_resolves_without_duplicate_provider() -> None:
    assert get_cadastre_provider("gb") is get_cadastre_provider("UK")
    assert get_cadastre_provider("gb").country_code == "GB"


def test_get_cadastre_provider_unknown() -> None:
    assert get_cadastre_provider("XX") is None
    assert get_cadastre_provider("") is None
