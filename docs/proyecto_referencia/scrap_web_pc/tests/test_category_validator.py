"""
tests/test_category_validator.py — Unit tests for validators/ package.

Covers (T6) KeywordValidator pure logic,
       (T7) OllamaValidator with mocked requests,
       (T8) CategoryValidator cascade + Orchestrator integration.
"""
from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest
import requests.exceptions

import config
from validators.category_validator import (
    CategoryValidator,
    KeywordValidator,
    OllamaValidator,
    ValidationResult,
)
from validators.keywords import CATEGORY_KEYWORDS


# ===========================================================================
# T6 — KeywordValidator (pure, no mocks)
# ===========================================================================

class TestKeywordValidator:

    def setup_method(self):
        self.kv = KeywordValidator()

    def test_keyword_hit_returns_valid(self):
        result = self.kv.run("MSI RTX 4070 Gaming X", "GPUs")
        assert result == ValidationResult.VALID

    def test_no_keyword_returns_uncertain(self):
        result = self.kv.run("Alfombra decorativa 2x3m", "GPUs")
        assert result == ValidationResult.UNCERTAIN

    def test_case_insensitive(self):
        result = self.kv.run("Kingston DDR5 32GB", "RAM")
        assert result == ValidationResult.VALID

    def test_unknown_category_returns_uncertain(self):
        result = self.kv.run("Some Product", "unknown_cat")
        assert result == ValidationResult.UNCERTAIN

    def test_all_configured_categories_have_keywords(self):
        """Every category in config.CATEGORIES must have an entry in CATEGORY_KEYWORDS."""
        missing = [c for c in config.CATEGORIES if c not in CATEGORY_KEYWORDS]
        assert not missing, f"Categories missing from CATEGORY_KEYWORDS: {missing}"


# ===========================================================================
# T7 — OllamaValidator (requests.post mocked)
# ===========================================================================

def _make_response(text: str) -> MagicMock:
    """Helper: build a mock requests.Response whose .json() returns {response: text}."""
    r = MagicMock()
    r.json.return_value = {"response": text}
    return r


class TestOllamaValidator:

    def setup_method(self):
        self.ov = OllamaValidator(url="http://localhost:11434", model="phi4-mini")

    @patch("requests.post")
    def test_ollama_yes_returns_valid(self, mock_post):
        mock_post.return_value = _make_response("YES")
        result = self.ov.run("EVGA 650W Gold PSU", "Fuentes de poder")
        assert result == ValidationResult.VALID

    @patch("requests.post")
    def test_ollama_no_returns_discard(self, mock_post):
        mock_post.return_value = _make_response("NO")
        result = self.ov.run("Alfombra decorativa", "GPUs")
        assert result == ValidationResult.DISCARD

    @patch("requests.post")
    def test_ollama_malformed_then_valid(self, mock_post):
        mock_post.side_effect = [
            _make_response("Sure thing!"),
            _make_response("YES"),
        ]
        result = self.ov.run("Some Product", "GPUs")
        assert result == ValidationResult.VALID
        assert mock_post.call_count == 2

    @patch("requests.post")
    def test_ollama_malformed_twice_returns_discard(self, mock_post):
        mock_post.side_effect = [
            _make_response("Definitely!"),
            _make_response("Absolutely!"),
        ]
        result = self.ov.run("Some Product", "GPUs")
        assert result == ValidationResult.DISCARD
        assert mock_post.call_count == 2

    @patch("requests.post")
    def test_ollama_connection_error_returns_unavailable(self, mock_post):
        mock_post.side_effect = requests.exceptions.ConnectionError("refused")
        result = self.ov.run("Any Product", "GPUs")
        assert result == ValidationResult.UNAVAILABLE
        assert mock_post.call_count == 1

    @patch("requests.post")
    def test_ollama_timeout_returns_unavailable(self, mock_post):
        mock_post.side_effect = requests.exceptions.Timeout("timed out")
        result = self.ov.run("Any Product", "GPUs")
        assert result == ValidationResult.UNAVAILABLE
        assert mock_post.call_count == 1


# ===========================================================================
# T8a — CategoryValidator cascade (injected fakes)
# ===========================================================================

def _fake_kw(result: ValidationResult) -> KeywordValidator:
    kv = MagicMock(spec=KeywordValidator)
    kv.run.return_value = result
    return kv


def _fake_ol(result: ValidationResult) -> OllamaValidator:
    ov = MagicMock(spec=OllamaValidator)
    ov.run.return_value = result
    return ov


class TestCategoryValidatorCascade:

    def test_cascade_keyword_valid_skips_ollama(self):
        kv = _fake_kw(ValidationResult.VALID)
        ov = _fake_ol(ValidationResult.DISCARD)  # would discard if called
        cv = CategoryValidator(keyword_validator=kv, ollama_validator=ov)
        result = cv.run("MSI RTX 4070", "GPUs")
        assert result == ValidationResult.VALID
        ov.run.assert_not_called()

    def test_cascade_uncertain_ollama_valid(self):
        kv = _fake_kw(ValidationResult.UNCERTAIN)
        ov = _fake_ol(ValidationResult.VALID)
        cv = CategoryValidator(keyword_validator=kv, ollama_validator=ov)
        result = cv.run("Some Product", "GPUs")
        assert result == ValidationResult.VALID
        ov.run.assert_called_once()

    def test_cascade_uncertain_ollama_discard_llm_reject(self, caplog):
        import logging
        kv = _fake_kw(ValidationResult.UNCERTAIN)
        ov = _fake_ol(ValidationResult.DISCARD)
        cv = CategoryValidator(keyword_validator=kv, ollama_validator=ov)
        with caplog.at_level(logging.WARNING):
            result = cv.run("Alfombra decorativa", "GPUs")
        assert result == ValidationResult.DISCARD
        assert "llm_reject" in caplog.text

    def test_cascade_uncertain_ollama_unavailable(self, caplog):
        import logging
        kv = _fake_kw(ValidationResult.UNCERTAIN)
        ov = _fake_ol(ValidationResult.UNAVAILABLE)
        cv = CategoryValidator(keyword_validator=kv, ollama_validator=ov)
        with caplog.at_level(logging.WARNING):
            result = cv.run("Alfombra decorativa", "GPUs")
        assert result == ValidationResult.DISCARD
        assert "llm_unavailable" in caplog.text

    def test_no_exception_propagates_on_unavailable(self):
        kv = _fake_kw(ValidationResult.UNCERTAIN)
        ov = _fake_ol(ValidationResult.UNAVAILABLE)
        cv = CategoryValidator(keyword_validator=kv, ollama_validator=ov)
        # Must not raise
        result = cv.run("Any Product", "GPUs")
        assert result == ValidationResult.DISCARD


# ===========================================================================
# T8b — Orchestrator integration (validator injected)
# ===========================================================================

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from config import StoreConfig
from orchestrator import Orchestrator
from scrapers.base import RawProduct
from storage import Storage


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _make_store(store_id: str = "teststore") -> StoreConfig:
    return StoreConfig(
        store_id=store_id,
        store_name=store_id.title(),
        base_url=f"https://{store_id}.example.com",
        scraper_class="scrapers.woocommerce.WooCommerceScraper",
        category_map={"GPUs": "tarjetas-de-video"},
        enabled=True,
    )


@pytest.fixture
def mem_storage() -> Storage:
    s = Storage(":memory:")
    s.init_schema()
    return s


def _gpu_raw_product(store_id: str = "teststore") -> RawProduct:
    return RawProduct(
        store_id=store_id,
        raw_name="Tarjeta de Video ASUS TUF RTX 4070 Ti 16GB",
        price_str="₡950,000",
        url="https://test.example.com/rtx4070",
        in_stock=True,
        category="GPUs",
        scraped_at=_now(),
    )


def _make_orch(mem_storage, validator, store_id="teststore"):
    stores = {store_id: _make_store(store_id)}
    mock_scraper = MagicMock()

    def _fake_scrape(category):
        if category == "GPUs":
            return [_gpu_raw_product(store_id)]
        return []

    mock_scraper.scrape.side_effect = _fake_scrape
    with patch("orchestrator._resolve_scraper_class") as mock_resolve:
        mock_resolve.return_value = MagicMock(return_value=mock_scraper)
        orch = Orchestrator(storage=mem_storage, stores=stores, validator=validator)
        summary = orch.run_scrape()
    return summary


def test_validator_discard_skips_upsert(mem_storage):
    """When validator returns DISCARD, upsert_product must not be called."""
    mock_validator = MagicMock(spec=CategoryValidator)
    mock_validator.run.return_value = ValidationResult.DISCARD

    # Wrap storage to spy on upsert_product
    original_upsert = mem_storage.upsert_product
    upsert_calls = []

    def spy_upsert(canonical):
        upsert_calls.append(canonical)
        return original_upsert(canonical)

    mem_storage.upsert_product = spy_upsert

    summary = _make_orch(mem_storage, mock_validator)
    assert len(upsert_calls) == 0
    assert summary["total_products"] == 0


def test_validator_valid_calls_upsert(mem_storage):
    """When validator returns VALID, upsert_product must be called."""
    mock_validator = MagicMock(spec=CategoryValidator)
    mock_validator.run.return_value = ValidationResult.VALID

    upsert_calls = []
    original_upsert = mem_storage.upsert_product

    def spy_upsert(canonical):
        upsert_calls.append(canonical)
        return original_upsert(canonical)

    mem_storage.upsert_product = spy_upsert

    summary = _make_orch(mem_storage, mock_validator)
    assert len(upsert_calls) >= 1
    assert summary["total_products"] >= 1


def test_ollama_down_does_not_crash_scrape_run(mem_storage):
    """When validator always returns DISCARD, run_scrape completes without error."""
    mock_validator = MagicMock(spec=CategoryValidator)
    mock_validator.run.return_value = ValidationResult.DISCARD

    summary = _make_orch(mem_storage, mock_validator)
    assert summary["total_products"] == 0
    assert summary["stores_failed"] == 0
