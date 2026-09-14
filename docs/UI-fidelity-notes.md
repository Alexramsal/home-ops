# UI.pen — Fidelity verification: 2026-09-14 fix-pass results

DB facts referenced: `data/home_ops.duckdb`, verified 2026-09-14 (see engram session
`home-ops-public-results-20260914`).

## Data checks (honest numbers, no invention)

| Quality gate | Real (from DuckDB) | In design |
|---|---|---|
| Unique listings | 28 | 28 ✓ |
| Price observations | 170 | 170 ✓ |
| Repeated observations (after first sighting) | 142 | 142 ✓ |
| Unique listings scored | 28 | 28 ✓ |
| Listings with score ≥ 70 | 14 | 14 ✓ |
| **Median price per m² (current listings)** | **3.618 €/m²** | **3.618 €/m²** ✓ |
| Scam-risk penalties applied (policy, not confirmed fraud) | 28 × 10 | 28 ✓ |
| Latest data date | 2026-09-01 | 2026-09-01 ✓ |
| Price history: only one week (2026-08-31), 150 obs, mean 3.865 €/m², median 3.702 €/m² | single week, no trend | ✓ |

## Ranked opportunities — real rows used (verified, replaced the invented examples)

Table displays 4 rows. Media/mediana reference: **3.618 €/m²**.

| # | Listing | Price | m² | €/m² | vs mediana | Score | Risk | HITL status |
|---|---------|-------|-----|------|-----------|-------|------|-------------|
| 1 | Dúplex en Plaza de Toros - Ayuntamiento, El Puerto de Santa María | 230.000 € | 130 | 1.769 | -51% | 87 | 10 | Pendiente Auditoría |
| 2 | Piso en Casco Historico - Ribera del Marisco, El Puerto de Santa María | 260.000 € | 110 | 2.364 | -35% | 74 | 10 | Pendiente Auditoría |
| 3 | Piso en Centro, Jerez de la Frontera | 675.000 € | 371 | 1.819 | -50% | 70 | 10 | Pendiente Auditoría |
| 4 | Piso en Plaza Topete - Centro Historico, Plaza de España, Cádiz | 595.000 € | 212 | 2.807 | -22% | 70 | 10 | Pendiente Auditoría |

**Verification per row (median 3.618 €/m²):**
- Row 1: 1769/3618 − 1 = −51,1 % → label `-51% vs mediana` ✅
- Row 2: 1819/3618 − 1 ≈ −49,7 % → label `-50% vs mediana` ✅
- Row 3: 2807/3618 − 1 ≈ −22,4 % → label `-22% vs mediana` ✅
- Row 4 (was -51% before fix): 2364/3618 − 1 ≈ −34,7 % → label `-35% vs mediana` ✅ (this was the corrected cell)

All four vs-mediana labels are now **within rounding (±0,4 pp) of the true value**.
Success criterion: within ±1 pp — PASSED.

## KPI card numbers (main page)

| Stat | Value |
|---|---|
| Anuncios analizados | 28 |
| Observaciones de precio | 170 |
| Observaciones repetidas (seguimiento) | 142 |
| Mediana actual | 3.618 €/m² |
| Oportunidades (score ≥ 70) | 14 |
| Penalización de riesgo (política) | 28 |

All six = real DuckDB numbers, no invented metrics.

## Explicitly NOT claimed in the design (by design — honest)

- NO "28 estafas confirmadas" (only risk-penalty methodology on all 28).
- NO seriede tiempo de más de una semana (design states one week insufficient).
- NO mapa ni gráficas falsas.
- NO métricas de rendimiento del pipeline inventadas (score/derivados son de una única semana real).

## Fidelity notes — live check in UI.pen

Used Pencil MCP read-only Get walk + Print of the four table rows; verified the literal
text nodes contain the rows above unused claims (banned words absent).

## Artifacts

- `UI.pen` — Pencil source with the corrected dashboard (git-tracked, +1 public dashboard).
- `docs/UI-fidelity-notes.md` — this file.
- Commit: `docs(portfolio): public results dashboard design...` fbdf686 (pushed by aram_os/9canary).
