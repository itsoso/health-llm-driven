"""Retrieval input guard for health knowledge lookups.

This guard is intentionally narrower than full anonymization: it removes direct
identifiers before a query reaches vector search, legacy Chroma, or audit logs,
while preserving medical terms such as labs, SNPs, drugs, and symptoms that are
needed for useful retrieval.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.llm.pii_scrub import scrub_pii


POLICY = "deterministic_direct_identifier_redaction_v1"


@dataclass(frozen=True)
class GuardedRetrievalQuery:
    query: str
    pii_hits: dict[str, int]

    @property
    def redacted(self) -> bool:
        return bool(self.pii_hits)

    def metadata(self) -> dict[str, object]:
        return {
            "policy": POLICY,
            "redacted": self.redacted,
            "pii_hits": dict(self.pii_hits),
        }


def guard_retrieval_query(query: str | None, *, max_chars: int = 500) -> GuardedRetrievalQuery:
    """Return the safe query used for retrieval and audit metadata."""

    normalized = (query or "").strip()
    if max_chars > 0:
        normalized = normalized[:max_chars]
    scrubbed, hits = scrub_pii(normalized)
    return GuardedRetrievalQuery(query=scrubbed, pii_hits=hits)
