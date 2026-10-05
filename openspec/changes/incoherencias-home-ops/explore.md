# Explore — incoherencias-home-ops

Read-only verification of seven reported implementation/documentation/test incoherences against the current repository at `main` (uncommitted working-tree changes in `README.md`, `pyproject.toml`, `assets/`, `.atl/` were left untouched).

- **Method**: CodeGraph-first structural exploration, targeted reads, and disposable runtime probes (no SQL against DuckDB, no secrets read, no anti-bot bypass).
- **Baseline**: `893 passed, 3 skipped` (pytest), `ruff check src tests` clean, `mypy src` clean on 58 files.

---

## status

`explored` — all seven items verified against code. Two items fully confirmed as real defects, three confirmed as documentation drift, one confirmed as a data-provenance defect plus an environment-dependent test, one confirmed as a vacuous-test correctness bug. No item could be verified as "already correct"; none required a network call to disprove.

---

## executive_summary

The single root cause behind five of the seven items is that **`search.municipality` is declared, documented, and validated — but never enforced against content, and never persisted by the product's own setup path.**

- `sources validate` proves the *URL string* contains the municipality text, then counts parsed rows and discards their locations (`src/home_ops/cli/sources.py:117-124`, `188-198`). Every parser already returns the municipality (e.g. `tests/test_daft.py:60` asserts `"Cork" in item["address"]`), so the evidence exists and is thrown away.
- `home_ops setup` / `profile init` cannot express search intent (`src/home_ops/setup/core.py:30-41` has no `search` section; `wizard.py` contains zero municipality/search references), and `filter_listing` enforces only price and area (`src/home_ops/scraper/filter.py:18-34`). Nothing downstream keeps listings inside the requested town.
- Because the local profile has no `search` block, `SearchConfig` silently defaults `municipality="Cádiz"` (`src/home_ops/models/schema.py:59`). Under that default, province-wide URLs such as `https://www.idealista.com/venta-viviendas/cadiz-provincia/` **pass** validation, because `"cadiz"` is a substring of the normalized URL. The repo's own template sources validate only by accident of the default.
- `scoring.thresholds.*` is the real runtime path (`src/home_ops/config/loader.py`), but `README.md` and `AGENTS.md` document three non-existent flat keys, one of which is the exact command an operator is told to run.
- The versioned template (`config/user_profile.template.yml`) is the only artifact that carries the requested intent; the live, gitignored `user_profile.yml` carries none of it and zero sources.

Severity ordering for a proposal: **(2) > (1) > (7) > (4)/(3) > (5)/(6)**.

---

## per_item_findings

### 1. `sources validate` does not compare scraped sample listings' municipality against `search.municipality`

**verdict: confirmed — defect**

The check is purely textual on the URL. `validate_source` fetches, parses, and then only counts:

- `src/home_ops/cli/sources.py:117-124`
  ```python
  def _municipality_matches(url: str, municipality: str) -> bool:
      if not municipality:
          return True
      parsed = urlparse(url)
      target = _normalize((parsed.hostname or "") + " " + parsed.path + " " + parsed.query)
      muni_norm = _normalize(municipality)
      return muni_norm in target
  ```
- `src/home_ops/cli/sources.py:156-158` — the only municipality gate:
  ```python
  if municipality and not _municipality_matches(url, municipality):
      return False, f"URL does not contain expected municipality '{municipality}'", 0
  ```
- `src/home_ops/cli/sources.py:188-198` — parsed items are used for `len(items)` only; no per-item location comparison, no aggregation, no tolerance.
  ```python
  if not items:
      return False, f"Parsed 0 items from {portal.name} page", 0

  return True, portal.name, len(items)
  ```

The parsers already produce location data, so this is a discarded-evidence defect, not a missing-capability one:

- `tests/test_daft.py:60` — `assert "Cork" in item["address"]`
- `tests/test_habitaclia_urls.py:15` — `"location": {"municipality": "Cádiz", "district": "Centro"}`

The data needed for a real check is present in the parsed output and never inspected.

**Same check, both directions (runtime probe against `_municipality_matches`, no network):**

| municipality | URL | result |
|---|---|---|
| `Chiclana de la Frontera` | `idealista.com/venta-viviendas/chiclana-de-la-frontera-cadiz/` | PASS |
| `Chiclana de la Frontera` | `pisos.com/venta/pisos-chiclana-de-la-frontera/` | PASS |
| `Chiclana de la Frontera` | `tecnocasa.es/venta/piso/andalucia/cadiz/chiclana-de-la-frontera/12345` | PASS |
| `Chiclana de la Frontera` | `habitaclia.com/comprar/viviendas/chiclana_de_la_frontera/s` | **FAIL** (underscore slug: `_normalize` at `:112` replaces only `"-"`) |
| `Chiclana de la Frontera` | `idealista.com/venta-viviendas/cadiz-provincia/` | FAIL (correctly rejected) |
| `Chiclana de la Frontera` | `fotocasa.es/es/comprar/viviendas/12345678/` | **FAIL** (ID-only URL rejected) |
| `Chiclana de la Frontera` | `pisos.com/comprar/piso-1234567/` | **FAIL** (ID-only URL rejected) |
| **`Cádiz` (the `SearchConfig` default)** | `idealista.com/venta-viviendas/cadiz-provincia/` | **PASS** (province-wide source validated as "Cádiz") |
| `Cádiz` | `habitaclia.com/comprar/viviendas/cadiz-provincia/s` | **PASS** |
| `Cádiz` | `fotocasa.es/.../jerez-de-la-frontera/...` | FAIL |

Two consequences, both material:

1. **False negatives (ID-only / non-hyphenated slugs).** `_municipality_matches` cannot resolve a URL whose location is encoded as an opaque ID or a slug using a separator other than `-`. `src/home_ops/scraper/portals.py` contains no per-portal URL builder — only paginators — so the repository itself holds no evidence of the real slug shape for any portal. The failure mode is therefore *unprovable from the repo alone* but structurally certain.
2. **False positives under the default.** Because matching is a raw substring test and the default municipality is `Cádiz`, any Cádiz-province URL satisfies it. The repo's own template sources are exactly this shape.

`tests/test_sources_cli.py:144-153` proves only the false-negative direction (a Madrid profile rejects `https://www.pisos.com/venta/pisos-cadiz/`). No test exercises a province-wide source against a same-named city, an ID-only URL, or a cross-municipality sample.

### 2. The configured municipality is never enforced on scraped listings

**verdict: confirmed — defect (gap in enforcement)**

Two independent omissions:

- **No runtime location filter.** `src/home_ops/scraper/filter.py:18-34` — `filter_listing` returns `True` unless price is missing/over budget or area is missing/under minimum. There is no municipality, province, or postal-code condition, and `filter_listings` adds none.
- **No persistence path.** `src/home_ops/setup/core.py:30-41` — `WIZARD_SECTIONS` contains no `search` entry. `src/home_ops/setup/core.py:222-241` (`build_yaml`) never emits a `search:` key. `grep -n "municipality\|search\|max_price" src/home_ops/setup/wizard.py` returns nothing.

Consequence: `homeops setup` and the wizard **preserve** an existing `search` block (because `build_yaml` starts from the existing document and only overwrites known sections) but can never **create** one. `profile init` does create one, but only by verbatim byte-copy of the template (`src/home_ops/cli/profile.py:60-83`, `content = template_path.read_text(...)`, `_copy_file_atomic(dest, content)`) — it does not ask the operator anything.

Current state on disk: `user_profile.yml` has **no `search` block** and `portal.urls: []`. The requested location survives only in `config/user_profile.template.yml`.

`tests/test_filter.py` covers criteria (e.g. `precio_maximo`) but contains no location case.

### 3. Scoring configuration documented under non-existent keys

**verdict: confirmed — documentation drift (operationally blocking)**

The runtime path is `scoring.thresholds.*`:

- `src/home_ops/models/schema.py:181-203` — `ScoringThresholds` fields: `affordability_high_ratio`, `affordability_medium_ratio`, `m2_large_threshold`, `m2_threshold`, `min_score_to_alert`, `price_median`, `price_over_median_penalty`, `salary_province`, `weights`.
- `src/home_ops/config/loader.py` — `raw["scoring"]["thresholds"]`.
- `config/user_profile.template.yml:33-48` — correctly uses `scoring: thresholds:`.
- `src/home_ops/cli/profile.py:256-284` — `set_profile_value` resolves dotted paths and requires the key to already exist; docs at `:261` state so.

Documented paths that do not exist at runtime:

| Location | Documented key | Reality |
|---|---|---|
| `README.md:115` | `scoring.price_median` | invalid |
| `README.md:213` | `scoring.price_median` (as the worked example for `profile set`) | invalid |
| `README.md:199` | `scoring.min_score_to_alert` | invalid |
| `README.md:200` | `scoring.weights` | invalid |
| `AGENTS.md:24` | `scoring.price_median` | invalid |
| `AGENTS.md:46` | `scoring.price_median` | invalid |

Runtime probe against the versioned template (backup/restore, no file change):

- `scoring.price_median 2100` → `Key 'price_median' not found. Available: ['thresholds']`
- `scoring.thresholds.price_median 2100` → `OK`

Two more silent-drift items surfaced in the same area:

- `config/user_profile.template.yml:37` declares `price_under_median_bonus`, which is **not** a `ScoringThresholds` field. `ScoringThresholds.model_config.get("extra")` is `None`, i.e. pydantic's default `ignore`, so the value is silently discarded — `hasattr(thresholds, "price_under_median_bonus")` is `False` after construction. An operator tuning this key sees no effect and no error.
- The template's `garage:` block is never read by the loader either.

### 4. Scoring documentation describes signals the deterministic scorer does not compute

**verdict: confirmed — documentation drift (misleading, not broken)**

| `README.md:61-67` claim | Actual implementation |
|---|---|
| "Energy certificate — 15% — Energy-efficiency signal" | `src/home_ops/scorer/rules.py:379-384` scores **certificate presence** (`1.0 if listing.energy_certificate else 0.0`). A G-rated and an F-rated listing score identically; grade/rating is never read. |
| "Price fit against your target range" (`:65`) | `src/home_ops/scorer/rules.py:313-341` compares `zone_median_price_per_m2` (or static `price_median`) — a **median**, not a range. `search.max_price` is a hard filter in `scraper/filter.py`, not a scoring dimension. |
| "LLM audit … does not replace the score" (`:85`) | Directionally true (the LLM never *assigns* the score) but incomplete: `src/home_ops/scorer/rules.py:32-50` (`KNOWN_RISK_FLAG_PENALTIES`) is applied at `:258-263`, so LLM-derived risk flags subtract points **inside** the deterministic total. A reader of `:85` would conclude the LLM is purely advisory. |

`README.md:65` also describes a locality dimension whose weight depends on the heuristic zone described in item 5.

### 5. All scraped listings receive the first source's price-history zone

**verdict: confirmed — data-provenance defect, with a co-located environment-dependent test**

`src/home_ops/cli/scan_runner.py:187-189`, after the multi-source collection loop:

```python
from home_ops.analytics import zone_from_portal_url

zone = zone_from_portal_url(portal_urls[0])
```

That single `zone` is then applied to every listing and every observation:

- `src/home_ops/cli/scan_runner.py:202-207` — `db.record_price_observation(..., zone, ...)` for each scraped listing.
- `src/home_ops/cli/scan_runner.py:246-248` — the same `zone` is passed into scoring.

Consumers:

- `src/home_ops/analytics.py:17` — `zone_from_portal_url` picks the **first** path segment containing `-`, excluding segments starting with `http` and the literals `venta-viviendas` / `alquiler-viviendas`. It never compares the result to `search.municipality`, so a district slug or a filter segment (e.g. `precio-max-250000`) can become the zone.
- `src/home_ops/scorer/rules.py:232-234` and `:337-339` → `src/home_ops/analytics.py:149` `zone_median_price_per_m2`.

So a scan across Idealista (Chiclana) + a Cádiz-province source prices every listing against the first source's median. With `price_median` weight at 25% (`config/user_profile.template.yml:46`), this silently biases scoring whenever sources disagree geographically — exactly the case item 4's template demonstrates.

Test coverage: `tests/test_cli.py:326, 407, 438, 469, 513, 591` configure **multiple** `portal_urls`, but every one of them asserts only status strings (`"partial"`, `"error"`, `"empty"`, `"some sources failed"`) and `record_scraping_run` kwargs. **No test asserts that an observation carries its own source's zone.** `tests/test_price_history.py:20-25` covers `zone_from_portal_url` with a single Idealista URL only, and `zone_median_price_per_m2` has no direct test.

The environment-dependent test:

- `tests/test_sources_cli.py:73-80` (`test_validate_source_pass`) resolves the profile from the current working directory via `_resolve_profile_path` rather than a `tmp_path` fixture.
- Observed: `15 passed` for the module with the repo's own `user_profile.yml` (no `search` → default `Cádiz` → `pisos-cadiz` passes).
- Observed: with `HOME_OPS_CONFIG` pointed at a disposable profile declaring `search.municipality: Chiclana de la Frontera`, the same test **failed** at `assert ok is True`. The temporary file was removed; the working tree is unchanged.

The suite's pass/fail for a documented happy path therefore depends on the developer's untracked local profile.

### 6. `config/user_profile.template.yml` versus the initial sources, and the setup flow

**verdict: confirmed — incoherence between template, sources, and docs**

`config/user_profile.template.yml` states one intent and ships sources for a different one:

- `:7` — `municipality: Chiclana de la Frontera`
- `:21-29` — `portal.urls` with province-wide Cádiz portals.

Combined with item 1, the consequence is concrete: **a fresh `profile init` produces a profile whose own `portal.urls` would be rejected by its own `sources add` gate**, because `_municipality_matches(".../cadiz-provincia/", "Chiclana de la Frontera")` is `False`. Conversely, against the *default* `Cádiz` municipality they all pass. The template is self-consistent only by accident of a default it never sets explicitly.

The onboarding narrative in `AGENTS.md:44-51` describes capturing país/municipio/presupuesto/superficie/preferencias and persisting them, but step 2 (`AGENTS.md:46`) offers `profile set` keys — one of which (`scoring.price_median`) is invalid per item 3 — and no step persists `search.municipality` through any working command. `AGENTS.md:21` describes `homeops setup` as the interactive entry point that writes `user_profile.yml` + `.env`; per item 2 it cannot write `search`.

### 7. Live HTML tests that pass vacuously versus genuinely optional ones

**verdict: confirmed — test-correctness defect**

`tests/test_sources_cli.py:84-132` (`test_validate_source_new_portals_temp_profiles`) reads `/tmp/*-live.html` files inside bare conditionals:

```python
pl = Path("/tmp/PL-live.html")
if pl.exists():
    ok, reason, count = validate_source("https://www.nieruchomosci-online.pl/...", fetcher=lambda u: pl.read_text())
    assert ok is True
```

When the file is absent, **no assertion executes and the test reports PASS**. The suite reports `893 passed`, which includes this vacuous pass. `pytest` shows no skip marker, so CI gives no signal.

By contrast the three per-portal live tests do it correctly, and already have versioned fixtures that cover the same parsing:

| Test | Live guard | Versioned fixture used by the same file |
|---|---|---|
| `tests/test_daft.py:49-51` | `pytest.skip` | `tests/fixtures/daft_cork.html` |
| `tests/test_sreality.py:49-51` | `pytest.skip` | `tests/fixtures/sreality_brno.html` |
| `tests/test_nieruchomosci_online.py:49-51` | `pytest.skip` | `tests/fixtures/nieruchomosci_online_krakow.html` |

These three are the **genuinely optional** live probes (network + anti-bot dependent). The `test_sources_cli` block is not optional behaviour — it asserts URL-validation semantics for PL/CZ/IE, which is fully reproducible offline. The `3 skipped` in the baseline run are exactly the three correct `pytest.skip` guards.

---

## affected_files

**Runtime**

- `src/home_ops/cli/sources.py` — textual-only municipality gate; parsed locations discarded (`:117-124`, `:156-158`, `:188-198`).
- `src/home_ops/scraper/filter.py` — no location filter (`:18-34`).
- `src/home_ops/cli/scan_runner.py` — first-source zone applied globally (`:187-189`, `:202-207`, `:246-248`).
- `src/home_ops/analytics.py` — heuristic `zone_from_portal_url` (`:17`), `zone_median_price_per_m2` (`:149`).
- `src/home_ops/scorer/rules.py` — energy = presence only (`:379-384`); LLM flag penalties folded into the deterministic total (`:32-50`, `:258-263`); zone median (`:232-234`, `:337-339`).
- `src/home_ops/setup/core.py` — no `search` wizard section (`:30-41`), no `search` in output (`:222-241`).
- `src/home_ops/setup/wizard.py` — no municipality/search fields.
- `src/home_ops/cli/profile.py` — `set_profile_value` requires existing dotted paths (`:256-284`); `profile init` byte-copies the template (`:60-83`).
- `src/home_ops/config/loader.py` — real `scoring.thresholds` mapping.
- `src/home_ops/models/schema.py` — `ScoringThresholds` (`:181-203`); `SearchConfig.municipality` default `"Cádiz"` (`:59`).
- `src/home_ops/cli/app.py` — `homeops web` defaults `host="127.0.0.1"`, `port=8000` (`:194-203`).
- `src/home_ops/scraper/portals.py` — paginators only; no per-portal URL builder.

**Configuration**

- `config/user_profile.template.yml` — `:7` municipality, `:21-29` province-wide sources, `:33-48` valid scoring, `:37` dead key.
- `user_profile.yml` (untracked/ignored) — no `search`, `portal.urls: []`.

**Documentation**

- `README.md` — `:61-67` scoring table, `:85` LLM claim, `:98` install, `:109`/`:117` "verified" definition, `:115`/`:213` invalid `profile set` keys, `:155` `pip install -e ".[dev]"`, `:172`/`:175` port 8321, `:199-200` invalid scoring keys.
- `AGENTS.md` — `:21` setup claim, `:24`/`:46` invalid `profile set` key, `:28` validate description, `:44-51` onboarding flow.

**Tests**

- `tests/test_sources_cli.py` — `:73-80` cwd-dependent; `:84-132` vacuous live assertions; `:144-153` only false-negative coverage.
- `tests/test_price_history.py` — `:20-25` single-URL zone coverage; no `zone_median_price_per_m2` test.
- `tests/test_cli.py` — multi-`portal_urls` cases assert status only (`:326, 407, 438, 469, 513, 591`).
- `tests/test_filter.py` — no location case.
- `tests/test_daft.py:49-51`, `tests/test_sreality.py:49-51`, `tests/test_nieruchomosci_online.py:49-51` — correct optional guards.
- `tests/fixtures/daft_cork.html`, `tests/fixtures/sreality_brno.html`, `tests/fixtures/nieruchomosci_online_krakow.html` — reusable offline fixtures.

---

## verification_surface

**Baseline (reproducible now):**

```
HOME_OPS_CONFIG= uv run pytest -q          → 893 passed, 3 skipped (50.49s)
uv run ruff check src tests                → All checks passed!
uv run mypy src                            → Success: no issues found in 58 source files
uv run pytest --collect-only -q            → 896 tests collected
```

`README.md:251-253` claims "896 Automated Tests", "84.25% Test Coverage", "Ruff clean; Mypy clean across 58 source files". Test count and the 58-file claim are accurate. (Coverage was not re-measured — `--no-cov` was used for speed.)

**Probes run (all disposable, working tree unchanged):**

- `_municipality_matches` truth table across 15 municipality/URL combinations — see item 1 table.
- `profile set` against a backup copy of the versioned template — invalid vs. valid key paths.
- `ScoringThresholds(**{... 'price_under_median_bonus': 0.2})` — extra key silently dropped.
- `HOME_OPS_CONFIG=<tmp> pytest tests/test_sources_cli.py` — reproduces the item-5 test failure.
- `profile init` code path read (not executed against the live profile).

**Evidence gap:** per-portal real slug shapes are unknown from the repository. `portals.py` has no URL builder, so item 1's ID-only/separator findings are structurally certain but not portal-attributed. Any portal-specific claim requires live `sources validate`, which was deliberately not attempted to respect the anti-bot guardrails in `AGENTS.md:50`.

---

## risks_and_unknowns

1. **No location enforcement end-to-end.** Until item 1/2 are fixed, a "verified" source and a `scan` run provide no guarantee that a listing is in the requested municipality. Listings from a province-wide source are scored, stored, and can be alerted.
2. **Scoring bias is silent.** Item 5 mixes price history across sources. No log line, no test, and no metric surfaces it; it only manifests as a defensibly-looking score.
3. **Docs instruct failing commands.** `AGENTS.md:24` and `README.md:213` name `scoring.price_median` as the example for `profile set`. Following the documented onboarding flow produces a hard error.
4. **Config drift is silent in both directions.** `ScoringThresholds` ignores unknown keys, so dead template keys (`price_under_median_bonus`, `garage:`) are accepted and have no effect. A stricter `extra="forbid"` would turn a silent no-op into a startup error — a design decision for the proposal, not a foregone conclusion.
5. **Test signal is inflated.** One test in `tests/test_sources_cli.py` reports PASS without executing an assertion. Coverage and green-CI numbers currently overstate verification, including `README.md:251-252`.
6. **Unverifiable from the repo.** Whether any real portal serves a municipality purely via ID (which item 1 would reject outright) is unknown and needs live validation under the guardrails.
7. **Secondary documentation gaps found but out of scope.** `README.md:98` (`uv sync`) installs no extras, yet `:172` requires `fastapi`/`uvicorn` (the `web` extra) and `:155` (`pip install -e ".[dev]"`) installs neither `web` nor `tui`, so the documented `uvicorn home_ops.web:app` run and `AGENTS.md:33-34`'s `homeops tui` fail after a documented install. Separately, `README.md:172`/`:175` use port 8321 while `homeops web` defaults to 8000 (`src/home_ops/cli/app.py:194-203`) — the README offers both commands and then points only at 8321.

---

## next_recommended

Ordered by leverage; each is independently proposable.

1. **Make `sources validate` verify content location.** Compare each parsed listing's municipality against `search.municipality` (normalized, accent-insensitive, tolerant of province/district granularity), require a declared minimum share to match, and report the observed distribution in the command output. Requires promoting `Listing.address`/portal location into a typed field the check can use. Update the `verified` definition in `README.md:109`/`:117` and `AGENTS.md:48` to match.
2. **Resolve zone per source.** Derive the zone inside the collection loop from each listing's own source URL (or from its parsed location) and drop the `portal_urls[0]` coupling at `src/home_ops/cli/scan_runner.py:189`. Add a multi-source test asserting per-source zones reach `record_price_observation`.
3. **Replace vacuous live assertions.** Convert the `/tmp/*-live.html` block in `tests/test_sources_cli.py:84-132` to `pytest.skip` + committed sanitized fixtures (reusing the existing `daft_cork` / `sreality_brno` / `nieruchomosci_online_krakow` pattern), and keep the three per-portal live probes as explicitly skipped opt-ins.
4. **Correct the configuration docs.** Fix the five invalid `scoring.*` references in `README.md` and `AGENTS.md` to `scoring.thresholds.*`; remove or implement `price_under_median_bonus` and the `garage:` block in the template; decide `extra="forbid"` vs. tolerant loading.
5. **Align the template's sources with its stated municipality**, and decide whether the wizard should collect `search` intent. If not, `AGENTS.md:21`/`:44-51` must stop implying that `homeops setup` captures location.
6. **Correct the scoring table** (`README.md:61-67`, `:85`) to describe certificate *presence*, a median rather than a range, and LLM risk flags as a score input.
7. **Low-priority doc hygiene:** state the `web`/`tui` extras in the install section, and reconcile the 8000/8321 port guidance.

---

## skill_resolution

- Skill loaded and followed: `/home/arami/.config/opencode/skills/sdd-explore/SKILL.md`.
- Artifact-store mode assumed **hybrid**: filesystem artifact written here plus Engram mirror (`topic_key=sdd/incoherencias-home-ops/explore`, project `home-ops`, `capture_prompt=false`).
- **Deviation to note:** the `sdd-explore` skill names the artifact `exploration.md`; the orchestrator explicitly requested `explore.md`. The orchestrator instruction was followed. The proposal/tasks/spec phases should be told which filename won so they do not look for the other.
- No other skill was applicable; the existing `openspec/` layout (`openspec/changes/archive`) was left untouched and no archive entry was created.

---

## artifacts

| Artifact | Location |
|---|---|
| This exploration report | `openspec/changes/incoherencias-home-ops/explore.md` |
| Engram mirror | project `home-ops`, topic_key `sdd/incoherencias-home-ops/explore`, type `architecture` |

Source and configuration files were **not** modified. Uncommitted working-tree changes that pre-existed this exploration (`README.md`, `pyproject.toml`, `assets/`, `.atl/`) are preserved.
