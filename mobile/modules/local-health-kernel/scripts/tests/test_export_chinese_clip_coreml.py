#!/usr/bin/env python3

from __future__ import annotations

import gc
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import warnings

import coremltools as ct
import torch
from torch import nn


warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=ResourceWarning)


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "export_chinese_clip_coreml.py"
SPEC = importlib.util.spec_from_file_location("export_chinese_clip_coreml", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


MODEL_REVISION = "7" * 40


class FakeVisual(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.image_projection = nn.Linear(3, 4, bias=False)

    def forward(self, image: torch.Tensor) -> torch.Tensor:
        pooled = image.mean(dim=(2, 3))
        return self.image_projection(pooled)


class FakeClipModel(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.visual = FakeVisual()
        self.text_projection = nn.Linear(8, 4, bias=False)

    def encode_image(self, image: torch.Tensor) -> torch.Tensor:
        return self.visual(image)

    def encode_text(self, text: torch.Tensor) -> torch.Tensor:
        return self.text_projection(text)


class ExportContractTests(unittest.TestCase):
    def test_wrapper_returns_only_unit_normalized_image_embeddings(self) -> None:
        wrapper = MODULE.ImageEncoderWrapper(FakeClipModel()).eval()
        image = torch.rand(2, 3, 4, 4)

        output = wrapper(image)

        self.assertEqual((2, 4), tuple(output.shape))
        self.assertTrue(torch.allclose(output.norm(dim=-1), torch.ones(2), atol=1e-6))

    def test_trace_has_one_image_input_and_no_text_parameters(self) -> None:
        traced = MODULE.trace_image_encoder(FakeClipModel(), image_size=4)
        graph = str(traced.inlined_graph)

        self.assertIn("image_projection", graph)
        self.assertNotIn("text_projection", graph)
        self.assertNotIn("encode_text", graph)

    def test_output_must_remain_under_model_build_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            allowed = root / ".build/models/chinese-clip-rn50/coreml/fp16/Model.mlpackage"
            MODULE.validate_output_path(allowed, root)

            with self.assertRaisesRegex(MODULE.ExportError, "output"):
                MODULE.validate_output_path(root / "Models/Model.mlpackage", root)

    def test_relative_output_is_resolved_against_module_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            relative = Path(
                ".build/models/chinese-clip-rn50/coreml/fp16/Model.mlpackage"
            )

            resolved = MODULE.resolve_output_path(relative, root)

            self.assertEqual((root / relative).resolve(), resolved)

    def test_unknown_compression_variant_is_rejected(self) -> None:
        with self.assertRaisesRegex(MODULE.ExportError, "variant"):
            MODULE.require_variant("fp8")

    def test_metadata_declares_image_only_ios16_contract(self) -> None:
        metadata = MODULE.build_metadata(
            model_revision=MODEL_REVISION,
            checkpoint_sha256="a" * 64,
            variant="fp16",
        )

        self.assertEqual("image_encoder", metadata["com.executor.shippedComponents"])
        self.assertEqual("iOS16", metadata["com.executor.minimumDeploymentTarget"])
        self.assertEqual("image", metadata["com.executor.inputName"])
        self.assertEqual("image_features", metadata["com.executor.outputName"])
        self.assertNotIn("text", json.dumps(metadata).lower().replace("context", ""))

    def test_committed_variants_manifest_preserves_measured_release_contract(self) -> None:
        manifest_path = SCRIPT_PATH.parents[1] / "model-manifests/chinese-clip-coreml-variants.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        fp16 = manifest["variants"]["fp16"]
        int8 = manifest["variants"]["int8"]

        self.assertEqual(["image_encoder"], manifest["shippedComponents"])
        self.assertGreater(fp16["totalInstalledBytes"], manifest["packageBudgetBytes"])
        self.assertLessEqual(int8["totalInstalledBytes"], manifest["packageBudgetBytes"])
        self.assertGreaterEqual(
            int8["parity"]["minimumCosine"], int8["parity"]["tolerance"]
        )
        self.assertEqual(65_536, manifest["compressionPolicy"]["weightThreshold"])

    def test_tiny_conversion_exposes_only_image_and_image_features(self) -> None:
        traced = MODULE.trace_image_encoder(FakeClipModel(), image_size=4)
        metadata = MODULE.build_metadata(MODEL_REVISION, "a" * 64, "fp16")

        model = MODULE.convert_traced_image_encoder(
            traced,
            image_size=4,
            variant="fp16",
            metadata=metadata,
        )

        specification = model.get_spec()
        self.assertEqual(["image"], [item.name for item in specification.description.input])
        self.assertEqual(
            ["image_features"], [item.name for item in specification.description.output]
        )
        self.assertEqual(
            "image_encoder", model.user_defined_metadata["com.executor.shippedComponents"]
        )
        del model
        gc.collect()

    def test_conversion_time_parity_uses_cpu_only_to_avoid_mpsgraph_abort(self) -> None:
        traced = MODULE.trace_image_encoder(FakeClipModel(), image_size=4)
        metadata = MODULE.build_metadata(MODEL_REVISION, "a" * 64, "fp16")

        with mock.patch.object(ct, "convert", wraps=ct.convert) as convert:
            model = MODULE.convert_traced_image_encoder(
                traced,
                image_size=4,
                variant="fp16",
                metadata=metadata,
            )

        self.assertEqual(ct.ComputeUnit.CPU_ONLY, convert.call_args.kwargs["compute_units"])
        del model
        gc.collect()

    def test_int8_uses_frozen_accuracy_preserving_quantization_policy(self) -> None:
        traced = MODULE.trace_image_encoder(FakeClipModel(), image_size=4)
        metadata = MODULE.build_metadata(MODEL_REVISION, "a" * 64, "int8")

        with mock.patch.object(
            ct.optimize.coreml,
            "OpLinearQuantizerConfig",
            wraps=ct.optimize.coreml.OpLinearQuantizerConfig,
        ) as quantizer_config:
            model = MODULE.convert_traced_image_encoder(
                traced,
                image_size=4,
                variant="int8",
                metadata=metadata,
            )

        self.assertEqual("linear", quantizer_config.call_args.kwargs["mode"])
        self.assertEqual(65_536, quantizer_config.call_args.kwargs["weight_threshold"])
        del model
        gc.collect()


if __name__ == "__main__":
    unittest.main()
