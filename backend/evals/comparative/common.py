"""对比评测共享工具 —— transcript 记录结构 + 轻量 HTTP + JSONL 读写。

只读评测。所有网络调用集中在 http_post_json / http_get_json 两个函数,便于测试 mock。
用 stdlib urllib(不引 requests),token 一律走 env,绝不入库/打印。
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_BASE = "https://health.executor.life/api/v1"


def eval_base() -> str:
    return os.environ.get("REVA_EVAL_BASE", DEFAULT_BASE).rstrip("/")


def eval_token() -> str:
    """从 env 读评测 token。缺失 fail-loud —— 绝不回退到硬编码/明文。"""
    tok = os.environ.get("REVA_EVAL_TOKEN", "").strip()
    if not tok:
        raise RuntimeError(
            "缺 REVA_EVAL_TOKEN 环境变量。评测 token 必须经 env 提供,绝不入库。"
        )
    return tok


@dataclass
class Turn:
    """多轮里的一轮。"""

    prompt: str
    answer: str
    latency_ms: int = 0
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Transcript:
    """单臂单题的完整回答记录(可含多轮)。写入 transcripts.jsonl 的一行。"""

    arm: str
    prompt_id: str
    family: str
    answer: str  # 最终/合并回答文本(多轮时是所有轮次拼接,判分主看它 + turns)
    latency_ms: int = 0
    cost: Optional[float] = None  # USD,拿不到则 None
    requires_personal_data: bool = False
    turns: List[Dict[str, Any]] = field(default_factory=list)  # 多轮明细
    meta: Dict[str, Any] = field(default_factory=dict)  # model / tokens / conversation_id 等
    error: Optional[str] = None

    def to_json(self) -> Dict[str, Any]:
        return asdict(self)


def http_post_json(
    url: str,
    payload: Dict[str, Any],
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 90,
) -> Dict[str, Any]:
    """POST JSON,返回 (json_body)。非 2xx 抛 RuntimeError(带 status + body 片段)。"""
    data = json.dumps(payload).encode("utf-8")
    hdrs = {"Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=data, headers=hdrs, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:  # noqa: PERF203
        detail = e.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"HTTP {e.code} {url}: {detail}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"网络错误 {url}: {e}") from e
    try:
        return json.loads(body)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"响应非 JSON {url}: {body[:200]}") from e


def http_get_json(
    url: str, headers: Optional[Dict[str, str]] = None, timeout: int = 60
) -> Dict[str, Any]:
    """GET JSON。非 2xx 抛 RuntimeError。"""
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"HTTP {e.code} {url}: {detail}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"网络错误 {url}: {e}") from e
    return json.loads(body)


def bearer_headers() -> Dict[str, str]:
    return {"Authorization": f"Bearer {eval_token()}"}


def write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    rows: List[Dict[str, Any]] = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as e:
            raise ValueError(f"{path}:{i} 非法 JSON: {e}") from e
    return rows


class Clock:
    """毫秒计时,便于测试注入。"""

    def now_ms(self) -> int:
        return int(time.monotonic() * 1000)
