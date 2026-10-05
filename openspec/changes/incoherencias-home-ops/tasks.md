# Tasks: Resolve Home-Ops Operational Incoherences and Drift

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 1,150–1,850 authored additions + deletions across implementation, tests, and documentation |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | Eight behavior-complete PRs; shared location, source verification, filtering, zone storage, scan provenance, setup serialization, wizard, template/docs |
| Delivery strategy | auto-chain |
| Chain strategy | pending; stacked-to-main recommended because each completed slice can land independently |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

Auto-chain authorizes slicing, not an invented cached team choice. The orchestrator must resolve/cache chain topology before creating branches or PRs. No PRs, commits, remote operations, or implementation are authorized by this planning artifact. PR numbers below describe review order, not existing branches.

### Planning constraints and contract discrepancies

- Execute as the dedicated tasks phase. Retrieve proposal/spec/design/tasks from Engram; update the explicitly requested existing filesystem tasks artifact and reconcile the source-verification spec/design copies. Persist the full revised tasks artifact to Engram; the filesystem output is an explicit exception, not a different inferred store.
- Strict TDD: capture an actual failing behavioral assertion before its GREEN task; passing existing safeguards are regression checks, not fabricated RED evidence. Keep each slice's tests and relevant documentation with its implementation.
- **Canonical source-verification rule (reconciled):** `resolved = matched + mismatched`; `verified` requires `resolved > 0` and `matched / resolved > 0.5`. Unresolved items are excluded from the denominator, never counted as matches. No resolved locations or province/district-only evidence returns `ambiguous`; an exact 50% tie returns `ambiguous`; below-threshold resolved evidence returns `mismatch`. All are explicit non-verified outcomes, exit 1, and prohibit add/profile mutation. Fetch/challenge/parse/zero-item failures remain `error`. Diagnostics report all evidence counts, resolved count, and matching share (undefined when resolved is zero).
- Opaque/ID-only URLs neither establish nor prohibit verification: matching parsed municipality content can satisfy the canonical rule; absent/insufficient content cannot. URL text remains diagnostic-only. This corrective rule supersedes both prior conflicting thresholds and the proposal's illustrative >=50% wording.
- The design's location interface returns only text, while its semantics distinguish explicit municipality from free-form address evidence. Preserve that distinction in the smallest helper interface; never classify an ordinary street or province-only address as a resolved mismatch.
- The spec requires obsolete flat-key errors to suggest the canonical key. Current `set_profile_value` rejects unknown keys but does not provide that specific suggestion. Phase 8 includes this small omitted implementation target.
- The threat matrix is explicitly N/A. No additional threat-matrix RED tasks are introduced; anti-bot/nonmutation safeguards remain explicit spec regression coverage.
- Preserve all pre-existing local edits, including README, pyproject, assets, `.atl/`, and `.pi/`. Do not rewrite ignored user profiles, `.env`, or runtime data. No schema migration, historical-zone backfill, new dependency, worldwide URL generator, or live portal claim.

### Suggested Work Units

| Unit | Goal / start and finish | Likely PR / dependencies | Estimate | Focused test command | Runtime harness | Rollback boundary |
|------|------------------------|--------------------------|----------|----------------------|-----------------|-------------------|
| 1 | Start: no shared classifier. Finish: evidence-aware local three-state classification. | PR 1; none | 100–180 | `uv run pytest tests/test_filter.py -k municipality` | N/A: pure helper; table-driven classification is the executable boundary | New location helper and its tests only; after consumers land, revert consumers first |
| 2 | Start: tuple/URL gate. Finish: explicit verification states, fixture-backed validate/add, honest diagnostics. | PR 2; unit 1 and reconciled verification contract | 220–350 | `uv run pytest tests/test_sources_cli.py tests/test_challenge.py` | Offline CliRunner validate/add with real committed HTML parsing and temporary profiles; fetch mocked, no network | Source-validation/API adaptation and associated fixture/tests; no persisted source mutations outside test profiles |
| 3 | Start: price/area filters only. Finish: resolved municipality exclusion with reason/stats. | PR 3; unit 1 | 90–150 | `uv run pytest tests/test_filter.py tests/test_cli.py -k 'municipality or filter'` | Offline scan harness proves rejected listing never reaches persistence/scoring/alerting | Municipality filter/stat changes and scan output only; preserve later provenance wiring on revert |
| 4 | Start: approximate URL zone extraction, no latest-zone method. Finish: tested safe zone lookup without schema changes. | PR 4; none | 100–170 | `uv run pytest tests/test_price_history.py` | In-memory DuckDBConnection through typed API, never direct access to the user's database | Zone helper and latest-zone API/tests; revert unit 5 first if already consumed |
| 5 | Start: first-source global zone. Finish: observations, scores, duplicates, approved rescoring use actual provenance. | PR 5; units 3 and 4 | 200–330 | `uv run pytest tests/test_cli.py -k 'provenance or zone or municipality'` | Offline multi-source scan with temporary config, stub scraper/enrichment/alerts, in-memory storage; assert scorer and observation inputs | Transient scan record, collection/scoring/rescoring changes and integration tests; existing history untouched |
| 6 | Start: setup loses search state. Finish: typed search load/build preservation and validation. | PR 6; none | 120–200 | `uv run pytest tests/test_setup_core.py` | Temporary profile load/build/write/reload with synthetic values, no credentials | Setup core serialization/default changes and tests; preserve existing profiles |
| 7 | Start: no search controls. Finish: wizard saves valid search intent, refuses invalid input without replacement. | PR 7; unit 6 | 140–230 | `uv run pytest tests/test_setup_wizard.py tests/test_setup_core.py` | Textual pilot populates six search fields, saves and reloads temporary profile; invalid save leaves file unchanged | Search controls/collection/error handling and pilot tests; keep core round-trip support |
| 8 | Start: stale template/guidance and flat-key diagnostic. Finish: consistent template, canonical command/error, accurate runtime guidance. | PR 8; units 2, 5, 6, 7 | 180–290 | `uv run pytest tests/test_profile_cli.py tests/test_sources_cli.py tests/test_setup_core.py tests/test_cli.py` | Temporary profile init/set/validate through CliRunner; web command mocked to inspect default port; template sources parsed offline | Template, focused profile error hint, docs hunks and matching tests; never revert unrelated README edits |

Each slice stays below 400 by forecast, not by code compression. Measure the actual authored additions + deletions against its own base. If a cohesive slice exceeds the budget after this one slicing pass, report the honest overage and request `size:exception`; do not weaken tests or silently combine units. Under stacked-to-main, each PR targets main and lands in dependency order. If the orchestrator selects feature-branch-chain instead, PR 1 targets the tracker branch and each later PR targets the immediately preceding child branch; retarget/rebase polluted child diffs before review.

## Phase 1: Shared Location Evidence — Unit 1

- [x] 1.1 RED: Add table-driven helper tests in `tests/test_filter.py` for explicit matching/different municipalities, accents/case, punctuation, underscores/hyphens, repeated whitespace, whole-token address matches, substring collisions, empty evidence, province-only and street-only unresolved text. Explicit municipality wins over conflicting free-form address text.
- [x] 1.2 GREEN: Create `src/home_ops/scraper/location.py` with the smallest pure extraction/normalization/classification helpers preserving explicit-versus-free-form evidence; return match/mismatch/unresolved without geocoding or province inference.
- [x] 1.3 REFACTOR/verify: Remove only helper-local duplication in `src/home_ops/scraper/location.py`; run the unit-1 focused command against `tests/test_filter.py` (read-only) and record RED/GREEN results. Do not change runtime filtering yet.

## Phase 2: Source Verification and Offline Fixture Hygiene — Unit 2

- [x] 2.1 Contract check: Compare `openspec/changes/incoherencias-home-ops/specs/source-verification/spec.md` (read-only) with `openspec/changes/incoherencias-home-ops/design.md` (read-only) and this canonical rule: strictly >50% of resolved items, unresolved excluded, zero resolved/province/district-only/exact tie/below threshold explicitly non-verified, opaque URLs verified only through qualifying content. Preserve the rule in test names/assertions; no unresolved consensus decision remains.
- [x] 2.2 RED: Replace `/tmp/*-live.html` conditional passes in `tests/test_sources_cli.py` with unconditional fixture assertions using `tests/fixtures/daft_cork.html` (read-only), `tests/fixtures/sreality_brno.html` (read-only), and `tests/fixtures/nieruchomosci_online_krakow.html` (read-only). Use `tmp_path` profiles and explicit config paths or HOME_OPS_CONFIG, including a conflicting working-directory profile case; mock fetch so tests cannot contact portals.
- [x] 2.3 RED: Add state/count/diagnostic cases in `tests/test_sources_cli.py`: 2 matches/1 mismatch verifies; 1 match/1 mismatch returns ambiguous (exact tie); 1 match/2 mismatches returns mismatch; 1 match/0 mismatches/9 unresolved verifies with resolved=1 and share=100% (not 10%). All unresolved, province-only and district-only samples return ambiguous, never verified. Cover misleading URLs with contradictory content, opaque URLs with qualifying content (verified) or no evidence (ambiguous), and zero items (error). Assert resolved/evidence counts and share (undefined with zero resolved); add no guessed URL semantics.
- [x] 2.4 RED/regression: In `tests/test_sources_cli.py`, assert add does not alter profile bytes for mismatch/ambiguous/error, verified add is atomic/idempotent, and unsupported/fetch/empty/parse failures remain precise. Adapt `tests/test_challenge.py` for explicit error results without changing anti-bot policy. Any genuinely optional live test retained here must report an explicit reasoned skip, never conditional PASS.
- [x] 2.5 GREEN: Modify `src/home_ops/cli/sources.py` to introduce SourceValidation/VerificationState and implement `resolved = matched + mismatched`, verifying only when resolved > 0 and matched/resolved > 0.5. Return ambiguous for zero resolved/province/district-only evidence or exact ties, mismatch for below-threshold resolved evidence, error for existing fetch/challenge/parse/zero-item failures. Make URL text diagnostic-only; expose item/evidence/resolved counts and share; adapt validate/add CLI call sites. Only verified permits mutation; preserve permitted fetch/challenge handling. Use existing HTML fixtures or parser stubs before creating new fixtures.
- [x] 2.6 REFACTOR/verify: Remove obsolete URL-only gate logic from `src/home_ops/cli/sources.py`; run both unit-2 test modules and record offline harness output. If a new HTML fixture is essential, name its exact path in an appended task before creating it; sanitize personal/session data and keep it minimal.

## Phase 3: Municipality Filtering Before Side Effects — Unit 3

- [x] 3.1 RED: Extend `tests/test_filter.py` for matching/unresolved acceptance, explicit out-of-town rejection, reason precedence after price/area, allow_missing not overriding mismatch, and municipality rejection stats.
- [x] 3.2 RED: Add scan cases in `tests/test_cli.py` asserting a resolved Jerez listing in a Chiclana search creates no listing insertion, price observation, enrichment/score, approval, or alert; unresolved province text still follows existing price/area checks.
- [x] 3.3 GREEN: Modify `src/home_ops/scraper/filter.py` to apply the shared classifier after existing checks, return municipality_mismatch, and count rejections in FilterStats. Modify `src/home_ops/cli/scan_runner.py` only as needed to expose the new count and enforce existing pre-persistence filtering.
- [x] 3.4 REFACTOR/verify: Preserve current non-location reason precedence in `src/home_ops/scraper/filter.py`; run unit-3 focused tests and offline rejection harness in `tests/test_cli.py` (read-only).

## Phase 4: Zone Extraction and Durable Lookup — Unit 4

- [x] 4.1 RED: Extend `tests/test_price_history.py` for distinct source zones, opaque/no-zone URLs, transaction/filter/query/hostname segments not becoming zones, latest non-null zone by content_hash, newer null observation, and no-history fallback. Use typed storage methods on isolated in-memory stores, not the user's database.
- [x] 4.2 GREEN: Modify `src/home_ops/analytics.py` only to fix evidenced source-zone extraction failures using standard URL parsing and existing formats; keep unknown zones None without inferred geography.
- [x] 4.3 GREEN: Add typed latest_price_zone lookup in `src/home_ops/models/data_storage.py` over existing price_history rows by content_hash with deterministic latest ordering and no schema change/backfill.
- [x] 4.4 REFACTOR/verify: Run `tests/test_price_history.py` (read-only) and record unit-4 typed-storage harness results; verify `src/home_ops/models/data_storage.py` introduces no migration or new persistent fields.

## Phase 5: Multi-Source Scan Provenance — Unit 5

- [x] 5.1 RED: Add provenance tests in `tests/test_cli.py` for two sources from the same portal with distinct zones; assert each observation and scoring call has its source's zone, reversing source order preserves attribution, and unknown source zone never inherits the first known zone.
- [x] 5.2 RED: Extend `tests/test_cli.py` for duplicate listing encounters retaining current observation provenance, approved-item rescoring using latest non-null historical zone, and no-history approved items using None/static scorer fallback. Keep municipality rejection coverage active.
- [x] 5.3 GREEN: Modify `src/home_ops/cli/scan_runner.py` to collect private listing/source_url/zone records, cache zone once per source, preserve records through filtering/observation/insertion/scoring, and eliminate portal_urls[0] global attribution. Do not add public Listing fields or alter dedup semantics.
- [x] 5.4 GREEN/REFACTOR: In `src/home_ops/cli/scan_runner.py`, use latest_price_zone for prior approved listings and None when absent; remove only obsolete global-zone plumbing. Run unit-5 tests plus complete CLI/price-history/filter modules; record offline harness results.

## Phase 6: Typed Search Setup Serialization — Unit 6

- [x] 6.1 RED: Extend `tests/test_setup_core.py` for loading/saving all six search fields, default profiles without search, round-trip preservation of existing intent/unknown top-level sections, invalid country/transaction/numeric values failing without profile mutation, and removal of the unused scoring bonus default.
- [x] 6.2 GREEN: Modify `src/home_ops/setup/core.py` to own search in WIZARD_SECTIONS, preserve/load typed defaults/state, validate with SearchConfig before writing, emit the complete block, and remove the dead price_under_median_bonus default without globally rejecting extras.
- [x] 6.3 REFACTOR/verify: Run unit-6 tests and temporary load/write/reload harness in `tests/test_setup_core.py` (read-only); confirm validation failures preserve prior profile and do not expose private values.

## Phase 7: Search Wizard Controls — Unit 7

- [x] 7.1 RED: Extend `tests/test_setup_wizard.py` with Textual pilot coverage for country_code, municipality, transaction, max_price, min_area_sqm, and garage_preferred rendering/prefill/collection; save/reload and confirm unknown profile sections survive.
- [x] 7.2 RED: Add invalid search numeric/enum input cases in `tests/test_setup_wizard.py`; save must show actionable errors and leave the existing profile unchanged, not silently use the prior/default value.
- [x] 7.3 GREEN: Modify `src/home_ops/setup/wizard.py` to add six search controls using existing widgets/label conventions and collect typed state through unit-6 validation. Do not reuse silent numeric fallback for invalid search inputs; preserve existing unrelated wizard behavior.
- [x] 7.4 REFACTOR/verify: Run wizard/core modules with the project's tui extra available; record pilot save/reload/error results from `tests/test_setup_wizard.py` (read-only). No live Telegram/LLM calls or real credentials.

## Phase 8: Template, Canonical CLI Guidance, and Documentation — Unit 8

- [x] 8.1 RED: Extend `tests/test_profile_cli.py` for template initialization followed by canonical scoring.thresholds.price_median update, untouched sibling keys, and obsolete scoring.price_median failure explicitly suggesting scoring.thresholds.price_median without mutation. Confirm existing correct behavior as regression rather than forced RED.
- [x] 8.2 GREEN: Modify `src/home_ops/cli/profile.py` only to provide targeted canonical-key hints for documented obsolete flat scoring keys; keep canonical nested-path behavior and atomic writes unchanged.
- [x] 8.3 RED: Extend `tests/test_setup_core.py` and `tests/test_sources_cli.py` to assert the shipped template lacks dead bonus/garage blocks, retains garage_preferred, keeps idealista_url equal to its first URL, and parses municipality-aligned source fixture evidence. Verify repository-evidenced Chiclana URLs, never guessed worldwide endpoints or live-verification claims.
- [x] 8.4 GREEN: Update `config/user_profile.template.yml` with the smallest evidenced municipality-scoped Chiclana source set; remove dead price_under_median_bonus and top-level garage only. Do not rewrite existing operator profiles.
- [x] 8.5 Update `README.md` surgically: canonical threshold/weight paths verified against runtime, setup search intent, reconciled verified semantics, extras [tui]/[web], port 8000, energy presence score, rolling zone median/static fallback, deterministic known LLM risk penalties, and non-ES affordability deactivation/weight redistribution. Preserve pre-existing README work.
- [x] 8.6 Update `AGENTS.md` with the same canonical commands/onboarding/evidence contract and accurately scoped scoring guidance; retain privacy, anti-bot, approved CLI, and financial-data boundaries. Do not claim worldwide fiscal support or that cloud-agent conversations stay local.
- [x] 8.7 Regression/verify: In `tests/test_cli.py`, assert the mocked web server invocation still defaults to 8000; cross-check `src/home_ops/cli/app.py` (read-only), `pyproject.toml` (read-only), and existing scorer tests (read-only via their discovered paths) against docs. No runtime port/dependency/scoring changes unless new contradictory evidence is reported first.

## Phase 9: Integration and Review Evidence

- [x] 9.1 Run `HOME_OPS_CONFIG= uv run pytest`, `uv run ruff check src tests`, and `uv run mypy src`; record exact outcomes against `openspec/changes/incoherencias-home-ops/tasks.md`. Mark only proven completed tasks; report pre-existing failures separately. Run all tests offline with isolated fixture/config state; no user database SQL, live scraping, or remote operations.
- [x] 9.2 Review the final diff against `openspec/changes/incoherencias-home-ops/proposal.md` (read-only), all four capability specs (read-only), and `openspec/changes/incoherencias-home-ops/design.md` (read-only). Record per-unit changed-line counts, focused/runtime results, rollback boundaries, resolved contract decisions, and preserved local-edit status in `openspec/changes/incoherencias-home-ops/tasks.md`; flag any remaining mismatch before sdd-verify.

### Phase 9 evidence (recorded)

**Quality gates (exact commands, final run):**

| Command | Result |
|---|---|
| `HOME_OPS_CONFIG= uv run pytest -q` | exit 0 — `963 passed, 4 skipped, 68 warnings in 83.77s`; coverage 85% (gate 70%) |
| `uv run ruff check src tests` | exit 0 — `All checks passed!` |
| `uv run mypy src` | exit 0 — `Success: no issues found in 59 source files` |

**Per-unit changed lines (authored additions/deletions, `git diff --numstat`):**

| Unit | Files | Add/Del |
|---|---|---|
| 1 | `src/home_ops/scraper/location.py` (new, ~150), `tests/test_filter.py` (+142) | ~292 |
| 2 | `src/home_ops/cli/sources.py` (+194/-49), `tests/test_sources_cli.py` (+338/-125), `tests/test_challenge.py` (+5/-5) | ~716 |
| 3 | `src/home_ops/scraper/filter.py` (+32/-5) | 37 |
| 4 | `src/home_ops/analytics.py` (+32/-8), `src/home_ops/models/data_storage.py` (+15), `tests/test_price_history.py` (+47) | 102 |
| 5 | `src/home_ops/cli/scan_runner.py` (+47/-16), `src/home_ops/scraper/lifecycle.py` (+19/-16), `src/home_ops/models/schema.py` (+6/-1), `tests/test_cli.py` (+172) | 261 |
| 6 | `src/home_ops/setup/core.py` (+28/-1), `tests/test_setup_core.py` (+101) | 130 |
| 7 | `src/home_ops/setup/wizard.py` (+54/-3), `tests/test_setup_wizard.py` (+94/-3) | 154 |
| 8 | `src/home_ops/cli/profile.py` (+14), `tests/test_profile_cli.py` (+40), `tests/test_config_loader.py` (+5/-5), `config/user_profile.template.yml` (+7/-15), `README.md` (+15/-12), `AGENTS.md` (+4/-3) | ~115 |

Total authored well above the 400-line review budget (forecast 1,150–1,850; realised ~1,800+). This is a genuine `size:exception`; the work was executed as one local worktree slice under the preflight `auto-chain`/`feature-branch-chain` instruction that forbade branches/commits/PRs.

**Focused/runtime harness results:** `tests/test_filter.py`, `tests/test_price_history.py`, `tests/test_sources_cli.py`, `tests/test_challenge.py`, `tests/test_cli.py`, `tests/test_setup_core.py`, `tests/test_setup_wizard.py`, `tests/test_profile_cli.py`, `tests/test_config_loader.py` all green. Scans run offline against in-memory DuckDB and mocked scrapers/persistence; no user database, live scraping, or remote calls.

**Rollback boundaries:** Unit 1 helper is additive; Units 3/5 revert filter/scan changes first, then helper. Unit 2 is confined to `cli/sources.py` + its tests. Unit 4 is `analytics.py` + `data_storage.latest_price_zone` (typed, no schema change). Units 6/7 are setup core/wizard + tests. Unit 8 is profile hint, template, and docs hunks.

**Resolved contract decisions:** canonical `verified` rule is `resolved = matched + mismatched`, `verified` iff `resolved > 0 and matched/resolved > 0.5`; unresolved excluded; zero-resolved/province/district-only/exact-tie → `ambiguous`; below-threshold → `mismatch`; error for fetch/challenge/parse/empty/zero-item. URL text diagnostic-only. Per-listing source zone provenance; no schema change.

**Preserved local-edit status:** pre-existing uncommitted changes in `README.md`, `pyproject.toml`, `.atl/`, `assets/`, and untracked `.pi/` were left intact; only surgical hunks were added to `README.md`/`AGENTS.md`. No commits/PRs/push performed.

**Remaining mismatch flagged for sdd-verify:** the design's location interface returns only text while its semantics require explicit-vs-free-form distinction; implementation carries that distinction via `LocationEvidence`/`explicit` flag plus a private, non-persisted `Listing._explicit_municipality`. Archive must confirm this deviation is acceptable.

## Coverage and Exclusions

Source states, tie/denominator policy, opaque content, unsupported/challenge/error boundaries, nonmutating add, deterministic fixture execution and host isolation: Phase 2. Location normalization/three-state evidence: Phase 1. Pre-side-effect filtering and stats: Phase 3. Zone helper and durable lookup: Phase 4. Current/duplicate/approved provenance and order independence: Phase 5. Typed search persistence/invalid saves: Phases 6–7. Template consistency, canonical command/errors, runtime default/extras/scoring documentation: Phase 8. Full quality gates and scope evidence: Phase 9.

No test execution or implementation was performed during task planning. Live municipality-scoped URL validity remains an operator-only concern requiring authorized access; fixtures prove offline parser/validation behavior only. Historical incorrect price zones remain unchanged because their source provenance cannot reliably be recovered.
