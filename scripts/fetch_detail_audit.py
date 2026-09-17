"""Fetch detail pages for top pisos/fotocasa listings missing descriptions,
persist the scraped description, then LLM-audit them.

The search-result parsers for pisos.com and fotocasa.es do not include the
description field (confirmed live 2026-09-16), so top opportunities scored
>= 70 without a description get their detail page fetched here:

- fotocasa: description lives in the embedded application/json block,
  key realEstateAdDetailEntityV2.description
- pisos:    description lives in <meta name="description"> / og:description

After persisting the description to listings.description the script calls the
standard LLM audit (llm_analyzer.analyze_description) for each listing, so the
full audit (state, orientation, noise, red flags, location verdict, summary)
is produced for listings that previously could not be audited.
"""

from __future__ import annotations

import json
import logging
import re
import sys
import time
from types import SimpleNamespace

import requests

from home_ops.config.loader import load_config
from home_ops.enricher import llm_analyzer
from home_ops.models.data_storage import get_connection, get_db_path

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("fetch_detail")

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    )
}
_BASES = {
    "pisos": "https://www.pisos.com",
    "fotocasa": "https://www.fotocasa.es",
}
_JSON_BLOCK_RE = re.compile(r'<script[^>]*application/json[^>]*>(.*?)</script>', re.S)


def _abs_url(portal: str, url: str) -> str:
    if url.startswith("http"):
        return url
    return _BASES[portal] + url


def _recurse_json(o: object, depth: int = 0) -> str | None:
    if depth > 6:
        return None
    if isinstance(o, dict):
        for k in ("description", "adDescription", "descriptionFull", "longDescription"):
            if k in o and isinstance(o[k], str) and len(o[k].strip()) > 20:
                return o[k].strip()
        for v in o.values():
            hit = _recurse_json(v, depth + 1)
            if hit:
                return hit
    elif isinstance(o, list):
        for v in o[:20]:
            hit = _recurse_json(v, depth + 1)
            if hit:
                return hit
    return None


def extract_fotocasa_desc(html: str) -> str:
    m = _JSON_BLOCK_RE.search(html)
    if not m:
        return ""
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return ""
    hit = _recurse_json(data)
    return hit or ""


def extract_pisos_desc(html: str) -> str:
    for pat in ("name", "property"):
        m = re.search(
            rf'<meta[^>]+(?:name|property)="{pat}:(?:description|og:description)"[^>]+content="([^"]+)"',
            html,
        )
        m2 = re.search(
            r'<meta[^>]+(?:name|property)="(?:description|og:description)"[^>]+content="([^"]+)"',
            html,
        )
        hit = m.group(1).strip() if m else (m2.group(1).strip() if m2 else "")
        if hit:
            return hit
    return ""


def _fetch_desc(portal: str, url: str) -> str:
    full = _abs_url(portal, url)
    r = requests.get(full, headers=_HEADERS, timeout=25)
    r.raise_for_status()
    if portal == "fotocasa":
        return extract_fotocasa_desc(r.text)
    return extract_pisos_desc(r.text)


def main() -> None:
    config = load_config()
    if not config.llm.enabled or not config.llm.api_key or not config.llm.model:
        logger.error("LLM disabled/unconfigured — aborting.")
        sys.exit(1)

    with get_connection(get_db_path()) as db:
        # Migrate llm_analysis schema (idempotent) without full init_db:
        # init_db replays ALTERs from the WAL after a hard kill and corrupted
        # the DB once; these three ALTERs are safe and additive.
        for col in ("ubicacion", "ubicacion_motivo", "auditoria"):
            db.conn.execute(
                f"ALTER TABLE llm_analysis ADD COLUMN IF NOT EXISTS {col} TEXT;"
            )
        rows = db.conn.execute(
            """
            SELECT l.id, l.portal, l.url, l.address
            FROM listings l
            LEFT JOIN llm_analysis a ON a.listing_id = l.id
            WHERE a.listing_id IS NULL
              AND l.portal IN ('pisos', 'fotocasa')
              AND (l.description IS NULL OR length(l.description) = 0)
              AND l.url IS NOT NULL AND l.url != ''
              AND l.score >= 70
            ORDER BY l.score DESC
            """
        ).fetchall()
        total = len(rows)
        print(f"[fetch_detail] {total} top listings sin descripción.", flush=True)
        if total == 0:
            return

        fetched = 0
        for i, row in enumerate(rows, 1):
            listing_id, portal, url, address = row
            try:
                desc = _fetch_desc(portal, url)
            except Exception as exc:  # noqa: BLE001
                logger.warning("fetch %s id=%s failed: %s", portal, listing_id, exc)
                desc = ""
            if desc:
                db.conn.execute(
                    "UPDATE listings SET description = ? WHERE id = ?",
                    [desc, listing_id],
                )
                fetched += 1
                print(f"  [{i}/{total}] id={listing_id} {portal} desc_len={len(desc)}", flush=True)
            else:
                print(f"  [{i}/{total}] id={listing_id} {portal} SIN desc", flush=True)
            time.sleep(0.5)  # gentle rate-limit

        print(f"[fetch_detail] {fetched}/{total} descripciones persistidas.", flush=True)
        db.conn.execute("CHECKPOINT;")

        # Now audit everything with a description that lacks an analysis.
        todo = db.conn.execute(
            """
            SELECT l.id, l.description, l.address, l.url, l.portal
            FROM listings l
            LEFT JOIN llm_analysis a ON a.listing_id = l.id
            WHERE a.listing_id IS NULL
              AND l.description IS NOT NULL AND length(l.description) > 0
            ORDER BY l.id
            """
        ).fetchall()
        print(f"[fetch_detail] auditando {len(todo)} listings…", flush=True)
        ok = fail = 0
        for row in todo:
            listing = SimpleNamespace(
                id=row[0], description=row[1], address=row[2], url=row[3], portal=row[4]
            )
            try:
                result = llm_analyzer.analyze_description(listing, config, db)
            except Exception as exc:  # noqa: BLE001
                logger.warning("audit %s failed: %s", row[0], exc)
                result = None
            if result is not None:
                ok += 1
                if result.ubicacion:
                    print(
                        f"  id={row[0]} ubicacion={result.ubicacion} "
                        f"({result.ubicacion_motivo})",
                        flush=True,
                    )
                if result.red_flags_llm:
                    print(f"  id={row[0]} FLAGS: {result.red_flags_llm}", flush=True)
            else:
                fail += 1
            time.sleep(0.3)
        print(f"[fetch_detail] auditoría: {ok} ok, {fail} fail.", flush=True)
        db.conn.execute("CHECKPOINT;")


if __name__ == "__main__":
    main()
