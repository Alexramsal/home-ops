# Home-Ops UI.pen — interpretación test fallida: NO CERRAR en falso
# Último estado verificado manualmente (esta sesión) — no inventar más.
#
# 2026-09-14: el pipeline público (docs/UI-fidelity-notes.md) quedó verificado
# contra DuckDB real: 28 únicos, 170 obs (142 repetidas), 14 con score ≥70,
# mediana 3.618 €/m². Única semana real: 2026-08-31, 150 obs (media 3.865,
# mediana 3.702). Números del dashboard = reales.
#
# Pendiente en el repo (tests fallidos — NO son del dashboard):
# tests/test_cli.py · TestGetDailyAlertCount (3) + test_queued_re_attempt...
# → la función _get_daily_alert_count espera firma antigua (un solo arg conn)
#   pero el refactor c75937e la renombró a _get_daily_alert_count_db y movió
#   el día a _schedule_day_bounds. Fix = añadir alias con firma antigua
#   (conn) + timezone-aware, mantener la DB como fuente canónica.
#   Archivo: src/home_ops/cli/app.py. 345 tests verdes, 4 rotos.
