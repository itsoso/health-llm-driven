#!/usr/bin/env python3
"""Build a deterministic, identity-only Chinese-CLIP food label bank."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import struct
from typing import Any, Protocol
import unicodedata


MAGIC = b"CCLBV1\x00\x00"
EXPECTED_PROMPT_TEMPLATES = ["{name}", "一张{name}的照片", "一份{name}"]
FORBIDDEN_KEY_TERMS = (
    "calorie",
    "kcal",
    "macro",
    "protein",
    "fat",
    "carb",
    "gram",
    "portion",
    "营养",
    "热量",
    "克",
    "份量",
)
COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")


class LabelBankError(ValueError):
    """Raised when label identity data or generated embeddings are invalid."""


class TextEncoder(Protocol):
    def encode_texts(self, texts: list[str]) -> list[list[float]]: ...


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise LabelBankError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except LabelBankError:
        raise
    except (OSError, json.JSONDecodeError) as error:
        raise LabelBankError(f"cannot load {path}: {error}") from error
    if not isinstance(value, dict):
        raise LabelBankError(f"{path} root must be an object")
    return value


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("utf-8")


def _require_exact_keys(value: dict[str, Any], expected: set[str], field: str) -> None:
    actual = set(value)
    if actual != expected:
        raise LabelBankError(
            f"{field} keys mismatch; missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}"
        )


def _require_nfc_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise LabelBankError(f"{field} must be a non-empty trimmed string")
    if unicodedata.normalize("NFC", value) != value:
        raise LabelBankError(f"{field} must use Unicode NFC")
    return value


def _reject_forbidden_keys(value: Any, path: str = "root") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized_key = unicodedata.normalize("NFC", str(key)).casefold()
            if any(term in normalized_key for term in FORBIDDEN_KEY_TERMS):
                raise LabelBankError(f"forbidden nutrition or portion key at {path}.{key}")
            _reject_forbidden_keys(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_forbidden_keys(child, f"{path}[{index}]")


def validate_label_source(source: dict[str, Any]) -> None:
    _reject_forbidden_keys(source)
    _require_exact_keys(
        source,
        {
            "schemaVersion",
            "labelSetVersion",
            "promptTemplateVersion",
            "promptTemplates",
            "labels",
        },
        "source",
    )
    if source["schemaVersion"] != 1:
        raise LabelBankError("schemaVersion must equal 1")
    _require_nfc_string(source["labelSetVersion"], "labelSetVersion")
    if source["promptTemplateVersion"] != "cn-food-prompts-v1":
        raise LabelBankError("promptTemplateVersion must equal cn-food-prompts-v1")
    if source["promptTemplates"] != EXPECTED_PROMPT_TEMPLATES:
        raise LabelBankError(f"promptTemplates must equal {EXPECTED_PROMPT_TEMPLATES}")

    labels = source["labels"]
    if not isinstance(labels, list) or not labels:
        raise LabelBankError("labels must be a non-empty array")

    canonical_ids: set[str] = set()
    names_and_aliases: set[str] = set()
    for index, raw_label in enumerate(labels):
        if not isinstance(raw_label, dict):
            raise LabelBankError(f"labels[{index}] must be an object")
        _require_exact_keys(
            raw_label,
            {"canonicalFoodId", "name", "aliases", "category", "source"},
            f"labels[{index}]",
        )
        canonical_id = _require_nfc_string(
            raw_label["canonicalFoodId"], f"labels[{index}].canonicalFoodId"
        )
        if canonical_id in canonical_ids:
            raise LabelBankError(f"duplicate canonicalFoodId: {canonical_id}")
        canonical_ids.add(canonical_id)

        aliases = raw_label["aliases"]
        if not isinstance(aliases, list):
            raise LabelBankError(f"labels[{index}].aliases must be an array")
        terms = [_require_nfc_string(raw_label["name"], f"labels[{index}].name")]
        terms.extend(
            _require_nfc_string(alias, f"labels[{index}].aliases[{alias_index}]")
            for alias_index, alias in enumerate(aliases)
        )
        for term in terms:
            normalized_term = unicodedata.normalize("NFC", term).casefold()
            if normalized_term in names_and_aliases:
                raise LabelBankError(f"duplicate name or alias: {term}")
            names_and_aliases.add(normalized_term)

        _require_nfc_string(raw_label["category"], f"labels[{index}].category")
        _require_nfc_string(raw_label["source"], f"labels[{index}].source")


def _unit(vector: list[float]) -> list[float]:
    if not vector or not all(math.isfinite(value) for value in vector):
        raise LabelBankError("encoder vectors must contain finite values")
    norm = math.sqrt(sum(value * value for value in vector))
    if not math.isfinite(norm) or norm <= 0:
        raise LabelBankError("encoder vectors must have a finite non-zero norm")
    return [value / norm for value in vector]


def _mean_unit(vectors: list[list[float]]) -> list[float]:
    if not vectors:
        raise LabelBankError("at least one encoder vector is required")
    dimension = len(vectors[0])
    if dimension == 0 or any(len(vector) != dimension for vector in vectors):
        raise LabelBankError("encoder vector dimension must be stable")
    normalized = [_unit([float(value) for value in vector]) for vector in vectors]
    mean = [sum(vector[index] for vector in normalized) / len(normalized) for index in range(dimension)]
    return _unit(mean)


def _build_labels_and_vectors(
    source: dict[str, Any], encoder: TextEncoder
) -> tuple[list[dict[str, Any]], list[list[float]]]:
    labels: list[dict[str, Any]] = []
    embeddings: list[list[float]] = []
    templates = source["promptTemplates"]
    expected_dimension: int | None = None
    for raw_label in source["labels"]:
        terms = [raw_label["name"], *raw_label["aliases"]]
        prompts = [template.format(name=term) for term in terms for template in templates]
        encoded = encoder.encode_texts(prompts)
        if len(encoded) != len(prompts):
            raise LabelBankError("encoder must return one vector per prompt")
        embedding = _mean_unit(encoded)
        if expected_dimension is None:
            expected_dimension = len(embedding)
        elif len(embedding) != expected_dimension:
            raise LabelBankError("encoder vector dimension must be stable across labels")
        labels.append(
            {
                "aliases": raw_label["aliases"],
                "canonicalFoodId": raw_label["canonicalFoodId"],
                "category": raw_label["category"],
                "name": raw_label["name"],
                "source": raw_label["source"],
            }
        )
        embeddings.append(embedding)
    return labels, embeddings


def build_label_bank_bytes(
    source: dict[str, Any], encoder: TextEncoder, model_revision: str
) -> bytes:
    validate_label_source(source)
    if not COMMIT_PATTERN.fullmatch(model_revision):
        raise LabelBankError("modelRevision must be a full lowercase 40-character commit")
    labels, embeddings = _build_labels_and_vectors(source, encoder)
    dimension = len(embeddings[0])
    header = {
        "embeddingDimension": dimension,
        "embeddingEncoding": "float32-little-endian",
        "labelSetVersion": source["labelSetVersion"],
        "labels": labels,
        "modelRevision": model_revision,
        "normalized": True,
        "promptTemplateVersion": source["promptTemplateVersion"],
        "schemaVersion": 1,
    }
    header_bytes = canonical_json_bytes(header)
    vector_bytes = b"".join(
        struct.pack(f"<{dimension}f", *embedding) for embedding in embeddings
    )
    return MAGIC + struct.pack("<I", len(header_bytes)) + header_bytes + vector_bytes


def parse_label_bank_bytes(value: bytes) -> dict[str, Any]:
    if len(value) < len(MAGIC) + 4 or value[: len(MAGIC)] != MAGIC:
        raise LabelBankError("invalid label bank magic")
    header_length = struct.unpack_from("<I", value, len(MAGIC))[0]
    header_start = len(MAGIC) + 4
    header_end = header_start + header_length
    if header_end > len(value):
        raise LabelBankError("truncated label bank header")
    try:
        header = json.loads(value[header_start:header_end].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise LabelBankError(f"invalid label bank header: {error}") from error
    dimension = header.get("embeddingDimension")
    labels = header.get("labels")
    if not isinstance(dimension, int) or dimension <= 0 or not isinstance(labels, list):
        raise LabelBankError("invalid label bank header fields")
    expected_vector_bytes = len(labels) * dimension * 4
    if len(value) - header_end != expected_vector_bytes:
        raise LabelBankError("label bank vector payload length mismatch")
    embeddings = [
        list(struct.unpack_from(f"<{dimension}f", value, header_end + index * dimension * 4))
        for index in range(len(labels))
    ]
    return {**header, "embeddings": embeddings}


def build_output_manifest(
    source: dict[str, Any], source_bytes: bytes, output: bytes, model_revision: str
) -> dict[str, Any]:
    parsed = parse_label_bank_bytes(output)
    return {
        "schemaVersion": 1,
        "labelSetVersion": source["labelSetVersion"],
        "promptTemplateVersion": source["promptTemplateVersion"],
        "modelRevision": model_revision,
        "sourcePath": "ModelSources/chinese-clip-food-labels-v1.json",
        "sourceSha256": hashlib.sha256(source_bytes).hexdigest(),
        "outputPath": ".build/models/chinese-clip-rn50/chinese-clip-label-bank-v1.bin",
        "outputSha256": hashlib.sha256(output).hexdigest(),
        "rowCount": len(parsed["labels"]),
        "embeddingDimension": parsed["embeddingDimension"],
        "format": "CCLBV1",
        "normalized": True,
    }


def _load_manifest_verifier() -> Any:
    path = Path(__file__).with_name("verify_chinese_clip_manifest.py")
    spec = importlib.util.spec_from_file_location("verify_chinese_clip_manifest", path)
    if spec is None or spec.loader is None:
        raise LabelBankError(f"cannot import manifest verifier at {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ChineseClipTextEncoder:
    def __init__(self, checkpoint_directory: Path) -> None:
        try:
            import torch
            from cn_clip.clip import load_from_name, tokenize
        except ImportError as error:
            raise LabelBankError(
                "real label generation requires pinned torch and cn_clip dependencies"
            ) from error
        self._torch = torch
        self._tokenize = tokenize
        self._model, _ = load_from_name(
            "RN50", device="cpu", download_root=str(checkpoint_directory)
        )
        self._model.eval()

    def encode_texts(self, texts: list[str]) -> list[list[float]]:
        tokens = self._tokenize(texts).to("cpu")
        with self._torch.no_grad():
            vectors = self._model.encode_text(tokens)
        return vectors.detach().float().cpu().tolist()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-manifest", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--output-manifest", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    verifier = _load_manifest_verifier()
    model_manifest = verifier.load_manifest(args.model_manifest)
    verifier.verify_files(model_manifest, Path(__file__).resolve().parents[1])

    source = load_json(args.labels)
    source_bytes = args.labels.read_bytes()
    checkpoint = Path(__file__).resolve().parents[1] / model_manifest["checkpoint"]["path"]
    encoder = ChineseClipTextEncoder(checkpoint.parent)
    output = build_label_bank_bytes(source, encoder, model_manifest["modelRevision"])
    manifest = build_output_manifest(source, source_bytes, output, model_manifest["modelRevision"])

    expected_output = Path(__file__).resolve().parents[1] / manifest["outputPath"]
    if args.output.resolve() != expected_output.resolve():
        raise LabelBankError(f"output must equal {expected_output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output)
    args.output_manifest.parent.mkdir(parents=True, exist_ok=True)
    args.output_manifest.write_bytes(canonical_json_bytes(manifest))
    print(
        json.dumps(
            {
                "embeddingDimension": manifest["embeddingDimension"],
                "labelSetVersion": manifest["labelSetVersion"],
                "outputSha256": manifest["outputSha256"],
                "rowCount": manifest["rowCount"],
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except LabelBankError as error:
        raise SystemExit(f"label bank build failed: {error}") from error
