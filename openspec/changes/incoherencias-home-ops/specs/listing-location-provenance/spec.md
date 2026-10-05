# Listing Location Provenance Specification

## Purpose

Keep scanned listings inside the requested municipality when their location is resolved, and keep price history and scoring tied to each listing's actual source.

## Requirements

### Requirement: Enforce resolved municipality at scan time

The scan MUST exclude a listing whose resolved municipality conflicts with `search.municipality` before it is scored, recorded as a price observation, or alerted. It MUST NOT infer a municipality match from province-only text. Listings with unresolved municipality MAY continue through existing filters, but MUST NOT be represented as location-verified.

#### Scenario: Matching listing continues

- GIVEN a search for `Chiclana de la Frontera` and a listing resolved to that municipality
- WHEN the scan applies listing filters
- THEN the listing remains eligible for price, area, scoring, and alert processing

#### Scenario: Resolved out-of-town listing is excluded

- GIVEN a search for `Chiclana de la Frontera` and a listing resolved to `Jerez de la Frontera`
- WHEN the scan applies listing filters
- THEN the listing is excluded before scoring, price observation, and alerting

#### Scenario: Ambiguous address is not treated as a proven mismatch

- GIVEN a listing with only province-level or otherwise unresolved location text
- WHEN the scan applies listing filters
- THEN location filtering does not assert a different municipality or silently claim a municipality match
- AND existing non-location filters still apply

### Requirement: Use per-listing source provenance for price history and scoring

Every listing used by a multi-source scan MUST retain association with the source from which it was collected. The scan MUST derive the price-history zone for that listing's source rather than assigning `portal.urls[0]` to all listings; scoring MUST use the same listing-specific zone. An unresolvable zone MUST remain unknown or use the existing explicit fallback, never another source's zone. This requirement MUST NOT require a DuckDB schema change.

#### Scenario: Distinct source zones remain distinct

- GIVEN two sources with different resolved zones and one listing collected from each
- WHEN the scan records price observations and scores the listings
- THEN each observation and scoring input uses its own listing's source zone

#### Scenario: An unresolved source zone does not inherit the first source

- GIVEN a listing collected from a source whose zone cannot be resolved
- AND another source in the same scan has a resolved zone
- WHEN the listing is observed and scored
- THEN its zone is unknown or the existing documented fallback applies
- AND the other source's zone is not attributed to it

#### Scenario: Duplicate listing retains observation provenance

- GIVEN a previously seen listing is encountered again from a known source
- WHEN a new price observation is recorded
- THEN that observation reflects the source associated with the current encounter rather than an unrelated first configured source
