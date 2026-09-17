"""Re-audit listings whose llm_analysis predates the extended audit prompt.

The first backfill (2026-09-16) used a prompt without the location verdict
(ubicacion/ubicacion_motivo) and the executive summary (auditoria) fields.
This re-runs analyze_description on every listing that has an analysis row
lacking `auditoria` or has no analysis row at all.
Old valid rows are atomically upserted only on successful analysis.
"""

from __future__ import annotations

import logging
import sys
import time
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

from home_ops.config.loader import load_config
from home_ops.enricher import llm_analyzer
from home_ops.models.data_storage import get_connection, get_db_path
from home_ops.models.schema import Listing

if TYPE_CHECKING:
    from home_ops.models.data_storage import DuckDBConnection
    from home_ops.models.schema import Config

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("reaudit")


def get_pending_reaudit_rows(db: DuckDBConnection) -> list[tuple[int, str, str | None, str | None, str | None]]:
    """Retrieve listings requiring initial audit or re-audit for missing auditoria."""
    for col in ("ubicacion", "ubicacion_motivo", "auditoria"):
        db.conn.execute(
            f"ALTER TABLE llm_analysis ADD COLUMN IF NOT EXISTS {col} TEXT;"
        )
    return db.conn.execute(
        """
        SELECT l.id, l.description, l.address, l.url, l.portal
        FROM listings l
        LEFT JOIN llm_analysis a ON a.listing_id = l.id
        WHERE (a.listing_id IS NULL OR a.auditoria IS NULL OR length(trim(a.auditoria)) = 0)
          AND l.description IS NOT NULL AND length(trim(l.description)) > 0
        ORDER BY l.id
        """
    ).fetchall()


def process_reaudit(config: Config, db: DuckDBConnection) -> tuple[int, int]:
    """Process all pending reaudit listings safely without deleting pre-existing rows."""
    rows = get_pending_reaudit_rows(db)
    total = len(rows)
    print(f"[reaudit] {total} análisis viejos a re-auditar.", flush=True)
    if total == 0:
        return 0, 0

    ok = fail = 0
    t0 = time.time()
    for i, row in enumerate(rows, 1):
        listing = SimpleNamespace(
            id=row[0], description=row[1], address=row[2], url=row[3], portal=row[4]
        )
        try:
            result = llm_analyzer.analyze_description(cast(Listing, listing), config, db)
        except Exception as exc:  # noqa: BLE001
            logger.warning("reaudit %s failed: %s", row[0], exc)
            result = None
        if result is not None and result.auditoria and result.auditoria.strip():
            ok += 1
            if result.ubicacion:
                print(
                    f"  [{i}/{total}] id={row[0]} {result.ubicacion} "
                    f"({result.ubicacion_motivo})",
                    flush=True,
                )
            if result.red_flags_llm:
                print(f"  [{i}/{total}] id={row[0]} FLAGS: {result.red_flags_llm}", flush=True)
        else:
            fail += 1
        if i % 25 == 0:
            elapsed = time.time() - t0
            print(f"  ... {i}/{total} ok={ok} fail={fail} {elapsed:.0f}s", flush=True)
            db.conn.execute("CHECKPOINT;")
        time.sleep(0.3)
    print(f"[reaudit] done: {ok} ok, {fail} fail, {time.time() - t0:.0f}s.", flush=True)
    db.conn.execute("CHECKPOINT;")
    return ok, fail


def main() -> None:
    config = load_config()
    if not config.llm.enabled or not config.llm.api_key or not config.llm.model:
        logger.error("LLM disabled/unconfigured — aborting.")
        sys.exit(1)

    with get_connection(get_db_path()) as db:
        process_reaudit(config, db)


if __name__ == "__main__":
    main()
