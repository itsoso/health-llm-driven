#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import math
from pathlib import Path
import unittest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "build_chinese_clip_label_bank.py"
SPEC = importlib.util.spec_from_file_location("build_chinese_clip_label_bank", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


MODEL_REVISION = "7" * 40


def valid_source() -> dict:
    return {
        "schemaVersion": 2,
        "labelSetVersion": "cn-food-labels-v2",
        "promptTemplateVersion": "cn-food-prompts-v2",
        "promptTemplates": {
            "food": ["{name}", "一张{name}的照片", "一份{name}"],
            "non_food": ["{name}", "一张{name}", "这张照片是{name}，不是食物"],
        },
        "labels": [
            {
                "canonicalFoodId": "food.rice.cooked.white",
                "name": "白米饭",
                "aliases": ["米饭"],
                "category": "staple",
                "source": "owner_authored",
            },
            {
                "canonicalFoodId": "non_food.screen",
                "name": "电子屏幕",
                "aliases": ["手机屏幕"],
                "category": "non_food",
                "source": "owner_authored",
            },
        ],
    }


class FakeEncoder:
    def encode_texts(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            codepoints = [ord(character) for character in text]
            vectors.append(
                [
                    float(sum(codepoints) % 101 + 1),
                    float(len(text) + 1),
                    float(sum(codepoints[::2]) % 97 + 1),
                    float(sum(codepoints[1::2]) % 89 + 1),
                ]
            )
        return vectors


class RecordingEncoder(FakeEncoder):
    def __init__(self) -> None:
        self.texts: list[str] = []

    def encode_texts(self, texts: list[str]) -> list[list[float]]:
        self.texts.extend(texts)
        return super().encode_texts(texts)


class NonFiniteEncoder:
    def encode_texts(self, texts: list[str]) -> list[list[float]]:
        return [[math.nan, 1.0] for _ in texts]


class InconsistentEncoder:
    def encode_texts(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 2.0] if index == 0 else [1.0] for index, _ in enumerate(texts)]


class LabelSourceContractTests(unittest.TestCase):
    def test_committed_source_is_valid(self) -> None:
        source_path = SCRIPT_PATH.parents[1] / "ModelSources/chinese-clip-food-labels-v2.json"
        source = MODULE.load_json(source_path)
        MODULE.validate_label_source(source)
        self.assertTrue(any(label["category"] == "non_food" for label in source["labels"]))

    def test_accepts_identity_only_source(self) -> None:
        MODULE.validate_label_source(valid_source())

    def test_rejects_duplicate_canonical_id(self) -> None:
        source = valid_source()
        source["labels"][1]["canonicalFoodId"] = source["labels"][0]["canonicalFoodId"]

        with self.assertRaisesRegex(MODULE.LabelBankError, "canonicalFoodId"):
            MODULE.validate_label_source(source)

    def test_rejects_duplicate_alias_after_unicode_normalization(self) -> None:
        source = valid_source()
        source["labels"][1]["aliases"] = ["米\u996d"]
        source["labels"][0]["aliases"] = ["米饭"]

        with self.assertRaisesRegex(MODULE.LabelBankError, "name or alias"):
            MODULE.validate_label_source(source)

    def test_rejects_non_normalized_text(self) -> None:
        source = valid_source()
        source["labels"][0]["name"] = "Cafe\u0301"

        with self.assertRaisesRegex(MODULE.LabelBankError, "Unicode NFC"):
            MODULE.validate_label_source(source)

    def test_rejects_empty_source(self) -> None:
        source = valid_source()
        source["labels"][0]["source"] = ""

        with self.assertRaisesRegex(MODULE.LabelBankError, "source"):
            MODULE.validate_label_source(source)

    def test_rejects_nutrition_or_portion_keys_recursively(self) -> None:
        for forbidden_key in ("kcal", "protein", "portionGrams", "营养", "份量"):
            with self.subTest(forbidden_key=forbidden_key):
                source = valid_source()
                source["labels"][0]["metadata"] = {forbidden_key: 10}
                with self.assertRaisesRegex(MODULE.LabelBankError, "forbidden"):
                    MODULE.validate_label_source(source)

    def test_rejects_prompt_template_drift(self) -> None:
        source = valid_source()
        source["promptTemplates"]["non_food"] = ["这是什么：{name}"]

        with self.assertRaisesRegex(MODULE.LabelBankError, "promptTemplates"):
            MODULE.validate_label_source(source)

    def test_rejects_food_and_non_food_id_category_mismatch(self) -> None:
        for canonical_id, category in [
            ("non_food.screen", "dish"),
            ("food.rice.cooked.white", "non_food"),
        ]:
            with self.subTest(canonical_id=canonical_id, category=category):
                source = valid_source()
                source["labels"][0]["canonicalFoodId"] = canonical_id
                source["labels"][0]["category"] = category
                with self.assertRaisesRegex(MODULE.LabelBankError, "non_food|food"):
                    MODULE.validate_label_source(source)


class LabelBankBuildTests(unittest.TestCase):
    def test_build_is_byte_deterministic_and_vectors_are_unit_length(self) -> None:
        source = valid_source()
        first = MODULE.build_label_bank_bytes(source, FakeEncoder(), MODEL_REVISION)
        second = MODULE.build_label_bank_bytes(source, FakeEncoder(), MODEL_REVISION)

        self.assertEqual(first, second)
        parsed = MODULE.parse_label_bank_bytes(first)
        self.assertEqual(2, len(parsed["labels"]))
        self.assertEqual(4, parsed["embeddingDimension"])
        for vector in parsed["embeddings"]:
            self.assertAlmostEqual(1.0, math.sqrt(sum(value * value for value in vector)), places=6)

    def test_aliases_contribute_to_the_label_embedding(self) -> None:
        with_alias = valid_source()
        without_alias = valid_source()
        without_alias["labels"][0]["aliases"] = []

        first = MODULE.parse_label_bank_bytes(
            MODULE.build_label_bank_bytes(with_alias, FakeEncoder(), MODEL_REVISION)
        )
        second = MODULE.parse_label_bank_bytes(
            MODULE.build_label_bank_bytes(without_alias, FakeEncoder(), MODEL_REVISION)
        )

        self.assertNotEqual(first["embeddings"][0], second["embeddings"][0])

    def test_non_food_labels_use_the_frozen_negative_prompt_family(self) -> None:
        source = valid_source()
        encoder = RecordingEncoder()

        MODULE.build_label_bank_bytes(source, encoder, MODEL_REVISION)

        self.assertIn("一份白米饭", encoder.texts)
        self.assertIn("这张照片是电子屏幕，不是食物", encoder.texts)
        self.assertNotIn("一份电子屏幕", encoder.texts)

    def test_rejects_non_finite_encoder_output(self) -> None:
        with self.assertRaisesRegex(MODULE.LabelBankError, "finite"):
            MODULE.build_label_bank_bytes(valid_source(), NonFiniteEncoder(), MODEL_REVISION)

    def test_rejects_inconsistent_embedding_dimensions(self) -> None:
        with self.assertRaisesRegex(MODULE.LabelBankError, "dimension"):
            MODULE.build_label_bank_bytes(valid_source(), InconsistentEncoder(), MODEL_REVISION)

    def test_manifest_is_derived_from_exact_source_and_output_bytes(self) -> None:
        source = valid_source()
        source_bytes = MODULE.canonical_json_bytes(source)
        output = MODULE.build_label_bank_bytes(source, FakeEncoder(), MODEL_REVISION)

        manifest = MODULE.build_output_manifest(source, source_bytes, output, MODEL_REVISION)

        self.assertEqual(2, manifest["rowCount"])
        self.assertEqual(4, manifest["embeddingDimension"])
        self.assertEqual(MODEL_REVISION, manifest["modelRevision"])
        self.assertEqual(
            "ModelSources/chinese-clip-food-labels-v2.json",
            manifest["sourcePath"],
        )
        self.assertEqual(
            ".build/models/chinese-clip-rn50/chinese-clip-label-bank-v2.bin",
            manifest["outputPath"],
        )
        self.assertRegex(manifest["sourceSha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(manifest["outputSha256"], r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
