# Archive Report: incoherencias-home-ops

**Change**: `incoherencias-home-ops`
**Artifact store (per orchestrator preflight)**: `engram`
**Archived on**: 2026-10-05
**Workspace**: `/home/arami/Escritorio/Proyectos/Home-Ops` (repo-local, `main` @ `8ddc301`)
**Mode**: `engram` — no delta-spec filesystem sync, no change-folder move (see "Disclosure: filesystem state not advanced")

---

## Executive Summary

All 9 planned phases and all 37 tasks of `incoherencias-home-ops` are implemented and marked complete in
the local worktree, and the final quality gates are green (`963 passed, 4 skipped, 85% coverage`;
`ruff` clean; `mypy` clean across 59 files). The change closed as **local worktree work only**: no
commits, branches, PRs, push, or publication were performed, per explicit user instruction. Verification
was **never run as an SDD phase** — there is no `verify-report` in either store — so no verification
certificate exists for this cycle, and the archive is a completion record, not a verified-release record.

---

## Final State

### Tasks — 37/37 complete, 0 unfinished

Independently re-counted from the persisted `tasks.md` artifact (rank 1 source):

| Check | Result |
|---|---|
| `- [x]` checkboxes | 37 |
| `- [ ]` checkboxes | 0 |
| Matches native `sdd-status` `taskProgress` | Yes — `total: 37, completed: 37, pending: 0, allComplete: true` |

No checkbox was repaired or rewritten during archive.

### Quality gates (final run, per orchestrator final-state facts and `tasks.md` Phase 9 evidence)

| Command | Result |
|---|---|
| `HOME_OPS_CONFIG= uv run pytest -q` | exit 0 — `963 passed, 4 skipped`, coverage 85% (gate 70%) |
| `uv run ruff check src tests` | exit 0 — `All checks passed!` |
| `uv run mypy src` | exit 0 — `Success: no issues found in 59 source files` |

The launch prompt and `tasks.md` Phase 9 evidence agree on these numbers; no contradiction to rank.
The 68 warnings recorded in `tasks.md` Phase 9 are not a gate failure and were not re-triaged after
that snapshot — their current count is unverified.

### Delivery

| Fact | State |
|---|---|
| Commits created | None |
| Branches created | None |
| Pull requests | None |
| Push / publication | None |
| Review size exception | Authored delta ~1,800+ lines vs. a 400-line budget → genuine `size:exception`, accepted implicitly by executing the whole change as one local worktree slice instead of the forecast 8-PR chain |
| Chain topology | Never resolved; forecast was `Chained PRs recommended: Yes`, `Chain strategy: pending` |

The change is therefore **uncommitted and unpushed**. It lives only as uncommitted worktree
modifications plus the untracked `openspec/changes/incoherencias-home-ops/` folder. Nothing about
delivery was decided by SDD; that remains ordinary repository policy.

### Pre-existing local edits preserved

Untouched as required: `README.md` (only surgical hunks added), `pyproject.toml`, `assets/`, `.atl/`,
`.pi/`. No operator profiles, `.env`, or runtime data rewritten. No DuckDB schema migration, no
historical price-history backfill, no new dependency.

---

## Capabilities Shipped

Four new capability specs, all authored by this change (the proposal declares **no** modified capabilities):

| Capability | Requirements | Substance |
|---|---|---|
| `source-verification` | 3 | `sources validate` verifies parsed listing evidence, not URL text. Canonical rule: `resolved = matched + mismatched`; `verified` iff `resolved > 0 and matched / resolved > 0.5`. Unresolved excluded from the denominator. Zero-resolved / province-only / district-only / exact tie → `ambiguous`; below threshold → `mismatch`; fetch/challenge/parse/empty/zero-item → `error`. |
| `listing-location-provenance` | 2 | Municipality mismatch is filtered before scoring, price observation, or alerting. Per-listing source provenance replaces global `portal.urls[0]` zone attribution, with no DuckDB schema change. |
| `config-and-docs-alignment` | 4 | Canonical `scoring.thresholds.*` keys, municipality-scoped template sources, port 8000 + `[web]`/`[tui]` extras, and accurate scoring semantics (energy presence, zone median, deterministic LLM penalties, non-ES affordability deactivation). |
| `fixture-test-hygiene` | 2 | No vacuous conditional PASS from missing `/tmp/*-live.html`; committed sanitized fixtures; host-profile isolation via `tmp_path`/`HOME_OPS_CONFIG`; genuinely optional network tests use explicit `pytest.skip`. |

Total: **11 requirements, 0 removed, 0 renamed.**

---

## Deviations and Unresolved Findings

### 1. Design interface deviation — accepted implementation, no verification certificate

`tasks.md` Phase 9 (line 144) explicitly flagged this for verification:

> "the design's location interface returns only text while its semantics require explicit-vs-free-form
> distinction; implementation carries that distinction via `LocationEvidence`/`explicit` flag plus a
> private, non-persisted `Listing._explicit_municipality`. **Archive must confirm this deviation is
> acceptable.**"

**Archive does not confirm it.** No `verify-report` exists, and archive has no authority to grant
verification. Recorded as the change's one open design/implementation deviation. Per the orchestrator's
final-state facts the attribute was added deliberately, as a private, non-persisted transport channel
(no DuckDB column, not in the dedup hash) rather than a public `Listing` field — a conservative
resolution of the design gap. It remains formally unreviewed.

### 2. Unreachable "no municipality configured" branch

`SearchConfig` defaults `municipality` to `Cádiz`, so a profile lacking a `search` block still resolves a
target. The "no municipality configured" rejection path is therefore only reachable if
`search.municipality` could be empty, which the validator forbids. Dead-ish branch, recorded not fixed.

### 3. Historical data left inconsistent (deliberate)

Price-history rows written before this change carry incorrect zone attribution and are **not** rewritten —
the original source provenance is unrecoverable. The main spec now guarantees correctness for new
observations only.

### 4. `size:exception` never formally requested

The forecast called for 8 chained PRs; the realised ~1,800 authored lines required an exception. The
exception was never formally requested or granted — it was simply absorbed by the "no branches/commits"
instruction. Recorded as a process gap, not a code defect.

### 5. No live portal validation

Offline fixtures only. Live municipality-scoped URL validity is unproven and explicitly not claimed.
This is consistent with the repo's guardrails (no anti-bot evasion) but leaves the
`source-verification` scenarios unexercised against real portals.

---

## Disclosure: filesystem state not advanced

Because the orchestrator preflight declared `artifactStore: engram`, this phase executed the engram
branch: **no delta specs were synced into `openspec/specs/` and the change folder was not moved to
`openspec/changes/archive/`.** That is a divergence worth stating loudly, because native status
disagrees with the preflight:

- `gentle-ai sdd-status --json` reports `"artifactStore": "openspec"` with
  `"planningHome": { "mode": "repo-local", "path": ".../openspec" }` and lists every artifact as a repo path.
- The preflight block (parent-confirmed, not modifiable by this agent) declares `engram`.

Consequences that remain open:

| Item | Current state |
|---|---|
| `openspec/specs/source-verification/spec.md` | **does not exist** |
| `openspec/specs/listing-location-provenance/spec.md` | **does not exist** |
| `openspec/specs/config-and-docs-alignment/spec.md` | **does not exist** |
| `openspec/specs/fixture-test-hygiene/spec.md` | **does not exist** |
| `openspec/specs/` contents | only `daemon-scheduler/` |
| `openspec/changes/incoherencias-home-ops/` | still an **active** change folder (untracked in git) |
| `gentle-ai sdd-status` for this change | still reports `nextRecommended: archive` |

The 11 shipped requirements therefore live **only** in this change folder and in Engram. If a
filesystem source of truth is wanted, an openspec-mode archive must still sync the four delta specs and
move the folder to `openspec/changes/archive/2026-10-05-incoherencias-home-ops/`. That was not performed
here because the mandated archive-report output path sits *inside* the active change folder
(`openspec/changes/incoherencias-home-ops/archive-report.md`), and moving the folder would have
invalidated it and violated the "no git history" constraint.

---

## Artifact Traceability

### Engram observations read (project `home-ops`)

| Artifact | Observation ID | Topic key |
|---|---|---|
| explore | 2662 | `sdd/incoherencias-home-ops/explore` |
| proposal | 2663 | `sdd/incoherencias-home-ops/proposal` |
| spec | 2664 | `sdd/incoherencias-home-ops/spec` |
| design | 2667 | `sdd/incoherencias-home-ops/design` |
| tasks | 2670 | `sdd/incoherencias-home-ops/tasks` |
| apply-progress | 2674 | `sdd/incoherencias-home-ops/apply-progress` |
| verify-report | **absent** — no observation, and native status reports the locator `<unresolved>` | `sdd/incoherencias-home-ops/verify-report` |

### Filesystem artifacts preserved unmodified

All under `openspec/changes/incoherencias-home-ops/` (byte-untouched; this phase wrote only
`archive-report.md`):

| File | Size | Observed |
|---|---|---|
| `proposal.md` | 10,093 B | present |
| `explore.md` | 25,787 B | present |
| `design.md` | 23,763 B | present |
| `tasks.md` | 24,736 B | present — 37/37 checked, original bytes retained |
| `apply-progress.md` | 5,023 B | present |
| `specs/source-verification/spec.md` | 3,834 B | present (3 requirements) |
| `specs/listing-location-provenance/spec.md` | 3,039 B | present (2 requirements) |
| `specs/config-and-docs-alignment/spec.md` | 4,382 B | present (4 requirements) |
| `specs/fixture-test-hygiene/spec.md` | 2,111 B | present (2 requirements) |
| `verify-report.md` | — | **missing** (never produced) |

No artifact was deleted, truncated, or rewritten. `openspec/config.yaml` declares no `rules.archive`,
so no archive-specific rule applied.

---

## SDD Cycle Status

| Phase | State |
|---|---|
| explore | done |
| proposal | done |
| spec | done (4 capability specs) |
| design | done |
| tasks | done (37 tasks, high 400-line budget risk) |
| apply | done (local worktree, no commits) |
| verify | **never run** |
| archive | closed — record persisted, filesystem state not advanced (see disclosure) |

**This archive is a completion record, not a verified-release record.** Implementation is complete and
gates are green; verification was never performed as an SDD phase. Five findings above are carried
forward unresolved, and the entire change remains uncommitted.