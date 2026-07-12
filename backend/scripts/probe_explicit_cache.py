#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""真网络探针: DashScope compatible-mode 的**显式上下文缓存** (Phase-2 rank3) 是否真生效。

背景 (合成轮 prefill 税):
  agent 主循环把 user 消息留在前部, 后续每轮追加工具结果到尾部 → 合成轮 (round2) 要**重新
  prefill** 那条 ~7.3k-16k token 的 system, 而它在几秒前的工具决策轮 (round1) 已原样发过一次
  (prod prefix-hash 实证: 同一 conversation 内 sys_hash 逐字节重复)。DashScope compatible-mode
  号称支持 Anthropic 式 `cache_control: {"type":"ephemeral"}` 断点 (4 断点/块≥1024 token/TTL
  5min 命中续期/命中计 10% 价), 把 round1 写的 system 缓存给 round2 命中, 跳过整条 system 的
  prefill → 合成 TTFT 省 1-3s、缓存前缀输入成本降 ~90%。

本脚本是「先拿地面真相再动手」的那道真网络门。它:
  - 构造一个固定 ~8k token 的 system 前缀 + **两个不同**的 user 尾 (tailA / tailB);
  - 三种模式各跑一遍:
      (a) baseline        —— content 用纯字符串, 不带任何 cache_control (量测**隐式**缓存底噪,
                             prod 观测隐式命中率 ~29%);
      (b) explicit-manual —— system content 转数组形 + cache_control ephemeral (手写, 验证
                             端点是否**接受** cache_control 字段, 以及 usage 怎么透传);
      (c) explicit-helper —— 走生产 helper prompt_cache.apply_cache_markers() 产出的**真实
                             布局** (system + history_prefix 断点), 端到端验证生产码的形状被接受;
    每种模式跑 callA(前缀+tailA) → 短暂等待 → callB(前缀+tailB, 前缀逐字节相同)。**命中在 callB**
    (callA 写缓存 / callB 读)。
  - 每次调用测: prompt_tokens / cached_tokens (usage.prompt_tokens_details.cached_tokens) /
    cache_creation (若透传) / TTFT(首个可见 token) / total。
  - 打一张裁决表 + 对 explicit vs baseline 的 cached_tokens 与 callB TTFT 做对比裁决。

诚实闸 (与 probe_qwen_thinking_budget 略不同):
  - 若端点**拒绝** cache_control 字段 (explicit 模式 create() 抛错) → 判 REJECTED 并 **exit 非零**
    (本探针要求任务方据此决定是否接线; 拒绝是硬失败, 不是"跑完了")。
  - 若接受但 callB **cached_tokens 不显著** (≤ 前缀 token 的一半, 与 baseline 隐式无实质差) →
    判 IGNORED (打标但不真命中), 表里记, exit 0 (可跑完, 让人看数据)。
  - 环境/网络/import 级失败 → exit 非零。

本脚本只探测/测量, **不接线**任何生产路径; supports_explicit_cache 的置位由人读完本表后手动改
model_registry。usage 直接从流式最后一个 chunk 读, 不经 usage_tracker (无本地 llm_usage_logs 噪声)。

用法:
  # TOKENPLAN_API_KEY 从仓库根 .env 读 (默认路径见 --env-file), 或直接 export。
  backend/venv/bin/python backend/scripts/probe_explicit_cache.py
  ... --model qwen3.6-flash        # 换模型 (缓存 per-model 不共享, flash/max 各测一遍)
  ... --repeat 2                   # 每模式多跑几次看抖动
  ... --skip-baseline              # 只测 explicit 两种
  ... --env-file /path/to/.env

  退出码: 0 = 跑完 (裁决在表里)。 非零 = 端点拒绝 cache_control / 环境 / 网络 / import 失败。
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# app.config 需要的 env (import app 前设好, 镜像 conftest / probe_qwen_thinking_budget)。
os.environ.setdefault("SECRET_KEY", "test-secret-key-32-chars-minimum!!")
os.environ.setdefault("GARMIN_ENCRYPTION_KEY", "mI4nYXirjGlbHD7sFogYlqPQJzirU04mUsS5LyDS0SU=")

_ROOT = Path(__file__).resolve().parents[1]  # backend/
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_DEFAULT_ENV_FILE = "/Users/liqiuhua/work/personal/health-llm-driven/.env"


def _load_env_file(path: str) -> None:
    """把 .env 里 TOKENPLAN_* 灌进 os.environ (env 已存在则不覆盖)。"""
    p = Path(path)
    if not p.exists():
        return
    wanted = {"TOKENPLAN_API_KEY", "TOKENPLAN_BASE_URL", "TOKENPLAN_MODEL"}
    for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        if key in wanted:
            os.environ.setdefault(key, val.strip().strip('"').strip("'"))


# ──── 固定 ~8k token system 前缀 (中文, 逼近生产合成轮的 system 规模) ────
# 一段 ~200 token 的健康指令块, 重复到 ~8k token。**逐字节确定**, 保证两次调用前缀完全相同。
_PREFIX_UNIT = (
    "你是用户的 AI 健康参谋。你综合数字健康孪生 (Digital Twin) 与专家发现, 给出个体化、可执行、"
    "非处方化的健康解读。硬规则: 只依据给定数据不臆造数值; 不开具体药物剂量与处方; 不下诊断标签; "
    "高风险信号必须显式点名并给就医动作; 把指标改善归因于某项干预时必须标注'相关性,非因果'; "
    "不得把补剂作为针对某指标的治疗方案推荐; 语气平实不用 emoji 不堆砌套话。数据记录规则: 所有记录"
    "必须调用工具才算完成, 绝不口头说'已记录'; 饮水/补剂直接执行, 血压/血糖/体重执行后复述数值确认; "
    "模糊数量先追问再记录; 时间归属按'昨天/刚才/今天'归档。分析规则: 简单查询走 health_query, 趋势"
    "分析走 health_analysis, 跨领域复杂问题走 orchestrator。"
)
# 需要多少份才到 ~8k token。中文 ~1.6 char/token, 8000 token ≈ 12800 char, 每份 ~380 char。
_PREFIX_SYSTEM = ("## 系统指令 (固定跨用户前缀)\n" + "\n".join(
    f"{i+1}. {_PREFIX_UNIT}" for i in range(34)
))

# 两个**不同**的 user 尾 (触发前缀命中 / 尾部不同): 内容不同、长度接近。
_TAIL_A = "综合上面的系统指令, 用三句话说明你会如何优先排序一个健康点。请直接给结论, 不要复述指令。"
_TAIL_B = "综合上面的系统指令, 用三句话说明你会如何给出一个可执行的两周行为调整。请直接给结论, 不要复述指令。"


def _approx_tokens(text: str) -> int:
    """粗估 token 数 (中文 ~1.6 char/token 的保守估计)。"""
    cjk = sum(1 for c in text if "一" <= c <= "鿿")
    other = len(text) - cjk
    return int(cjk / 1.6 + other / 4)


@dataclass
class CacheCallResult:
    label: str
    ok: bool = False
    error: str = ""
    ttft_s: Optional[float] = None
    total_s: Optional[float] = None
    prompt_tokens: Optional[int] = None
    cached_tokens: Optional[int] = None
    cache_creation_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    content_chars: int = 0


def _read_cache_usage(usage: Any) -> Tuple[Optional[int], Optional[int], Optional[int], Optional[int]]:
    """(prompt_tokens, cached_tokens, cache_creation_tokens, completion_tokens)。

    cached: usage.prompt_tokens_details.cached_tokens (openai_provider 已在读同一字段)。
    cache_creation: 若 DashScope 透传 (字段名各家不一, 尽力读 cache_creation_input_tokens
    / cache_creation_tokens, 直接属性或 model_extra)。
    """
    if usage is None:
        return None, None, None, None
    pt = getattr(usage, "prompt_tokens", None)
    ct = getattr(usage, "completion_tokens", None)
    details = getattr(usage, "prompt_tokens_details", None)
    cached = None
    creation = None
    if details is not None:
        cached = getattr(details, "cached_tokens", None)
        creation = (
            getattr(details, "cache_creation_input_tokens", None)
            or getattr(details, "cache_creation_tokens", None)
        )
        extra = getattr(details, "model_extra", None)
        if isinstance(extra, dict):
            cached = cached if cached is not None else extra.get("cached_tokens")
            creation = creation if creation is not None else (
                extra.get("cache_creation_input_tokens") or extra.get("cache_creation_tokens")
            )
    return pt, cached, creation, ct


def _one_call(
    client: Any, label: str, model: str, messages: List[Dict[str, Any]], max_tokens: int = 256,
) -> CacheCallResult:
    """跑一次流式调用, 读 usage 的 cached_tokens。异常如实记录 (端点拒 cache_control 会在此抛)。"""
    res = CacheCallResult(label=label)
    create_kwargs: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": max_tokens,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    t0 = time.perf_counter()
    content_parts: List[str] = []
    usage_obj = None
    try:
        stream = client.chat.completions.create(**create_kwargs)
        for chunk in stream:
            now = time.perf_counter()
            u = getattr(chunk, "usage", None)
            if u is not None:
                usage_obj = u
            choices = getattr(chunk, "choices", None)
            if not choices:
                continue
            delta = choices[0].delta
            c = getattr(delta, "content", None)
            if c:
                if res.ttft_s is None:
                    res.ttft_s = now - t0
                content_parts.append(c)
        res.total_s = time.perf_counter() - t0
    except Exception as e:  # noqa: BLE001 — 探针要如实记录端点拒绝
        res.error = f"{type(e).__name__}: {e}"
        res.total_s = time.perf_counter() - t0
        return res
    res.content_chars = len("".join(content_parts))
    pt, cached, creation, ct = _read_cache_usage(usage_obj)
    res.prompt_tokens, res.cached_tokens = pt, cached
    res.cache_creation_tokens, res.completion_tokens = creation, ct
    res.ok = not res.error
    return res


def _plain_messages(tail: str) -> List[Dict[str, Any]]:
    """baseline: 纯字符串 content, 无 cache_control。"""
    return [
        {"role": "system", "content": _PREFIX_SYSTEM},
        {"role": "user", "content": tail},
    ]


def _manual_marked_messages(tail: str) -> List[Dict[str, Any]]:
    """explicit-manual: 手写 system content 数组形 + cache_control ephemeral。"""
    return [
        {
            "role": "system",
            "content": [
                {"type": "text", "text": _PREFIX_SYSTEM, "cache_control": {"type": "ephemeral"}}
            ],
        },
        {"role": "user", "content": tail},
    ]


def _helper_marked_messages(tail: str) -> List[Dict[str, Any]]:
    """explicit-helper: 走生产 helper 产出的真实布局 (端到端验证生产码形状)。"""
    from app.services.llm.prompt_cache import apply_cache_markers

    return apply_cache_markers(_plain_messages(tail))


def _build_client() -> Any:
    from app.config import settings

    if not settings.tokenplan_api_key:
        raise SystemExit("[FAIL] TOKENPLAN_API_KEY 未配置 (env 或 --env-file 都没有)")
    from openai import OpenAI

    client = OpenAI(api_key=settings.tokenplan_api_key, base_url=settings.tokenplan_base_url)
    print(f"[info] base_url={settings.tokenplan_base_url}")
    return client


def _fmt(v: Optional[float], nd: int = 2) -> str:
    return f"{v:.{nd}f}" if isinstance(v, (int, float)) else "-"


def _fmt_i(v: Optional[int]) -> str:
    return str(v) if isinstance(v, int) else "-"


def _run_mode(
    client: Any, model: str, mode: str, build, repeat: int,
) -> Tuple[CacheCallResult, CacheCallResult]:
    """跑一个模式的 callA(写)/callB(读, 不同尾)。repeat 时取 callB cached_tokens 最大的一轮。"""
    best_a: Optional[CacheCallResult] = None
    best_b: Optional[CacheCallResult] = None
    for i in range(repeat):
        a = _one_call(client, f"{mode} callA", model, build(_TAIL_A))
        time.sleep(1.0)  # 让缓存落地 (同 5min TTL 窗内, 秒级足够)
        b = _one_call(client, f"{mode} callB", model, build(_TAIL_B))
        print(
            f"    [{i+1}/{repeat}] {mode}: "
            f"A(ok={a.ok} ttft={_fmt(a.ttft_s)} p_tok={_fmt_i(a.prompt_tokens)} "
            f"cached={_fmt_i(a.cached_tokens)}) "
            f"B(ok={b.ok} ttft={_fmt(b.ttft_s)} p_tok={_fmt_i(b.prompt_tokens)} "
            f"cached={_fmt_i(b.cached_tokens)} create={_fmt_i(b.cache_creation_tokens)})"
            + (f" A_err={a.error[:80]}" if a.error else "")
            + (f" B_err={b.error[:80]}" if b.error else "")
        )
        if best_b is None or (b.cached_tokens or -1) > (best_b.cached_tokens or -1):
            best_a, best_b = a, b
    assert best_a is not None and best_b is not None
    return best_a, best_b


def _print_table(rows: List[Tuple[str, CacheCallResult, CacheCallResult]]) -> None:
    print("\n" + "=" * 108)
    print("显式缓存裁决表 (ttft/total 秒; tok=token; cached=callB 命中的缓存 prompt token)")
    print("=" * 108)
    header = (
        f"{'mode':<18} {'okA':<3} {'okB':<3} {'p_tokB':>7} {'cachedB':>8} "
        f"{'createB':>8} {'ttftA':>7} {'ttftB':>7} {'Δttft':>7}"
    )
    print(header)
    print("-" * 108)
    for mode, a, b in rows:
        dttft = (
            a.ttft_s - b.ttft_s
            if (a.ttft_s is not None and b.ttft_s is not None)
            else None
        )
        print(
            f"{mode:<18} {('Y' if a.ok else 'n'):<3} {('Y' if b.ok else 'n'):<3} "
            f"{_fmt_i(b.prompt_tokens):>7} {_fmt_i(b.cached_tokens):>8} "
            f"{_fmt_i(b.cache_creation_tokens):>8} {_fmt(a.ttft_s):>7} {_fmt(b.ttft_s):>7} "
            f"{_fmt(dttft):>7}"
        )
        if b.error:
            print(f"    └─ callB error: {b.error[:150]}")
    print("=" * 108)


def main() -> int:
    parser = argparse.ArgumentParser(description="DashScope 显式上下文缓存真网络探针 (rank3)")
    parser.add_argument("--model", default="qwen3.7-max", help="缓存 per-model 不共享; flash/max 各测一遍")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--skip-baseline", action="store_true", help="只测 explicit 两种")
    parser.add_argument("--env-file", default=_DEFAULT_ENV_FILE)
    args = parser.parse_args()

    _load_env_file(args.env_file)
    prefix_tok = _approx_tokens(_PREFIX_SYSTEM)
    print(f"[info] system 前缀 ~{prefix_tok} est_token ({len(_PREFIX_SYSTEM)} char), "
          f"tailA/tailB 不同; 命中判定阈值 = 前缀的一半 ({prefix_tok // 2} tok)")
    if prefix_tok < 1024:
        print(f"[WARN] 前缀 ~{prefix_tok} tok < 1024 最小可缓存前缀 —— 端点可能忽略断点!")

    client = _build_client()

    modes: List[Tuple[str, Any]] = []
    if not args.skip_baseline:
        modes.append(("baseline", _plain_messages))
    modes.append(("explicit-manual", _manual_marked_messages))
    modes.append(("explicit-helper", _helper_marked_messages))

    rows: List[Tuple[str, CacheCallResult, CacheCallResult]] = []
    explicit_rejected = False
    for mode, build in modes:
        print(f"\n[probe] model={args.model} mode={mode} (repeat={args.repeat}) ...")
        a, b = _run_mode(client, args.model, mode, build, args.repeat)
        rows.append((mode, a, b))
        # 诚实闸: explicit 模式若两次调用都因错误失败 (端点拒 cache_control) → 硬失败。
        if mode.startswith("explicit") and not a.ok and not b.ok and (a.error or b.error):
            explicit_rejected = True

    _print_table(rows)

    # ──── 裁决 ────
    print("\n[裁决 · 显式上下文缓存]")
    threshold = prefix_tok // 2
    baseline_cached = None
    for mode, _a, b in rows:
        if mode == "baseline":
            baseline_cached = b.cached_tokens
            print(f"  baseline (隐式): callB cached_tokens={_fmt_i(b.cached_tokens)} "
                  f"(prod 隐式命中率 ~29%, 这是底噪)")
    for mode, a, b in rows:
        if not mode.startswith("explicit"):
            continue
        if not a.ok and not b.ok and (a.error or b.error):
            print(f"  {mode}: 端点**拒绝** cache_control → REJECTED。 {(b.error or a.error)[:120]}")
            continue
        cached = b.cached_tokens
        if cached is None:
            print(f"  {mode}: 接受但 usage **不透传** cached_tokens —— 无法确认命中 (需查原始 usage/账单)。")
            continue
        gain = cached - (baseline_cached or 0)
        if cached >= threshold:
            dttft = (a.ttft_s - b.ttft_s) if (a.ttft_s and b.ttft_s) else None
            print(f"  {mode}: SUPPORTED —— callB cached={cached} tok (≥ 阈值 {threshold}), "
                  f"较 baseline 隐式 +{gain} tok, callB TTFT 较 callA Δ={_fmt(dttft)}s。")
        else:
            print(f"  {mode}: IGNORED —— callB cached={cached} tok (< 阈值 {threshold}), "
                  f"与 baseline 隐式无实质差 → 断点未真命中 (勿置 supports_explicit_cache)。")

    if explicit_rejected:
        print("\n[FAIL] explicit 模式被端点拒绝 → exit 非零 (cache_control 不被 compatible-mode 接受)。")
        return 2
    print("\n[done] 探针跑完 —— 读上表 + 裁决, 再决定是否给该模型置 supports_explicit_cache=True。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
