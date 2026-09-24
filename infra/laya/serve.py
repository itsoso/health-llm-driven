"""Offline, CPU-only, loopback System One service for the Reva host."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
manifest = json.loads((ROOT / "model-manifest.json").read_text())
key = os.environ.get("LAYA_API_KEY", "")
if len(key) < 32 or not key.isascii():
    raise RuntimeError("A private Laya bearer key is required")
os.environ.update({
    "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
    "HF_HUB_DISABLE_IMPLICIT_TOKEN": "1", "HF_HUB_DISABLE_TELEMETRY": "1",
    "TOKENIZERS_PARALLELISM": "false", "LAYA_DEVICE": "cpu",
})

import torch
import uvicorn
from laya import Router
from laya.serve import create_app

torch.set_num_threads(2)
torch.set_num_interop_threads(1)


class PinnedRouter(Router):
    def predict(self, state, questions, *, model=None, **kwargs):
        if model not in (None, "multilingual"):
            raise ValueError("Only the multilingual model is deployed")
        result = super().predict(state, questions, model="multilingual", **kwargs)
        result["model"] = "laya-multilingual@" + manifest["revision"][:12]
        result.pop("routing", None)
        return result


router = PinnedRouter(
    models={"multilingual": str(ROOT / "models/multilingual")},
    default="multilingual", device="cpu", max_loaded=1,
)
router.preload(["multilingual"])
uvicorn.run(create_app(router), host="127.0.0.1", port=8092,
            access_log=False, limit_concurrency=8)
