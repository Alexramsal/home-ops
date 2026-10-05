# Apply Progress: Resolve Home-Ops Operational Incoherences and Drift

**Change**: `incoherencias-home-ops`
**Mode**: Standard (Strict TDD not active)
**Store**: engram + filesystem
**Delivery**: local worktree slice only — no branches, commits, PRs, push, or publish (per preflight).

## Status

All phases (1–9) implemented and verified in the current local worktree.

- Quality gates: `963 passed, 4 skipped`, `ruff` clean, `mypy` clean (59 files).
- Review budget: realised authored delta (~1,800+ lines) exceeds the 400-line budget → **`size:exception` recommended**. Slicing was not possible under the instruction to implement all dependency-ready tasks without creating branches/commits.

## Completed Tasks

- [x] 1.1–1.3 Shared location evidence helper + RED/GREEN tests
- [x] 2.1–2.6 Source verification states, fixture-backed validate/add, offline hygiene
- [x] 3.1–3.4 Municipality filtering before side effects (+ reason precedence, stats)
- [x] 4.1–4.4 Zone extraction hardening + typed `latest_price_zone` lookup
- [x] 5.1–5.4 Multi-source scan provenance (`SourcedListing`, per-source zone)
- [x] 6.1–6.3 Typed search setup serialization + dead-key removal
- [x] 7.1–7.4 Search wizard controls with non-silent invalid-save handling
- [x] 8.1–8.7 Canonical key hints, template alignment, README/AGENTS, web-port regression
- [x] 9.1–9.2 Full quality gates + review evidence recorded

## Files Changed

| File | Action | What |
|---|---|---|
| `src/home_ops/scraper/location.py` | Created | `normalize_text`, `MunicipalityMatch`, `LocationEvidence`, `classify_municipality`, `parsed_location_evidence` |
| `src/home_ops/cli/sources.py` | Modified | `VerificationState`/`SourceValidation`; fetched-content consensus (`resolved>0`, `matched/resolved>0.5`); URL text diagnostic-only; validate/add call sites |
| `src/home_ops/scraper/filter.py` | Modified | Municipality mismatch after price/area; `rejected_municipality` stat; `explicit_location` |
| `src/home_ops/cli/scan_runner.py` | Modified | `SourcedListing` records; per-source zone cache; no `portal_urls[0]`; per-listing approved rescoring zone; municipality stat |
| `src/home_ops/analytics.py` | Modified | `zone_from_portal_url` via `urlparse`; excludes hostname/query/filter/opaque-ID segments |
| `src/home_ops/models/data_storage.py` | Modified | `latest_price_zone(content_hash)` typed lookup (no schema change) |
| `src/home_ops/models/schema.py` | Modified | Private, non-persisted `Listing._explicit_municipality` |
| `src/home_ops/scraper/lifecycle.py` | Modified | Preserve explicit parser municipality evidence |
| `src/home_ops/setup/core.py` | Modified | `search` in `WIZARD_SECTIONS`; typed load/validate/emit; removed dead bonus default |
| `src/home_ops/setup/wizard.py` | Modified | Six search controls; strict search numeric; markup-escaped status; accent-safe section ids |
| `src/home_ops/cli/profile.py` | Modified | Canonical-key hints for obsolete flat scoring keys |
| `config/user_profile.template.yml` | Modified | Municipality-scoped Chiclana sources; removed dead `price_under_median_bonus` and `garage` |
| `README.md` | Modified | Canonical `scoring.thresholds.*`; scoring semantics; port 8000; `[web]`/`[tui]` extras; search keys |
| `AGENTS.md` | Modified | Canonical keys; strict verified contract; scoring semantics; extras/port |
| `tests/…` (9 modules) | Modified | Fixture-backed offline validation, provenance, setup/search, profile hints, template consistency |

## Deviations from Design

- Design's location interface returns only text but its semantics require an explicit-vs-free-form distinction. Implemented `LocationEvidence(explicit=...)` plus a **private, non-persisted** `Listing._explicit_municipality` (not in DuckDB, not in the dedup hash) so resolved out-of-town listings are rejected end-to-end without adding a public Listing field.
- `filter_listings` gained an optional `explicit_locations` parameter (test-only) to exercise municipality rejection stats.

## Issues Found

- `SearchConfig` default municipality is `Cádiz`, so a profile without a `search` block still resolves a target; the "no municipality configured" branch is only reachable if `search.municipality` could be empty (forbidden by the validator).
- Existing `tests/test_config_loader.py::test_portal_configs_include_cadiz_integrations` asserted the old province-wide template; updated to the municipality-scoped template.

## Limitations

- Live portal URL validity was **not** executed and is not claimed; fixtures prove offline parser/validation behavior only.
- No SQL against the user DuckDB; scans in tests use in-memory stores and mocked scrapers/persistence.
- Historical price-history rows with incorrect zones are not rewritten (provenance unrecoverable).

## Verification Commands

```
HOME_OPS_CONFIG= uv run pytest -q   # 963 passed, 4 skipped
uv run ruff check src tests         # All checks passed!
uv run mypy src                     # Success: no issues found in 59 source files
```
