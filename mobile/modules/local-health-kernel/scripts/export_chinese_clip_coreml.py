#!/usr/bin/env python3
"""Export the pinned Chinese-CLIP RN50 image tower to Core ML."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
from typing import Any


MODEL_ID = "OFA-Sys/chinese-clip-rn50"
MODEL_ARCHITECTURE = "RN50"
IMAGE_SIZE = 224
ALLOWED_VARIANTS = {"fp16", "int8"}
CHECKPOINT_PATTERN = re.compile(r"[0-9a-f]{64}")
COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")
CLIP_MEAN = [0.48145466, 0.4578275, 0.40821073]
CLIP_STD = [0.26862954, 0.26130258, 0.27577711]
PARITY_TOLERANCE = {"fp16": 0.999, "int8": 0.99}


class ExportError(ValueError):
    """Raised when conversion would violate the image-only artifact contract."""


def require_variant(value: str) -> str:
    if value not in ALLOWED_VARIANTS:
        raise ExportError(f"variant must be one of {sorted(ALLOWED_VARIANTS)}")
    return value


def resolve_output_path(output: Path, module_root: Path) -> Path:
    if output.is_absolute():
        return output.resolve()
    return (module_root.resolve() / output).resolve()


def validate_output_path(output: Path, module_root: Path) -> None:
    output = resolve_output_path(output, module_root)
    allowed_root = (
        module_root.resolve() / ".build/models/chinese-clip-rn50/coreml"
    ).resolve()
    if output.suffix != ".mlpackage":
        raise ExportError("output must use the .mlpackage suffix")
    if output == allowed_root or allowed_root not in output.parents:
        raise ExportError(f"output must remain under {allowed_root}")


def build_metadata(
    model_revision: str, checkpoint_sha256: str, variant: str
) -> dict[str, str]:
    if not COMMIT_PATTERN.fullmatch(model_revision):
        raise ExportError("modelRevision must be a full lowercase commit")
    if not CHECKPOINT_PATTERN.fullmatch(checkpoint_sha256):
        raise ExportError("checkpointSha256 must be a lowercase SHA-256")
    require_variant(variant)
    return {
        "com.executor.checkpointSha256": checkpoint_sha256,
        "com.executor.inputName": "image",
        "com.executor.inputNormalization": json.dumps(
            {"mean": CLIP_MEAN, "std": CLIP_STD}, separators=(",", ":"), sort_keys=True
        ),
        "com.executor.minimumDeploymentTarget": "iOS16",
        "com.executor.modelId": MODEL_ID,
        "com.executor.modelRevision": model_revision,
        "com.executor.outputL2Normalized": "true",
        "com.executor.outputName": "image_features",
        "com.executor.parityComputeUnits": "CPU_ONLY",
        "com.executor.precisionVariant": variant,
        "com.executor.shippedComponents": "image_encoder",
    }


def _dependencies() -> tuple[Any, Any, Any]:
    try:
        import coremltools as ct
        import torch
        from torch import nn
    except ImportError as error:
        raise ExportError("export requires pinned torch and coremltools dependencies") from error
    return ct, torch, nn


class ImageEncoderWrapper:
    """Own only the visual tower so traced state cannot retain text parameters."""

    def __new__(cls, clip_model: Any) -> Any:
        _, torch, nn = _dependencies()

        class _ImageOnlyModule(nn.Module):
            def __init__(self, visual: Any) -> None:
                super().__init__()
                self.visual = visual

            def forward(self, image: Any) -> Any:
                features = self.visual(image)
                return torch.nn.functional.normalize(features.float(), p=2, dim=-1)

        visual = getattr(clip_model, "visual", None)
        if visual is None:
            raise ExportError("Chinese-CLIP model must expose a visual tower")
        return _ImageOnlyModule(visual)


def trace_image_encoder(clip_model: Any, image_size: int = IMAGE_SIZE) -> Any:
    _, torch, _ = _dependencies()
    if not isinstance(image_size, int) or image_size <= 0:
        raise ExportError("image_size must be a positive integer")
    wrapper = ImageEncoderWrapper(clip_model).float().eval()
    dummy_image = torch.linspace(
        0.0,
        1.0,
        steps=3 * image_size * image_size,
        dtype=torch.float32,
    ).reshape(1, 3, image_size, image_size)
    with torch.no_grad():
        return torch.jit.trace(wrapper, dummy_image, strict=True)


def convert_traced_image_encoder(
    traced_model: Any,
    image_size: int,
    variant: str,
    metadata: dict[str, str],
) -> Any:
    ct, _, _ = _dependencies()
    require_variant(variant)
    base_model = ct.convert(
        traced_model,
        inputs=[ct.TensorType(name="image", shape=(1, 3, image_size, image_size))],
        outputs=[ct.TensorType(name="image_features")],
        convert_to="mlprogram",
        compute_precision=ct.precision.FLOAT16,
        minimum_deployment_target=ct.target.iOS16,
        compute_units=ct.ComputeUnit.CPU_ONLY,
    )
    if variant == "int8":
        optimization_config = ct.optimize.coreml.OptimizationConfig(
            global_config=ct.optimize.coreml.OpLinearQuantizerConfig(
                mode="linear",
                dtype="int8",
                granularity="per_channel",
                weight_threshold=65_536,
            )
        )
        base_model = ct.optimize.coreml.linear_quantize_weights(
            base_model, config=optimization_config
        )
    base_model.user_defined_metadata.update(metadata)
    return base_model


def _load_manifest_verifier() -> Any:
    path = Path(__file__).with_name("verify_chinese_clip_manifest.py")
    spec = importlib.util.spec_from_file_location("verify_chinese_clip_manifest", path)
    if spec is None or spec.loader is None:
        raise ExportError(f"cannot import manifest verifier at {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_pinned_clip_model(checkpoint_path: Path) -> Any:
    _, torch, _ = _dependencies()
    try:
        from cn_clip.clip.utils import _MODEL_INFO, create_model
    except ImportError as error:
        raise ExportError("pinned cn_clip source package is unavailable") from error
    try:
        with checkpoint_path.open("rb") as handle:
            checkpoint = torch.load(handle, map_location="cpu")
    except (OSError, RuntimeError) as error:
        raise ExportError(f"cannot load checkpoint {checkpoint_path}: {error}") from error
    model = create_model(_MODEL_INFO[MODEL_ARCHITECTURE]["struct"], checkpoint)
    return model.float().eval()


def _parity_inputs() -> list[Any]:
    _, torch, _ = _dependencies()
    base = torch.linspace(
        -1.0,
        1.0,
        steps=3 * IMAGE_SIZE * IMAGE_SIZE,
        dtype=torch.float32,
    ).reshape(1, 3, IMAGE_SIZE, IMAGE_SIZE)
    return [base, base.flip(-1), base.flip(-2)]


def measure_parity(traced_model: Any, coreml_model: Any, variant: str) -> dict[str, Any]:
    _, torch, _ = _dependencies()
    cosine_values: list[float] = []
    for image in _parity_inputs():
        with torch.no_grad():
            expected = traced_model(image).detach().float().cpu().numpy()[0]
        prediction = coreml_model.predict({"image": image.cpu().numpy()})
        actual = prediction["image_features"]
        actual = actual.reshape(-1)
        expected_norm = math.sqrt(float((expected * expected).sum()))
        actual_norm = math.sqrt(float((actual * actual).sum()))
        if expected_norm <= 0 or actual_norm <= 0:
            raise ExportError("parity output must have non-zero norm")
        cosine = float((expected * actual).sum()) / (expected_norm * actual_norm)
        if not math.isfinite(cosine):
            raise ExportError("parity cosine must be finite")
        cosine_values.append(cosine)
    minimum_cosine = min(cosine_values)
    tolerance = PARITY_TOLERANCE[variant]
    if minimum_cosine < tolerance:
        raise ExportError(
            f"{variant} parity {minimum_cosine:.8f} is below frozen tolerance {tolerance}"
        )
    return {
        "caseCount": len(cosine_values),
        "minimumCosine": minimum_cosine,
        "tolerance": tolerance,
    }


def _directory_size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-manifest", type=Path, required=True)
    parser.add_argument("--variant", choices=sorted(ALLOWED_VARIANTS), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--parity-report", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    module_root = Path(__file__).resolve().parents[1]
    validate_output_path(args.output, module_root)
    output_path = resolve_output_path(args.output, module_root)
    verifier = _load_manifest_verifier()
    manifest = verifier.load_manifest(args.model_manifest)
    verifier.verify_files(manifest, module_root)

    checkpoint_path = module_root / manifest["checkpoint"]["path"]
    clip_model = load_pinned_clip_model(checkpoint_path)
    traced = trace_image_encoder(clip_model)
    metadata = build_metadata(
        manifest["modelRevision"], manifest["checkpoint"]["sha256"], args.variant
    )
    coreml_model = convert_traced_image_encoder(
        traced, image_size=IMAGE_SIZE, variant=args.variant, metadata=metadata
    )
    parity = measure_parity(traced, coreml_model, args.variant)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    coreml_model.save(str(output_path))
    report = {
        "schemaVersion": 1,
        "modelId": manifest["modelId"],
        "modelRevision": manifest["modelRevision"],
        "checkpointSha256": manifest["checkpoint"]["sha256"],
        "variant": args.variant,
        "minimumDeploymentTarget": "iOS16",
        "input": {"name": "image", "shape": [1, 3, IMAGE_SIZE, IMAGE_SIZE]},
        "output": {"name": "image_features", "l2Normalized": True},
        "shippedComponents": ["image_encoder"],
        "artifactPath": str(output_path.relative_to(module_root)),
        "artifactBytes": _directory_size(output_path),
        "artifactSha256": _hash_directory(output_path),
        "parity": parity,
        "conversion": {
            "coremltools": _dependencies()[0].__version__,
            "parityComputeUnits": "CPU_ONLY",
            "torch": _dependencies()[1].__version__,
        },
    }
    args.parity_report.parent.mkdir(parents=True, exist_ok=True)
    args.parity_report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
    return 0


def _hash_directory(path: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(candidate for candidate in path.rglob("*") if candidate.is_file()):
        digest.update(item.relative_to(path).as_posix().encode("utf-8"))
        digest.update(b"\x00")
        with item.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ExportError as error:
        raise SystemExit(f"Core ML export failed: {error}") from error
