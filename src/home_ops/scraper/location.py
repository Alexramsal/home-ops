"""Pure municipality location-evidence extraction and classification.

Shared by source validation (``cli/sources.py``) and scan filtering
(``scraper/filter.py``). The helpers never geocode and never infer a
municipality from province, district, or opaque text: an explicit
structured locality value may be a ``match`` or ``mismatch``, while a
free-form address that does not contain the target stays ``unresolved``.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

_NON_TOKEN = re.compile(r"[^a-z0-9]+")

# Nested parser keys that unambiguously name a locality/municipality.
_EXPLICIT_KEYS = ("municipality", "city", "town", "locality")

# Tokens that label a province/region level rather than a municipality.
# ponytail: whole-token adjacency only; extend the set if a portal exposes
# another qualifier adjacent to the target.
_REGION_MARKERS = frozenset(
    {
        "province",
        "provincia",
        "provincie",
        "provinz",
        "província",
        "county",
        "region",
        "región",
        "district",
        "distrito",
        "kraj",
    }
)

# Linking words that may sit between a region marker and the target, e.g.
# "provincia de cadiz", "provincia del cadiz", "region of cadiz".
_CONNECTORS = frozenset({"de", "del", "da", "do", "di", "du", "of", "la", "el", "los", "las"})


class MunicipalityMatch(StrEnum):
    """Outcome of comparing location evidence against the target town."""

    MATCH = "match"
    MISMATCH = "mismatch"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class LocationEvidence:
    """Location text plus whether it is an explicit locality or free-form.

    ``explicit`` is True only for structured municipality/locality values
    (e.g. a parser ``location.municipality`` field). Addresses are
    free-form and can therefore be a ``match`` but never a ``mismatch``.
    """

    text: str
    explicit: bool


def normalize_text(text: str) -> str:
    """Lower-case, strip accents, and collapse punctuation to single spaces."""
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_lower = "".join(c for c in nfkd if not unicodedata.combining(c)).lower()
    return _NON_TOKEN.sub(" ", ascii_lower).strip()


def _tokens(text: str) -> list[str]:
    norm = normalize_text(text)
    return norm.split() if norm else []


def _contains_sequence(haystack: list[str], needle: list[str]) -> bool:
    """Whole-token containment; avoids substring collisions like chiloe/chiloea."""
    if not needle or len(needle) > len(haystack):
        return False
    return any(haystack[i : i + len(needle)] == needle for i in range(len(haystack) - len(needle) + 1))


def _neighbor_is_region_marker(tokens: list[str], index: int, step: int) -> bool:
    """Walk outward from ``index``, skipping connectors, until a non-connector.

    Returns True when that nearest meaningful token is a province/region marker.
    """
    while 0 <= index < len(tokens):
        token = tokens[index]
        if token in _REGION_MARKERS:
            return True
        if token not in _CONNECTORS:
            return False
        index += step
    return False


def _is_region_only(tokens: list[str], target: list[str]) -> bool:
    """True when every target occurrence sits next to a province/region marker.

    Callers invoke this only after ``_contains_sequence`` succeeds, so at
    least one occurrence exists. A single occurrence away from a marker makes
    the text municipality evidence rather than province context.
    """
    width = len(target)
    for start in range(len(tokens) - width + 1):
        if tokens[start : start + width] != target:
            continue
        if not (
            _neighbor_is_region_marker(tokens, start - 1, -1)
            or _neighbor_is_region_marker(tokens, start + width, 1)
        ):
            return False
    return True


def classify_municipality(
    location: str | None,
    municipality: str,
    *,
    explicit: bool = False,
) -> MunicipalityMatch:
    """Classify ``location`` against ``municipality`` as match/mismatch/unresolved.

    An explicit structured locality must equal the target after normalization:
    the same token sequence is a ``match``, any other value is a ``mismatch``.
    Free-form text is a ``match`` only when the target occurs as a whole token
    sequence and is not province/region context; otherwise it stays
    ``unresolved`` so province, street, and district text never asserts a
    different town.
    """
    if not location or not location.strip():
        return MunicipalityMatch.UNRESOLVED
    target = _tokens(municipality)
    if not target:
        return MunicipalityMatch.UNRESOLVED
    location_tokens = _tokens(location)
    if explicit:
        return MunicipalityMatch.MATCH if location_tokens == target else MunicipalityMatch.MISMATCH
    if _contains_sequence(location_tokens, target) and not _is_region_only(location_tokens, target):
        return MunicipalityMatch.MATCH
    return MunicipalityMatch.UNRESOLVED


def parsed_location_evidence(item: dict[str, Any]) -> LocationEvidence | None:
    """Extract location evidence from a raw parser item.

    Checks a nested ``location`` mapping first, then top-level structured
    keys, then the shared ``address`` field. Explicit municipality wins
    over conflicting free-form address text.
    """
    nested = item.get("location")
    if isinstance(nested, dict):
        for key in _EXPLICIT_KEYS:
            value = nested.get(key)
            if isinstance(value, str) and value.strip():
                return LocationEvidence(value, explicit=True)
        for key in ("address", "locality"):
            value = nested.get(key)
            if isinstance(value, str) and value.strip():
                return LocationEvidence(value, explicit=False)
    for key in _EXPLICIT_KEYS:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return LocationEvidence(value, explicit=True)
    address = item.get("address")
    if isinstance(address, str) and address.strip():
        return LocationEvidence(address, explicit=False)
    return None


def classify_evidence(
    evidence: LocationEvidence | None, municipality: str
) -> MunicipalityMatch:
    """Classify an already-extracted evidence record."""
    if evidence is None:
        return MunicipalityMatch.UNRESOLVED
    return classify_municipality(evidence.text, municipality, explicit=evidence.explicit)
