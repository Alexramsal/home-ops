# Design: Resolve Home-Ops Operational Incoherences and Drift

## Technical Approach

Repair the seven findings by preserving evidence already available at each boundary instead of introducing new infrastructure. A small shared location-classification module will normalize parsed location text and classify it as `match`, `mismatch`, or `unresolved`. Source validation will aggregate those classifications into explicit verification states; scan filtering will reject only resolved mismatches. The scan runner will retain each listing's source URL and derived zone in transient scan records so price observations and scoring no longer inherit `portal_urls[0]`.

Configuration, setup, documentation, and tests will then be aligned with those runtime contracts. No database schema, dependency, external service, or dynamic portal URL builder is added. Strict TDD from `openspec/config.yaml` applies: each behavioral defect receives a failing fixture-based test before implementation.

## Architecture Decisions

### Decision: Centralize location normalization and classification

**Choice**: Create `src/home_ops/scraper/location.py` with pure helpers that extract candidate location text from parser dictionaries or `Listing.address`, normalize Unicode accents/case/separators/whitespace, and classify against the configured municipality as `match`, `mismatch`, or `unresolved`.

**Alternatives considered**: Duplicate string logic in `cli/sources.py` and `scraper/filter.py`; add portal-specific municipality parsers; geocode every listing.

**Rationale**: Source validation and scan filtering require identical semantics. Pure local helpers are fixture-testable, avoid network coupling, and consume current parser output without changing all 15 adapters. Portal-specific extractors or geocoding would expand scope and create fragile external dependencies.

### Decision: Use conservative three-state item classification

**Choice**: An explicit parser municipality matching the normalized target is `match`; a different explicit municipality is `mismatch`. When no structured municipality exists, an address containing the target as a whole normalized token sequence is `match`, while an address without the target is `unresolved` unless the parser provides an unambiguous locality component. An absent/empty location is also `unresolved`. Normalization treats punctuation, underscores, hyphens, repeated whitespace, case, and accents equivalently. It does not infer municipality from province names, street-only addresses, or opaque IDs.

**Alternatives considered**: Fuzzy matching; province-level acceptance; rejecting every unresolved listing.

**Rationale**: Substring matching after token normalization handles known parser formats while avoiding invented geographic inference. Fuzzy or province matching could recreate Cádiz-city versus Cádiz-province false positives. Rejecting unresolved data would discard valid opaque or sparse listings.

### Decision: Promote source validation to explicit verification states

**Choice**: Introduce a `SourceValidation` result with state `verified`, `mismatch`, `ambiguous`, or `error`, plus portal, item count, match/mismatch/unresolved counts, and diagnostic text. `validate_source` returns this result; CLI presentation and `add_source` adapt at the boundary. Only `verified` can be added.

A source is:

- `verified` only when `resolved = matched + mismatched > 0` and `matched / resolved > 0.5`; unresolved items never count as matches and are excluded from the denominator;
- `mismatch` when resolved evidence exists but the matching share is below 50%; this is explicitly non-verified;
- `ambiguous` when parsing succeeds but no item exposes usable municipality evidence (including province/district-only samples), or the resolved evidence is an exact 50% tie; this is explicitly non-verified;
- `error` for unsupported portal, fetch/challenge, parse, empty-page, or zero-item failures.

The URL text remains supporting evidence only. A textual URL mismatch must not preempt parsed content; it is included in diagnostics. An opaque/ID-only URL can therefore become `verified` through content, while content with no location remains `ambiguous` rather than falsely passing.

**Alternatives considered**: Keep the current `(bool, str, int)` tuple; let URL matching decide before fetch; accept ambiguous sources.

**Rationale**: A boolean cannot distinguish unavailable evidence from contradictory evidence. Explicit states make the `verified` contract testable and provide actionable CLI output. The canonical strict majority of resolved items reconciles the specification and design under the corrective feedback: missing evidence is not a match or part of the denominator, and a tie cannot verify a source. Report resolved counts and matching share alongside all item counts; the share is undefined when resolved is zero.

### Decision: Filter only resolved municipality mismatches at scan time

**Choice**: Extend `filter_listing` with location classification after existing price/area checks. A resolved mismatch returns `municipality_mismatch`; a match or unresolved address continues through the pipeline. Extend `FilterStats` and scan output with a municipality rejection count.

**Alternatives considered**: Reject unresolved addresses; trust source verification and skip listing-level filtering; filter before price/area checks.

**Rationale**: Source pages can contain promoted or boundary listings despite successful verification, so listing-level enforcement remains necessary. Allowing unresolved addresses preserves current behavior where evidence is absent. Keeping price/area checks first preserves existing reason precedence and test expectations.

### Decision: Carry source provenance in transient scan records

**Choice**: In `scan_runner.py`, represent each collected result as a private scan-local record containing `listing`, `source_url`, and `zone`. Compute the zone once per configured source using `zone_from_portal_url`, cache it by source URL, and preserve the record through filtering, observation recording, insertion, and scoring. Do not add fields to `Listing` or alter DuckDB tables.

For approved listings from previous scans, query the latest non-null zone already stored in `price_history` by `content_hash` through a typed `DuckDBConnection.latest_price_zone()` method. If absent, rescore without a zone, triggering the scorer's existing static `price_median` fallback. Never substitute the first configured source.

**Alternatives considered**: Add `source_url` and `zone` columns to `listings`; derive zone from each detail URL; map by portal name; retain the global first-source zone.

**Rationale**: The source URL is known exactly at collection time. A transient record fixes current observation/scoring provenance without schema migration. Detail URLs often omit search geography, and one portal can have multiple source zones, so neither detail URL nor portal name is sufficient. Existing `price_history.zone` preserves enough provenance for later approved-item rescoring.

### Decision: Keep source filtering before persistence and scoring

**Choice**: Preserve the current pipeline boundary: scrape all configured sources, classify/filter listings, then record price history, insert, enrich, score, and alert. Rejected municipality listings create no listing row, price observation, score, approval, or alert.

**Alternatives considered**: Persist rejected rows for analytics; filter only before alerting.

**Rationale**: Persisting out-of-area prices would continue contaminating medians. Filtering only at alert time would leave incorrect analytics and scoring inputs.

### Decision: Make setup own the typed `search` section

**Choice**: Add `search` to `WIZARD_SECTIONS`, load it into setup state, render fields for country, municipality, transaction, maximum price, minimum area, and garage preference, validate them through `SearchConfig`, and emit the complete `search` block from `build_yaml`. Preserve unknown top-level sections as today.

**Alternatives considered**: Documentation-only correction; require users to edit YAML manually; use only repeated `profile set` commands.

**Rationale**: The setup command claims to capture search intent and already owns profile creation/update. Persisting the typed section closes the root configuration gap without a second configuration path.

### Decision: Remove dead template keys instead of implementing new behavior

**Choice**: Remove `scoring.thresholds.price_under_median_bonus` and the top-level `garage` block from the versioned template and from setup defaults. Keep `SearchConfig.garage_preferred`, the active per-listing garage fields, and existing scoring weights.

**Alternatives considered**: Implement a new below-median bonus and garage-price defaults; make every Pydantic model globally reject extras.

**Rationale**: Neither dead key has a runtime consumer. Implementing them would be feature expansion, while globally changing extra-field policy could break unrelated profiles. Removal makes the shipped template honest with the smallest blast radius.

### Decision: Align template sources without inventing global URL generation

**Choice**: Replace province-wide Cádiz examples with the smallest set of municipality-scoped Chiclana URLs whose formats are already represented in repository evidence. Keep `idealista_url` equal to the first `portal.urls` entry. Fixture tests prove parser/location compatibility; any live verification remains an operator step under existing anti-bot guardrails.

**Alternatives considered**: Keep province sources and weaken validation; generate URLs dynamically for every portal; ship opaque URLs not evidenced by the repository.

**Rationale**: The template must not contradict its own municipality. A small evidenced example set is safer than broad guessed coverage and respects the proposal's explicit exclusion of worldwide URL generation.

### Decision: Treat code as authority for scoring and runtime defaults

**Choice**: Update `README.md` and `AGENTS.md` to document canonical `scoring.thresholds.*` paths, energy-certificate presence scoring, price-per-square-metre comparison against a rolling zone median with static fallback, direct deterministic subtraction of recognized LLM risk penalties, and non-ES affordability exclusion with weight redistribution. Standardize web examples on port `8000`. Document installation extras explicitly: `[tui]` for setup/TUI and `[web]` for the dashboard.

**Alternatives considered**: Change scorer behavior to match prose; change the runtime port to 8321; move optional UI dependencies into core.

**Rationale**: The verified runtime behavior is internally coherent; the documentation is stale. Port 8000 is already the CLI default, and optional extras already provide clean dependency boundaries.

### Decision: Replace environmental tests with committed fixtures

**Choice**: Rework `tests/test_sources_cli.py` to use committed sanitized fixtures and `tmp_path` profiles for every municipality-sensitive case. Reuse `daft_cork.html`, `sreality_brno.html`, and `nieruchomosci_online_krakow.html`; add only minimal fixtures needed for match/mismatch/unresolved scenarios not represented by those files. Keep genuinely live portal tests as explicit `pytest.skip` opt-ins in their portal-specific modules.

**Alternatives considered**: Keep `/tmp/*-live.html` conditionals; mock parser return values exclusively; run live network tests in CI.

**Rationale**: Committed HTML fixtures exercise parser-to-validation integration offline. Temporary profile isolation removes dependence on ignored local configuration. Explicit skips preserve honest test accounting.

## Data Flow

### Source validation

```text
URL + profile
    │
    ├── portal registry lookup
    ├── fetch / anti-bot check
    └── portal parser ──→ raw listing dictionaries
                              │
                              └── location text extraction
                                      │
search.municipality ──→ normalization/classification
                                      │
                         aggregate evidence counts
                                      │
                 verified | mismatch | ambiguous | error
                                      │
                      CLI diagnostics / add gate
```

The validation output reports both the state and evidence distribution. URL text is diagnostic context, never the sole verification proof.

### Multi-source scan provenance

```text
source URL A ──→ scrape ──→ (Listing, source A, zone A) ─┐
source URL B ──→ scrape ──→ (Listing, source B, zone B) ─┤
                                                        │
                                  price / area / municipality filter
                                                        │
                                      accepted scan-local records
                                                        │
                  ┌─────────────────────────────────────┼──────────────────┐
                  │                                     │                  │
          price_history(zone)                    insert listing       score(zone)
                  │                                                        │
          rolling zone median                                      approval / alert
```

The provenance record exists only during the scan. Durable zone history remains in the existing `price_history.zone` column. Previous approved listings recover their latest known zone by `content_hash`; no provenance means no zone-specific median.

### Setup and profile synchronization

```text
existing YAML ──→ load_state ──→ typed search wizard fields
                                         │
                                  SearchConfig validation
                                         │
template/defaults ─────────────────→ build_yaml ──→ atomic profile write
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/home_ops/scraper/location.py` | Create | Pure normalization, parsed-location extraction, and three-state municipality classification shared by validation and filtering. |
| `src/home_ops/cli/sources.py` | Modify | Replace URL-only gate with parsed-content aggregation; return explicit verification states and actionable diagnostics; allow `add_source` only for `verified`. |
| `src/home_ops/scraper/filter.py` | Modify | Reject resolved municipality mismatches; add reason and stats counter while preserving unresolved listings. |
| `src/home_ops/cli/scan_runner.py` | Modify | Carry `(listing, source_url, zone)` records from each source through filtering, observation recording, scoring, and approved-item rescoring; remove `portal_urls[0]` coupling. |
| `src/home_ops/models/data_storage.py` | Modify | Add typed latest-zone lookup over existing `price_history` rows for approved listings; no schema change. |
| `src/home_ops/analytics.py` | Modify | Harden/document source URL zone extraction as the per-source fallback and add focused cases for excluded/filter segments if needed. |
| `src/home_ops/setup/core.py` | Modify | Load, validate, preserve, and emit the canonical `search` section; remove the dead scoring default. |
| `src/home_ops/setup/wizard.py` | Modify | Add search-intent fields and collect them into setup state. |
| `config/user_profile.template.yml` | Modify | Use municipality-scoped Chiclana source examples; remove dead `price_under_median_bonus` and `garage` keys. |
| `README.md` | Modify | Correct config paths, scoring behavior, verified-source semantics, optional extras, setup flow, and port 8000 examples. Preserve unrelated local edits by surgical hunks. |
| `AGENTS.md` | Modify | Correct CLI key paths and onboarding/source-verification contracts. |
| `tests/test_sources_cli.py` | Modify | Replace `/tmp` conditionals with fixture-driven state tests and isolate profiles using `tmp_path`. |
| `tests/test_filter.py` | Modify | Add municipality match, mismatch, unresolved, normalization, and stats tests. |
| `tests/test_cli.py` | Modify | Add multi-source scan assertions proving each observation and score receives its own zone; cover approved-item zone lookup/fallback. |
| `tests/test_price_history.py` | Modify | Test source URL zone extraction and latest-zone retrieval from existing history. |
| `tests/test_setup_core.py` | Modify | Test search round-trip, preservation, validation, and dead-key removal. |
| `tests/test_setup_wizard.py` | Modify | Test search field rendering/collection and saved profile output. |
| `tests/fixtures/` | Modify / Create minimally | Reuse existing sanitized portal pages; add only missing small fixtures for ambiguous or cross-municipality validation evidence. |

`pyproject.toml` and `src/home_ops/cli/app.py` need no runtime change: `[web]`, `[tui]`, and port `8000` are already correct. Existing local modifications in `README.md`, `pyproject.toml`, `assets/`, and `.atl/` must remain intact.

## Interfaces / Contracts

### Location evidence

```python
from enum import StrEnum
from typing import Any

class MunicipalityMatch(StrEnum):
    MATCH = "match"
    MISMATCH = "mismatch"
    UNRESOLVED = "unresolved"


def parsed_location_text(item: dict[str, Any]) -> str | None: ...
def classify_municipality(location: str | None, municipality: str) -> MunicipalityMatch: ...
```

`parsed_location_text` checks explicit nested location values first, then the shared `address` field. It returns evidence text only; it does not geocode or infer geography.

### Source verification

```python
from dataclasses import dataclass
from enum import StrEnum

class VerificationState(StrEnum):
    VERIFIED = "verified"
    MISMATCH = "mismatch"
    AMBIGUOUS = "ambiguous"
    ERROR = "error"

@dataclass(frozen=True)
class SourceValidation:
    state: VerificationState
    portal: str | None
    item_count: int
    matched: int = 0
    mismatched: int = 0
    unresolved: int = 0
    message: str = ""

    @property
    def verified(self) -> bool:
        return self.state is VerificationState.VERIFIED
```

CLI exit behavior:

| State | `sources validate` | `sources add` |
|-------|--------------------|---------------|
| `verified` | Exit 0; print portal, parsed count, evidence distribution | Append atomically or report already present |
| `mismatch` | Exit 1; print expected municipality and observed distribution | Do not mutate profile |
| `ambiguous` | Exit 1; explain missing location evidence and request a municipality-specific source/manual verification | Do not mutate profile |
| `error` | Exit 1; retain precise unsupported/fetch/challenge/parse/empty reason | Do not mutate profile |

### Filtering contract

```python
filter_listing(listing, search_cfg) -> tuple[bool, str | None]
# Additional rejection reason: "municipality_mismatch"
```

`allow_missing=True` continues to affect missing price/area only. It does not allow a resolved municipality mismatch.

### Scan-local provenance

```python
@dataclass(frozen=True)
class SourcedListing:
    listing: Listing
    source_url: str
    zone: str | None
```

This private type is not persisted and does not become part of the public `Listing` model.

### Setup state

```python
state["search"] = {
    "country_code": "ES",
    "municipality": "Chiclana de la Frontera",
    "transaction": "buy",
    "max_price": 250000.0,
    "min_area_sqm": 80.0,
    "garage_preferred": True,
}
```

`build_yaml` validates this block with `SearchConfig` before writing. Invalid values fail the save with an actionable setup error; they are not silently replaced.

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | Normalization and three-state location classification | Table-driven cases for accents, case, `_`, `-`, punctuation, municipality within full addresses, different municipalities, and empty evidence. |
| Unit | Validation state aggregation | Parser-result samples covering majority match, majority mismatch, all unresolved, mixed unresolved/resolved, unsupported portal, challenge, parse failure, and zero items. |
| Unit | Listing filtering | Existing price/area cases plus match, mismatch, unresolved, reason precedence, `allow_missing`, and municipality stats. |
| Unit | Zone helpers | Distinct source URLs, opaque URLs returning `None`, excluded transaction/filter segments, and latest observation zone lookup. |
| Unit | Setup serialization | `search` load/build round-trip, existing-profile preservation, invalid typed values, and absence of dead template keys. |
| Integration | `sources validate` and `sources add` | `CliRunner`, committed HTML fixtures, and `tmp_path` profile files; assert output, exit code, evidence counts, and no mutation on mismatch/ambiguous/error. |
| Integration | Multi-source scan | Stub each source to return a listing; assert `record_price_observation` and scorer calls receive distinct source-derived zones, municipality mismatches never reach persistence/scoring, and source order does not change results. |
| Integration | Approved listing rescoring | Seed/mock existing price history; assert latest stored zone is used, absent zone falls back without borrowing another source. |
| Integration | Setup wizard | Textual pilot tests populate search controls, save, reload, and compare typed state. |
| Regression | Offline portal fixtures | Reuse Daft Cork, Sreality Brno, and Nieruchomosci Kraków fixtures; no `/tmp/*-live.html` conditional may report a pass. |
| Full suite | Repository quality gates | Run `HOME_OPS_CONFIG= uv run pytest`, `uv run ruff check src tests`, and `uv run mypy src`. |

Strict TDD ordering for implementation: first add RED tests for false-positive source verification, opaque URL content verification, ambiguous evidence, municipality filtering, per-source zones, setup search persistence, and fixture non-vacuity; then implement the smallest passing changes.

## Threat Matrix

N/A — this change does not add or modify routing, shell commands, subprocesses, VCS/PR automation, executable-file classification, or process-integration boundaries. Existing CLI command behavior changes only through local validation and documentation; no threat-matrix boundary applies.

## Migration / Rollout

No database migration required.

Rollout is code-and-configuration only:

1. Land shared location classification with RED/GREEN unit tests.
2. Land source validation and fixture-based CLI tests.
3. Land scan filtering and source-zone provenance tests.
4. Land setup/template synchronization.
5. Land documentation corrections and run all quality gates.

Existing user profiles are not rewritten automatically. Profiles without `search` continue using current `SearchConfig` defaults until the user runs setup or edits the profile. Existing price-history rows remain valid; rows with incorrect historical zones are not rewritten because source provenance cannot be reconstructed reliably. New scans record correct per-source zones.

Given the 400-line review budget and broad test/doc surface, `sdd-tasks` should forecast chained review slices under the preflight `auto-chain` strategy rather than combine all findings into one oversized review.

## Open Questions

None blocking. Live validity of municipality-scoped example URLs remains an operator verification concern under portal ToS/anti-bot constraints; implementation must not claim live verification from fixture evidence alone.
