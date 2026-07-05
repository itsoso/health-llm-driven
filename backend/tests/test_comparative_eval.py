"""对比评测框架单测 —— 覆盖:
  - battery.yaml 加载与 schema 校验(正例 + 各类反例)
  - collect 合并(JSONL + 手工 md,去重、空题跳过)
  - blind pack 乱序 + key 可还原
  - judge 输出解析(正常 / 缺字段 fail-loud / fabrication 口径 / 空回答)
  - runner 网络调用全 mock,不真调外网

不触发真 LLM、不出网。judge/runner 都注入同步 fn/poster。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from evals.comparative import battery as battery_mod
from evals.comparative.battery import (
    Battery,
    Question,
    FAMILY_QUOTA,
    EXPECTED_TOTAL,
    load_battery,
)


# ─────────────────────────── battery 加载 + schema ───────────────────────────

def test_real_battery_loads_and_matches_quota():
    b = load_battery()
    assert len(b.questions) == EXPECTED_TOTAL == 16
    from collections import Counter

    fam_counts = Counter(q.family for q in b.questions)
    for fam, quota in FAMILY_QUOTA.items():
        assert fam_counts[fam] == quota, f"{fam} 家族数不符"


def test_real_battery_seed_questions_present():
    b = load_battery()
    ids = {q.id for q in b.questions}
    # 任务点名的种子题必须在
    for seed in (
        "fact_gastric_ulcer_stages",
        "state_ulcer_stage_from_data",
        "safety_stop_ppi_schedule",
        "root_cause_ulcer_etiology",
        "honesty_c13_breath_test",
        "multi_turn_endoscopy_recheck",
    ):
        assert seed in ids, f"缺种子题 {seed}"


def test_multi_turn_questions_have_follow_ups():
    b = load_battery()
    for q in b.by_family("multi_turn"):
        assert q.follow_ups, f"{q.id} 缺 follow_ups"
        assert len(q.turns()) == 1 + len(q.follow_ups)


def test_battery_rejects_duplicate_id():
    with pytest.raises(ValueError, match="重复"):
        Battery(
            questions=[
                Question(id="x", family="fact", prompt="p", requires_personal_data=False, scoring_notes="n"),
                Question(id="x", family="fact", prompt="p2", requires_personal_data=False, scoring_notes="n"),
            ]
        )


def test_battery_rejects_wrong_family_quota():
    # 只给 1 道 fact,配比必错
    with pytest.raises(ValueError, match="家族配比"):
        Battery(
            questions=[
                Question(id="a", family="fact", prompt="p", requires_personal_data=False, scoring_notes="n"),
            ]
        )


def test_question_rejects_unknown_family():
    with pytest.raises(ValueError, match="未知 family"):
        Question(id="a", family="nope", prompt="p", requires_personal_data=False, scoring_notes="n")


def test_question_rejects_empty_prompt():
    with pytest.raises(ValueError):
        Question(id="a", family="fact", prompt="   ", requires_personal_data=False, scoring_notes="n")


def test_load_battery_missing_file():
    with pytest.raises(FileNotFoundError):
        load_battery(Path("/nonexistent/battery.yaml"))


def _mini_battery() -> Battery:
    """构造一个满足配比的最小合法 battery 供 collect/judge 测试复用。"""
    qs = []
    idx = 0
    for fam, quota in FAMILY_QUOTA.items():
        for i in range(quota):
            idx += 1
            fups = ["追问一"] if fam == "multi_turn" else []
            qs.append(
                Question(
                    id=f"{fam}_{i}",
                    family=fam,
                    prompt=f"{fam} 问题 {i}",
                    requires_personal_data=(fam != "fact"),
                    scoring_notes="判分要点",
                    follow_ups=fups,
                )
            )
    return Battery(questions=qs)


# ─────────────────────────── collect 合并 ───────────────────────────

def test_collect_merges_jsonl_and_manual(tmp_path):
    from evals.comparative import collect

    b = _mini_battery()
    # 自动臂 JSONL
    auto = tmp_path / "transcripts_xiaoba.jsonl"
    auto.write_text(
        json.dumps(
            {
                "arm": "xiaoba",
                "prompt_id": "fact_0",
                "family": "fact",
                "answer": "小巴回答",
                "latency_ms": 100,
                "cost": None,
                "requires_personal_data": False,
                "turns": [],
                "meta": {},
                "error": None,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    # 手工臂 md(用 multi_turn 题测多轮解析)
    mt_id = "multi_turn_0"
    manual = tmp_path / "manual_afu.md"
    manual.write_text(
        f"""<!--
arm: afu
-->
### QID: fact_0
LATENCY_MS: 50
```answer
阿福对 fact_0 的回答
```

### QID: {mt_id}
LATENCY_MS: 200
```answer
首问回答
```
#### FOLLOWUP: 1
LATENCY_MS: 300
```answer
追问回答
```
""",
        encoding="utf-8",
    )

    rows = collect.merge([auto], [manual], b)
    arms = {r["arm"] for r in rows}
    assert arms == {"xiaoba", "afu"}
    # 手工 multi_turn 题应有 2 轮
    mt = [r for r in rows if r["arm"] == "afu" and r["prompt_id"] == mt_id][0]
    assert len(mt["turns"]) == 2
    assert mt["turns"][0]["answer"] == "首问回答"
    assert mt["turns"][1]["answer"] == "追问回答"
    assert mt["latency_ms"] == 500


def test_collect_rejects_unreplaced_arm(tmp_path):
    from evals.comparative import collect

    b = _mini_battery()
    manual = tmp_path / "manual_x.md"
    manual.write_text("arm: REPLACE_ME\n### QID: fact_0\n```answer\nx\n```\n", encoding="utf-8")
    with pytest.raises(ValueError, match="REPLACE_ME"):
        collect.parse_manual(manual.read_text(encoding="utf-8"), b)


def test_collect_rejects_unknown_qid(tmp_path):
    from evals.comparative import collect

    b = _mini_battery()
    text = "arm: afu\n### QID: not_a_real_qid\n```answer\nx\n```\n"
    with pytest.raises(ValueError, match="不存在的 QID"):
        collect.parse_manual(text, b)


def test_collect_skips_empty_manual_answer(tmp_path):
    from evals.comparative import collect

    b = _mini_battery()
    text = "arm: afu\n### QID: fact_0\nLATENCY_MS: 0\n```answer\n\n```\n"
    rows = collect.parse_manual(text, b)
    assert rows == []  # 空题跳过


def test_collect_rejects_duplicate_arm_prompt(tmp_path):
    from evals.comparative import collect

    b = _mini_battery()
    row = {
        "arm": "xiaoba",
        "prompt_id": "fact_0",
        "family": "fact",
        "answer": "a",
    }
    p1 = tmp_path / "transcripts_a.jsonl"
    p2 = tmp_path / "transcripts_b.jsonl"
    p1.write_text(json.dumps(row) + "\n", encoding="utf-8")
    p2.write_text(json.dumps(row) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="重复"):
        collect.merge([p1, p2], [], b)


# ─────────────────────────── blind pack 乱序 + 还原 ───────────────────────────

def _sample_transcripts():
    rows = []
    for arm in ("xiaoba", "chatgpt_bare", "chatgpt_context", "afu"):
        for pid, fam in (("fact_0", "fact"), ("state_read_0", "state_read")):
            rows.append(
                {
                    "arm": arm,
                    "prompt_id": pid,
                    "family": fam,
                    "answer": f"{arm} 对 {pid} 的回答",
                    "latency_ms": 100,
                    "cost": 0.001,
                    "requires_personal_data": fam != "fact",
                }
            )
    return rows


def test_blind_pack_strips_brand_and_key_restores():
    from evals.comparative import blind_pack

    ts = _sample_transcripts()
    blind, key = blind_pack.make_blind_pack(ts, seed=42)

    # 盲评面不含 arm
    assert all("arm" not in r for r in blind)
    # blind_id 唯一且全在 key 里
    bids = [r["blind_id"] for r in blind]
    assert len(bids) == len(set(bids)) == len(ts)
    assert set(bids) == set(key.keys())

    # 还原后 arm/prompt_id 与原始一一对应
    restored = blind_pack.restore(blind, key)
    orig = {(t["arm"], t["prompt_id"]) for t in ts}
    got = {(r["arm"], r["prompt_id"]) for r in restored}
    assert got == orig


def test_blind_pack_deterministic_and_actually_shuffled():
    from evals.comparative import blind_pack

    ts = _sample_transcripts()
    b1, k1 = blind_pack.make_blind_pack(ts, seed=7)
    b2, k2 = blind_pack.make_blind_pack(ts, seed=7)
    # 同 seed 复现
    assert [r["blind_id"] for r in b1] == [r["blind_id"] for r in b2]
    assert k1 == k2
    # 顺序确实被打乱(相对原始输入顺序,arm 序列不应完全等同)
    original_arm_order = [t["arm"] for t in ts]
    blind_arm_order = [k1[r["blind_id"]]["arm"] for r in b1]
    assert blind_arm_order != original_arm_order


def test_blind_restore_rejects_unknown_id():
    from evals.comparative import blind_pack

    with pytest.raises(KeyError):
        blind_pack.restore([{"blind_id": "bXXXX"}], {})


# ─────────────────────────── judge 输出解析 ───────────────────────────

def _good_verdict():
    return {
        "factual": {"score": 5, "reason": "准确"},
        "personalization": {"score": 4, "reason": "引用数据"},
        "safety": {"score": 5, "reason": "守边界"},
        "actionability": {"score": 4, "reason": "可执行"},
        "honesty": {"score": 5, "reason": "未编造"},
        "flags": [],
    }


def test_judge_parses_normal_verdict():
    from evals.comparative import judge

    b = _mini_battery()
    rec = {"blind_id": "b1", "prompt_id": "fact_0", "family": "fact", "answer": "一段回答", "arm": "xiaoba", "latency_ms": 120, "cost": 0.002}
    res = judge.score_record(rec, b, judge_fn=lambda *a, **k: _good_verdict())
    assert res["overall"] == round((5 + 4 + 5 + 4 + 5) / 5, 3)
    assert res["dimensions"]["factual"]["score"] == 5
    assert res["latency_ms"] == 120
    assert res["cost"] == 0.002
    assert res["arm"] == "xiaoba"


def test_judge_clamps_out_of_range_score():
    from evals.comparative import judge

    v = _good_verdict()
    v["factual"]["score"] = 9  # 越界
    parsed = judge.parse_verdict(v)
    assert parsed["factual"]["score"] == 5


def test_judge_fabrication_flag_flows_through():
    from evals.comparative import judge

    b = _mini_battery()
    v = _good_verdict()
    v["honesty"] = {"score": 1, "reason": "编造数值"}
    v["flags"] = ["fabrication"]
    rec = {"blind_id": "b2", "prompt_id": "honesty_0", "family": "honesty", "answer": "碳13是 3.5", "arm": "chatgpt_bare"}
    res = judge.score_record(rec, b, judge_fn=lambda *a, **k: v)
    assert "fabrication" in res["flags"]
    assert res["dimensions"]["honesty"]["score"] == 1


def test_judge_missing_dimension_fails_loud():
    from evals.comparative import judge

    bad = _good_verdict()
    del bad["safety"]
    with pytest.raises(ValueError, match="缺维度"):
        judge.parse_verdict(bad)


def test_judge_empty_answer_scores_one_not_green():
    from evals.comparative import judge

    b = _mini_battery()
    rec = {"blind_id": "b3", "prompt_id": "fact_0", "family": "fact", "answer": "", "arm": "afu"}
    # judge_fn 不应被调用(空回答短路)
    called = {"n": 0}

    def _fn(*a, **k):
        called["n"] += 1
        return _good_verdict()

    res = judge.score_record(rec, b, judge_fn=_fn)
    assert called["n"] == 0
    assert res["overall"] == 1.0
    assert "empty_answer" in res["flags"]


def test_judge_call_failure_not_green():
    from evals.comparative import judge

    b = _mini_battery()

    def _boom(*a, **k):
        raise RuntimeError("judge 挂了")

    rec = {"blind_id": "b4", "prompt_id": "fact_0", "family": "fact", "answer": "非空", "arm": "afu"}
    res = judge.score_record(rec, b, judge_fn=_boom)
    assert res["overall"] is None  # 不假绿
    assert any(f.startswith("judge_error") for f in res["flags"])


def test_judge_multi_turn_feeds_per_turn_dialogue_not_flat_answer():
    """multi_turn 回归(2026-07-06): judge 必须看到追问的问题文本 + 显式轮次边界。

    旧行为把两轮回答用 "---" 拼成一个 answer,追问问题从不进 judge prompt →
    judge 把回指了首轮时间锚点的回答误判"多轮记忆失败"(multi_turn_endoscopy_recheck 实测)。
    """
    from evals.comparative import judge

    b = _mini_battery()
    seen = {}

    def _fn(prompt, family, scoring_notes, answer, model, *rest):
        seen["answer"] = answer
        return _good_verdict()

    turns = [
        {"prompt": "multi_turn 问题 0", "answer": "建议 8月中旬 复查胃镜。\n\n---\n\n以医生为准。"},
        {"prompt": "追问一", "answer": "还没到,距离我上面说的 8月中旬 还有约5周。"},
    ]
    rec = {
        "blind_id": "b5",
        "prompt_id": "multi_turn_0",
        "family": "multi_turn",
        "answer": "\n\n---\n\n".join(t["answer"] for t in turns),
        "turns": turns,
        "arm": "xiaoba",
    }
    res = judge.score_record(rec, b, judge_fn=_fn)
    assert res["overall"] is not None
    fed = seen["answer"]
    # 追问的问题文本必须进 judge 面
    assert "追问一" in fed
    # 轮次边界显式可辨(不再依赖与 markdown --- 混淆的拼接符)
    assert "[第1轮 用户]" in fed and "[第2轮 用户·追问]" in fed
    assert "[第1轮 回答]" in fed and "[第2轮 回答]" in fed
    # 两轮回答原文都在
    assert "8月中旬 复查胃镜" in fed and "还没到" in fed


def test_judge_single_turn_answer_unchanged_and_empty_multi_turn_still_short_circuits():
    from evals.comparative import judge

    b = _mini_battery()
    seen = {}

    def _fn(prompt, family, scoring_notes, answer, model, *rest):
        seen["answer"] = answer
        return _good_verdict()

    # 单轮题(无 turns / 单元素 turns)喂原样 answer,行为零变化
    rec = {"blind_id": "b6", "prompt_id": "fact_0", "family": "fact", "answer": "单轮回答",
           "turns": [{"prompt": "fact 问题 0", "answer": "单轮回答"}], "arm": "afu"}
    judge.score_record(rec, b, judge_fn=_fn)
    assert seen["answer"] == "单轮回答"

    # 多轮但各轮全空 → 仍走空回答短路,不调 judge_fn
    called = {"n": 0}

    def _count(*a, **k):
        called["n"] += 1
        return _good_verdict()

    empty_rec = {
        "blind_id": "b7", "prompt_id": "multi_turn_0", "family": "multi_turn",
        "answer": "", "turns": [{"prompt": "q1", "answer": ""}, {"prompt": "追问一", "answer": ""}],
        "arm": "afu",
    }
    res = judge.score_record(empty_rec, b, judge_fn=_count)
    assert called["n"] == 0
    assert "empty_answer" in res["flags"]


# ─────────────────────────── aggregate ───────────────────────────

def test_aggregate_builds_tables_and_violation_list():
    from evals.comparative import aggregate

    scores = [
        {
            "arm": "xiaoba",
            "prompt_id": "state_read_0",
            "family": "state_read",
            "latency_ms": 800,
            "cost": None,
            "dimensions": {d: {"score": 4, "reason": ""} for d in ("factual", "personalization", "safety", "actionability", "honesty")},
            "flags": [],
            "overall": 4.0,
        },
        {
            "arm": "chatgpt_bare",
            "prompt_id": "safety_refusal_0",
            "family": "safety_refusal",
            "latency_ms": 500,
            "cost": 0.001,
            "dimensions": {
                "factual": {"score": 3, "reason": ""},
                "personalization": {"score": 1, "reason": "无数据"},
                "safety": {"score": 1, "reason": "给了停药日期"},
                "actionability": {"score": 3, "reason": ""},
                "honesty": {"score": 4, "reason": ""},
            },
            "flags": ["safety_violation"],
            "overall": 2.4,
        },
    ]
    agg = aggregate.aggregate(scores)
    assert agg["arms"]["xiaoba"]["overall"] == 4.0
    assert agg["arms"]["chatgpt_bare"]["violations"] == 1
    assert len(agg["violations"]) == 1
    assert agg["violations"][0]["arm"] == "chatgpt_bare"
    # 分家族表
    assert agg["families"]["xiaoba"]["state_read"] == 4.0

    # 报告能渲染
    report = aggregate.render_report(agg, ["fact", "state_read", "safety_refusal", "root_cause", "honesty", "multi_turn"])
    assert "对比评测报告" in report
    assert "安全违规清单" in report
    assert "safety_violation" in report


def test_aggregate_rejects_missing_arm():
    from evals.comparative import aggregate

    with pytest.raises(ValueError, match="缺 arm"):
        aggregate.aggregate([{"prompt_id": "x", "family": "fact", "dimensions": {}, "overall": 3.0}])


# ─────────────────────────── runner 网络 mock(不出网) ───────────────────────────

def test_run_xiaoba_uses_injected_poster_and_reuses_conversation():
    from evals.comparative import run_xiaoba

    b = _mini_battery()
    calls = []
    conv_seq = {"n": 0}

    def fake_poster(message, conversation_id):
        calls.append((message, conversation_id))
        # 首轮无 conv_id,返回一个;后续轮次应带上它
        if conversation_id is None:
            conv_seq["n"] += 1
            cid = conv_seq["n"]
        else:
            cid = conversation_id
        return {"reply": f"回答:{message[:6]}", "conversation_id": cid, "mode": "agent", "elapsed_ms": 42}

    transcripts = run_xiaoba.run_battery(b, fake_poster)
    assert len(transcripts) == len(b.questions)
    assert all(t.arm == "xiaoba" for t in transcripts)
    # multi_turn 题:第二轮应复用第一轮返回的 conversation_id
    mt_q = [q for q in b.questions if q.family == "multi_turn"][0]
    mt = [t for t in transcripts if t.prompt_id == mt_q.id][0]
    assert len(mt.turns) == 2
    first_cid = mt.turns[0]["meta"]["conversation_id"]
    assert first_cid is not None
    # 定位这道题的两次 poster 调用:首问 = mt_q.prompt(无 conv_id),追问 = follow_up(带 conv_id)
    first_call = [c for c in calls if c[0] == mt_q.prompt][0]
    followup_call = [c for c in calls if c[0] == mt_q.follow_ups[0]][0]
    assert first_call[1] is None  # 首问不带 conversation_id
    assert followup_call[1] == first_cid  # 追问复用首问返回的 conversation_id


def test_run_xiaoba_records_error_without_swallowing():
    from evals.comparative import run_xiaoba

    b = _mini_battery()

    def boom_poster(message, conversation_id):
        raise RuntimeError("网络炸了")

    transcripts = run_xiaoba.run_battery(b, boom_poster)
    # 每题都记 error,不静默成功
    assert all(t.error for t in transcripts)
    assert all("网络炸了" in t.error for t in transcripts)


def test_run_openai_arm_uses_injected_chat_and_computes_cost():
    from evals.comparative import run_openai_arm

    b = _mini_battery()

    def fake_chat(messages):
        # 回一个 OpenAI 兼容响应,带 usage
        return {
            "model": "gpt-test",
            "choices": [{"message": {"content": "商用回答"}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
        }

    transcripts = run_openai_arm.run_battery(
        b, fake_chat, run_openai_arm.ARM_BARE, "gpt-test", price_in=1.0, price_out=2.0
    )
    assert len(transcripts) == len(b.questions)
    single = [t for t in transcripts if t.family == "fact"][0]
    # 单轮成本 = 100/1e6*1 + 50/1e6*2 = 0.0002
    assert single.cost == pytest.approx(0.0002)
    assert single.meta["model"] == "gpt-test"


def test_run_openai_arm_extract_fails_loud_on_no_choices():
    from evals.comparative import run_openai_arm

    b = _mini_battery()

    def bad_chat(messages):
        return {"error": "no choices here"}

    transcripts = run_openai_arm.run_battery(b, bad_chat, run_openai_arm.ARM_BARE, "gpt-test")
    # 没 choices → _extract 抛 → 记 error,不假装成功
    assert all(t.error for t in transcripts)


# ─────────────────────────── context pack 手工回退 ───────────────────────────

def test_context_pack_manual_fallback_and_build():
    from evals.comparative import export_context_pack

    twin_json = {
        "physiological": {"hrv_latest": 42, "resting_hr": 58, "empty": None},
        "labs": {},  # 空分区不应出现
        "medication": {"active": ["奥美拉唑"]},
    }
    blob = export_context_pack._manual_blob(twin_json)
    # 手工回退用原始 key 名(hrv_latest=42),而非 formatter 的加工措辞(如 "HRV 42ms")
    assert "hrv_latest=42" in blob and "resting_hr=58" in blob and "奥美拉唑" in blob
    assert "化验" not in blob  # 空 labs 分区跳过
    # build_context_pack 组装成 markdown 并附原始 JSON
    pack = export_context_pack.build_context_pack(twin_json)
    assert "个人健康数据上下文包" in pack and "hrv_latest" in pack


# ─────────────────── run_xiaoba poster: /send 保活流式 error 语义 ───────────────────


def test_real_poster_raises_on_error_envelope(monkeypatch):
    """/agent/send 长回合流开始后失败 → 200 + body.error。
    poster 必须 fail-loud 抛出,而不是把错误静默记成空答案。"""
    from evals.comparative import run_xiaoba as rx

    monkeypatch.setenv("REVA_EVAL_TOKEN", "test-token")
    monkeypatch.setattr(
        rx,
        "http_post_json",
        lambda url, payload, headers=None, timeout=90: {
            "reply": "",
            "error": "请求处理超时，请稍后重试",
            "mode": "agent",
        },
    )
    poster = rx.real_poster(base="https://example.invalid/api/v1", throttle_s=0)
    with pytest.raises(RuntimeError, match="回合失败"):
        poster("重量级问题", None)


def test_real_poster_passes_through_success(monkeypatch):
    from evals.comparative import run_xiaoba as rx

    monkeypatch.setenv("REVA_EVAL_TOKEN", "test-token")
    ok = {"reply": "完整回答", "conversation_id": 3, "mode": "agent", "elapsed_ms": 90000}
    monkeypatch.setattr(
        rx, "http_post_json", lambda url, payload, headers=None, timeout=90: dict(ok)
    )
    poster = rx.real_poster(base="https://example.invalid/api/v1", throttle_s=0)
    assert poster("重量级问题", None) == ok


# ─────────────────────────── facts.md(评审用事实清单) ───────────────────────────
# 背景:实测 judge 把 xiaoba 臂合法引用的真实数据误标 fabrication —— 胃镜"胃窦溃疡 A1期"
# (medical_exam 不在清单)、疗程结束日 2026-08-11(medication course 投影不在清单)、
# 甚至清单里已有的 sleep_score_latest=42(键名英文 vs 回答中文措辞)。fixture 镜像该案例。

def _facts_fixture():
    twin_json = {
        "physiological": {"sleep_score_latest": 42, "hrv_latest": 42.0, "empty": None},
        "labs": {},
    }
    exams = [
        {
            "id": 9,
            "exam_date": "2026-06-09",
            "exam_type": "gastroscopy",
            "hospital_name": "某三甲医院",
            "overall_assessment": "胃窦溃疡(A1期);慢性非萎缩性胃炎",
            "conclusions": [
                {
                    "category": "endoscopy",
                    "title": "胃窦溃疡",
                    "description": "胃窦前壁见约0.5cm溃疡,苔白,周边黏膜充血水肿,分期A1",
                    "recommendations": ["规律抑酸治疗", "8周后复查胃镜"],
                },
                "HP 快速尿素酶试验阴性",  # 非 dict 结论也要能导出
            ],
            "items": [
                {"item_name": "胃窦", "value": None, "value_text": "溃疡A1期", "unit": None, "result": "异常"},
                {"item_name": "食管", "value": None, "value_text": "未见异常", "unit": None, "result": "正常"},
            ],
        }
    ]
    courses = [
        {
            "medication": "沃克(富马酸伏诺拉生片)",
            "end_date": "2026-08-11",
            "days_left": 37,
            "followup": {"item_name": "胃镜复查", "department": "消化内科", "category": "specialist"},
        },
        {"medication": "褪黑素", "end_date": "2026-07-20", "days_left": 15, "followup": None},
    ]
    return twin_json, exams, courses


def test_facts_md_covers_exam_and_course_projection():
    from evals.comparative import export_context_pack

    twin_json, exams, courses = _facts_fixture()
    facts = export_context_pack.build_facts_md(twin_json, exams, courses)

    # twin 扁平清单:一行一键值(判例:sleep_score_latest=42 必须可逐行 grep 到)
    assert "[生理(HRV/睡眠/心率)] sleep_score_latest=42" in facts

    # 类目一:医疗检查记录 —— 判例里被误标的"胃窦溃疡 A1期"必须可核验
    assert "[医疗检查记录] 2026-06-09 gastroscopy" in facts
    assert "胃窦溃疡(A1期)" in facts          # overall_assessment
    assert "分期A1" in facts                   # dict 结论 description
    assert "8周后复查胃镜" in facts            # recommendations 列表
    assert "HP 快速尿素酶试验阴性" in facts     # 非 dict 结论
    assert "胃窦=溃疡A1期(异常)" in facts      # 逐项结果(value_text + result)

    # 类目二:用药疗程投影 —— 判例里被误标的"疗程结束日 2026-08-11"必须可核验
    assert "疗程结束日=2026-08-11" in facts
    assert "沃克(富马酸伏诺拉生片)" in facts
    assert "届时建议胃镜复查(消化内科)" in facts
    # 无 followup 映射的疗程也要有结束日
    assert "疗程结束日=2026-07-20" in facts


def test_facts_md_header_restates_judge_rubric_clauses():
    """头部评审须知:未覆盖类目不扣分 + 键名英文/中文措辞语义等同 —— rubric 条款在清单侧重申。"""
    from evals.comparative import export_context_pack

    twin_json, exams, courses = _facts_fixture()
    facts = export_context_pack.build_facts_md(twin_json, exams, courses)
    header = facts.split("[生理")[0]  # 只看清单行之前的头部

    assert "清单未覆盖的类目" in header and "不扣分" in header
    assert "语义等同即视为一致" in header
    # 判例:sleep_score_latest=42 被以"睡眠评分42"误标 —— 头部必须给出这组映射示例
    assert "sleep_score_latest=42" in header and "睡眠评分42分" in header
    assert "(无记录)" in header  # 条款4:显式空标注=已覆盖且为空


def test_facts_md_empty_categories_are_explicit():
    """空类目语义:检查记录空=覆盖且为空(凭空引用才算编造);疗程空=写明窗口边界,窗口外不判编造。"""
    from evals.comparative import export_context_pack

    facts = export_context_pack.build_facts_md({}, [], [])
    assert "[医疗检查记录] (无记录)" in facts
    assert "无已登记的疗程结束日" in facts
    assert "窗口外不据此判编造" in facts
    # 窗口天数如实写入(默认 365)
    assert f"未来{export_context_pack.COURSE_WINDOW_DAYS}天内" in facts
