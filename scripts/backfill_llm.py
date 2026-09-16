"""Backfill LLM audit for listings missing llm_analysis.

Reuses the production path home_ops.enricher.llm_analyzer.analyze_description
so the exact same prompt/persist/red-flags logic applies. Best-effort:
failures are logged, never raised.
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
logger = logging.getLogger("backfill")


def main() -> None:
    config = load_config()
    db_path = get_db_path()
    rows = None
    with get_connection(db_path) as db:
        # NOTE: no db.init_db() here on purpose — replaying the ALTERs from
        # the WAL after a hard kill corrupted the DB once. Schema already
        # exists in production; opening read-write is enough.
        rows = db.conn.execute(
            """
            SELECT l.id, l.description, l.address, l.url, l.portal
            FROM listings l
            LEFT JOIN llm_analysis a ON a.listing_id = l.id
            WHERE a.listing_id IS NULL
              AND l.description IS NOT NULL
              AND length(l.description) > 0
            ORDER BY l.id ASC
            """
        ).fetchall()
        total = len(rows)
        print(f"[backfill] {total} listings sin análisis LLM.", flush=True)

        if not config.llm.enabled or not config.llm.api_key or not config.llm.model:
            logger.error("LLM disabled/unconfigured — aborting.")
            sys.exit(1)

        ok = fail = 0
        t0 = time.time()
        for i, row in enumerate(rows, 1):
            listing = SimpleNamespace(
                id=row[0],
                description=row[1] or "",
                address=row[2],
                url=row[3],
                portal=row[4],
            )
            try:
                result = llm_analyzer.analyze_description(listing, config, db)
            except Exception as exc:  # noqa: BLE001
                logger.warning("listing %s error: %s", row[0], exc)
                fail += 1
                continue
            if result is not None and result.red_flags_llm:
                print(f"  ! FLAGS listing {row[0]}: {result.red_flags_llm}", flush=True)
            ok += 1 if result is not None else 0
            fail += 1 if result is None else 0
            if i % 50 == 0:
                elapsed = time.time() - t0
                rate = i / elapsed
                eta = (total - i) / rate / 60
                print(f"  [{i}/{total}] ok={ok} fail={fail}  {rate:.1f}/s  ETA {eta:.0f} min", flush=True)
                db.conn.execute("CHECKPOINT;")  # keep WAL small and healthy
            time.sleep(0.3)  # gentle rate-limit

        print(f"[backfill] done: {ok} analizados, {fail} fallos, {time.time() - t0:.0f}s.", flush=True)


if __name__ == "__main__":
    main()
