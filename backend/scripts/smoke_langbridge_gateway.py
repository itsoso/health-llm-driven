#!/usr/bin/env python3
"""LangBridge Gateway 端到端烟测.

从 health 这一侧, 用 OpenAI 兼容协议串到 browser-llm-orchestrator 的
`/api/llm/chat/completions`, 验证四件事 (任一失败脚本 exit code 非零):

1. GET  /api/llm/health           — gateway 探活
2. GET  /api/llm/models           — Bearer auth + 模型清单含 commercial/*
3. POST /api/llm/chat/completions — 非流式纯文本
4. POST /api/llm/chat/completions — SSE 流式
5. POST /api/llm/chat/completions — 多模态 (生成一张 8x8 红色 PNG, 走 base64)

用法:
  export LANGBRIDGE_GATEWAY_BASE_URL=https://base.executor.life/api/llm
  export LANGBRIDGE_GATEWAY_API_KEY=<the token>
  python3 backend/scripts/smoke_langbridge_gateway.py
  python3 backend/scripts/smoke_langbridge_gateway.py --model commercial/GPT-5.5
  python3 backend/scripts/smoke_langbridge_gateway.py --skip-vision  # 模型不支持图片时

退出码: 0=全过, 1=至少一项失败.
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import struct
import sys
import time
import urllib.error
import urllib.request
import zlib

DEFAULT_MODEL = "commercial/Claude-Opus-4.7"


# ── 工具 ────────────────────────────────────────────────

ANSI_GREEN = "\033[32m"
ANSI_RED = "\033[31m"
ANSI_DIM = "\033[2m"
ANSI_RESET = "\033[0m"


def _pass(name: str, detail: str = "") -> None:
    msg = f"{ANSI_GREEN}✔{ANSI_RESET} {name}"
    if detail:
        msg += f"  {ANSI_DIM}{detail}{ANSI_RESET}"
    print(msg)


def _fail(name: str, err: str) -> None:
    print(f"{ANSI_RED}✘{ANSI_RESET} {name}\n  {ANSI_RED}{err}{ANSI_RESET}")


def _http(
    method: str,
    url: str,
    token: str,
    body: dict | None = None,
    timeout: int = 60,
    stream: bool = False,
):
    """轻量 HTTP — 不依赖 health 的 httpx, 让脚本能在裸机 python3 跑."""
    headers = {"Authorization": f"Bearer {token}"}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    return urllib.request.urlopen(req, timeout=timeout)


def _make_red_png() -> bytes:
    """8x8 全红 PNG, 不依赖 PIL — 直接 zlib + 4-byte CRC PNG chunks."""
    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", 8, 8, 8, 2, 0, 0, 0)  # 8x8, 8-bit RGB
    # 8 rows of (filter=0) + 8 pixels of RGB (255,0,0)
    raw = b"".join(b"\x00" + b"\xff\x00\x00" * 8 for _ in range(8))
    idat = zlib.compress(raw, 9)
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


# ── 测试用例 ────────────────────────────────────────────

def test_health(base_url: str, token: str) -> bool:
    name = "GET /api/llm/health"
    try:
        with _http("GET", f"{base_url}/health", token, timeout=10) as r:
            payload = json.loads(r.read().decode())
            assert payload.get("ok") is True, payload
            assert payload.get("token_configured") is True, "gateway 未配置 LLM_GATEWAY_TOKEN"
        _pass(name, f"models={payload.get('exposed_models')}")
        return True
    except Exception as e:
        _fail(name, str(e))
        return False


def test_models(base_url: str, token: str) -> bool:
    name = "GET /api/llm/models"
    try:
        with _http("GET", f"{base_url}/models", token, timeout=10) as r:
            payload = json.loads(r.read().decode())
        ids = {m["id"] for m in payload.get("data", [])}
        assert "commercial/Claude-Opus-4.7" in ids
        assert "commercial/GPT-5.5" in ids
        assert "commercial/Gemini-3.1-Pro-Preview" in ids
        _pass(name, f"{len(ids)} models, 含三家商用")
        return True
    except Exception as e:
        _fail(name, str(e))
        return False


def test_auth_rejects_no_token(base_url: str) -> bool:
    name = "GET /api/llm/models without token → 401"
    try:
        try:
            _http("GET", f"{base_url}/models", token="")
        except urllib.error.HTTPError as e:
            assert e.code == 401, f"expected 401, got {e.code}"
            _pass(name)
            return True
        _fail(name, "expected 401, got 200")
        return False
    except Exception as e:
        _fail(name, str(e))
        return False


def test_non_stream(base_url: str, token: str, model: str) -> bool:
    name = f"POST /api/llm/chat/completions (non-stream, {model})"
    body = {
        "model": model,
        "messages": [{"role": "user", "content": "回复就一个字: 好"}],
        "max_tokens": 50,
        "stream": False,
    }
    t0 = time.perf_counter()
    try:
        with _http("POST", f"{base_url}/chat/completions", token, body=body, timeout=120) as r:
            payload = json.loads(r.read().decode())
        choices = payload.get("choices", [])
        assert choices, f"no choices in response: {payload}"
        text = choices[0].get("message", {}).get("content", "")
        assert text.strip(), f"empty content: {payload}"
        usage = payload.get("usage", {})
        elapsed = time.perf_counter() - t0
        _pass(name, f"{elapsed:.1f}s, tokens={usage.get('total_tokens')}, reply={text[:60]!r}")
        return True
    except Exception as e:
        _fail(name, str(e))
        return False


def test_stream(base_url: str, token: str, model: str) -> bool:
    name = f"POST /api/llm/chat/completions (stream, {model})"
    body = {
        "model": model,
        "messages": [{"role": "user", "content": "数到 3, 一行一个数字"}],
        "max_tokens": 50,
        "stream": True,
    }
    t0 = time.perf_counter()
    try:
        with _http("POST", f"{base_url}/chat/completions", token, body=body, timeout=120) as r:
            raw = r.read().decode("utf-8", errors="replace")
        chunks_seen = 0
        delta_text_parts: list[str] = []
        saw_done = False
        for line in raw.splitlines():
            if not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str.strip() == "[DONE]":
                saw_done = True
                continue
            try:
                chunk = json.loads(data_str)
            except json.JSONDecodeError:
                continue
            chunks_seen += 1
            for ch in chunk.get("choices", []):
                token_text = ch.get("delta", {}).get("content", "") or ""
                if token_text:
                    delta_text_parts.append(token_text)
        assert chunks_seen > 0, f"no SSE chunks parsed from {raw[:200]!r}"
        assert saw_done, "missing [DONE] sentinel"
        full = "".join(delta_text_parts)
        elapsed = time.perf_counter() - t0
        _pass(
            name,
            f"{elapsed:.1f}s, {chunks_seen} chunks, content={full[:60]!r}",
        )
        return True
    except Exception as e:
        _fail(name, str(e))
        return False


def test_vision(base_url: str, token: str, model: str) -> bool:
    name = f"POST /api/llm/chat/completions (vision base64, {model})"
    png_bytes = _make_red_png()
    data_uri = "data:image/png;base64," + base64.b64encode(png_bytes).decode()
    body = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "这张小图主要是什么颜色? 一个词回答."},
                    {"type": "image_url", "image_url": {"url": data_uri}},
                ],
            }
        ],
        "max_tokens": 30,
        "stream": False,
    }
    t0 = time.perf_counter()
    try:
        with _http("POST", f"{base_url}/chat/completions", token, body=body, timeout=180) as r:
            payload = json.loads(r.read().decode())
        text = payload.get("choices", [{}])[0].get("message", {}).get("content", "")
        assert text.strip(), f"empty reply: {payload}"
        elapsed = time.perf_counter() - t0
        # 注意: 不强校验模型是否回答了"红色" — 烟测只验链路通畅, 不验内容质量
        _pass(name, f"{elapsed:.1f}s, reply={text[:60]!r}")
        return True
    except Exception as e:
        _fail(name, str(e))
        return False


# ── main ────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--base-url",
        default=os.environ.get("LANGBRIDGE_GATEWAY_BASE_URL", ""),
        help="gateway base URL (default: $LANGBRIDGE_GATEWAY_BASE_URL)",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("LANGBRIDGE_GATEWAY_API_KEY", ""),
        help="bearer token (default: $LANGBRIDGE_GATEWAY_API_KEY)",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("LANGBRIDGE_SMOKE_MODEL", DEFAULT_MODEL),
        help=f"model id (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--skip-vision",
        action="store_true",
        help="跳过 vision 测试 (模型不支持图片时)",
    )
    parser.add_argument(
        "--skip-stream",
        action="store_true",
        help="跳过流式测试 (远端代理可能 buffer SSE)",
    )
    args = parser.parse_args()

    if not args.base_url or not args.token:
        print(
            f"{ANSI_RED}缺少配置{ANSI_RESET}: 请设 LANGBRIDGE_GATEWAY_BASE_URL + "
            f"LANGBRIDGE_GATEWAY_API_KEY (或用 --base-url / --token 显式传)",
            file=sys.stderr,
        )
        return 2

    base_url = args.base_url.rstrip("/")
    token = args.token

    print(f"Gateway: {base_url}")
    print(f"Model:   {args.model}\n")

    results: list[bool] = []
    results.append(test_health(base_url, token))
    results.append(test_auth_rejects_no_token(base_url))
    results.append(test_models(base_url, token))
    results.append(test_non_stream(base_url, token, args.model))
    if not args.skip_stream:
        results.append(test_stream(base_url, token, args.model))
    if not args.skip_vision:
        results.append(test_vision(base_url, token, args.model))

    passed = sum(1 for r in results if r)
    total = len(results)
    print()
    if passed == total:
        print(f"{ANSI_GREEN}全部 {total} 项通过{ANSI_RESET}")
        return 0
    print(f"{ANSI_RED}{total - passed}/{total} 项失败{ANSI_RESET}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
