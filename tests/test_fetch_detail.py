"""Detail-page description extractors for pisos/fotocasa top audits."""

from scripts.fetch_detail_audit import extract_fotocasa_desc, extract_pisos_desc


def test_fotocasa_extracts_nested_description() -> None:
    html = (
        '<script type="application/json">{"realEstateAdDetailEntityV2": '
        '{"title": "x", "description": "Piso luminoso en el centro de Cádiz, '
        'totalmente reformado, 3 dormitorios y terraza. Zona peatonal muy '
        'tranquila y bien comunicada."}, "other": 1}</script>'
    )
    desc = extract_fotocasa_desc(html)
    assert "Piso luminoso" in desc
    assert "bien comunicada" in desc


def test_fotocasa_empty_when_no_json() -> None:
    assert extract_fotocasa_desc("<html>no script</html>") == ""


def test_pisos_extracts_meta_description() -> None:
    html = (
        '<html><head><meta property="og:description" content="Chalet reformado '
        'en zona exclusiva de Chiclana, 4 hab, piscina privada, parcela 500m2. '
        'Urbanización cerrada con vigilancia."></head></html>'
    )
    desc = extract_pisos_desc(html)
    assert "Chalet reformado" in desc


def test_pisos_empty_without_meta() -> None:
    assert extract_pisos_desc("<html><head></head></html>") == ""
