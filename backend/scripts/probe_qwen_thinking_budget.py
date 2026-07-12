#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""真网络探针: qwen3.7-max 合成轮的**思考预算**(thinking budget)时延杠杆是否存在。

背景 (合成轮 TTFT 谜团):
  prod 观测 qwen3.7-max 在合成/答案轮的 in-call TTFT p50 ~20-24s —— 首个**可见**
  token 之前有一段沉默的 reasoning 阶段;decode ~12-13 tok/s;最终答案却只有
  ~373 个真实 completion token。假说: 隐藏的 thinking 阶段吃掉了绝大部分墙钟时间。
  若 tokenplan/DashScope 端支持 `enable_thinking:false` 或 `thinking_budget:N` 把这段
  思考封顶/关掉, 合成 TTFT 可能从 ~20s 塌到 ~2-5s。

  第二个杠杆: 若 thinking 阶段本身是**可流式**的 (reasoning_content delta 早早就到),
  那可以把它实时喂进现有「思考过程」UI, 用真实的思考流填掉那段死气 (dead air),
  而不必关掉思考。本探针同时测这一点。

本脚本就是「先拿地面真相再动手」的那道真网络门。它:
  - 对 qwen3.7-max 用一个固定的 ~2k token 中等 prompt, 跑三种方式:
      (a) default              —— 不带任何 thinking 控制 (基线)
      (b) enable_thinking=false —— DashScope 兼容参数, 试图关掉思考
      (c) thinking_budget=512   —— DashScope 兼容参数, 试图给思考封顶
    每种都试 extra_body **顶层**放置; 若被拒再退回 `parameters` 嵌套放置,
    并记录哪种放置生效。
  - 每次测: TTFT(首个**可见 content** token)、首个 reasoning delta 时刻、
    total ms、prompt/completion/reasoning token、decode tok/s、是否退化为空/报错。
  - 附带 (coordinator 追加, 纯测量不接线): deepseek-v3.2 (balanced 档, 0 prod 样本)
    在两个输出尺寸 (~150 / ~500 token) 下的 TTFT/total/completion/tok-s, 判断它到底
    是 flash 级 decode (30-40 tok/s) 还是又一个 ~12 tok/s 的哑弹。
  - 打印一张裁决表。

诚实闸: 若端点**拒绝**这些参数, 或**忽略**它们 (TTFT 与基线无差), 判 NOT SUPPORTED。
本脚本只做探测/测量, 不接线任何生产路径。

用法:
  # TOKENPLAN_API_KEY 从仓库根 .env 读 (默认路径见 --env-file), 或直接 export。
  backend/venv/bin/python backend/scripts/probe_qwen_thinking_budget.py
  ... --repeat 2                 # 每个变体多跑几次看抖动 (默认 1, 差异 20s→2s 单样本即决定性)
  ... --skip-deepseek            # 只测 qwen thinking 杠杆
  ... --env-file /path/to/.env   # 指定 .env

  退出码: 0 = 跑完 (裁决在表里, 不因 NOT SUPPORTED 而非零 —— 这是探针不是闸)。
          非 0 = 环境/网络/import 级失败 (拿不到地面真相)。

注意: 本探针**故意**直接用 OpenAI SDK client (从 settings 取 api_key/base_url,
  与 OpenAIProvider 同源), 而非包装过的 provider —— 因为要观测 provider 目前
  丢弃的 reasoning_content delta, 并精确控制 extra_body 放置。这是探测, 不是生产码。
  usage 直接从流式最后一个 chunk 读, 不经 usage_tracker, 故无 llm_usage_logs 本地噪声。
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# app.config 需要的 env (import app 前设好, 镜像 conftest / smoke_fast_tool_model)。
os.environ.setdefault("SECRET_KEY", "test-secret-key-32-chars-minimum!!")
os.environ.setdefault("GARMIN_ENCRYPTION_KEY", "mI4nYXirjGlbHD7sFogYlqPQJzirU04mUsS5LyDS0SU=")

_ROOT = Path(__file__).resolve().parents[1]  # backend/
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_DEFAULT_ENV_FILE = "/Users/liqiuhua/work/personal/health-llm-driven/.env"

_QWEN_MODEL = "qwen3.7-max"
_DEEPSEEK_MODEL = "deepseek-v3.2"


def _load_env_file(path: str) -> None:
    """把 .env 里我们需要的 TOKENPLAN_* 灌进 os.environ (env 已存在则不覆盖)。

    pydantic-settings 优先级: env var > .env 文件, 所以 setdefault 即可让 settings 读到。
    只挑我们需要的 key, 不做通用 dotenv 解析 (避免污染)。
    """
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
            val = val.strip().strip('"').strip("'")
            os.environ.setdefault(key, val)


# ──── 固定 ~2k token 中等 prompt (镜像一次真实合成轮: twin 上下文 + 健康问题) ────
_SYSTEM = (
    "你是「小巴」——一个严谨、克制的健康参谋。你综合用户的数字健康孪生 (Digital Twin) "
    "与专家发现, 给出个体化、可执行、非处方化的健康解读。规则: (1) 只依据给定数据, 不臆造数值; "
    "(2) 不开具体药物剂量/处方, 不下诊断; (3) 高风险信号必须显式点名并给就医动作; "
    "(4) 语气平实, 不用 emoji, 不堆砌套话。"
)

# ~1.6k token 的合成 twin 上下文 (中文, 逼近生产合成轮的 prompt 规模)。
_TWIN_BLOB = (
    "【数字健康孪生快照 · 生理】静息心率 58 bpm(7日均), HRV(rMSSD)夜间 42ms(较基线 -18%), "
    "睡眠 6.2h(深睡 0.9h / REM 1.1h / 觉醒 6 次), body battery 起床 61 / 睡前 32, 压力评分日均 47。 "
    "【身体成分】体重 72.4kg, BMI 23.1, 体脂率 19.8%(生物阻抗), 腰围 82cm(180天前测, 已过期需重测)。 "
    "【化验 · 近 30 天】空腹血糖 5.4 mmol/L, HbA1c 5.6%, 总胆固醇 5.1, LDL-C 3.3 mmol/L(临界偏高), "
    "HDL-C 1.2, 甘油三酯 1.7, 尿酸 431 μmol/L(偏高), ALT 34 / AST 28, eGFR 96, hsCRP 1.8 mg/L, "
    "尿素氮 5.2, 肌酐 84, TSH 2.1, 维生素 D 22 ng/mL(不足), 铁蛋白 88, 同型半胱氨酸 11.2 μmol/L(偏高)。 "
    "【CGM · 近 14 天】TIR(3.9-10)88%, 平均血糖 6.1, GMI 5.7%, CV 21%, 夜间无低血糖, 餐后 1h 峰值 8.9。 "
    "【用药/补剂】维生素 D3 2000IU/日(3周), 鱼油 1g/日, 无处方药。 "
    "【基因(已上传报告)】MTHFR C677T 杂合(CT), APOE ε3/ε3, FTO AA(高食欲倾向), "
    "ALDH2 *1/*2(乙醛代谢弱), ACTN3 RR(力量型), VDR Bsm bb。 "
    "【环境】常驻城市 AQI 今日 78(良), PM2.5 42, 花粉中等, 湿度 61%, UV 6。 "
    "【行为 · 近 7 天】日均步数 8200, 中高强度运动 3 次(力量2/有氧1), 久坐日均 9.1h, "
    "训练负荷 ACWR 1.18(适中), 日均饮水 1500ml(低于目标 2000), 咖啡因 2 杯/日, 无酒精。 "
    "【专家发现摘要】RecoveryCoach: readiness 54/100(偏低, 主因 HRV 下滑+深睡不足)。 "
    "FuelStrategist: 蛋白摄入约 0.9g/kg(低于 1.4 目标), 建议早餐补蛋白; MTHFR 杂合关注叶酸活性形式。 "
    "MovementCoach: ACWR 适中可维持, 力量型基因(ACTN3 RR)偏好抗阻。 "
    "SafetyGuardian: 尿酸偏高(431)非急症但需饮食关注; LDL-C 临界; 维 D 不足; 同型半胱氨酸偏高(与 MTHFR 相关)。 "
    "MetabolicSpecialist: 代谢综合征 5 项中命中 1 项(暂无), CGM 控制良好。 "
    "LongitudinalAnalyst: 近 3 个月 HRV 缓降、体重稳定、LDL 微升。"
)

_USER_QUESTION = (
    "综合我上面的数字孪生和专家发现, 帮我梳理: (1) 当前最值得优先关注的 2-3 个健康点是什么, 各自的依据; "
    "(2) 未来两周我可以落地的具体行为调整(饮食/运动/睡眠/补剂方向, 不要给药物剂量); "
    "(3) 哪些指标需要复测或就医确认。请分点讲, 简洁务实。"
)

_QWEN_MESSAGES = [
    {"role": "system", "content": _SYSTEM},
    {"role": "user", "content": _TWIN_BLOB + "\n\n" + _USER_QUESTION},
]

# deepseek 用同一 twin 上下文, 但换两个明确长度约束的问法。
_DS_MESSAGES_SHORT = [
    {"role": "system", "content": _SYSTEM},
    {"role": "user", "content": _TWIN_BLOB + "\n\n请用**大约150字**给我一句话总结当前最该关注的健康点和一个立即行动。"},
]
_DS_MESSAGES_LONG = [
    {"role": "system", "content": _SYSTEM},
    {"role": "user", "content": _TWIN_BLOB + "\n\n" + _USER_QUESTION + " (目标篇幅约 500 字)"},
]


@dataclass
class ProbeResult:
    label: str
    model: str
    ok: bool = False
    error: str = ""
    placement: str = "-"          # 哪种 extra_body 放置生效: top-level / parameters / n-a
    ttft_content_s: Optional[float] = None   # 首个可见 content token
    ttft_reasoning_s: Optional[float] = None # 首个 reasoning_content delta
    ttft_any_s: Optional[float] = None       # 首个任意 delta
    total_s: Optional[float] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    reasoning_tokens: Optional[int] = None
    content_chars: int = 0
    reasoning_chars: int = 0
    decode_tok_s: Optional[float] = None
    content_preview: str = ""


def _extract_reasoning(delta: Any) -> Optional[str]:
    """从流式 delta 里取 reasoning_content (DashScope/qwen 思考流)。

    OpenAI SDK 的 ChoiceDelta 不认识这个字段, 会落到 model_extra 或直接属性上。
    """
    r = getattr(delta, "reasoning_content", None)
    if r:
        return r
    extra = getattr(delta, "model_extra", None)
    if isinstance(extra, dict):
        r = extra.get("reasoning_content")
        if r:
            return r
    return None


def _read_usage(usage: Any) -> Tuple[Optional[int], Optional[int], Optional[int]]:
    """(prompt_tokens, completion_tokens, reasoning_tokens)。"""
    if usage is None:
        return None, None, None
    pt = getattr(usage, "prompt_tokens", None)
    ct = getattr(usage, "completion_tokens", None)
    rt = None
    details = getattr(usage, "completion_tokens_details", None)
    if details is not None:
        rt = getattr(details, "reasoning_tokens", None)
        if rt is None and isinstance(getattr(details, "model_extra", None), dict):
            rt = details.model_extra.get("reasoning_tokens")
    return pt, ct, rt


def _one_stream_call(
    client: Any,
    label: str,
    model: str,
    messages: List[Dict[str, Any]],
    max_tokens: int,
    extra_body: Optional[Dict[str, Any]],
    temperature: float = 0.3,
) -> ProbeResult:
    """跑一次流式调用并测量。extra_body=None 表示基线(不带 thinking 控制)。"""
    res = ProbeResult(label=label, model=model)
    create_kwargs: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if extra_body:
        create_kwargs["extra_body"] = extra_body

    t0 = time.perf_counter()
    content_parts: List[str] = []
    reasoning_parts: List[str] = []
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
            r = _extract_reasoning(delta)
            if r:
                if res.ttft_any_s is None:
                    res.ttft_any_s = now - t0
                if res.ttft_reasoning_s is None:
                    res.ttft_reasoning_s = now - t0
                reasoning_parts.append(r)
            c = getattr(delta, "content", None)
            if c:
                if res.ttft_any_s is None:
                    res.ttft_any_s = now - t0
                if res.ttft_content_s is None:
                    res.ttft_content_s = now - t0
                content_parts.append(c)
        res.total_s = time.perf_counter() - t0
    except Exception as e:  # noqa: BLE001 — 探针要如实记录端点拒绝
        res.error = f"{type(e).__name__}: {e}"
        res.total_s = time.perf_counter() - t0
        return res

    content = "".join(content_parts)
    reasoning = "".join(reasoning_parts)
    res.content_chars = len(content)
    res.reasoning_chars = len(reasoning)
    res.content_preview = content.strip()[:80].replace("\n", " ")
    pt, ct, rt = _read_usage(usage_obj)
    res.prompt_tokens, res.completion_tokens, res.reasoning_tokens = pt, ct, rt
    # decode tok/s = completion_tokens / (从首个可见 token 到结束的时间)
    if ct and res.ttft_content_s is not None and res.total_s is not None:
        decode_window = res.total_s - res.ttft_content_s
        if decode_window > 0.05:
            res.decode_tok_s = ct / decode_window
    res.ok = bool(content) and not res.error
    return res


def _call_with_placement_fallback(
    client: Any,
    label: str,
    model: str,
    messages: List[Dict[str, Any]],
    max_tokens: int,
    thinking_params: Dict[str, Any],
) -> ProbeResult:
    """试 top-level 放置; 被拒则退回 `parameters` 嵌套放置, 记录哪种生效。"""
    # 放置 1: extra_body 顶层 (DashScope compatible-mode 标准)
    res = _one_stream_call(client, label, model, messages, max_tokens, dict(thinking_params))
    if res.ok:
        res.placement = "top-level"
        return res
    # 顶层报错 → 试嵌套 parameters (DashScope 原生 API 风格)
    if res.error:
        nested = {"parameters": dict(thinking_params)}
        res2 = _one_stream_call(client, label, model, messages, max_tokens, nested)
        if res2.ok:
            res2.placement = "parameters"
            return res2
        # 两种都失败: 保留顶层的错误信息 (更能说明端点是否认识该参数)
        res.placement = "both-failed"
        if res2.error:
            res.error = f"top-level: {res.error} | parameters: {res2.error}"
        return res
    # 顶层没报错但退化为空 (content 为空) → 记 top-level 但标不 ok
    res.placement = "top-level(empty)"
    return res


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


def _print_table(results: List[ProbeResult]) -> None:
    print("\n" + "=" * 118)
    print("裁决表 (TTFT/total 单位秒; tok = token; decode = 首可见 token 之后的 tok/s)")
    print("=" * 118)
    header = (
        f"{'variant':<26} {'ok':<3} {'place':<14} {'ttft_c':>7} {'ttft_r':>7} "
        f"{'total':>7} {'p_tok':>6} {'c_tok':>6} {'r_tok':>6} {'dec/s':>6}"
    )
    print(header)
    print("-" * 118)
    for r in results:
        print(
            f"{r.label:<26} {('Y' if r.ok else 'n'):<3} {r.placement:<14} "
            f"{_fmt(r.ttft_content_s):>7} {_fmt(r.ttft_reasoning_s):>7} "
            f"{_fmt(r.total_s):>7} {_fmt_i(r.prompt_tokens):>6} {_fmt_i(r.completion_tokens):>6} "
            f"{_fmt_i(r.reasoning_tokens):>6} {_fmt(r.decode_tok_s, 1):>6}"
        )
        if r.error:
            print(f"    └─ error: {r.error[:150]}")
        elif r.content_preview:
            print(f"    └─ answer[:80]: {r.content_preview}")
    print("=" * 118)


def _verdict(qwen_results: List[ProbeResult]) -> None:
    """对 qwen thinking 杠杆下诚实裁决。"""
    by_label = {r.label: r for r in qwen_results}
    base = by_label.get("qwen default")
    print("\n[裁决 · qwen3.7-max thinking 杠杆]")
    if base is None or not base.ok or base.ttft_content_s is None:
        print("  基线调用失败, 无法比较 —— 见上表 error。")
        return
    print(f"  基线 default: ttft_content={_fmt(base.ttft_content_s)}s total={_fmt(base.total_s)}s "
          f"completion={_fmt_i(base.completion_tokens)}tok reasoning={_fmt_i(base.reasoning_tokens)}tok")

    for label in ("qwen enable_thinking=false", "qwen thinking_budget=512"):
        r = by_label.get(label)
        if r is None:
            continue
        if r.error and not r.ok:
            print(f"  {label}: 端点**拒绝** → NOT SUPPORTED。 {r.error[:120]}")
            continue
        if not r.ok:
            print(f"  {label}: 退化为空/无内容 → NOT SUPPORTED (placement={r.placement})。")
            continue
        if r.ttft_content_s is None:
            print(f"  {label}: 无 ttft 数据。")
            continue
        # 判定: ttft_content 相对基线是否显著下降 (>40% 且绝对 > 5s 视为有效杠杆)
        drop = base.ttft_content_s - r.ttft_content_s
        drop_pct = drop / base.ttft_content_s * 100 if base.ttft_content_s else 0
        verdict = (
            "SUPPORTED (TTFT 显著下降)" if (drop > 5.0 and drop_pct > 40)
            else "IGNORED (TTFT 无实质变化) → NOT SUPPORTED"
        )
        print(f"  {label}: ttft_content={_fmt(r.ttft_content_s)}s (Δ={_fmt(drop)}s, {drop_pct:.0f}%) "
              f"reasoning_tok={_fmt_i(r.reasoning_tokens)} placement={r.placement} → {verdict}")

    # Lever 2: reasoning 是否可流式 (死气可被真实思考流填掉)
    stream_lever = [r for r in qwen_results if r.ttft_reasoning_s is not None]
    if stream_lever:
        r = stream_lever[0]
        gap = None
        if r.ttft_content_s is not None and r.ttft_reasoning_s is not None:
            gap = r.ttft_content_s - r.ttft_reasoning_s
        print(f"\n[裁决 · Lever 2 思考流可视化] reasoning_content **可流式**: "
              f"首个 reasoning delta @ {_fmt(r.ttft_reasoning_s)}s, 首个可见 content @ {_fmt(r.ttft_content_s)}s, "
              f"死气可被填 ~{_fmt(gap)}s → 可把思考流实时喂进「思考过程」UI。")
    else:
        print("\n[裁决 · Lever 2 思考流可视化] 流式**未**暴露 reasoning_content delta —— "
              "思考阶段在网关侧被 buffer, 无法实时填充死气 (只有关/封顶思考这一条杠杆)。")


def _run_qwen(client: Any, repeat: int) -> List[ProbeResult]:
    print(f"\n[probe] qwen3.7-max thinking 杠杆 (repeat={repeat}) ...")
    variants: List[Tuple[str, Optional[Dict[str, Any]]]] = [
        ("qwen default", None),
        ("qwen enable_thinking=false", {"enable_thinking": False}),
        ("qwen thinking_budget=512", {"enable_thinking": True, "thinking_budget": 512}),
    ]
    results: List[ProbeResult] = []
    for label, thinking in variants:
        best: Optional[ProbeResult] = None
        for i in range(repeat):
            if thinking is None:
                r = _one_stream_call(client, label, _QWEN_MODEL, _QWEN_MESSAGES, 1024, None)
                r.placement = "n-a"
            else:
                r = _call_with_placement_fallback(
                    client, label, _QWEN_MODEL, _QWEN_MESSAGES, 1024, thinking
                )
            print(f"    [{i+1}/{repeat}] {label}: ok={r.ok} place={r.placement} "
                  f"ttft_c={_fmt(r.ttft_content_s)}s total={_fmt(r.total_s)}s "
                  f"c_tok={_fmt_i(r.completion_tokens)} r_tok={_fmt_i(r.reasoning_tokens)}"
                  + (f" err={r.error[:80]}" if r.error else ""))
            # 取 total 最小的一次 (代表最好情况; 单样本时就是它自己)
            if best is None or (r.ok and (not best.ok or (r.total_s or 9e9) < (best.total_s or 9e9))):
                best = r
        if best is not None:
            results.append(best)
    return results


def _run_deepseek(client: Any, repeat: int) -> List[ProbeResult]:
    print(f"\n[probe] deepseek-v3.2 decode 速度 (纯测量, 不接线; repeat={repeat}) ...")
    variants: List[Tuple[str, List[Dict[str, Any]], int]] = [
        ("deepseek ~150tok", _DS_MESSAGES_SHORT, 256),
        ("deepseek ~500tok", _DS_MESSAGES_LONG, 768),
    ]
    results: List[ProbeResult] = []
    for label, msgs, max_tok in variants:
        best: Optional[ProbeResult] = None
        for i in range(repeat):
            r = _one_stream_call(client, label, _DEEPSEEK_MODEL, msgs, max_tok, None)
            r.placement = "n-a"
            print(f"    [{i+1}/{repeat}] {label}: ok={r.ok} ttft_c={_fmt(r.ttft_content_s)}s "
                  f"total={_fmt(r.total_s)}s c_tok={_fmt_i(r.completion_tokens)} "
                  f"decode={_fmt(r.decode_tok_s, 1)} tok/s"
                  + (f" err={r.error[:80]}" if r.error else ""))
            if best is None or (r.ok and (not best.ok or (r.total_s or 9e9) < (best.total_s or 9e9))):
                best = r
        if best is not None:
            results.append(best)
    return results


def _deepseek_verdict(ds_results: List[ProbeResult]) -> None:
    print("\n[裁决 · deepseek-v3.2 decode 速度 (plan-rank9 是否值得建)]")
    decodes = [r.decode_tok_s for r in ds_results if r.decode_tok_s]
    if not decodes:
        print("  无有效 decode 数据 (见上表 error)。")
        return
    peak = max(decodes)
    if peak >= 28:
        cls = f"flash 级 (峰值 {peak:.0f} tok/s ≥ 28) → balanced 档有真正更快的占位, plan-rank9 值得建。"
    elif peak >= 18:
        cls = f"中速 ({peak:.0f} tok/s, 介于 flash 与 ~12 之间) → 边际收益, 需权衡。"
    else:
        cls = f"又一个 ~12 tok/s 哑弹 (峰值仅 {peak:.0f} tok/s) → balanced 档无更快占位, plan-rank9 不值得建。"
    print(f"  {cls}")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="qwen3.7-max thinking-budget 时延杠杆真网络探针")
    ap.add_argument("--repeat", type=int, default=1, help="每个变体跑几次 (默认 1)")
    ap.add_argument("--env-file", default=_DEFAULT_ENV_FILE, help=".env 路径 (读 TOKENPLAN_*)")
    ap.add_argument("--skip-deepseek", action="store_true", help="跳过 deepseek-v3.2 测量")
    ap.add_argument("--skip-qwen", action="store_true", help="跳过 qwen thinking 探测")
    ns = ap.parse_args(argv)

    _load_env_file(ns.env_file)
    client = _build_client()

    qwen_results: List[ProbeResult] = []
    ds_results: List[ProbeResult] = []
    if not ns.skip_qwen:
        qwen_results = _run_qwen(client, ns.repeat)
    if not ns.skip_deepseek:
        ds_results = _run_deepseek(client, ns.repeat)

    _print_table(qwen_results + ds_results)
    if qwen_results:
        _verdict(qwen_results)
    if ds_results:
        _deepseek_verdict(ds_results)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
