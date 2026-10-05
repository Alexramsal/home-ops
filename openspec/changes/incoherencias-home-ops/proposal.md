# Proposal: Resolve Home-Ops Operational Incoherences and Drift

## Intent

Resolve 7 verified architectural, operational, and documentation incoherences identified across the Home-Ops codebase during exploration. Specifically:
1. `sources validate` currently evaluates only the raw URL string without validating parsed sample listings against the target municipality, discarding available parsing evidence and permitting false positives/negatives.
2. `scan_runner.py` assigns the first source's price zone (`portal_urls[0]`) globally to all listings and observations across multi-source scans, biasing historical price metrics and scoring.
3. Documentation and agent guides (`README.md`, `AGENTS.md`) specify invalid flat configuration keys (e.g., `scoring.price_median`) instead of runtime-supported nested keys (`scoring.thresholds.price_median`), causing documented CLI commands to fail.
4. The versioned user profile template sets `municipality: Chiclana de la Frontera` but configures province-wide Cádiz portal sources, which fail validation under its own stated municipality.
5. Scoring documentation misrepresents implementation realities (energy certificate presence vs. letter grade, median vs. range comparison, direct deduction of LLM risk flag penalties in deterministic scoring, and non-ES affordability deactivation with weight redistribution).
6. Tooling and installation instructions drift from runtime reality (port 8000 vs. 8321, optional dependency extras `web` and `tui`, and onboarding workflow steps).
7. Portal CLI validation tests pass vacuously when temporary files `/tmp/*-live.html` do not exist, masking test coverage gaps in CI.

## Scope

### In Scope
- **Strict Source Validation**: Update `sources validate` to inspect parsed listing items, compare extracted locations against `search.municipality`, handle opaque/ID-only URLs safely, and return actionable diagnostics.
- **Per-Source Zone Provenance & Location Filtering**: Ensure `scan_runner.py` derives and persists zone provenance per listing source, and apply municipality filtering when listing location is resolved.
- **Configuration & CLI Key Harmonization**: Fix documentation in `README.md` and `AGENTS.md` to use canonical nested keys (`scoring.thresholds.*`), remove dead keys (`price_under_median_bonus`, `garage:`) from templates or document their handling.
- **Template Alignment**: Provide valid, municipality-aligned source URLs in `config/user_profile.template.yml` for Chiclana de la Frontera, and allow profile setup tooling to handle search parameters.
- **Accurate Scoring Documentation**: Clarify exact scoring mechanisms in `README.md` and `AGENTS.md`: energy certificate binary presence score, price comparison against zone median, inclusion of LLM risk flags as deterministic penalty subtractions, and Spanish-only affordability calculation.
- **Environment & CLI Defaults Unification**: Align default web port to 8000 across code and docs, document required extras (`[web]`, `[tui]`), and reconcile setup instructions.
- **Test Hygiene & Fixtures**: Replace ephemeral `/tmp/*-live.html` test logic in `tests/test_sources_cli.py` with committed sanitized fixtures in `tests/fixtures/` and isolate test configuration paths with `tmp_path` fixtures so tests never depend on host working-directory configuration.

### Out of Scope
- Artificial feature expansion or dynamic URL generation for all international portals.
- Automated CAPTCHA solving, anti-bot evasion, or scraping paywall bypasses.
- Implementing full Catastro/OVC enrichment for countries outside Spain.
- Changing DuckDB database schemas beyond existing columns.

## Capabilities

### New Capabilities
- `source-verification`: Validates portal sources against search municipality using parsed listing sample locations, handles ambiguous/ID-only URLs, and enforces strict `verified` contract semantics.
- `listing-location-provenance`: Enforces municipality boundaries on scraped listings and derives price-history zone per source/listing rather than globally from the first source.
- `config-and-docs-alignment`: Reconciles configuration keys (`scoring.thresholds.*`), template sources, CLI defaults (port 8000), optional dependency documentation, and scoring calculation descriptions.
- `fixture-test-hygiene`: Enforces offline, sanitized fixture testing for portal validation and replaces vacuous conditional passes with explicit skips.

### Modified Capabilities
- None

## Approach

1. **Source Validation Logic (`src/home_ops/cli/sources.py`)**:
   - Extract location metadata from parsed sample listings (using existing parser output fields such as `location` and `address`).
   - Compare normalized extracted municipalities with `search.municipality`.
   - If listings contain municipality data, require a consensus threshold (e.g. >= 50% matching) to mark as `verified`.
   - If the URL is ID-only or listings lack explicit municipality text, flag as `ambiguous` with clear operator instructions rather than failing blindly or passing falsely.
2. **Scan Runner & Provenance (`src/home_ops/cli/scan_runner.py`, `src/home_ops/scraper/filter.py`)**:
   - Associate each scraped listing with its originating source URL.
   - Calculate zone per listing source when recording price observations in DuckDB.
   - Filter out listings whose parsed municipality does not match `search.municipality` (when location data is present).
3. **Template & Setup Alignment (`config/user_profile.template.yml`, `src/home_ops/setup/`)**:
   - Align template source URLs to point to Chiclana de la Frontera endpoints matching the configured municipality.
   - Clean up dead keys in `user_profile.template.yml`.
   - Support `search` configuration in `setup` wizard or clarify onboarding commands in `AGENTS.md`.
4. **Documentation & Port Correction (`README.md`, `AGENTS.md`, `src/home_ops/cli/app.py`)**:
   - Replace all instances of `scoring.price_median`, `scoring.min_score_to_alert`, and `scoring.weights` with `scoring.thresholds.*`.
   - Standardize web dashboard port on 8000 in documentation and CLI help.
   - Document optional extras (`web`, `tui`) needed for `homeops web` and `homeops tui`.
   - Detail scoring behavior: energy cert presence (0.0 or 1.0), price per m2 vs. median, LLM risk penalty deduction, and affordability exclusion outside ES.
5. **Test Fixtures & Reliability (`tests/test_sources_cli.py`)**:
   - Replace `/tmp/*-live.html` conditional blocks with committed test fixtures in `tests/fixtures/` (e.g., using existing `daft_cork.html`, `sreality_brno.html`, `nieruchomosci_online_krakow.html`).
   - Use `pytest.skip` with clear messages for genuinely optional network tests.
   - Isolate `test_validate_source_pass` by pointing `HOME_OPS_CONFIG` to a temporary fixture profile.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/home_ops/cli/sources.py` | Modified | Add parsed sample listing municipality verification; improve ambiguous URL handling. |
| `src/home_ops/cli/scan_runner.py` | Modified | Track source URL per listing; record per-source zone in price observations; pass accurate zone to scoring. |
| `src/home_ops/scraper/filter.py` | Modified | Add optional municipality filter for listings with resolved locations. |
| `config/user_profile.template.yml` | Modified | Align source URLs with Chiclana municipality; remove unparsed dead keys. |
| `src/home_ops/setup/core.py` | Modified | Preserve/emit `search` configuration during setup. |
| `README.md` | Modified | Fix scoring config keys, clarify scoring signals, align port 8000, document dependency extras. |
| `AGENTS.md` | Modified | Fix documented `profile set` commands, align setup flow, update verified source requirements. |
| `tests/test_sources_cli.py` | Modified | Isolate profile path via fixture; replace vacuous `/tmp` tests with committed fixtures. |
| `tests/fixtures/` | Modified / New | Add missing portal fixtures if needed; wire into offline tests. |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Portal listing samples have inconsistent address formats | Medium | Use robust normalization (strip accents, case-fold, check substrings and parent municipality tokens). |
| Real portal URLs with opaque IDs get rejected | Low | Distinguish textual slug validation from sample content validation; report ambiguous status when URL lacks slug. |
| Multi-source zone calculation overhead | Low | `zone_from_portal_url` is a fast regex/URL parse; caching by source URL avoids redundant computation. |
| User profile template changes break existing tests | Low | Update test fixtures that mock template initialization to match aligned structure. |

## Rollback Plan

All modifications are confined to application logic, documentation, configuration templates, and unit tests. If issues arise:
1. Revert Git commits associated with the change branch.
2. Verify clean baseline with `uv run pytest`, `uv run ruff check src tests`, and `uv run mypy src`.
3. No DuckDB schema migration or data transformation rollback is required.

## Dependencies

- None. No external dependencies, libraries, or external services are introduced.

## Success Criteria

- [ ] `sources validate` rejects sources where sample listings clearly belong to a different municipality than configured.
- [ ] `sources validate` passes sources when parsed listings match the configured municipality.
- [ ] Multi-source scan records distinct zones for observations from different source URLs.
- [ ] `README.md` and `AGENTS.md` document exact valid nested configuration keys (`scoring.thresholds.*`).
- [ ] Documented `profile set` commands execute successfully against initialized profiles.
- [ ] Web dashboard documentation and CLI defaults consistently specify port 8000.
- [ ] All tests in `tests/test_sources_cli.py` run offline using committed fixtures without relying on `/tmp/*` files.
- [ ] Full test suite passes: `uv run pytest` (0 failures, no vacuous passes).
- [ ] Static validation clean: `uv run ruff check src tests` and `uv run mypy src` pass with 0 errors.
