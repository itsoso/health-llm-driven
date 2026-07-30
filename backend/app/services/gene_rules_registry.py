"""Gene rules registry (loaded from ak-kbase gene_knowledge.json).

Loaded once at process start and re-loaded when /knowledge/gene-drug-rules
POST endpoint is hit.

Source of truth: down-dedao/artifacts/gene_knowledge.json (llm-wiki-v2 schema).
Local mirror path: $HEALTH_GENE_KNOWLEDGE_PATH. Production defaults to
/var/lib/health-app/runtime/gene_knowledge.json; development keeps backend/data.

This module REPLACES the hard-coded gene ladders in two places:
- app/twin/gene_config.py: phenotype → summary_line lookup
- app/services/agent_executor.py: gene safety rules in system prompt

Consumers use the public helpers:
- get_registry() → GeneRulesRegistry
- registry.summary_lines_for_phenotypes(...) → list[str]
- registry.constraints_for_user(user_genes) → dict[gene, dict]
- registry.system_prompt_section(user_genes=None) → str (for agent prompt)
"""
from __future__ import annotations

import json
import logging
import os
import stat
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from app.utils.runtime_data import configured_runtime_path, runtime_data_path

logger = logging.getLogger(__name__)


def default_path() -> Path:
    configured = os.environ.get("HEALTH_GENE_KNOWLEDGE_PATH", "").strip()
    if configured:
        return configured_runtime_path(
            configured,
            "HEALTH_GENE_KNOWLEDGE_PATH",
        )
    return runtime_data_path("gene_knowledge.json")


DEFAULT_PATH = default_path()


class AtomicPayloadCommitError(RuntimeError):
    """The file was replaced, but its parent-directory sync failed."""


def _atomic_write_payload(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    replaced = False
    try:
        descriptor, raw_temp_path = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.name}.",
        )
        temp_path = Path(raw_temp_path)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            os.fchmod(handle.fileno(), 0o600)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        replaced = True
        temp_path = None
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except Exception as exc:
        if replaced:
            raise AtomicPayloadCommitError(
                "payload replaced but parent directory fsync failed"
            ) from exc
        raise
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


@dataclass
class GeneRulesRegistry:
    path: Path = DEFAULT_PATH
    version: str = ""
    compiled_at: str = ""
    schema_id: str = ""
    gene_rules: Dict[str, Dict[str, Dict[str, list]]] = field(default_factory=dict)
    claims: List[Dict[str, Any]] = field(default_factory=list)
    snp_registry: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    entities: Dict[str, Dict[str, Dict[str, Any]]] = field(default_factory=dict)
    _loaded: bool = False

    def _load_data(self, data: Dict[str, Any]) -> bool:
        self.version = data.get("version", "")
        self.compiled_at = data.get("compiled_at", "")
        self.schema_id = data.get("schema_id", "")
        self.gene_rules = data.get("gene_rules", {}) or {}
        self.claims = data.get("claims", []) or []
        self.snp_registry = data.get("snp_registry", {}) or {}
        self.entities = data.get("entities", {}) or {}
        self._loaded = True
        logger.info(
            "Gene knowledge loaded: version=%s genes=%d claims=%d snps=%d",
            self.version,
            len(self.gene_rules),
            len(self.claims),
            len(self.snp_registry),
        )
        return True

    def load(self) -> bool:
        if not self.path.exists():
            logger.warning("gene_knowledge.json not found at %s; registry empty", self.path)
            self._loaded = False
            return False
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.error("Failed to parse gene_knowledge.json: %s", exc)
            self._loaded = False
            return False
        return self._load_data(data)

    def is_loaded(self) -> bool:
        return self._loaded

    # ─────────────────────────────────────────
    # Lookup helpers
    # ─────────────────────────────────────────

    def rules_for(self, gene: str, phenotype: str) -> Optional[Dict[str, list]]:
        """Return {avoid, substitute, monitor, supplement, lifestyle} for (gene, phenotype) or None."""
        gene_bucket = self.gene_rules.get(gene)
        if not gene_bucket:
            return None
        return gene_bucket.get(phenotype)

    def all_phenotypes(self, gene: str) -> List[str]:
        return list((self.gene_rules.get(gene) or {}).keys())

    def constraints_for_user(self, user_phenotypes: Dict[str, str]) -> Dict[str, Dict[str, list]]:
        """user_phenotypes: {gene: phenotype}. Returns matched (gene→rules) blocks only."""
        out: Dict[str, Dict[str, list]] = {}
        for gene, phen in user_phenotypes.items():
            rules = self.rules_for(gene, phen)
            if rules:
                out[gene] = rules
        return out

    # ─────────────────────────────────────────
    # Summaries (replace hard-coded prompt lines)
    # ─────────────────────────────────────────

    _PHEN_LABEL = {
        "poor": "慢代谢 (PM)",
        "intermediate": "中间代谢 (IM)",
        "rapid": "快代谢",
        "ultra_rapid": "超快代谢 (UM)",
        "deficient": "酶活缺陷",
        "decreased_function": "转运下降",
        "low_conversion": "转化低效",
        "homozygous_risk": "高风险纯合",
        "iron_overload_risk": "铁过载风险",
        "lactase_non_persistence": "乳糖酶不持续",
        "high_caffeine_sensitivity": "咖啡因高敏",
    }

    def summary_line(self, gene: str, phenotype: str) -> Optional[str]:
        """Single-line human summary for a (gene, phenotype) tuple."""
        rules = self.rules_for(gene, phenotype)
        if not rules:
            return None
        phen_label = self._PHEN_LABEL.get(phenotype, phenotype)
        bits: List[str] = []
        for item in rules.get("avoid", [])[:2]:
            if isinstance(item, str):
                drug = item
            elif isinstance(item, dict):
                drug = str(item.get("drug") or "")
            else:
                drug = ""
            if drug:
                bits.append(f"避免 {drug}")
        for item in rules.get("substitute", [])[:2]:
            if isinstance(item, str):
                text = item
            elif isinstance(item, dict):
                src = str(item.get("from") or "")
                dst = str(item.get("to") or "")
                text = f"{src}→{dst}" if src or dst else ""
            else:
                text = ""
            if text:
                bits.append(text)
        for item in rules.get("monitor", [])[:1]:
            if isinstance(item, str):
                target = item
            elif isinstance(item, dict):
                target = str(item.get("drug") or item.get("metric") or "")
            else:
                target = ""
            if target:
                bits.append(f"监测 {target}")
        if not bits:
            return None
        return f"{gene} {phen_label}: " + "; ".join(bits)

    def summary_lines_for_phenotypes(self, user_phenotypes: Dict[str, str]) -> List[str]:
        out: List[str] = []
        for gene, phen in user_phenotypes.items():
            line = self.summary_line(gene, phen)
            if line:
                out.append(line)
        return out

    def system_prompt_section(self, user_phenotypes: Optional[Dict[str, str]] = None) -> str:
        """Compose the gene safety block injected into LLM system prompts.

        If user_phenotypes is None, returns the universal high-priority rules across all genes.
        Otherwise returns the user-specific constraints.
        """
        if not self._loaded:
            return ""
        if user_phenotypes:
            lines = self.summary_lines_for_phenotypes(user_phenotypes)
            if not lines:
                return ""
            body = "\n".join(f"- {line}" for line in lines)
            return (
                "## 用户基因相关用药约束 (来自 ak-kbase gene_knowledge v"
                + (self.version or "?") + ")\n" + body
            )
        # Universal high-priority warnings (poor / homozygous_risk / deficient)
        lines: List[str] = []
        for gene, phens in self.gene_rules.items():
            for severe in ("poor", "deficient", "homozygous_risk", "iron_overload_risk"):
                if severe in phens:
                    line = self.summary_line(gene, severe)
                    if line:
                        lines.append(line)
        if not lines:
            return ""
        body = "\n".join(f"- {line}" for line in lines)
        return "## 基因用药安全规则 (来自 ak-kbase gene_knowledge)\n" + body


# ─────────────────────────────────────────
# Module-level singleton
# ─────────────────────────────────────────

_registry: Optional[GeneRulesRegistry] = None
_registry_signature: tuple[int, int, int, int] | None = None
_lock = threading.Lock()


def _path_signature(path: Path) -> tuple[int, int, int, int] | None:
    try:
        current = path.stat()
    except FileNotFoundError:
        return None
    return (
        current.st_dev,
        current.st_ino,
        current.st_size,
        current.st_mtime_ns,
    )


def _load_registry_snapshot(
    path: Path,
) -> tuple[GeneRulesRegistry, tuple[int, int, int, int] | None]:
    registry = GeneRulesRegistry(path=path)
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
        )
    except FileNotFoundError:
        logger.warning("gene_knowledge.json not found at %s; registry empty", path)
        return registry, None
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise RuntimeError("gene knowledge path is not a regular file")
        chunks = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    signature = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    )
    if signature != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ):
        raise RuntimeError("gene knowledge changed while reading")
    try:
        data = json.loads(b"".join(chunks).decode("utf-8"))
    except Exception as exc:
        logger.error("Failed to parse gene_knowledge.json: %s", exc)
        return registry, signature
    registry._load_data(data)
    return registry, signature


def get_registry() -> GeneRulesRegistry:
    global _registry, _registry_signature
    signature = _path_signature(DEFAULT_PATH)
    if (
        _registry is None
        or _registry.path != DEFAULT_PATH
        or _registry_signature != signature
    ):
        with _lock:
            signature = _path_signature(DEFAULT_PATH)
            if (
                _registry is None
                or _registry.path != DEFAULT_PATH
                or _registry_signature != signature
            ):
                _registry, _registry_signature = (
                    _load_registry_snapshot(DEFAULT_PATH)
                )
    return _registry


def reload_from_payload(payload: Dict[str, Any]) -> GeneRulesRegistry:
    """Persist an uploaded gene_knowledge payload and reload the singleton.

    Used by /knowledge/gene-knowledge upload endpoint.
    Accepts either the new gene_knowledge.json shape or the legacy
    gene_drug_rules.json shape (which lacks claims/snp_registry/entities).
    """
    global _registry, _registry_signature
    with _lock:
        path = DEFAULT_PATH
        # Normalize legacy shape into new shape so registry has at least gene_rules.
        if "gene_rules" not in payload and "rules" in payload:
            # Legacy gene_drug_rules.json with high/medium tiers.
            tier_to_phenotype = {"high": "poor", "medium": "intermediate"}
            gene_rules: Dict[str, Dict[str, Dict[str, list]]] = {}
            for gene, tiers in (payload.get("rules") or {}).items():
                gene_bucket: Dict[str, Dict[str, list]] = {}
                for tier_key, tier_block in (tiers or {}).items():
                    phen = tier_to_phenotype.get(tier_key, tier_key)
                    phen_bucket = gene_bucket.setdefault(phen, {})
                    for key in ("avoid", "substitute", "monitor", "supplement", "lifestyle"):
                        if tier_block.get(key):
                            phen_bucket.setdefault(key, []).extend(tier_block[key])
                if gene_bucket:
                    gene_rules[gene] = gene_bucket
            payload = {
                **payload,
                "schema_id": "llm-wiki-v2-gene-knowledge",
                "gene_rules": gene_rules,
                "claims": [],
                "snp_registry": {},
                "entities": {},
                "stats": {
                    "claim_count": 0,
                    "gene_count": len(gene_rules),
                    "snp_count": 0,
                    "entity_counts": {},
                },
            }
        committed_error: AtomicPayloadCommitError | None = None
        try:
            _atomic_write_payload(path, payload)
        except AtomicPayloadCommitError as exc:
            committed_error = exc
        next_registry, next_signature = _load_registry_snapshot(path)
        loaded = next_registry.is_loaded()
        _registry = next_registry
        _registry_signature = next_signature
        if not loaded:
            raise RuntimeError(
                "committed gene knowledge could not be reloaded"
            ) from committed_error
        if committed_error is not None:
            raise committed_error
    return _registry
