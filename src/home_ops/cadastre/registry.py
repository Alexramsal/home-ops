"""Multi-country Cadastre / Land Registry Information System for Home-Ops."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CadastreProvider:
    """Official Cadastre or Land Registry provider for a specific country."""

    country_code: str
    country_name: str
    authority_name: str
    portal_url: str
    api_url: str | None
    description: str
    is_automated: bool


CADASTRE_REGISTRY: dict[str, CadastreProvider] = {
    "ES": CadastreProvider(
        country_code="ES",
        country_name="España",
        authority_name="Sede Electrónica del Catastro (Ministerio de Hacienda)",
        portal_url="https://www meic.catastro.minhap.es/",
        api_url="https://ovc.catastro.meh.es/ovcservweb/OVCSWLocalizacionRC/OVCCallejero.asmx/Consulta_DNPLOC",
        description="Consulta pública de referencia catastral, superficie construida, uso y antigüedad.",
        is_automated=True,
    ),
    "DE": CadastreProvider(
        country_code="DE",
        country_name="Deutschland",
        authority_name="BORIS-D / Gutachterausschüsse / Grundbuchamt",
        portal_url="https://www.gutachterausschuesse-online.de/",
        api_url=None,
        description="Bodenrichtwerte und Immobilienmarktberichte der amtlichen Gutachterausschüsse.",
        is_automated=False,
    ),
    "FR": CadastreProvider(
        country_code="FR",
        country_name="France",
        authority_name="Cadastre.gouv.fr & Etalab DVF (Demandes de Valeurs Foncières)",
        portal_url="https://cadastre.gouv.fr/",
        api_url="https://app.dvf.etalab.gouv.fr/",
        description="Consultation du plan cadastral français et historique public des ventes foncières.",
        is_automated=True,
    ),
    "HR": CadastreProvider(
        country_code="HR",
        country_name="Hrvatska",
        authority_name="Katastar.hr / Zajednički informacijski sustav (ZIS)",
        portal_url="https://www.katastar.hr/",
        api_url=None,
        description="Javni uvid u katastarske podatke i posjedovne listove Republike Hrvatske.",
        is_automated=False,
    ),
    "UK": CadastreProvider(
        country_code="UK",
        country_name="United Kingdom",
        authority_name="HM Land Registry",
        portal_url="https://www.gov.uk/government/organisations/land-registry",
        api_url="https://landregistry.data.gov.uk/",
        description="Official land title, price paid data, and property boundary registration.",
        is_automated=True,
    ),
    "US": CadastreProvider(
        country_code="US",
        country_name="United States",
        authority_name="County Assessor / Public Records GIS",
        portal_url="https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.html",
        api_url=None,
        description="County assessor property assessment records, parcel maps, and tax appraisal data.",
        is_automated=False,
    ),
}


def get_cadastre_provider(country_code: str) -> CadastreProvider | None:
    """Return the official cadastre provider for a country code (uppercase)."""
    if not country_code:
        return None
    return CADASTRE_REGISTRY.get(country_code.upper())


__all__ = ["CadastreProvider", "CADASTRE_REGISTRY", "get_cadastre_provider"]
