#!/usr/bin/env python3

from __future__ import annotations

import copy
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "verify_chinese_clip_manifest.py"
SPEC = importlib.util.spec_from_file_location("verify_chinese_clip_manifest", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


REVISION = "a" * 40
SOURCE_REVISION = "b" * 40
SHA256 = "c" * 64


def valid_manifest() -> dict:
    return {
        "schemaVersion": 1,
        "modelId": "OFA-Sys/chinese-clip-rn50",
        "modelRevision": REVISION,
        "checkpoint": {
            "path": ".build/models/chinese-clip-rn50/source/clip_cn_rn50.pt",
            "url": (
                "https://huggingface.co/OFA-Sys/chinese-clip-rn50/resolve/"
                f"{REVISION}/clip_cn_rn50.pt"
            ),
            "sha256": SHA256,
        },
        "sourceCode": {
            "repository": "https://github.com/OFA-Sys/Chinese-CLIP",
            "revision": SOURCE_REVISION,
            "license": "MIT",
            "licensePath": "ThirdPartyNotices/Chinese-CLIP-code-MIT.txt",
            "licenseSha256": SHA256,
        },
        "modelLicense": {
            "spdx": "Apache-2.0",
            "declarationUrl": (
                "https://huggingface.co/OFA-Sys/chinese-clip-rn50/"
                f"blob/{REVISION}/README.md"
            ),
            "licensePath": "ThirdPartyNotices/Chinese-CLIP-model-Apache-2.0.txt",
            "licenseSha256": SHA256,
        },
        "components": {
            "shipped": ["image_encoder"],
            "buildTimeOnly": ["text_encoder", "tokenizer"],
        },
        "artifactRoot": ".build/models/chinese-clip-rn50",
    }


class ManifestContractTests(unittest.TestCase):
    def test_accepts_pinned_image_only_manifest(self) -> None:
        MODULE.validate_manifest(valid_manifest())

    def test_rejects_mutable_model_revision(self) -> None:
        manifest = valid_manifest()
        manifest["modelRevision"] = "main"

        with self.assertRaisesRegex(MODULE.ManifestError, "modelRevision"):
            MODULE.validate_manifest(manifest)

    def test_rejects_checkpoint_url_that_does_not_match_revision(self) -> None:
        manifest = valid_manifest()
        manifest["checkpoint"]["url"] = (
            "https://huggingface.co/OFA-Sys/chinese-clip-rn50/resolve/main/clip_cn_rn50.pt"
        )

        with self.assertRaisesRegex(MODULE.ManifestError, "checkpoint.url"):
            MODULE.validate_manifest(manifest)

    def test_rejects_invalid_hash(self) -> None:
        manifest = valid_manifest()
        manifest["checkpoint"]["sha256"] = "ABC123"

        with self.assertRaisesRegex(MODULE.ManifestError, "checkpoint.sha256"):
            MODULE.validate_manifest(manifest)

    def test_rejects_non_https_source(self) -> None:
        manifest = valid_manifest()
        manifest["sourceCode"]["repository"] = "http://github.com/OFA-Sys/Chinese-CLIP"

        with self.assertRaisesRegex(MODULE.ManifestError, "sourceCode.repository"):
            MODULE.validate_manifest(manifest)

    def test_rejects_unknown_license(self) -> None:
        manifest = valid_manifest()
        manifest["modelLicense"]["spdx"] = "unknown"

        with self.assertRaisesRegex(MODULE.ManifestError, "modelLicense.spdx"):
            MODULE.validate_manifest(manifest)

    def test_rejects_text_encoder_in_shipped_components(self) -> None:
        manifest = valid_manifest()
        manifest["components"] = {
            "shipped": ["image_encoder", "text_encoder"],
            "buildTimeOnly": ["tokenizer"],
        }

        with self.assertRaisesRegex(MODULE.ManifestError, "image encoder"):
            MODULE.validate_manifest(manifest)

    def test_rejects_artifact_root_outside_build_models(self) -> None:
        manifest = valid_manifest()
        manifest["artifactRoot"] = "Models/chinese-clip-rn50"

        with self.assertRaisesRegex(MODULE.ManifestError, "artifactRoot"):
            MODULE.validate_manifest(manifest)

    def test_verify_files_hashes_checkpoint_and_notices(self) -> None:
        manifest = valid_manifest()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkpoint = root / manifest["checkpoint"]["path"]
            code_license = root / manifest["sourceCode"]["licensePath"]
            model_license = root / manifest["modelLicense"]["licensePath"]
            for path, content in (
                (checkpoint, b"checkpoint"),
                (code_license, b"mit"),
                (model_license, b"apache"),
            ):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)

            manifest["checkpoint"]["sha256"] = hashlib.sha256(b"checkpoint").hexdigest()
            manifest["sourceCode"]["licenseSha256"] = hashlib.sha256(b"mit").hexdigest()
            manifest["modelLicense"]["licenseSha256"] = hashlib.sha256(b"apache").hexdigest()

            MODULE.verify_files(manifest, root)

            bad_manifest = copy.deepcopy(manifest)
            bad_manifest["checkpoint"]["sha256"] = "0" * 64
            with self.assertRaisesRegex(MODULE.ManifestError, "checkpoint"):
                MODULE.verify_files(bad_manifest, root)

    def test_load_manifest_rejects_duplicate_json_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text('{"schemaVersion": 1, "schemaVersion": 2}', encoding="utf-8")

            with self.assertRaisesRegex(MODULE.ManifestError, "duplicate"):
                MODULE.load_manifest(path)


if __name__ == "__main__":
    unittest.main()
