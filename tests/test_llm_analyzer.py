"""Tests for the LLM description enrichment module."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from home_ops.enricher import llm_analyzer
from home_ops.models.schema import Config, Listing, LlmConfig

if TYPE_CHECKING:
    from home_ops.models.data_storage import DuckDBConnection

_VALID_JSON = (
    '{"estado_reforma": "reformado", "orientacion": "sur", '
    '"ruido_zona": "tranquila", "red_flags_llm": ["urgencia de pago"]}'
)


def _make_config(enabled: bool = True) -> Config:
    """Config with LLM enabled and a fake key/model (no real network)."""
    return Config(
        llm=LlmConfig(
            enabled=enabled,
            model="test/model",
            base_url="http://127.0.0.1:9/v1",
            api_key="sk-test",
        )
    )


def _make_listing(
    db: DuckDBConnection,
    description: str = "Piso reformado, orientación sur, zona tranquila.",
) -> Listing:
    listing = Listing(
        content_hash=f"hash-llm-{description[:8]}",
        address="Calle Test 1",
        url="https://www.idealista.com/inmueble/999/",
        portal="idealista",
        description=description,
    )
    listing.id = db.insert_listing(listing)
    return listing


def _mock_completion(json_body: str) -> MagicMock:
    """Build a litellm.completion mock returning a single-choice response."""
    choice = MagicMock()
    choice.message.content = json_body
    response = MagicMock()
    response.choices = [choice]
    response.usage = MagicMock(prompt_tokens=10, completion_tokens=5)
    return MagicMock(return_value=response)


class TestValidResponse:
    def test_parses_and_persists(self, db: DuckDBConnection) -> None:
        listing = _make_listing(db)
        with patch("litellm.completion", _mock_completion(_VALID_JSON)):
            result = llm_analyzer.analyze_description(listing, _make_config(), db)
        assert result is not None
        assert result.estado_reforma == "reformado"
        assert result.orientacion == "sur"
        assert result.ruido_zona == "tranquila"
        assert result.red_flags_llm == ["urgencia de pago"]
        assert result.model_used == "test/model"
        # Persisted
        rows = db.conn.execute(
            "SELECT estado_reforma, model_used, raw_response "
            "FROM llm_analysis WHERE listing_id = ?",
            [listing.id],
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "reformado"
        assert rows[0][1] == "test/model"
        assert rows[0][2] == _VALID_JSON


class TestMalformedJson:
    def test_fallback_none_but_persists_raw(self, db: DuckDBConnection) -> None:
        """GIVEN a non-JSON completion WHEN analyzed THEN fields None, raw persisted."""
        listing = _make_listing(db)
        raw = "esto no es json"
        with patch("litellm.completion", _mock_completion(raw)):
            result = llm_analyzer.analyze_description(listing, _make_config(), db)
        assert result is not None
        assert result.estado_reforma is None
        assert result.red_flags_llm == []
        rows = db.conn.execute(
            "SELECT raw_response FROM llm_analysis WHERE listing_id = ?",
            [listing.id],
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == raw

    def test_malformed_json_preserves_existing_analysis(self, db: DuckDBConnection) -> None:
        """GIVEN an existing valid row WHEN LLM returns malformed JSON THEN existing row preserved, returns None."""
        listing = _make_listing(db)
        db.conn.execute(
            """
            INSERT INTO llm_analysis (listing_id, estado_reforma, auditoria, model_used, raw_response)
            VALUES (?, 'reformado', 'auditoria previa', 'model-v1', '{"estado_reforma":"reformado"}')
            """,
            [listing.id],
        )
        raw = "esto no es json"
        with patch("litellm.completion", _mock_completion(raw)):
            result = llm_analyzer.analyze_description(listing, _make_config(), db)
        assert result is None
        row = db.conn.execute(
            "SELECT estado_reforma, auditoria, model_used FROM llm_analysis WHERE listing_id = ?",
            [listing.id],
        ).fetchone()
        assert row is not None
        assert row[0] == "reformado"
        assert row[1] == "auditoria previa"
        assert row[2] == "model-v1"

    @pytest.mark.parametrize(
        "invalid_raw",
        [
            "{}",
            '{"ubicacion": 42}',
            '{"ubicacion": "invalida"}',
            '{"estado_reforma": 123}',
            '{"red_flags_llm": "not a list"}',
            '{"red_flags_llm": [123]}',
            '{"red_flags_llm": [null]}',
            '{"red_flags_llm": [{"a": 1}]}',
            '{"red_flags_llm": ["   "]}',
            '{"foo": "bar"}',
            '{"estado_reforma": "   "}',
        ],
    )
    def test_invalid_json_responses_preserve_existing_row_byte_for_byte(
        self, db: DuckDBConnection, invalid_raw: str
    ) -> None:
        """GIVEN an existing valid row WHEN LLM returns invalid JSON dict THEN existing row preserved byte-for-byte and returns None."""
        listing = _make_listing(db)
        db.conn.execute(
            """
            INSERT INTO llm_analysis (listing_id, estado_reforma, auditoria, model_used, raw_response)
            VALUES (?, 'reformado', 'auditoria previa', 'model-v1', '{"estado_reforma":"reformado"}')
            """,
            [listing.id],
        )
        old_row = db.conn.execute(
            "SELECT * FROM llm_analysis WHERE listing_id = ?",
            [listing.id],
        ).fetchone()
        with patch("litellm.completion", _mock_completion(invalid_raw)):
            result = llm_analyzer.analyze_description(listing, _make_config(), db)
        assert result is None
        new_row = db.conn.execute(
            "SELECT * FROM llm_analysis WHERE listing_id = ?",
            [listing.id],
        ).fetchone()
        assert new_row == old_row

    def test_markdown_fenced_json_parsed(self, db: DuckDBConnection) -> None:
        """GIVEN JSON wrapped in markdown fences WHEN analyzed THEN parsed via fence strip."""
        listing = _make_listing(db)
        fenced = f"```json\n{_VALID_JSON}\n```"
        with patch("litellm.completion", _mock_completion(fenced)):
            result = llm_analyzer.analyze_description(listing, _make_config(), db)
        assert result is not None
        assert result.estado_reforma == "reformado"


class TestDisabled:
    def test_disabled_does_not_call_litellm(self, db: DuckDBConnection) -> None:
        listing = _make_listing(db)
        with patch("litellm.completion") as mock_completion:
            result = llm_analyzer.analyze_description(listing, _make_config(enabled=False), db)
        mock_completion.assert_not_called()
        assert result is None

    def test_unconfigured_model_returns_none(self, db: DuckDBConnection) -> None:
        listing = _make_listing(db)
        config = Config(llm=LlmConfig(enabled=True, model="", api_key="", base_url=""))
        with patch("litellm.completion") as mock_completion:
            result = llm_analyzer.analyze_description(listing, config, db)
        mock_completion.assert_not_called()
        assert result is None


class TestNetworkFailure:
    def test_exception_caught_returns_none(self, db: DuckDBConnection) -> None:
        listing = _make_listing(db)
        with patch(
            "litellm.completion",
            side_effect=Exception("connection refused"),
        ):
            result = llm_analyzer.analyze_description(listing, _make_config(), db)
        assert result is None
        # Nothing persisted on network failure (call never completed).
        rows = db.conn.execute(
            "SELECT COUNT(*) FROM llm_analysis WHERE listing_id = ?",
            [listing.id],
        ).fetchone()
        assert rows is not None and rows[0] == 0

    def test_timeout_preserves_existing_analysis(self, db: DuckDBConnection) -> None:
        """GIVEN an existing row WHEN LLM completion times out THEN existing row preserved, returns None."""
        listing = _make_listing(db)
        db.conn.execute(
            """
            INSERT INTO llm_analysis (listing_id, estado_reforma, auditoria, model_used, raw_response)
            VALUES (?, 'reformado', 'auditoria previa', 'model-v1', '{"estado_reforma":"reformado"}')
            """,
            [listing.id],
        )
        with patch("litellm.completion", side_effect=Exception("timeout")):
            result = llm_analyzer.analyze_description(listing, _make_config(), db)
        assert result is None
        row = db.conn.execute(
            "SELECT estado_reforma, auditoria FROM llm_analysis WHERE listing_id = ?",
            [listing.id],
        ).fetchone()
        assert row is not None
        assert row[0] == "reformado"
        assert row[1] == "auditoria previa"


class TestPersistenceFailure:
    def test_persistence_failure_returns_none(self, db: DuckDBConnection) -> None:
        """GIVEN a valid response WHEN db persistence fails THEN returns None."""
        listing = _make_listing(db)
        mock_conn = MagicMock()
        mock_conn.execute.side_effect = Exception("db lock error")
        db._conn = mock_conn
        with patch("litellm.completion", _mock_completion(_VALID_JSON)):
            result = llm_analyzer.analyze_description(listing, _make_config(), db)
        assert result is None


class TestUpsertBehavior:
    def test_valid_response_upserts_and_refreshes_timestamp(self, db: DuckDBConnection) -> None:
        """GIVEN an existing row WHEN valid analysis completed THEN atomic upsert updates row."""
        listing = _make_listing(db)
        db.conn.execute(
            """
            INSERT INTO llm_analysis (listing_id, estado_reforma, auditoria, model_used, raw_response, analyzed_at)
            VALUES (?, 'viejo', NULL, 'old-model', 'old raw', TIMESTAMP '2020-01-01 00:00:00')
            """,
            [listing.id],
        )
        old_row = db.conn.execute(
            "SELECT analyzed_at FROM llm_analysis WHERE listing_id = ?",
            [listing.id],
        ).fetchone()
        assert old_row is not None
        old_ts = old_row[0]

        json_new = '{"estado_reforma": "reformado", "auditoria": "nueva audit"}'
        with patch("litellm.completion", _mock_completion(json_new)):
            result = llm_analyzer.analyze_description(listing, _make_config(), db)
        assert result is not None
        assert result.auditoria == "nueva audit"
        row = db.conn.execute(
            "SELECT estado_reforma, auditoria, model_used, analyzed_at FROM llm_analysis WHERE listing_id = ?",
            [listing.id],
        ).fetchone()
        assert row is not None
        assert row[0] == "reformado"
        assert row[1] == "nueva audit"
        assert row[2] == "test/model"
        assert row[3] > old_ts  # strict increase assertion


class TestEmptyDescription:
    def test_empty_description_returns_none(self, db: DuckDBConnection) -> None:
        listing = _make_listing(db, description="")
        with patch("litellm.completion") as mock_completion:
            result = llm_analyzer.analyze_description(listing, _make_config(), db)
        mock_completion.assert_not_called()
        assert result is None
