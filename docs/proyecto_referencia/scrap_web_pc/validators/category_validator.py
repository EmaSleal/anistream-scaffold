"""
validators/category_validator.py — Two-layer category validation cascade.

Classes:
    ValidationResult  — enum: VALID, UNCERTAIN, DISCARD, UNAVAILABLE
    KeywordValidator  — fast keyword-match layer (no I/O)
    OllamaValidator   — LLM disambiguation layer (HTTP to Ollama)
    CategoryValidator — facade that chains both layers and logs discards
"""
from __future__ import annotations

import logging
from enum import Enum

import requests
import requests.exceptions

import config
from validators.keywords import CATEGORY_KEYWORDS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result enum
# ---------------------------------------------------------------------------

class ValidationResult(Enum):
    VALID       = "valid"
    UNCERTAIN   = "uncertain"
    DISCARD     = "discard"
    UNAVAILABLE = "unavailable"


# ---------------------------------------------------------------------------
# KeywordValidator
# ---------------------------------------------------------------------------

class KeywordValidator:
    """Returns VALID if the lowercase canonical_key contains at least one
    keyword for the given category, UNCERTAIN otherwise."""

    def run(self, canonical_key: str, category: str) -> ValidationResult:
        keywords = CATEGORY_KEYWORDS.get(category)
        if not keywords:
            return ValidationResult.UNCERTAIN
        name_lower = canonical_key.lower()
        for kw in keywords:
            if kw in name_lower:
                return ValidationResult.VALID
        return ValidationResult.UNCERTAIN


# ---------------------------------------------------------------------------
# OllamaValidator
# ---------------------------------------------------------------------------

class OllamaValidator:
    """Sends a YES/NO prompt to Ollama and interprets the response.

    Returns:
        VALID       — Ollama answered YES
        DISCARD     — Ollama answered NO or both attempts yielded malformed text
        UNAVAILABLE — Connection error or timeout (no retry)
    """

    def __init__(self, url: str, model: str, timeout: float = 5.0) -> None:
        self._url = url.rstrip("/") + "/api/generate"
        self._model = model
        self._timeout = timeout

    def run(self, canonical_key: str, category: str) -> ValidationResult:
        prompt = (
            f"Does '{canonical_key}' belong to the '{category}' hardware category? "
            "Answer YES or NO only."
        )
        payload = {"model": self._model, "prompt": prompt, "stream": False}

        try:
            result = self._call_once(payload)
            if result is not None:
                return result
            # First call returned malformed — retry once
            result = self._call_once(payload)
            if result is not None:
                return result
            return ValidationResult.DISCARD
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            return ValidationResult.UNAVAILABLE

    def _call_once(self, payload: dict) -> ValidationResult | None:
        """Make a single POST. Returns VALID/DISCARD on parseable response,
        None on malformed. Propagates ConnectionError / Timeout to caller."""
        resp = requests.post(self._url, json=payload, timeout=self._timeout)
        text = resp.json().get("response", "").strip().upper()
        if text.startswith("YES"):
            return ValidationResult.VALID
        if text.startswith("NO"):
            return ValidationResult.DISCARD
        return None  # malformed


# ---------------------------------------------------------------------------
# CategoryValidator
# ---------------------------------------------------------------------------

class CategoryValidator:
    """Cascade facade: KeywordValidator → OllamaValidator.

    Decision table:
        Keyword VALID                    → VALID  (Ollama never called)
        Keyword UNCERTAIN + Ollama VALID → VALID
        Keyword UNCERTAIN + Ollama DISCARD      → DISCARD (log llm_reject)
        Keyword UNCERTAIN + Ollama UNAVAILABLE  → VALID   (log llm_unavailable, fail-open)

    Never raises exceptions to the caller.
    """

    def __init__(
        self,
        keyword_validator: KeywordValidator | None = None,
        ollama_validator: OllamaValidator | None = None,
    ) -> None:
        self._kw = keyword_validator or KeywordValidator()
        self._ol = ollama_validator or OllamaValidator(
            url=config.OLLAMA_URL,
            model=config.OLLAMA_MODEL,
            timeout=config.OLLAMA_TIMEOUT,
        )

    def run(self, canonical_key: str, category: str) -> ValidationResult:
        try:
            kw_result = self._kw.run(canonical_key, category)

            if kw_result == ValidationResult.VALID:
                return ValidationResult.VALID

            # UNCERTAIN — escalate to Ollama
            ol_result = self._ol.run(canonical_key, category)

            if ol_result == ValidationResult.VALID:
                return ValidationResult.VALID

            if ol_result == ValidationResult.UNAVAILABLE:
                logger.warning(
                    'llm_unavailable product="%s" category="%s" — passing through',
                    canonical_key,
                    category,
                )
                return ValidationResult.VALID

            logger.warning(
                'DISCARDED product="%s" category="%s" reason=llm_reject',
                canonical_key,
                category,
            )
            return ValidationResult.DISCARD

        except Exception:
            logger.exception(
                "CategoryValidator: unexpected error for product=%r category=%r — discarding",
                canonical_key,
                category,
            )
            return ValidationResult.DISCARD
