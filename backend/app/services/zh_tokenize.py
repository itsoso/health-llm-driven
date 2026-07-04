"""Chinese word segmentation for System KB v2 retrieval.

Why this exists
---------------
The serving KB's FTS leg runs PostgreSQL ``to_tsvector("simple", ...)`` /
``websearch_to_tsquery("simple", ...)`` and the lexical leg runs a char-bigram
BM25. Neither splits Chinese into *words*, so a multi-word query like
``"高血压 运动建议"`` is near-dead on the FTS leg (the whole clause becomes one
opaque token) and noisy on the bigram leg. Feeding jieba word tokens
(space-joined) into both the indexed text and the query makes the ``"simple"``
config behave like a real word tokenizer — no PG extension required.

Contract
--------
* ``seg_text(text) -> str`` — jieba word tokens, space-joined, lowercased-preserving.
  Empty / whitespace input returns "".
* Lazy-init + thread-safe: the userdict (drug names) is loaded exactly once,
  guarded by a lock. jieba's own default-dict build is already process-safe.
* **Fail-loud**: jieba is a hard requirement (see requirements.txt). If it cannot
  be imported, the FIRST call raises ``ZhTokenizerUnavailable`` — there is NO
  silent fallback to the broken (unsegmented) behavior, because a silent fallback
  would make retrieval quietly worse with no signal. Call sites that want to
  detect the problem at startup (not per-query) call
  ``check_zh_tokenizer_available()``.

Drug-name userdict
------------------
Drug names must never be split (``司美格鲁肽`` must stay one token, not
``司美 / 格鲁 / 肽``). We seed jieba's userdict from the drug-name aliases that
actually exist in this codebase — ``ddi.DRUG_ALIASES`` (the safety engine's
class→alias map) plus the ``originator_drugs`` originator table. Only Chinese
terms of length >= 3 are added (2-char fragments like ``普利`` / ``沙坦`` are
substrings, not full drug names, and would fight jieba's segmentation).
"""

from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_initialized = False
_jieba = None  # module handle, set on successful init


class ZhTokenizerUnavailable(RuntimeError):
    """Raised when jieba (a hard dependency) cannot be imported/initialized."""


def _collect_drug_terms() -> list[str]:
    """Chinese drug names (len>=3) from the existing drug-name sources.

    Kept defensive: a missing/renamed source degrades the *userdict* only (jieba
    still segments with its default dict), so import errors here are logged, not
    raised — the hard failure is reserved for jieba itself being absent.
    """
    terms: set[str] = set()

    def _add(value: object) -> None:
        if not isinstance(value, str):
            return
        term = value.strip()
        # Chinese, length>=3: real drug names, not ambiguous 2-char substrings.
        if len(term) >= 3 and all("一" <= ch <= "鿿" for ch in term):
            terms.add(term)

    try:
        from app.agents.safety_guardian.rules.ddi import DRUG_ALIASES

        for aliases in DRUG_ALIASES.values():
            for alias in aliases:
                _add(alias)
    except Exception as exc:  # noqa: BLE001 - userdict is best-effort, jieba is not
        logger.warning("[zh_tokenize] DDI drug aliases unavailable for userdict: %s", exc)

    try:
        from app.services.originator_drugs import _ALIASES, _TABLE

        for key, row in _TABLE.items():
            _add(key)
            _add(row.get("generic"))
            _add(row.get("brand"))
        for alias in _ALIASES:
            _add(alias)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[zh_tokenize] originator drug table unavailable for userdict: %s", exc)

    return sorted(terms)


def _ensure_initialized() -> None:
    global _initialized, _jieba
    if _initialized:
        return
    with _lock:
        if _initialized:  # re-check under lock
            return
        try:
            import jieba  # local import so the module loads even when reporting the error
        except Exception as exc:  # noqa: BLE001
            raise ZhTokenizerUnavailable(
                "jieba is a required dependency for System KB retrieval but could not be "
                "imported. Install it (pip install jieba==0.42.1). Refusing to fall back to "
                "unsegmented Chinese search, which would silently degrade retrieval."
            ) from exc

        # Seed the userdict so drug names stay intact.
        for term in _collect_drug_terms():
            try:
                jieba.add_word(term)
            except Exception as exc:  # noqa: BLE001
                logger.warning("[zh_tokenize] jieba.add_word(%r) failed: %s", term, exc)

        # Warm the tokenizer once so the (default-dict build + userdict) cost is paid
        # here, not on the first user query.
        list(jieba.cut("初始化"))
        _jieba = jieba
        _initialized = True
        logger.info("[zh_tokenize] jieba initialized with drug-name userdict")


def check_zh_tokenizer_available() -> bool:
    """Startup-time probe. Forces init and re-raises loudly if jieba is missing.

    Call this once at process startup (NOT per-query) so a missing dependency is a
    loud boot-time failure instead of a silent per-request degradation.
    """
    _ensure_initialized()
    return True


def seg_text(text: str) -> str:
    """Return jieba word tokens joined by single spaces. "" for empty input."""
    if not text or not text.strip():
        return ""
    _ensure_initialized()
    tokens = [tok for tok in _jieba.cut(text) if tok and not tok.isspace()]
    return " ".join(tokens)
