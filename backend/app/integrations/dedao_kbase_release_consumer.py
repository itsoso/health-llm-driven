"""Transport immutable dedao-kbase Knowledge Releases into draft System KB artifacts."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import json
from pathlib import Path
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from app.services.dedao_kbase_export_importer import compile_dedao_kbase_export_payload_artifacts
from app.services.system_knowledge_ingest import IngestResult


RELEASE_PIPELINE_NAME = "dedao_kbase_release_v1"
AGENT_PACKAGE_PIPELINE_NAME = "dedao_kbase_agent_package_v1"
AGENT_PACKAGE_V2_PIPELINE_NAME = "dedao_kbase_agent_package_v2"
_OPAQUE_ID = re.compile(r"[^A-Za-z0-9._:-]+")


class DedaoKBaseReleaseClient:
    def __init__(self, base_url: str, *, auth_token: str | None = None, timeout: float = 30) -> None:
        self.base_url = base_url.rstrip("/")
        if not self.base_url:
            raise ValueError("dedao-kbase release base URL is required")
        self.auth_token = (auth_token or "").strip()
        self.timeout = timeout

    def list_releases(self, *, after: str = "", limit: int = 50) -> list[dict[str, Any]]:
        if limit < 1 or limit > 200:
            raise ValueError("release list limit must be between 1 and 200")
        query = urlencode({"after": after, "limit": limit})
        payload = self._request("GET", f"/api/knowledge/releases?{query}")
        records = payload.get("releases") if isinstance(payload, dict) else None
        if not isinstance(records, list) or any(not isinstance(item, dict) for item in records):
            raise ValueError("dedao-kbase release list has invalid schema")
        return records

    def get_release(self, release_id: str) -> dict[str, Any]:
        payload = self._request("GET", f"/api/knowledge/releases/{quote(release_id, safe='')}")
        _validate_release(payload)
        return payload

    def list_agent_packages(self, *, after: str = "", limit: int = 50) -> list[dict[str, Any]]:
        if limit < 1 or limit > 200:
            raise ValueError("agent package list limit must be between 1 and 200")
        query = urlencode({"after": after, "limit": limit})
        payload = self._request("GET", f"/api/agent-packages?{query}")
        records = payload.get("packages") if isinstance(payload, dict) else None
        if not isinstance(records, list) or any(not isinstance(item, dict) for item in records):
            raise ValueError("dedao-kbase agent package list has invalid schema")
        return records

    def get_agent_package(self, package_id: str, *, version: str) -> dict[str, Any]:
        query = urlencode({"version": version})
        payload = self._request(
            "GET",
            f"/api/agent-packages/{quote(package_id, safe='')}?{query}",
        )
        _validate_agent_package(payload)
        return payload

    def post_feedback(
        self,
        release_id: str,
        *,
        event_id: str,
        consumer: str,
        outcome: str,
        claim_ids: list[str] | None = None,
        reason_code: str = "",
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "event_id": event_id,
            "consumer": consumer,
            "outcome": outcome,
        }
        if claim_ids:
            body["claim_ids"] = claim_ids
        if reason_code:
            body["reason_code"] = reason_code
        payload = self._request(
            "POST",
            f"/api/knowledge/releases/{quote(release_id, safe='')}/feedback",
            body,
        )
        if not isinstance(payload, dict):
            raise ValueError("dedao-kbase feedback response has invalid schema")
        return payload

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        headers = {"Accept": "application/json"}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=True, separators=(",", ":")).encode("ascii")
            headers["Content-Type"] = "application/json"
        request = Request(f"{self.base_url}{path}", headers=headers, data=data, method=method)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except HTTPError as exc:
            raise RuntimeError(f"dedao-kbase release request failed: HTTP {exc.code} {path}") from exc
        except URLError as exc:
            raise RuntimeError(f"dedao-kbase release request failed: {path}: {exc.reason}") from exc
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"dedao-kbase release response is not valid JSON: {path}") from exc


def compile_knowledge_release_artifacts(
    *,
    release: dict[str, Any],
    base_artifact_dir: str | Path,
    source_root: str | Path,
    now: datetime | None = None,
) -> IngestResult:
    _validate_release(release)
    current_time = now or datetime.now(UTC)
    payload = _release_as_system_kb_export(release, current_time)
    result = compile_dedao_kbase_export_payload_artifacts(
        source_root=source_root,
        base_artifact_dir=base_artifact_dir,
        payload=payload,
        export_ref=f"knowledge-release:{release['release_id']}",
        now=current_time,
    )
    claim_metadata_by_doc_id = {
        str(row.get("doc_id") or ""): dict(row.get("metadata") or {}) for row in result.claims
    }
    for row in [*result.pages, *result.entities, *result.claims, *result.relations]:
        metadata = dict(row.get("metadata") or {})
        metadata.update(
            {
                "origin": "dedao-kbase-release",
                "release_id": release["release_id"],
                "content_hash": release["content_hash"],
                "usage_policy": release["usage_policy"],
                "review_status": "draft",
            }
        )
        row["metadata"] = metadata
    for relation in result.relations:
        target_metadata = claim_metadata_by_doc_id.get(str(relation.get("dst_doc_id") or ""), {})
        release_claim_id = target_metadata.get("release_claim_id")
        if release_claim_id:
            relation["metadata"]["release_claim_id"] = release_claim_id
    result.manifest["ingest"].update(
        {
            "pipeline": RELEASE_PIPELINE_NAME,
            "review_status": "draft",
            "requires_review": True,
            "serving_allowed": False,
        }
    )
    result.manifest["release_id"] = release["release_id"]
    result.manifest["usage_policy"] = release["usage_policy"]
    return result


def compile_agent_package_artifacts(
    *,
    package: dict[str, Any],
    releases: list[dict[str, Any]],
    base_artifact_dir: str | Path,
    source_root: str | Path,
    now: datetime | None = None,
) -> IngestResult:
    """Compile one eligible package into draft-only review artifacts.

    The producer's persisted evaluation report is required and verified here.
    Health still retains domain review, serving-index ownership, and all
    user-facing safety decisions.
    """
    assessment = assess_agent_package_for_health(package, releases)
    if not assessment["eligible"]:
        raise ValueError(f"agent package held: {', '.join(assessment['hold_reasons'])}")

    current_time = now or datetime.now(UTC)
    references_by_release_id = {
        str(reference["release_id"]): reference for reference in package["releases"]
    }
    release_results = [
        compile_knowledge_release_artifacts(
            release=_scope_release_to_package_reference(
                release,
                references_by_release_id[str(release["release_id"])],
            ),
            base_artifact_dir=base_artifact_dir,
            source_root=source_root,
            now=current_time,
        )
        for release in releases
    ]
    result = combine_release_results(release_results)
    evaluation_policy = package["evaluation_policy"]
    evaluation = package["evaluation"]
    safety_policy = package["safety_policy"]
    release_ids = [str(ref["release_id"]) for ref in package["releases"]]
    lineage = _agent_package_lineage(package)
    package_metadata = {
        "origin": "dedao-kbase-agent-package",
        "package_id": package["package_id"],
        "package_version": package["version"],
        "package_content_hash": package["content_hash"],
        "package_release_ids": release_ids,
        "evaluation_status": "passed",
        "evaluation_suite_version": evaluation_policy["suite_version"],
        "evaluation_input_hash": evaluation["input_hash"],
        "evaluation_evaluator_version": evaluation["evaluator_version"],
        "evaluated_at": evaluation["evaluated_at"],
        "agent_package_lineage": [lineage],
        "safety_flags": {
            "usage_policy": safety_policy["usage_policy"],
            "abstention_reasons": list(safety_policy["abstention_reasons"]),
            "escalation_target": safety_policy["escalation_target"],
        },
        "review_status": "draft",
    }
    evidence_policy = None
    if package.get("schema_version") == "agent-package.v2":
        evidence_policy = _evidence_policy_snapshot(package["evidence_policy"])
        package_metadata.update(
            {
                "package_schema_version": "agent-package.v2",
                "evidence_policy": evidence_policy,
            }
        )
    for row in [*result.pages, *result.entities, *result.claims, *result.relations]:
        metadata = dict(row.get("metadata") or {})
        metadata.update(package_metadata)
        row["metadata"] = metadata

    result.manifest["ingest"] = {
        "pipeline": (
            AGENT_PACKAGE_V2_PIPELINE_NAME
            if package.get("schema_version") == "agent-package.v2"
            else AGENT_PACKAGE_PIPELINE_NAME
        ),
        "review_status": "draft",
        "requires_review": True,
        "serving_allowed": False,
    }
    package_manifest = {
        "package_id": package["package_id"],
        "version": package["version"],
        "content_hash": package["content_hash"],
        "evaluation_status": "passed",
        "evaluation_suite_version": evaluation_policy["suite_version"],
        "evaluation_input_hash": evaluation["input_hash"],
        "evaluation_evaluator_version": evaluation["evaluator_version"],
        "evaluated_at": evaluation["evaluated_at"],
        "release_ids": release_ids,
    }
    if package.get("schema_version") == "agent-package.v2":
        package_manifest.update(
            {
                "schema_version": "agent-package.v2",
                "evidence_policy": evidence_policy,
            }
        )
    result.manifest["agent_package"] = package_manifest
    result.manifest["agent_packages"] = [lineage]
    for source_stat in result.source_stats:
        source_stat.update(
            {
                "agent_package_id": package["package_id"],
                "agent_package_version": package["version"],
                "agent_package_content_hash": package["content_hash"],
            }
        )
    return result


def _scope_release_to_package_reference(
    release: dict[str, Any], reference: dict[str, Any]
) -> dict[str, Any]:
    """Return only the release evidence authorized by one hashed package reference."""
    scoped = deepcopy(release)
    allowed_citation_ids = {
        str(value).strip() for value in reference.get("citation_ids") or [] if str(value).strip()
    }
    scoped["citations"] = [
        citation
        for citation in scoped.get("citations") or []
        if isinstance(citation, dict)
        and str(citation.get("citation_id") or "").strip() in allowed_citation_ids
    ]
    allowed_chunk_ids = {
        str(citation.get("chunk_id") or "").strip()
        for citation in scoped["citations"]
        if str(citation.get("chunk_id") or "").strip()
    }
    scoped["sources"] = [
        source
        for source in scoped.get("sources") or []
        if isinstance(source, dict)
        and (
            str(source.get("id") or "").strip() in allowed_citation_ids
            or str(source.get("id") or "").strip() in allowed_chunk_ids
            or str(source.get("chunk_id") or "").strip() in allowed_chunk_ids
        )
    ]
    scoped_claims: list[dict[str, Any]] = []
    for claim in scoped["analysis"].get("claims") or []:
        citation_ids = [
            str(value).strip()
            for value in claim.get("citation_ids") or []
            if str(value).strip() in allowed_citation_ids
        ]
        if not citation_ids:
            continue
        claim["citation_ids"] = citation_ids
        scoped_claims.append(claim)
    scoped["analysis"]["claims"] = scoped_claims
    scoped["analysis"]["summary"] = " ".join(
        str(claim.get("statement") or "").strip()
        for claim in scoped_claims
        if str(claim.get("statement") or "").strip()
    )
    return scoped


def assess_agent_package_for_health(
    package: dict[str, Any],
    releases: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return deterministic eligibility without mutating review or serving state."""
    _validate_agent_package(package)
    for release in releases:
        _validate_release(release)
    reasons = _agent_package_hold_reasons(package, releases)
    assessment = {
        "eligible": not reasons,
        "hold_reasons": reasons,
        "evaluation_status": "passed" if "unevaluated" not in reasons else "unevaluated",
    }
    if package.get("schema_version") == "agent-package.v2":
        assessment.update(
            {
                "schema_version": "agent-package.v2",
                "evidence_policy": _evidence_policy_snapshot(package["evidence_policy"]),
            }
        )
    return assessment


def combine_release_results(results: list[IngestResult]) -> IngestResult:
    if not results:
        raise ValueError("at least one release result is required")
    combined = results[-1]
    combined.pages = _unique_rows(results, "pages", "doc_id")
    combined.entities = _unique_rows(results, "entities", "doc_id")
    combined.claims = _unique_rows(results, "claims", "doc_id")
    combined.relations = _unique_relations(results)
    combined.diff = {
        "pages_added": len(combined.pages),
        "entities_added": len(combined.entities),
        "claims_added": len(combined.claims),
        "relations_added": len(combined.relations),
    }
    combined.source_stats = [item for result in results for item in result.source_stats]
    package_lineages = _unique_package_lineages(
        item
        for result in results
        for item in result.manifest.get("agent_packages") or []
        if isinstance(item, dict)
    )
    if package_lineages:
        combined.manifest["agent_packages"] = package_lineages
    return combined


def _validate_agent_package(payload: Any) -> None:
    if not isinstance(payload, dict):
        raise ValueError("dedao-kbase agent package must be a JSON object")
    schema_version = payload.get("schema_version")
    if schema_version == "agent-package.v1":
        _validate_agent_package_v1(payload)
        return
    if schema_version == "agent-package.v2":
        _validate_agent_package_v2(payload)
        return
    raise ValueError("dedao-kbase agent package has unsupported schema_version")


def _validate_agent_package_v1(payload: dict[str, Any]) -> None:
    required = (
        "schema_version",
        "package_id",
        "version",
        "content_hash",
        "lifecycle_state",
        "releases",
        "safety_policy",
        "evaluation_policy",
    )
    missing = [field for field in required if field not in payload]
    if missing:
        raise ValueError(f"dedao-kbase agent package missing fields: {', '.join(missing)}")
    if payload.get("schema_version") != "agent-package.v1":
        raise ValueError("dedao-kbase agent package has unsupported schema_version")
    if not all(str(payload.get(field) or "").strip() for field in ("package_id", "version", "content_hash")):
        raise ValueError("dedao-kbase agent package identity is incomplete")
    if not isinstance(payload.get("releases"), list) or not payload["releases"]:
        raise ValueError("dedao-kbase agent package requires pinned releases")
    if any(not isinstance(item, dict) for item in payload["releases"]):
        raise ValueError("dedao-kbase agent package release references must be JSON objects")
    if not isinstance(payload.get("safety_policy"), dict):
        raise ValueError("dedao-kbase agent package safety_policy must be a JSON object")
    if not isinstance(payload.get("evaluation_policy"), dict):
        raise ValueError("dedao-kbase agent package evaluation_policy must be a JSON object")
    if "evaluation" in payload and not isinstance(payload.get("evaluation"), dict):
        raise ValueError("dedao-kbase agent package evaluation must be a JSON object")


def _validate_agent_package_v2(payload: dict[str, Any]) -> None:
    required = (
        "schema_version",
        "package_id",
        "version",
        "content_hash",
        "lifecycle_state",
        "releases",
        "retrieval_policy",
        "model_policy",
        "prompt_profiles",
        "tool_policy",
        "safety_policy",
        "evaluation_policy",
        "evidence_policy",
        "ui_manifest",
    )
    missing = [field for field in required if field not in payload]
    if missing:
        raise ValueError(f"dedao-kbase agent package v2 missing fields: {', '.join(missing)}")
    if not all(str(payload.get(field) or "").strip() for field in ("package_id", "version", "content_hash")):
        raise ValueError("dedao-kbase agent package v2 identity is incomplete")
    if payload.get("lifecycle_state") not in {"draft", "published", "superseded"}:
        raise ValueError("dedao-kbase agent package v2 has invalid lifecycle_state")
    releases = payload.get("releases")
    if not isinstance(releases, list) or not releases:
        raise ValueError("dedao-kbase agent package v2 requires pinned releases")
    if any(not isinstance(item, dict) for item in releases):
        raise ValueError("dedao-kbase agent package v2 release references must be JSON objects")
    release_ids = []
    for reference in releases:
        release_id = str(reference.get("release_id") or "").strip()
        content_hash = str(reference.get("content_hash") or "").strip()
        citation_ids = reference.get("citation_ids")
        if not release_id or not content_hash:
            raise ValueError("dedao-kbase agent package v2 release identity is incomplete")
        if not isinstance(citation_ids, list) or not citation_ids or any(
            not str(value).strip() for value in citation_ids
        ):
            raise ValueError("dedao-kbase agent package v2 release citation_ids are required")
        release_ids.append(release_id)
    if len(set(release_ids)) != len(release_ids):
        raise ValueError("dedao-kbase agent package v2 has duplicate release id")
    safety_policy = payload.get("safety_policy")
    if not isinstance(safety_policy, dict):
        raise ValueError("dedao-kbase agent package v2 safety_policy must be a JSON object")
    if safety_policy.get("usage_policy") not in {"standard", "evidence_only"}:
        raise ValueError("dedao-kbase agent package v2 has invalid usage_policy")
    evaluation_policy = payload.get("evaluation_policy")
    if not isinstance(evaluation_policy, dict):
        raise ValueError("dedao-kbase agent package v2 evaluation_policy must be a JSON object")
    if not str(evaluation_policy.get("suite_version") or "").strip():
        raise ValueError("dedao-kbase agent package v2 evaluation_policy suite_version is required")
    minimum_scores = evaluation_policy.get("minimum_scores")
    if not isinstance(minimum_scores, dict) or not minimum_scores or any(
        not isinstance(value, (int, float)) for value in minimum_scores.values()
    ):
        raise ValueError("dedao-kbase agent package v2 evaluation_policy minimum_scores is invalid")
    _validate_evidence_policy(payload.get("evidence_policy"), release_ids)


def _validate_evidence_policy(policy: Any, release_ids: list[str]) -> None:
    if not isinstance(policy, dict):
        raise ValueError("dedao-kbase agent package v2 evidence_policy must be a JSON object")
    required = (
        "release_roles",
        "minimum_independent_sources",
        "max_claims",
        "max_evidence_per_claim",
        "allowed_verdicts",
        "freshness_policy",
        "report_schema",
    )
    missing = [field for field in required if field not in policy]
    if missing:
        raise ValueError(f"evidence_policy missing fields: {', '.join(missing)}")
    roles = policy.get("release_roles")
    if not isinstance(roles, list) or len(roles) < 2 or any(not isinstance(item, dict) for item in roles):
        raise ValueError("evidence_policy release_roles requires primary and supporting releases")
    role_ids = [str(item.get("release_id") or "").strip() for item in roles]
    role_names = [str(item.get("role") or "").strip() for item in roles]
    if any(release_id not in release_ids for release_id in role_ids):
        raise ValueError("evidence_policy release_roles reference unknown release")
    if len(set(role_ids)) != len(role_ids):
        raise ValueError("evidence_policy release_roles contain duplicate release")
    if role_names.count("primary") != 1:
        raise ValueError("evidence_policy release_roles require exactly one primary release")
    if role_names.count("supporting") < 1:
        raise ValueError("evidence_policy release_roles require a supporting release")
    if any(role not in {"primary", "supporting"} for role in role_names):
        raise ValueError("evidence_policy release_roles contain an invalid role")
    for field, minimum, maximum in (
        ("minimum_independent_sources", 1, None),
        ("max_claims", 1, 8),
        ("max_evidence_per_claim", 1, 5),
    ):
        value = policy.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < minimum or (
            maximum is not None and value > maximum
        ):
            suffix = f" between {minimum} and {maximum}" if maximum is not None else f" >= {minimum}"
            raise ValueError(f"evidence_policy {field} must be an integer{suffix}")
    allowed_verdicts = policy.get("allowed_verdicts")
    if not isinstance(allowed_verdicts, list) or not allowed_verdicts or any(
        verdict not in {"supported", "contradicted", "mixed", "insufficient"}
        for verdict in allowed_verdicts
    ):
        raise ValueError("evidence_policy allowed_verdicts is invalid")
    freshness = policy.get("freshness_policy")
    if not isinstance(freshness, dict) or not isinstance(freshness.get("max_age_days"), int) or (
        isinstance(freshness.get("max_age_days"), bool) or freshness["max_age_days"] < 1
    ) or not isinstance(freshness.get("require_publication_date"), bool):
        raise ValueError("evidence_policy freshness_policy is invalid")
    if policy.get("report_schema") != "evidence-audit.v1":
        raise ValueError("evidence_policy report_schema must be evidence-audit.v1")


def _evidence_policy_snapshot(policy: dict[str, Any]) -> dict[str, Any]:
    """Keep only the evidence controls Health is allowed to consume."""
    freshness = policy["freshness_policy"]
    return {
        "release_roles": [
            {"release_id": str(item["release_id"]), "role": str(item["role"])}
            for item in policy["release_roles"]
        ],
        "minimum_independent_sources": int(policy["minimum_independent_sources"]),
        "max_claims": int(policy["max_claims"]),
        "max_evidence_per_claim": int(policy["max_evidence_per_claim"]),
        "allowed_verdicts": [str(value) for value in policy["allowed_verdicts"]],
        "freshness_policy": {
            "max_age_days": int(freshness["max_age_days"]),
            "require_publication_date": bool(freshness["require_publication_date"]),
        },
        "report_schema": "evidence-audit.v1",
    }


def _agent_package_hold_reasons(
    package: dict[str, Any],
    releases: list[dict[str, Any]],
) -> list[str]:
    reasons: list[str] = []
    if package.get("lifecycle_state") != "published":
        reasons.append("stale")

    safety_policy = package.get("safety_policy") or {}
    if safety_policy.get("usage_policy") != "evidence_only" or any(
        release.get("usage_policy") != "evidence_only" for release in releases
    ):
        reasons.append("non_evidence_only")

    evaluation_policy = package.get("evaluation_policy") or {}
    evaluation = package.get("evaluation") or {}
    minimum_scores = evaluation_policy.get("minimum_scores")
    metrics = evaluation.get("metrics")
    thresholds_pass = (
        isinstance(minimum_scores, dict)
        and bool(minimum_scores)
        and isinstance(metrics, dict)
        and all(
            isinstance(metrics.get(metric), (int, float))
            and float(metrics[metric]) >= float(threshold)
            for metric, threshold in minimum_scores.items()
            if isinstance(threshold, (int, float))
        )
        and all(isinstance(threshold, (int, float)) for threshold in minimum_scores.values())
    )
    if (
        evaluation.get("schema_version") != "agent-evaluation-report.v1"
        or evaluation.get("passed") is not True
        or str(evaluation.get("package_id") or "") != str(package.get("package_id") or "")
        or str(evaluation.get("package_content_hash") or "")
        != str(package.get("content_hash") or "")
        or str(evaluation.get("suite_version") or "")
        != str(evaluation_policy.get("suite_version") or "")
        or not str(evaluation.get("input_hash") or "").strip()
        or not str(evaluation.get("evaluator_version") or "").strip()
        or not str(evaluation.get("evaluated_at") or "").strip()
        or not thresholds_pass
        or not str(evaluation_policy.get("suite_version") or "").strip()
    ):
        reasons.append("unevaluated")

    releases_by_id = {
        str(release.get("release_id") or ""): release
        for release in releases
        if str(release.get("release_id") or "").strip()
    }
    seen_release_ids: set[str] = set()
    for reference in package.get("releases") or []:
        release_id = str(reference.get("release_id") or "").strip()
        if not release_id or release_id in seen_release_ids:
            reasons.append("conflict")
            continue
        seen_release_ids.add(release_id)
        release = releases_by_id.get(release_id)
        if release is None or str(reference.get("content_hash") or "") != str(
            release.get("content_hash") or ""
        ):
            reasons.append("conflict")
            continue
        available_citations = {
            str(citation.get("citation_id") or "")
            for citation in release.get("citations") or []
            if isinstance(citation, dict)
        }
        pinned_citations = {
            str(citation_id)
            for citation_id in reference.get("citation_ids") or []
            if str(citation_id).strip()
        }
        if not pinned_citations or not pinned_citations.issubset(available_citations):
            reasons.append("conflict")
    if set(releases_by_id) != seen_release_ids:
        reasons.append("conflict")
    if package.get("schema_version") == "agent-package.v2":
        evidence_policy = package["evidence_policy"]
        pinned_release_ids = set(seen_release_ids)
        role_release_ids = {
            str(item.get("release_id") or "")
            for item in evidence_policy.get("release_roles") or []
            if isinstance(item, dict)
        }
        if role_release_ids != pinned_release_ids:
            reasons.append("conflict")
        if int(evidence_policy["minimum_independent_sources"]) > len(role_release_ids):
            reasons.append("insufficient_independent_sources")
    return list(dict.fromkeys(reasons))


def _validate_release(payload: Any) -> None:
    if not isinstance(payload, dict):
        raise ValueError("dedao-kbase release must be a JSON object")
    required = ("release_id", "book_id", "content_hash", "usage_policy", "book", "analysis", "quality")
    missing = [field for field in required if not payload.get(field)]
    if missing:
        raise ValueError(f"dedao-kbase release missing fields: {', '.join(missing)}")
    if not isinstance(payload["book"], dict) or not isinstance(payload["analysis"], dict):
        raise ValueError("dedao-kbase release book and analysis must be JSON objects")
    if not isinstance(payload["quality"], dict):
        raise ValueError("dedao-kbase release quality must be a JSON object")
    if payload["usage_policy"] not in {"standard", "evidence_only"}:
        raise ValueError("dedao-kbase release has invalid usage_policy")
    if payload["quality"].get("decision") != "pass":
        raise ValueError("dedao-kbase release quality decision must be pass")
    claims = payload["analysis"].get("claims") if isinstance(payload["analysis"], dict) else None
    if not isinstance(claims, list) or not claims:
        raise ValueError("dedao-kbase release requires structured claims")
    if any(not isinstance(claim, dict) for claim in claims):
        raise ValueError("dedao-kbase release claims must be JSON objects")
    claim_ids = [str(claim.get("id") or "").strip() for claim in claims]
    if any(not claim_id for claim_id in claim_ids):
        raise ValueError("dedao-kbase release claim id is required")
    if len(set(claim_ids)) != len(claim_ids):
        raise ValueError("dedao-kbase release has duplicate claim id")


def _release_as_system_kb_export(release: dict[str, Any], now: datetime) -> dict[str, Any]:
    release_id = str(release["release_id"])
    book_id = _safe_id(str(release["book_id"]))
    book = release["book"]
    analysis = release["analysis"]
    title = str(book.get("title") or book.get("name") or release["book_id"])
    source_ids = [str(item.get("id")) for item in release.get("sources") or [] if item.get("id")]
    page_id = f"release-{_safe_id(release_id)}"
    claims = []
    relations = []
    entity_doc_id = f"entity:knowledge_source:{book_id}"
    for claim in analysis["claims"]:
        release_claim_id = str(claim.get("id") or "").strip()
        claim_id = f"{_safe_id(release_id)}-{_safe_id(release_claim_id)}"
        citation_ids = [str(item) for item in claim.get("citation_ids") or []]
        metadata = {
            "release_id": release_id,
            "release_claim_id": release_claim_id,
            "content_hash": release["content_hash"],
            "usage_policy": release["usage_policy"],
            "citation_ids": citation_ids,
            "scope": claim.get("scope") or [],
            "risk_level": claim.get("risk_level") or "low",
            "review_status": "draft",
        }
        claims.append(
            {
                "claim_id": claim_id,
                "entity_type": "knowledge_source",
                "entity_id": book_id,
                "title": str(claim.get("statement") or title),
                "summary": str(claim.get("statement") or ""),
                "body": str(claim.get("statement") or ""),
                "sources": citation_ids or source_ids or [release_id],
                "metadata": metadata,
            }
        )
        relations.append(
            {
                "src_doc_id": entity_doc_id,
                "dst_doc_id": f"claim:{claim_id}",
                "relation": "has_claim",
                "confidence": float(claim.get("confidence") or 0.5),
                "source_claim_id": f"claim:{claim_id}",
                "metadata": metadata,
            }
        )
    return {
        "schema_id": "knowledge-release-system-kb-export",
        "version": release_id,
        "source": "dedao-kbase",
        "source_commit": release["content_hash"],
        "compiled_at": now.isoformat(),
        "pages": [
            {
                "id": page_id,
                "title": title,
                "summary": str(analysis.get("summary") or ""),
                "content": str(analysis.get("summary") or ""),
                "content_hash": release["content_hash"],
                "review_status": "draft",
            }
        ],
        "entities": [
            {
                "doc_id": entity_doc_id,
                "entity_type": "knowledge_source",
                "entity_id": book_id,
                "title": title,
                "summary": str(analysis.get("summary") or ""),
                "body": str(analysis.get("summary") or ""),
                "sources": source_ids or [release_id],
                "metadata": {"release_id": release_id, "review_status": "draft"},
            }
        ],
        "claims": claims,
        "relations": relations,
    }


def _safe_id(value: str) -> str:
    return _OPAQUE_ID.sub("-", value.strip()).strip("-") or "unknown"


def _unique_rows(results: list[IngestResult], field: str, key: str) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for result in results:
        for row in getattr(result, field):
            row_key = str(row[key])
            rows[row_key] = _merge_package_lineage(rows.get(row_key), row)
    return sorted(rows.values(), key=lambda row: str(row[key]))


def _unique_relations(results: list[IngestResult]) -> list[dict[str, Any]]:
    rows: dict[tuple[str, str, str], dict[str, Any]] = {}
    for result in results:
        for row in result.relations:
            key = (str(row["src_doc_id"]), str(row["relation"]), str(row["dst_doc_id"]))
            rows[key] = _merge_package_lineage(rows.get(key), row)
    return [rows[key] for key in sorted(rows)]


def _agent_package_lineage(package: dict[str, Any]) -> dict[str, Any]:
    evaluation = package["evaluation"]
    lineage = {
        "package_id": package["package_id"],
        "version": package["version"],
        "content_hash": package["content_hash"],
        "release_ids": [str(reference["release_id"]) for reference in package["releases"]],
        "evaluation": {
            "status": "passed",
            "suite_version": evaluation["suite_version"],
            "input_hash": evaluation["input_hash"],
            "evaluator_version": evaluation["evaluator_version"],
            "evaluated_at": evaluation["evaluated_at"],
        },
    }
    if package.get("schema_version") == "agent-package.v2":
        lineage.update(
            {
                "schema_version": "agent-package.v2",
                "evidence_policy": _evidence_policy_snapshot(package["evidence_policy"]),
            }
        )
    return lineage


def _merge_package_lineage(
    previous: dict[str, Any] | None,
    current: dict[str, Any],
) -> dict[str, Any]:
    if previous is None:
        return current
    merged = dict(current)
    previous_metadata = dict(previous.get("metadata") or {})
    current_metadata = dict(current.get("metadata") or {})
    lineages = _unique_package_lineages(
        [
            *(previous_metadata.get("agent_package_lineage") or []),
            *(current_metadata.get("agent_package_lineage") or []),
        ]
    )
    if lineages:
        current_metadata["agent_package_lineage"] = lineages
    merged["metadata"] = current_metadata
    return merged


def _unique_package_lineages(items: Any) -> list[dict[str, Any]]:
    unique: dict[tuple[str, str, str], dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        key = (
            str(item.get("package_id") or ""),
            str(item.get("version") or ""),
            str(item.get("content_hash") or ""),
        )
        if all(key):
            unique[key] = item
    return [unique[key] for key in sorted(unique)]
