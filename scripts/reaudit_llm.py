"""Re-audit listings whose llm_analysis predates the extended audit prompt.

The first backfill (2026-09-16) used a prompt without the location verdict
(ubicacion/ubicacion_motivo) and the executive summary (auditoria) fields.
This re-runs analyze_description on every listing that has an analysis row
but no `auditoria`, refreshing state/orientation/noise/flags AND adding the
new fields. Old rows are deleted first (PK conflict), then re-inserted.
"""

from __future__ import annotations

import logging
import sys
import time
from types import SimpleNamespace

from home_ops.config.loader import load_config
from home_ops.enricher import llm_analyzer
from home_ops.models.data_storage import get_connection, get_db_path

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("reaudit")


def main() -> None:
    config = load_config()
    if not config.llm.enabled or not config.llm.api_key or not config.llm.model:
        logger.error("LLM disabled/unconfigured — aborting.")
        sys.exit(1)

    with get_connection(get_db_path()) as db:
        for col in ("ubicacion", "ubicacion_motivo", "auditoria"):
            db.conn.execute(
                f"ALTER TABLE llm_analysis ADD COLUMN IF NOT EXISTS {col} TEXT;"
            )
        rows = db.conn.execute(
            """
            SELECT l.id, l.description, l.address, l.url, l.portal
            FROM llm_analysis a
            JOIN listings l ON l.id = a.listing_id
            WHERE a.auditoria IS NULL
              AND l.description IS NOT NULL AND length(l.description) > 0
            ORDER BY l.id
            """
        ).fetchall()
        total = len(rows)
        print(f"[reaudit] {total} análisis viejos a re-auditar.", flush=True)
        if total == 0:
            return

        ok = fail = 0
        t0 = time.time()
        for i, row in enumerate(rows, 1):
            listing = SimpleNamespace(
                id=row[0], description=row[1], address=row[2], url=row[3], portal=row[4]
            )
            try:
                db.conn.execute(
                    "DELETE FROM llm_analysis WHERE listing_id = ?", [row[0]]
                )
                result = llm_analyzer.analyze_description(listing, config, db)
            except Exception as exc:  # noqa: BLE001
                logger.warning("reaudit %s failed: %s", row[0], exc)
                result = None
            if result is not None:
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


if __name__ == "__main__":
    main()
