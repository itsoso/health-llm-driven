"""Fail-closed authority routing for user-visible health evidence.

System KB retrieval supplies relevance candidates. This module performs the separate
admission decision: a candidate is not medical evidence until review, license,
authority, freshness, source-registry and applicability metadata all pass.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import parse_qs, urlsplit

from app.services.clinical_claim_release import (
    is_clinical_claim_serving_allowed,
)


ALLOWED_LICENSE_SCOPES = frozenset({"internal_transformed_claims"})
ALLOWED_TIERS_BY_RISK = {
    "low": frozenset({"T1", "T2", "T3"}),
    "medium": frozenset({"T1", "T2"}),
    "high": frozenset({"T1"}),
    "emergency": frozenset({"T1"}),
}


@dataclass(frozen=True)
class TrustedSourcePolicy:
    """Immutable identity and tier for one official external source."""

    authority_tier: str
    organization: str
    kind: str
    hostname: str
    path_prefix: str
    canonical_url: str
    title: str
    version: str
    required_query: tuple[tuple[str, str], ...] = ()


OFFICIAL_SOURCE_REGISTRY: Mapping[str, TrustedSourcePolicy] = MappingProxyType({
    "nice:ng59": TrustedSourcePolicy(
        authority_tier="T1",
        organization="NICE",
        kind="guideline",
        hostname="www.nice.org.uk",
        path_prefix="/guidance/ng59",
        canonical_url="https://www.nice.org.uk/guidance/ng59",
        title="Low back pain and sciatica in over 16s: assessment and management",
        version="NG59 updated 2020-12-11",
    ),
    "nice:ng127": TrustedSourcePolicy(
        authority_tier="T1",
        organization="NICE",
        kind="guideline",
        hostname="www.nice.org.uk",
        path_prefix="/guidance/ng127",
        canonical_url="https://www.nice.org.uk/guidance/ng127",
        title="Suspected neurological conditions: recognition and referral",
        version="NG127 recommendation 1.7.3, accessed 2026-07-29",
    ),
    "nhs:back-pain-2026": TrustedSourcePolicy(
        authority_tier="T1",
        organization="NHS",
        kind="public_health_guidance",
        hostname="www.nhs.uk",
        path_prefix="/conditions/back-pain",
        canonical_url="https://www.nhs.uk/conditions/back-pain/",
        title="Back pain",
        version="Reviewed 2026-03-05",
    ),
    "acr:low-back-pain-2026": TrustedSourcePolicy(
        authority_tier="T1",
        organization="American College of Radiology",
        kind="appropriateness_criteria",
        hostname="gravitas.acr.org",
        path_prefix="/ACPortal/TopicNarrativePdf",
        canonical_url=(
            "https://gravitas.acr.org/ACPortal/TopicNarrativePdf?topicId=141"
        ),
        title="ACR Appropriateness Criteria: Low Back Pain",
        version="Revised 2021; accessed 2026-07-29",
        required_query=(("topicId", "141"),),
    ),
    "who:9789240081789": TrustedSourcePolicy(
        authority_tier="T1",
        organization="World Health Organization",
        kind="guideline",
        hostname="www.who.int",
        path_prefix="/publications-detail-redirect/9789240081789",
        canonical_url=(
            "https://www.who.int/publications-detail-redirect/9789240081789"
        ),
        title=(
            "WHO guideline for non-surgical management of chronic primary "
            "low back pain in adults"
        ),
        version="2023",
    ),
})


@dataclass(frozen=True)
class CandidateClaimPolicy:
    """Immutable admission policy for a clinically held claim candidate."""

    domain: str
    source_ids: tuple[str, ...]
    risk_levels: frozenset[str]
    populations: frozenset[str]
    use_cases: frozenset[str]
    artifact_sha256: str


# Security admission manifest. A seed edit must be explicitly reviewed and its
# canonical artifact hash updated here; this policy cannot override the separate
# global clinical serving hold.
LOW_BACK_CLAIM_POLICY: Mapping[str, CandidateClaimPolicy] = MappingProxyType({
    "claim:c_low_back_emergency_neurologic_red_flags": CandidateClaimPolicy(
        domain="low_back_pain",
        source_ids=("nice:ng127", "nhs:back-pain-2026"),
        risk_levels=frozenset({"emergency"}),
        populations=frozenset({"adults_16_plus"}),
        use_cases=frozenset({"symptom_triage"}),
        artifact_sha256=(
            "5db7d6bf292dc6563e7958f05031d2e2ad904cf23c83cbcb952ca24ffd09457f"
        ),
    ),
    "claim:c_low_back_serious_cause_screening_boundary": CandidateClaimPolicy(
        domain="low_back_pain",
        source_ids=("nice:ng59",),
        risk_levels=frozenset({"high", "medium"}),
        populations=frozenset({"adults_16_plus"}),
        use_cases=frozenset({"initial_assessment"}),
        artifact_sha256=(
            "8e943e3a0caf2b2a903e0d3601c9b163536d88d73e5d7c64d1a63382fb9a1730"
        ),
    ),
    "claim:c_low_back_self_management_activity_boundary": CandidateClaimPolicy(
        domain="low_back_pain",
        source_ids=("nice:ng59", "nhs:back-pain-2026"),
        risk_levels=frozenset({"low", "medium"}),
        populations=frozenset({"adults_16_plus"}),
        use_cases=frozenset({"self_management_after_red_flag_screen"}),
        artifact_sha256=(
            "fc9eee179dfa3af79704c867719fe9b060af9f6055ee1e21dc249c912b4f3354"
        ),
    ),
    "claim:c_low_back_imaging_not_routine_boundary": CandidateClaimPolicy(
        domain="low_back_pain",
        source_ids=("nice:ng59", "acr:low-back-pain-2026"),
        risk_levels=frozenset({"low", "medium"}),
        populations=frozenset({"adults_16_plus"}),
        use_cases=frozenset({"imaging_decision", "specialist_assessment"}),
        artifact_sha256=(
            "f57b323f5985e614cf23667db9f59f638502a166a169c3efff147c3c8f50dfe3"
        ),
    ),
    "claim:c_chronic_low_back_holistic_care_boundary": CandidateClaimPolicy(
        domain="low_back_pain",
        source_ids=("who:9789240081789",),
        risk_levels=frozenset({"low", "medium"}),
        populations=frozenset({"adults_16_plus"}),
        use_cases=frozenset({"chronic_primary_care"}),
        artifact_sha256=(
            "5663d3f22f89c9b2cc753a0d296c4a9c30a3a0d0a98b14b9600b4c60087b45ce"
        ),
    ),
})


@dataclass(frozen=True)
class AuthoritySource:
    source: str
    kind: str
    organization: str
    title: str
    version: str

    def public_dict(self, *, authority_tier: str) -> dict[str, str]:
        return {
            "source": self.source,
            "kind": self.kind,
            "organization": self.organization,
            "title": self.title,
            "version": self.version,
            "authority_tier": authority_tier,
        }


@dataclass(frozen=True)
class AuthorityEvidence:
    doc_id: str
    title: str
    summary: str
    source_ids: tuple[str, ...]
    sources: tuple[AuthoritySource, ...]
    authority_tier: str


@dataclass(frozen=True)
class AuthorityRejection:
    doc_id: str
    reason: str


@dataclass(frozen=True)
class AuthorityBundle:
    status: str
    accepted: tuple[AuthorityEvidence, ...]
    rejections: tuple[AuthorityRejection, ...]

    def public_manifest(self) -> dict[str, Any]:
        sources: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for evidence in self.accepted:
            for source in evidence.sources:
                key = (source.source, evidence.authority_tier)
                if key in seen:
                    continue
                seen.add(key)
                sources.append(
                    source.public_dict(authority_tier=evidence.authority_tier)
                )
        return {
            "status": self.status,
            "evidence_refs": [item.doc_id for item in self.accepted],
            "sources": sources,
        }

    def to_prompt(self) -> str:
        if not self.accepted:
            return (
                "## 权威医学证据\n"
                "本轮没有通过审核、授权、时效和适用性门槛的医学证据；"
                "不得编造引用或据此给出确定性医学结论。"
            )
        lines = [
            "## 权威医学证据（只可使用以下已通过门槛的短结论）",
            "这些是通用健康管理依据，不是诊断或处方。",
        ]
        for item in self.accepted:
            source_ids = ", ".join(item.source_ids)
            lines.append(
                f"- [{item.doc_id}] {item.title}: {item.summary} "
                f"(authority={item.authority_tier}; sources={source_ids})"
            )
        return "\n".join(lines)


@dataclass(frozen=True)
class _RegisteredSources:
    sources: tuple[AuthoritySource, ...] = ()
    authority_tier: str = ""
    reason: str | None = None


def route_authority_results(
    results: Sequence[Mapping[str, Any]] | None,
    *,
    domain: str,
    risk_level: str,
    population: str | None = None,
    use_case: str | None = None,
    now: datetime | None = None,
) -> AuthorityBundle:
    """Admit reviewed System KB search results into an authority bundle.

    The first failing dimension is recorded for traceability. Unknown risk levels use
    the strict high-risk tier policy instead of widening access.
    """

    reference_now = _aware_utc(now or datetime.now(UTC))
    allowed_tiers = ALLOWED_TIERS_BY_RISK.get(
        str(risk_level or "").strip().lower(),
        ALLOWED_TIERS_BY_RISK["high"],
    )
    accepted: list[AuthorityEvidence] = []
    rejected: list[AuthorityRejection] = []

    for raw in results or ():
        document = _mapping(raw.get("document")) if isinstance(raw, Mapping) else {}
        doc_id = _text(document.get("doc_id")) or "unknown"
        metadata = _mapping(document.get("metadata") or document.get("metadata_json"))

        reason = _rejection_reason(
            document=document,
            metadata=metadata,
            domain=domain,
            risk_level=risk_level,
            population=population,
            use_case=use_case,
            allowed_tiers=allowed_tiers,
            now=reference_now,
        )
        if reason:
            rejected.append(AuthorityRejection(doc_id=doc_id, reason=reason))
            continue

        source_ids = tuple(_text_list(document.get("sources")))
        registered = _registered_sources(document, metadata)
        accepted.append(
            AuthorityEvidence(
                doc_id=doc_id,
                title=_text(document.get("title")) or doc_id,
                summary=_text(document.get("summary")),
                source_ids=source_ids,
                sources=registered.sources,
                authority_tier=registered.authority_tier,
            )
        )

    return AuthorityBundle(
        status="sufficient" if accepted else "insufficient",
        accepted=tuple(accepted),
        rejections=tuple(rejected),
    )


def _rejection_reason(
    *,
    document: Mapping[str, Any],
    metadata: Mapping[str, Any],
    domain: str,
    risk_level: str,
    population: str | None,
    use_case: str | None,
    allowed_tiers: frozenset[str],
    now: datetime,
) -> str | None:
    if not is_clinical_claim_serving_allowed(document.get("doc_id")):
        return "clinical_review_pending"
    if _text(metadata.get("review_status")).lower() != "reviewed":
        return "unreviewed"
    if _text(metadata.get("license_scope")) not in ALLOWED_LICENSE_SCOPES:
        return "disallowed_license"

    tier = _text(metadata.get("authority_tier")).upper()
    if not tier:
        return "missing_tier"
    if tier not in allowed_tiers:
        return "tier_not_allowed_for_risk"

    valid_until = _parse_datetime(metadata.get("review_valid_until"))
    if valid_until is None or valid_until < now:
        return "stale"

    applicability = _mapping(metadata.get("applicability"))
    domains = set(_text_list(applicability.get("domains")))
    normalized_domain = _text(domain).lower()
    if not normalized_domain or normalized_domain not in {
        item.lower() for item in domains
    }:
        return "wrong_domain"

    normalized_risk = _text(risk_level).lower()
    if not normalized_risk:
        return "missing_risk_context"
    risks = {item.lower() for item in _text_list(applicability.get("risk_levels"))}
    if not risks:
        return "missing_risk_applicability"
    if normalized_risk not in risks:
        return "wrong_risk"

    normalized_population = _text(population).lower()
    if not normalized_population:
        return "missing_population_context"
    populations = {
        item.lower() for item in _text_list(applicability.get("populations"))
    }
    if not populations:
        return "missing_population_applicability"
    if normalized_population not in populations:
        return "wrong_population"

    normalized_use_case = _text(use_case).lower()
    if not normalized_use_case:
        return "missing_use_case_context"
    use_cases = {
        item.lower() for item in _text_list(applicability.get("use_cases"))
    }
    if not use_cases:
        return "missing_use_case_applicability"
    if normalized_use_case not in use_cases:
        return "wrong_use_case"

    registered_reason = _registered_sources(document, metadata).reason
    if registered_reason:
        return registered_reason
    return _published_claim_reason(
        document=document,
        metadata=metadata,
        domain=normalized_domain,
        risk_level=normalized_risk,
        population=normalized_population,
        use_case=normalized_use_case,
    )


def _registered_sources(
    document: Mapping[str, Any],
    metadata: Mapping[str, Any],
) -> _RegisteredSources:
    source_ids = tuple(_text_list(document.get("sources")))
    if not source_ids:
        return _RegisteredSources(reason="missing_source_id")
    if len(set(source_ids)) != len(source_ids):
        return _RegisteredSources(reason="source_registry_mismatch")

    policies: list[TrustedSourcePolicy] = []
    for source_id in source_ids:
        policy = OFFICIAL_SOURCE_REGISTRY.get(source_id)
        if policy is None:
            return _RegisteredSources(reason="untrusted_source_id")
        policies.append(policy)

    reviewed_sources = tuple(_reviewed_sources(metadata.get("external_sources")))
    if not reviewed_sources:
        return _RegisteredSources(reason="missing_source_registry")
    if len(reviewed_sources) != len(source_ids):
        return _RegisteredSources(reason="source_registry_mismatch")

    ordered_sources: list[AuthoritySource] = []
    unused_indexes = set(range(len(reviewed_sources)))
    for policy in policies:
        matching = [
            index
            for index in unused_indexes
            if _source_matches_policy(reviewed_sources[index], policy)
        ]
        if len(matching) != 1:
            return _RegisteredSources(reason="source_identity_mismatch")
        index = matching[0]
        unused_indexes.remove(index)
        ordered_sources.append(
            AuthoritySource(
                source=policy.canonical_url,
                kind=policy.kind,
                organization=policy.organization,
                title=policy.title,
                version=policy.version,
            )
        )
    if unused_indexes:
        return _RegisteredSources(reason="source_registry_mismatch")

    tiers = {policy.authority_tier for policy in policies}
    if len(tiers) != 1:
        return _RegisteredSources(reason="source_registry_mismatch")
    authority_tier = tiers.pop()
    if _text(metadata.get("authority_tier")).upper() != authority_tier:
        return _RegisteredSources(reason="authority_tier_mismatch")
    return _RegisteredSources(
        sources=tuple(ordered_sources),
        authority_tier=authority_tier,
    )


def _source_matches_policy(
    source: AuthoritySource,
    policy: TrustedSourcePolicy,
) -> bool:
    if (
        source.organization != policy.organization
        or source.kind != policy.kind
        or source.title != policy.title
        or source.version != policy.version
    ):
        return False
    try:
        parsed = urlsplit(source.source)
        port = parsed.port
    except ValueError:
        return False
    if (
        parsed.scheme != "https"
        or parsed.hostname != policy.hostname
        or port not in {None, 443}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        return False
    path = parsed.path.rstrip("/") or "/"
    expected_path = policy.path_prefix.rstrip("/") or "/"
    if path != expected_path and not path.startswith(f"{expected_path}/"):
        return False
    query = parse_qs(parsed.query, keep_blank_values=True)
    return all(query.get(key) == [value] for key, value in policy.required_query)


def _published_claim_reason(
    *,
    document: Mapping[str, Any],
    metadata: Mapping[str, Any],
    domain: str,
    risk_level: str,
    population: str,
    use_case: str,
) -> str | None:
    doc_id = _text(document.get("doc_id"))
    policy = LOW_BACK_CLAIM_POLICY.get(doc_id)
    if policy is None:
        return "untrusted_claim_id"
    if policy.domain != domain:
        return "claim_policy_mismatch"

    source_ids = tuple(_text_list(document.get("sources")))
    applicability = _mapping(metadata.get("applicability"))
    risk_levels = frozenset(
        item.lower() for item in _text_list(applicability.get("risk_levels"))
    )
    populations = frozenset(
        item.lower() for item in _text_list(applicability.get("populations"))
    )
    use_cases = frozenset(
        item.lower() for item in _text_list(applicability.get("use_cases"))
    )
    if (
        source_ids != policy.source_ids
        or risk_levels != policy.risk_levels
        or populations != policy.populations
        or use_cases != policy.use_cases
    ):
        return "claim_policy_mismatch"
    if (
        risk_level not in policy.risk_levels
        or population not in policy.populations
        or use_case not in policy.use_cases
    ):
        return "claim_policy_mismatch"
    if _claim_artifact_sha256(document, metadata) != policy.artifact_sha256:
        return "claim_artifact_mismatch"
    return None


def _claim_artifact_sha256(
    document: Mapping[str, Any],
    metadata: Mapping[str, Any],
) -> str:
    artifact = {
        "doc_id": document.get("doc_id"),
        "doc_type": document.get("doc_type"),
        "title": document.get("title"),
        "summary": document.get("summary"),
        "body": document.get("body"),
        "sources": document.get("sources"),
        "metadata": dict(metadata),
    }
    try:
        payload = json.dumps(
            artifact,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError):
        return ""
    return hashlib.sha256(payload).hexdigest()


def _reviewed_sources(raw: Any) -> list[AuthoritySource]:
    if not isinstance(raw, Iterable) or isinstance(raw, (str, bytes, Mapping)):
        return []
    sources: list[AuthoritySource] = []
    for item in raw:
        source = _mapping(item)
        if _text(source.get("review_status")).lower() != "reviewed":
            continue
        required = {
            key: _text(source.get(key))
            for key in ("source", "kind", "organization", "title", "version")
        }
        if not all(required.values()):
            continue
        sources.append(AuthoritySource(**required))
    return sources


def _parse_datetime(value: Any) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    try:
        return _aware_utc(datetime.fromisoformat(text.replace("Z", "+00:00")))
    except ValueError:
        return None


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple, set, frozenset)):
        return []
    return [text for item in value if (text := _text(item))]
