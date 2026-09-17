# SDD Proposal & Spec: audit-safe-refresh

## Proposal
- **Problem**: `scripts/reaudit_llm.py` deletes `llm_analysis` rows before `analyze_description()` API calls, leading to lost analysis data on API timeouts or failures. Furthermore, `_persist()` swallows DuckDB errors and returns `result` instead of `None`, wrongly counting failed persists as success. `analyze_description` also overwrites valid existing rows even when LLM output is malformed. Finally, `reaudit_llm.py` selection query misses listings that have no `llm_analysis` row at all.
- **Solution**: 
  1. Remove `DELETE FROM llm_analysis` in `reaudit_llm.py`.
  2. Implement atomic UPSERT (`ON CONFLICT (listing_id) DO UPDATE ...`) in `llm_analyzer.py` on valid response.
  3. If LLM call times out, fails, or returns malformed output when an existing analysis row is present, preserve the existing row byte-for-byte and return `None`.
  4. Preserve legacy raw-response persistence for first-time malformed replies (when no prior row exists).
  5. Make `_persist` return boolean status and return `None` from `analyze_description` on persistence failure.
  6. Update `reaudit_llm.py` query to select listings with no `llm_analysis` row or `auditoria IS NULL`.

## Specification & Design
- **`analyze_description` Contract**:
  - Valid response + persistence success -> return `LlmAnalysis`, atomic UPSERT row, refresh `analyzed_at`.
  - Malformed JSON / invalid response + existing row present -> preserve existing row byte-for-byte, return `None`.
  - Malformed JSON + NO existing row present -> persist raw response, return `LlmAnalysis` (if persist succeeds).
  - Timeout / API exception / Persistence failure -> return `None`, log warning.
- **`scripts/reaudit_llm.py` Contract**:
  - Selection query: `LEFT JOIN llm_analysis a ON a.listing_id = l.id WHERE (a.listing_id IS NULL OR a.auditoria IS NULL) AND l.description IS NOT NULL AND length(trim(l.description)) > 0`.
  - Loop: call `analyze_description(listing, config, db)` directly without pre-deleting the row.

## Tasks & Verification Plan
- Tasks:
  1. Write failing regression tests in `tests/test_llm_analyzer.py` and `tests/test_reaudit_llm.py`.
  2. Run pytest (confirm RED).
  3. Update `src/home_ops/enricher/llm_analyzer.py` and `scripts/reaudit_llm.py`.
  4. Run pytest (confirm GREEN).
  5. Run linters & type checks (`ruff check`, `mypy`, `git diff --check`).

## Deferred Risks & Major Weaknesses
1. **First-time Raw Trace Accumulation**: First-time calls with malformed JSON persist unparsed raw responses (`raw_response` stored, structured fields `None`). These rows require subsequent re-audit scripts to populate structured fields once prompt issues are fixed.
2. **Stale Valid Row Retention on Repeated Invalid LLM Outputs**: If an LLM repeatedly yields invalid JSON dicts (e.g. `{}` or unexpected types), existing valid rows are preserved byte-for-byte and never updated until the model returns a valid response.
3. **Web DuckDB Writer Locking**: Concurrent web server requests writing to DuckDB can collide with background processes under lock contention.
4. **Unverified Geography Claims**: Geographic locations from LLM outputs are accepted without cross-referencing official spatial datasets.
5. **Detail Fetching Not Integrated Beyond Idealista**: Extended detail scraping/enrichment pipeline is only active for idealista listings.
6. **165 Short Tecnocasa Descriptions**: 165 Tecnocasa listings carry truncated descriptions limiting enrichment quality.
7. **LLM Flags Not Changing Numeric Score**: `red_flags_llm` extracted by LLM are recorded but do not adjust numerical property scores.

## Evidence & Verification
- **Status**: Recorded SDD unit as verified implementation; larger hardening not complete.
- **Automated Tests**: `pytest -q`: 676 passed (coverage 88.13%), verified independently.
- **Parametric Test Coverage**: Added parametric assertions in `tests/test_llm_analyzer.py` verifying that arbitrary JSON dicts (`{}`, `{"ubicacion": 42}`, `{"ubicacion": "invalida"}`, `{"estado_reforma": 123}`, invalid/whitespace `red_flags_llm`, etc.) preserve existing `llm_analysis` rows byte-for-byte (`SELECT *` equality) and return `None`.
- **Timestamp Increase**: Verified strict timestamp comparison (`new_ts > old_ts`) during atomic upserts.
- **Linting & Typing**: Executed `ruff check` (0 errors) and `mypy` on modified files (0 errors).
