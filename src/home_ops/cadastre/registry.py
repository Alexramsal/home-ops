"""Official cadastre and land-registry portals by country."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CadastreProvider:
    """Fuente oficial localizada; Home-Ops solo consulta automáticamente cuando is_automated=True y existe cliente runtime (actualmente ES); otros manual/regional."""

    country_code: str
    country_name: str
    authority_name: str
    portal_url: str
    api_url: str | None
    description: str
    is_automated: bool


def _provider(code: str, name: str, authority: str, url: str, description: str) -> CadastreProvider:
    return CadastreProvider(code, name, authority, url, None, description, False)


CADASTRE_REGISTRY: dict[str, CadastreProvider] = {
    "ES": CadastreProvider(
        "ES",
        "España",
        "Sede Electrónica del Catastro",
        "https://www.sedecatastro.gob.es/",
        "https://ovc.catastro.meh.es/ovcservweb/OVCSWLocalizacionRC/OVCCallejero.asmx/Consulta_DNPLOC",
        "Cartografía, referencia catastral, superficies y valoración catastral; no acredita titularidad ni cargas jurídicas.",
        True,
    ),
    "US": _provider(
        "US",
        "United States",
        "Decentralized State & County Assessors",
        "https://www.usa.gov/state-local-governments",
        "Sistema descentralizado; los registros de propiedad, parcelas e impuestos son gestionados localmente por condados/municipios.",
    ),
    "DE": _provider("DE", "Deutschland", "BORIS-D / Gutachterausschüsse", "https://www.boris-d.de/", "Valores del suelo y valoración oficial; el Grundbuch acredita titularidad y cargas."),
    "HR": _provider("HR", "Hrvatska", "Državna geodetska uprava / ZIS", "https://oss.uredjenazemlja.hr/", "Catastro y registro de la propiedad para consulta manual; titularidad y cargas constan en el registro jurídico."),
    "FR": CadastreProvider(
        "FR",
        "France",
        "Direction générale des finances publiques",
        "https://www.cadastre.gouv.fr/",
        "https://app.dvf.etalab.gouv.fr/",
        "Plan catastral y datos parcelarios; el Service de la publicité foncière acredita derechos y cargas.",
        False,
    ),
    "GB": _provider("GB", "United Kingdom", "HM Land Registry", "https://www.gov.uk/government/organisations/land-registry", "Registro jurídico de títulos, titularidad y cargas en Inglaterra y Gales; no es un catastro fiscal único del Reino Unido."),
    "IT": _provider("IT", "Italia", "Agenzia delle Entrate Catasto/Conservatoria", "https://www.agenziaentrate.gov.it/portale/", "Catastro y Conservatoria: datos catastrales y publicidad inmobiliaria jurídica sobre titularidad y cargas."),
    "PT": _provider("PT", "Portugal", "Predial Online + Direção-Geral do Território", "https://www.predialonline.pt/", "Predial Online ofrece registro jurídico; DGT ofrece cartografía y datos territoriales."),
    "NL": _provider("NL", "Nederland", "Kadaster", "https://www.kadaster.nl/", "Catastro, mapas y registro jurídico de titularidad y cargas."),
    "BE": _provider("BE", "Belgique", "CadGIS / SPF Finances + Sécurité juridique", "https://finances.belgium.be/fr/E-services/CadGIS", "CadGIS ofrece parcelas y cartografía; la seguridad jurídica acredita titularidad y cargas."),
    "AT": _provider("AT", "Österreich", "Grundbuch / Bundesamt für Eich- und Vermessungswesen", "https://www.justiz.gv.at/", "Grundbuch registra titularidad y cargas; BEV ofrece cartografía y catastro."),
    "PL": _provider("PL", "Polska", "Geoportal EGiB + Elektroniczne Księgi Wieczyste", "https://www.geoportal.gov.pl/", "EGiB ofrece parcelas y cartografía; Elektroniczne Księgi Wieczyste ofrece titularidad y cargas jurídicas."),
    "CZ": _provider("CZ", "Česko", "Český úřad zeměměřický a katastrální", "https://nahlizenidokn.cuzk.cz/", "Catastro inmobiliario oficial, incluyendo parcelas, titularidad y cargas consultables manualmente."),
    "IE": _provider("IE", "Ireland", "Tailte Éireann", "https://tailte.ie/", "Mapas y registro de títulos inmobiliarios; consulta manual de titularidad y cargas."),
    "SE": _provider("SE", "Sverige", "Lantmäteriet", "https://www.lantmateriet.se/", "Mapas, datos de propiedades y registro inmobiliario oficial de titularidad y cargas."),
    "GR": _provider("GR", "Ελλάδα", "Ελληνικό Κτηματολόγιο", "https://www.ktimatologio.gr/", "Catastro nacional, mapas y registro de derechos inmobiliarios y cargas."),
}

# UK remains a compatibility alias; both keys reference one provider.
CADASTRE_REGISTRY["UK"] = CADASTRE_REGISTRY["GB"]


def get_cadastre_provider(country_code: str) -> CadastreProvider | None:
    """Resolve an ISO code case-insensitively, accepting UK as GB alias."""
    if not country_code:
        return None
    return CADASTRE_REGISTRY.get(country_code.strip().upper())


__all__ = ["CadastreProvider", "CADASTRE_REGISTRY", "get_cadastre_provider"]
