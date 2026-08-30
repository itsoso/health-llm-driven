"""深报告合成模型延迟/质量真网探针 (2026-07-15, D 组模型决策输入)。

对比 tokenplan 流式候选在**一次典型深报告合成**上的:TTFT / 生成速度(chars·s⁻¹)/
总壁钟 / 输出长度 / 是否截断。同一 prompt 喂所有模型 → tok/s 相对可比。

langbridge 商用模型(claude/gpt/gemini)registry 标 stream=False(万擎公网签名 RPC
结构性非流式,ttft≈total),本地无 key 且已知 wall-clock 差,不在本探针内。

用法: cd backend && source venv/bin/activate && python scripts/probe_synthesis_models.py
输出: 表格到 stdout + 各模型全文到 /tmp/synth_probe/<model>.txt
"""
import asyncio
import os
import time

os.environ.setdefault("SECRET_KEY", "test-secret-key-32-chars-minimum!!")
os.environ.setdefault("GARMIN_ENCRYPTION_KEY", "mI4nYXirjGlbHD7sFogYlqPQJzirU04mUsS5LyDS0SU=")

# 典型深报告合成负载: 多专家结构化 finding → 综合报告。~1500 token 输入 / 期望 ~2000 输出。
SYSTEM_PROMPT = (
    "你是一位资深的个人健康参谋。基于下面多位专科专家的结构化分析,综合成一份"
    "有优先级、可执行的健康报告。要求:①先给关键结论(3-5条);②按 恢复/营养/运动/"
    "慢病 分区展开机制与建议;③每条建议要具体可执行、标注为什么现在做;④用中文,"
    "结构清晰,2000字左右,务必写完整并以一句免责声明收尾。\n"
    "【严格医疗边界·最高优先级·违反视为严重错误】任何补剂或药物,一律只描述"
    "其种类/形式(如 活性叶酸、维生素D3)与随餐时机,绝对禁止输出任何具体剂量数字"
    "——不写 mg/μg/IU/g/克/毫克/单位,不写 每日X、补充X剂量、X到Y 这类量化处方。"
    "具体剂量一律交由临床医生。②只能使用上面专家 findings 里出现过的补剂/指标,"
    "禁止引入 findings 中未提及的补剂(如镁等)。③涉及处方药只能建议咨询医生,"
    "绝不暗示自行停药/换药/改剂量。"
)
USER_PROMPT = """请综合以下专家分析,给我一份完整的健康报告:

【Recovery Coach】readiness 62/100(偏低)。HRV 40.3ms 较7日均值↓11%,深睡占比偏低,
身体电量峰值 58。判定:恢复负债,今日不宜高强度。

【Fuel Strategist】TDEE≈2180kcal,昨日摄入 1650kcal(缺口偏大),蛋白 58g(目标 95g,
不足)。基因:MTHFR TT(叶酸代谢弱)、APOE ε3/ε4(饱和脂肪敏感)。

【Movement Coach】ACWR 1.35(略偏高,负荷累积),ACTN3 RR(力量偏好)。结合 readiness 偏低,
建议今日恢复性活动为主。

【Metabolic Specialist】空腹血糖 5.6,HbA1c 5.5%,TG 1.9(偏高),HDL 1.1(偏低),
腰围 88cm。代谢综合征 5 项命中 2 项,未达标但需关注。

【Hypertension Specialist】近30天平均 128/82,ACC/AHA 分级:升高血压(Elevated)。

【Chronic - 胃】胃窦慢性轻度炎,HP 阴性。近期晨起反酸。补剂随餐服用。

【Labs】肝酶正常,LDL 3.4(临界),尿酸 415(临界),eGFR 正常,维D 22ng/ml(不足)。

请综合给出带优先级的行动清单和机制解读。"""

CANDIDATES = [
    ("deepseek-v4-flash", "fast·硬prompt重测"),
    ("deepseek-v4-pro", "reasoning·硬prompt重测"),
    ("qwen3.7-max", "基线·硬prompt对照"),
]


async def probe(model_id: str) -> dict:
    from app.services.llm.factory import create_provider_for_model_id

    provider = create_provider_for_model_id(model_id)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_PROMPT},
    ]
    t0 = time.monotonic()
    ttft = None
    out = []
    finish = None
    try:
        result = await provider.chat(
            messages=messages, temperature=0.3, max_tokens=3200, stream=True
        )
        if hasattr(result, "__aiter__"):
            async for chunk in result:
                text = chunk if isinstance(chunk, str) else str(chunk)
                if text:
                    if ttft is None:
                        ttft = time.monotonic() - t0
                    out.append(text)
        else:  # 非流式 provider
            text = result.get("content") if isinstance(result, dict) else str(result or "")
            ttft = time.monotonic() - t0
            out.append(text or "")
    except Exception as e:  # noqa: BLE001
        return {"model": model_id, "error": f"{type(e).__name__}: {str(e)[:160]}"}
    total = time.monotonic() - t0
    body = "".join(out)
    chars = len(body)
    return {
        "model": model_id,
        "ttft_s": round(ttft or total, 1),
        "total_s": round(total, 1),
        "chars": chars,
        "chars_per_s": round(chars / total, 1) if total > 0 else 0,
        "gen_s": round(total - (ttft or 0), 1),
        "gen_chars_per_s": round(chars / (total - ttft), 1) if (ttft and total > ttft) else 0,
        "body": body,
    }


async def main():
    os.makedirs("/tmp/synth_probe", exist_ok=True)
    print(f"{'model':20s} {'note':18s} {'TTFT':>6s} {'total':>7s} {'chars':>6s} {'c/s':>6s} {'gen c/s':>8s}")
    print("-" * 78)
    for model_id, note in CANDIDATES:
        r = await probe(model_id)
        if r.get("error"):
            print(f"{model_id:20s} {note:18s}  ERROR: {r['error']}")
            continue
        with open(f"/tmp/synth_probe/{model_id}.txt", "w") as f:
            f.write(r["body"])
        print(
            f"{r['model']:20s} {note:18s} {r['ttft_s']:>6}s {r['total_s']:>6}s "
            f"{r['chars']:>6} {r['chars_per_s']:>6} {r['gen_chars_per_s']:>8}"
        )
    print("\n全文见 /tmp/synth_probe/<model>.txt(供质量对比)")


if __name__ == "__main__":
    asyncio.run(main())
