"""Tests for the reaudit script."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

from home_ops.enricher.llm_analyzer import LlmAnalysis
from home_ops.models.schema import Config, Listing, LlmConfig
from scripts import reaudit_llm

if TYPE_CHECKING:
    from home_ops.models.data_storage import DuckDBConnection


def _make_config() -> Config:
    return Config(
        llm=LlmConfig(
            enabled=True,
            model="test/model",
            base_url="http://127.0.0.1:9/v1",
            api_key="sk-test",
        )
    )


def test_reaudit_selection_includes_missing_and_legacy_listings(db: DuckDBConnection) -> None:
    """Selection query must include listings without llm_analysis and listings with auditoria IS NULL."""
    # Listing 1: no llm_analysis row
    l1 = Listing(
        content_hash="hash-reaudit-1",
        address="Calle 1",
        url="https://idealista.com/1",
        portal="idealista",
        description="Piso luminoso en centro",
    )
    l1.id = db.insert_listing(l1)

    # Listing 2: llm_analysis row with auditoria IS NULL
    l2 = Listing(
        content_hash="hash-reaudit-2",
        address="Calle 2",
        url="https://idealista.com/2",
        portal="idealista",
        description="Piso a reformar",
    )
    l2.id = db.insert_listing(l2)
    db.conn.execute(
        "INSERT INTO llm_analysis (listing_id, estado_reforma) VALUES (?, 'a reformar')",
        [l2.id],
    )

    # Listing 3: llm_analysis row with valid auditoria (not pending)
    l3 = Listing(
        content_hash="hash-reaudit-3",
        address="Calle 3",
        url="https://idealista.com/3",
        portal="idealista",
        description="Piso en buen estado",
    )
    l3.id = db.insert_listing(l3)
    db.conn.execute(
        "INSERT INTO llm_analysis (listing_id, auditoria) VALUES (?, 'Auditoria completa')",
        [l3.id],
    )

    # Listing 4: empty description
    l4 = Listing(
        content_hash="hash-reaudit-4",
        address="Calle 4",
        url="https://idealista.com/4",
        portal="idealista",
        description="",
    )
    l4.id = db.insert_listing(l4)

    # Listing 5: whitespace auditoria
    l5 = Listing(
        content_hash="hash-reaudit-5",
        address="Calle 5",
        url="https://idealista.com/5",
        portal="idealista",
        description="Piso con auditoria vacia",
    )
    l5.id = db.insert_listing(l5)
    db.conn.execute(
        "INSERT INTO llm_analysis (listing_id, auditoria) VALUES (?, '   ')",
        [l5.id],
    )

    rows = reaudit_llm.get_pending_reaudit_rows(db)
    selected_ids = [r[0] for r in rows]

    assert l1.id in selected_ids
    assert l2.id in selected_ids
    assert l3.id not in selected_ids
    assert l4.id not in selected_ids
    assert l5.id in selected_ids


def test_reaudit_does_not_delete_old_row_on_llm_failure(db: DuckDBConnection) -> None:
    """When analyze_description fails during reaudit, existing row must not be deleted."""
    listing_item = Listing(
        content_hash="hash-reaudit-fail",
        address="Calle Fail",
        url="https://idealista.com/fail",
        portal="idealista",
        description="Piso con vicios ocultos",
    )
    listing_item.id = db.insert_listing(listing_item)
    db.conn.execute(
        "INSERT INTO llm_analysis (listing_id, estado_reforma) VALUES (?, 'vicios')",
        [listing_item.id],
    )

    # Mock analyze_description to return None (simulating failure/timeout)
    with patch("home_ops.enricher.llm_analyzer.analyze_description", return_value=None):
        reaudit_llm.process_reaudit(config=_make_config(), db=db)

    row = db.conn.execute(
        "SELECT estado_reforma FROM llm_analysis WHERE listing_id = ?",
        [listing_item.id],
    ).fetchone()
    assert row is not None
    assert row[0] == "vicios"


def test_reaudit_first_time_malformed_counts_fail_never_ok(db: DuckDBConnection) -> None:
    """First-time raw malformed traces remain persisted but count fail, never ok."""
    listing = Listing(
        content_hash="hash-reaudit-malformed",
        address="Calle Malformed",
        url="https://idealista.com/malformed",
        portal="idealista",
        description="Piso descripcion",
    )
    listing_id = db.insert_listing(listing)
    assert listing_id is not None
    fake = LlmAnalysis(listing_id=listing_id, model_used="test", auditoria=None)
    with patch("home_ops.enricher.llm_analyzer.analyze_description", return_value=fake):
        ok, fail = reaudit_llm.process_reaudit(config=_make_config(), db=db)
    assert ok == 0
    assert fail == 1
