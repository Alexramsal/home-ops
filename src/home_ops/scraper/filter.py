"""Strict data quality filtering for scraped listings."""

from dataclasses import dataclass

from home_ops.models.schema import Listing, SearchConfig
from home_ops.scraper.location import MunicipalityMatch, classify_municipality


@dataclass
class FilterStats:
    total_seen: int = 0
    accepted: int = 0
    rejected_price: int = 0
    rejected_m2: int = 0
    rejected_missing_price: int = 0
    rejected_missing_m2: int = 0
    rejected_municipality: int = 0


def filter_listing(
    listing: Listing,
    search_cfg: SearchConfig,
    allow_missing: bool = False,
    explicit_location: str | None = None,
) -> tuple[bool, str | None]:
    """Validate a single listing against search criteria and data completeness rules.

    Location filtering runs after price/area checks and only rejects a
    resolved municipality mismatch: ``explicit_location`` is structured
    locality evidence when available, otherwise the free-form ``address``
    is used and can only match or stay unresolved.
    """
    if listing.price is None:
        if not allow_missing:
            return False, "missing_price"
    elif float(listing.price) > search_cfg.max_price:
        return False, "price_exceeded"

    if listing.m2 is None:
        if not allow_missing:
            return False, "missing_m2"
    elif listing.m2 < search_cfg.min_area_sqm:
        return False, "area_insufficient"

    municipality = getattr(search_cfg, "municipality", "") or ""
    if explicit_location is not None:
        match = classify_municipality(explicit_location, municipality, explicit=True)
    else:
        match = classify_municipality(listing.address, municipality)
    if match is MunicipalityMatch.MISMATCH:
        return False, "municipality_mismatch"

    return True, None


def filter_listings(
    listings: list[Listing],
    search_cfg: SearchConfig,
    allow_missing: bool = False,
    explicit_locations: list[str | None] | None = None,
) -> tuple[list[Listing], FilterStats]:
    """Filter a list of listings and return accepted listings with filter statistics."""
    stats = FilterStats(total_seen=len(listings))
    accepted: list[Listing] = []

    for index, listing in enumerate(listings):
        explicit = explicit_locations[index] if explicit_locations is not None else None
        is_ok, reason = filter_listing(
            listing, search_cfg, allow_missing=allow_missing, explicit_location=explicit
        )
        if is_ok:
            accepted.append(listing)
            stats.accepted += 1
        else:
            if reason == "price_exceeded":
                stats.rejected_price += 1
            elif reason == "area_insufficient":
                stats.rejected_m2 += 1
            elif reason == "missing_price":
                stats.rejected_missing_price += 1
            elif reason == "missing_m2":
                stats.rejected_missing_m2 += 1
            elif reason == "municipality_mismatch":
                stats.rejected_municipality += 1

    return accepted, stats
