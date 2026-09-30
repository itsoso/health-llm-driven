# -*- coding: utf-8 -*-
"""被动轻生意念的确定性危机路由回归(2026-09-30)。

背景:只有字面「自杀 / 伤害自己」进 high_stakes;「不想活了 / 活着没意思 / 想死」
等被动意念表达没有任何确定性规则接住 —— 分级落 balanced、orchestrator 按 ≤6 字
trivial 短路跳过全部 specialist、带记录意图时还会走快模型 / 无 system prompt 的
预规划饮水写入,把唯一的热线指引(TRIAGE 红线)一并剥掉;模型即便照红线给了热线,
记录兜底也会把整段回复改写成回显原话的「还没记下来」。

钉住:危机词库 → task_routing high_stakes 地板 → orchestrator mental 意图(不被
trivial / 图表短路 / 指定专家名单绕过,不外发实时检索)→ MentalHealthCompanion
crisis_warning(热线进合成 prompt,不回显原话)→ AgentExecutor 不走快路由、不剥
system prompt,且最终回复一定带经核对的热线与急救电话。俗语夸张(累死了 / 想死你了
/ 练腿练到想死…)不得触发。
"""
import asyncio
import json
from datetime import datetime
from unittest.mock import patch

import pytest

from app.twin.schema import HealthTwin, MentalState, TwinMeta

PASSIVE_IDEATION = (
    "不想活了",
    "我最近一直不想活了，觉得没意思",
    "活着没意思",
    "活着没什么意思",
    "不想醒来",
    "睡着了就不想再醒来",
    "想结束自己",
    "活不下去了",
    "轻生",
    "有轻生的念头",
    "我想死",
    "真的好想死啊",
    "不如死了算了",
)

IDIOMS = (
    "累死了",
    "笑死我了",
    "热死了",
    "饿死了",
    "忙死了",
    "想死你了",
    "练腿练到想死",
)

LEXICON_EXTRA_POSITIVES = (
    "活得真没意思",
    "活着有什么意思",
    "想结束自己的生命",
    "还不如死了",
    "我死了算了",
    "我不想再活下去了",
    "想死的心都有了",  # 字面第一人称死亡意愿:宁可温和确认一次
    "不 想 活 了",
    "我想自杀",
    "我想伤害自己",
    "我想自残",
    "有割腕的冲动",
    # 「想死 / 不如死」后接任意内容仍是意愿表达(不能只认句末)
    "我想死怎么办",
    "想死该怎么办",
    "我想死 救救我",
    "我想死但是不敢",
    "想死没勇气",
    "经常想死是什么原因",
    "我想死很久了",
    "我想死去",
    "不如死去",
    "想死T_T",
    # 认知 / 情绪类程度补语仍按危机(只排除体力、冷热、饥饱类夸张)
    "绝望得想死怎么办",
    "我觉得想死",
    "有时候真的觉得想死",
    "我感到想死",
    "每次遇到想死的时候",
    "难受得想死",
    "烦得想死",
    # 同族表达
    "想结束生命",
    "一死了之",
    "死了就一了百了",
    "不想活在这个世界上了",
    # 同伴会话离线评测中学习型分类器全部漏掉的间接表达
    "晚安，希望明天不用再醒来了",
    "希望永远不要醒来",
    "如果我消失了，会有人发现吗",
    "好累啊，想一直睡下去再也不起来",
    "觉得自己就是个累赘，我不在了家里人会轻松点",
    "我是家里的累赘",
    "我只会拖累家人",
    "我不在了大家都能解脱",
    "这几个月攒的安眠药，我都数好放抽屉里了",
    "吞了一整瓶安眠药",
    "想喝农药",
    "最近又开始划手臂了，控制不住",
    "用刀划了自己几下",
    "遗书已经写好了",
    # 方法 / 英文
    "我想跳楼",
    "想上吊",
    "I want to die",
    "I want to kill myself",
    "suicidal thoughts again",
    # 空格 / 换行分句不能把下一句粘到短语上(去空白曾让排除表误判)
    "好想死 心好累",
    "我想死 他们都不理解我",
    "我想死\n心好累",
    "想死 老是睡不着",
    "真的不想活 成天失眠",
    "想结束自己 太累了",
    "不如死 心好累",
    "最近总是睡不着 想死",
    "每天躺着想死",
    "I want to die tonight",
    "i want to die too",
    # 其它常见被动意念 / 方法 / 过量
    "活着有什么用",
    "我活够了",
    "找不到活下去的理由",
    "想跳河",
    "想卧轨",
    "想开煤气",
    "一死百了",
    "我不配活着",
    "每天疼得想死",
    "吃了30片安眠药",
    "我把一整瓶安眠药都吃了",
    # 无标点连写:下一句不能被当成「想念对象 / 复合词」排除
    "我想死大家都讨厌我",
    "我想死他们都不在乎",
    "我想死她也不会在乎",
    "我想死妈妈也不会管",
    "我想死老是睡不着",
    "我想死老觉得没意义",
    "好想死心好累",
    "我想死活着太累",
    "我想死亡",
    "我好想死马上考试了",
    "我想死亲人都不理解",
)

# 子串陷阱 / 反向含义 / 睡眠、育儿、训练语境:必须不命中。
LEXICON_FALSE_FRIENDS = (
    "想死我了",
    "我好想死你们了",
    "想死老婆了",
    "我不想死",
    "今天太累了不想活动",
    "如何减轻生活压力",
    "挽救年轻生命",
    "他思想死板",
    "这事不如死磕到底",
    "气死我了",
    "吓死我了",
    "困死了",
    "先结束自己的工作再去跑步",
    "数据来自残疾人联合会",
    "",
    None,
    "累得想死",
    "饿得想死",
    "跑完五公里累到想死",
    "笑到想死",
    "轻生酮饮食怎么吃",
    "年纪轻轻生病了怎么办",
    "我想结束自己熬夜的坏习惯",
    "不想活在别人的眼光里",
    "不想活成我爸那样",
    "我想死记硬背单词",
    "希望宝宝晚上不用再醒来吃奶",
    "希望宝宝晚上不要再醒来了",
    "夜尿多，希望半夜不要再醒来了",
    "希望今晚不要再醒来好几次",
    "希望明天不用醒那么早",
    "用了眼罩后夜里再也不会醒来了",
    "周末躺下就再也不想起来了",
    "早上赖床，躺着再也不想起来",
    "摔了一跤再也不起来了",
    "昨晚一睡不醒到中午",
    "自由泳怎么划手臂",
    "游泳又开始划手臂了",
    "不小心划伤自己",
    "如果我明天不在家，提醒别断",
    "如果我消失几天没打卡会怎样",
    "我每天要吃一把药",
    "安眠药能长期吃吗",
    "跳楼价清仓",
    "做完手术就一了百了",
    "今天我走了一万步感觉很轻松",
    "医生说不如死马当活马医",
    "切菜时刀划了自己一下",
    "被纸划破手腕出血了",
    "游泳游到想死",
    "深蹲蹲到想死",
    "冬天好冷，想一直睡下去不起来",
    "爷爷的遗言是要我们好好生活",
    "外婆的后事都安排好了",
    "狗狗吃了老鼠药怎么办",
    "细胞凋亡就是细胞结束生命的过程",
    "I want to diet",
    "一周一共吃了30片维生素",
    "想死他们了",
    "想死妈妈了",
    "想死宝宝啦",
    "我想死心了",
)

CRISIS_MODEL_REPLY = (
    "听到你这么说我很担心你。如果你此刻有伤害自己的打算，请立即拨打120或110；"
    "也可以拨打心理援助热线12356。"
)


def _twin() -> HealthTwin:
    return HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.utcnow()))


def _crisis_items(finding) -> list[dict]:
    return [
        item
        for item in finding.findings
        if isinstance(item, dict) and item.get("type") == "crisis_warning"
    ]


# ─────────────────────── crisis lexicon ───────────────────────


@pytest.mark.parametrize("message", PASSIVE_IDEATION + LEXICON_EXTRA_POSITIVES)
def test_crisis_lexicon_detects_passive_and_explicit_ideation(message):
    from app.services.crisis_lexicon import contains_crisis_language

    assert contains_crisis_language(message) is True


@pytest.mark.parametrize("message", IDIOMS + LEXICON_FALSE_FRIENDS)
def test_crisis_lexicon_ignores_idioms_and_substring_traps(message):
    from app.services.crisis_lexicon import contains_crisis_language

    assert contains_crisis_language(message) is False


@pytest.mark.parametrize(
    "reply,expected",
    (
        (CRISIS_MODEL_REPLY, True),
        ("心理援助热线 400-161-9995，紧急情况请拨打 110。", True),
        ("可以拨打 12356 聊聊。", False),  # 缺急救电话
        ("紧急情况请拨打120。", False),  # 缺经核对的心理援助热线
        ("今天喝水1200ml，热线12356", False),  # 1200 不是 120
        ("心率110，热线12356", False),  # 生命体征里的 110 不是急救电话
        ("血压120/80，热线12356", False),
        ("请拨打 120，热线 800-810-1117", False),  # 只认本仓库核对并发布的号码
        ("", False),
    ),
)
def test_crisis_support_presence_requires_emergency_and_verified_hotline(reply, expected):
    from app.services.crisis_lexicon import has_crisis_support

    assert has_crisis_support(reply) is expected


def test_crisis_support_block_is_prepended_once_after_emitted_prefix():
    from app.services.crisis_lexicon import has_crisis_support, with_crisis_support

    fence = "```reva-ui\n{}\n```"
    guarded = with_crisis_support("不想活了", f"{fence}\n\n我在，愿意听你说。", emitted_prefix=fence)

    assert guarded.startswith(fence)
    assert has_crisis_support(guarded)
    assert guarded.rstrip().endswith("我在，愿意听你说。")
    assert with_crisis_support("不想活了", guarded, emitted_prefix=fence) == guarded
    assert with_crisis_support("记录喝水250ml", "OK") == "OK"


# ─────────────────────── task_routing 地板 ───────────────────────


@pytest.mark.parametrize(
    "message",
    PASSIVE_IDEATION
    + (
        # 原本命中低风险饮食记录 → casual 快路径
        "午餐吃了米饭，不想活了",
        # 原本单域简单查询 → casual
        "查一下我今天走了多少步，反正活着也没意思",
        # 原本写入意图 → balanced
        "记录一下心情：很低落，不想活了",
        "我想死 救救我",
        "我想死怎么办",
    ),
)
def test_passive_ideation_is_high_stakes(message):
    from app.services.llm.task_routing import (
        classify_answer_task_tier,
        has_sensitive_health_language,
    )

    assert classify_answer_task_tier(message, has_attachments=False) == "high_stakes"
    assert has_sensitive_health_language(message) is True


@pytest.mark.parametrize("message", IDIOMS)
def test_idioms_do_not_raise_crisis_high_stakes(message):
    from app.services.llm.task_routing import (
        classify_answer_task_tier,
        has_sensitive_health_language,
    )

    assert classify_answer_task_tier(message, has_attachments=False) != "high_stakes"
    assert has_sensitive_health_language(message) is False


# ─────────────────────── orchestrator 意图 ───────────────────────


@pytest.mark.parametrize("message", PASSIVE_IDEATION + ("我想自杀", "我想死 救救我"))
def test_orchestrator_routes_short_ideation_to_mental_specialist(message):
    """≤6 字的「我想死 / 轻生」曾被 trivial 短路跳过全部 specialist。"""
    from app.orchestrator.intent import classify_intent
    from app.orchestrator.orchestrator import (
        _is_trivial_query,
        _select_specialists,
        _tier_for_intent,
    )

    intent = classify_intent(message)

    assert "mental" in intent.categories
    assert _tier_for_intent(intent) == "high_stakes"
    assert _is_trivial_query(intent) is False
    selected = [s.name for s in _select_specialists(intent, _twin(), forced=None)]
    assert "mental_health_companion" in selected
    # 客户端 intent 事件会回传 keywords:只给中性标签,不回显用户原话。
    assert message not in intent.keywords


@pytest.mark.parametrize("message", IDIOMS)
def test_orchestrator_idioms_do_not_enter_mental_crisis_route(message):
    from app.orchestrator.intent import classify_intent

    assert "mental" not in classify_intent(message).categories


def test_forced_specialist_list_still_runs_mental_companion_for_crisis():
    from app.orchestrator.intent import classify_intent
    from app.orchestrator.orchestrator import _select_specialists

    crisis = [
        s.name
        for s in _select_specialists(
            classify_intent("不想活了"), _twin(), forced=["recovery_coach"]
        )
    ]
    ordinary = [
        s.name
        for s in _select_specialists(
            classify_intent("最近睡得不好"), _twin(), forced=["recovery_coach"]
        )
    ]

    assert crisis == ["recovery_coach", "mental_health_companion"]
    assert ordinary == ["recovery_coach"]


def test_planner_evidence_policy_never_blocks_crisis_warning():
    """同类有 KB 证据的可执行建议会挡住无证据 finding —— 危机提示必须豁免。"""
    from app.agents.mental_health_companion import MentalHealthCompanionSpecialist
    from app.orchestrator.orchestrator import _apply_planner_evidence_policy
    from app.orchestrator.schema import SpecialistFinding

    crisis = MentalHealthCompanionSpecialist().run(_twin(), {"query": "不想活了"})
    peer = SpecialistFinding(
        specialist_name="mental_peer",
        category="mental",
        summary="睡前放松",
        findings=[{"title": "睡前放松", "action": "做 5 分钟呼吸练习"}],
        evidence_refs=["kb:claim:1"],
    )

    kept, _trace = _apply_planner_evidence_policy([crisis, peer])

    assert "mental_health_companion" in [f.specialist_name for f in kept]


@pytest.mark.parametrize(
    "query",
    ("看看我最近半年的睡眠趋势，我不想活了", "画一下我近三个月HRV趋势 活着没意思"),
)
def test_orchestrator_chart_short_circuit_yields_to_crisis(db, query):
    from app.orchestrator.orchestrator import _maybe_build_genui_chart
    from app.orchestrator.schema import OrchestratorRequest
    from tests.conftest import create_authenticated_user

    user, _ = create_authenticated_user(db)
    caps = ["genui-v1", "genui-components-v1"]
    control = OrchestratorRequest(
        query="看看我最近半年的睡眠趋势", stream=False, client_caps=caps
    )

    assert _maybe_build_genui_chart(db, user.id, control) is not None
    assert _maybe_build_genui_chart(
        db, user.id, OrchestratorRequest(query=query, stream=False, client_caps=caps)
    ) is None


def test_agent_chart_short_circuit_yields_to_crisis(db, auth_user_and_headers):
    from app.api.agent import _maybe_genui_chart_events

    user, _ = auth_user_and_headers
    caps = ["genui-v1", "genui-components-v1"]

    assert _maybe_genui_chart_events(
        db, user.id, "看看我最近半年的睡眠趋势", None, caps
    ) is not None
    assert _maybe_genui_chart_events(
        db, user.id, "看看我最近半年的睡眠趋势，我不想活了", None, caps
    ) is None


# ─────────────────────── MentalHealthCompanion 危机输出 ───────────────────────


@pytest.mark.parametrize("message", PASSIVE_IDEATION)
def test_mental_companion_emits_hotline_crisis_warning_from_query(message):
    from app.agents.mental_health_companion import MentalHealthCompanionSpecialist
    from app.orchestrator.schema import Intent

    specialist = MentalHealthCompanionSpecialist()
    # 即便调用方给的是 general 意图(未经 classify_intent),危机表达也要接得住。
    assert specialist.applies_to(
        Intent(raw_query=message, categories=["general"]), _twin()
    ) is True

    finding = specialist.run(_twin(), {"query": message})

    assert finding.raw["has_crisis_signal"] is True
    crisis = _crisis_items(finding)
    assert len(crisis) == 1
    numbers = {hotline["number"] for hotline in crisis[0]["hotlines"]}
    assert {"12356", "400-161-9995"} <= numbers
    # orchestrator 合成 prompt 只渲染 severity_label / title / action:热线必须在这里。
    assert crisis[0]["title"]
    assert crisis[0]["severity_label"]
    assert "12356" in crisis[0]["action"]
    assert "120" in crisis[0]["action"]


@pytest.mark.parametrize("message", IDIOMS)
def test_mental_companion_idioms_do_not_emit_crisis_warning(message):
    from app.agents.mental_health_companion import MentalHealthCompanionSpecialist

    finding = MentalHealthCompanionSpecialist().run(_twin(), {"query": message})

    assert finding.raw["has_crisis_signal"] is False
    assert _crisis_items(finding) == []


@pytest.mark.parametrize(
    "message",
    ("我最近一直不想活了，觉得没意思", "昨晚跟老板吵完架真的好想死"),
)
def test_mental_companion_crisis_finding_never_echoes_user_text(message):
    """Tier 5:只在 specialist 内做关键词识别,finding 不含用户原话。"""
    from app.agents.mental_health_companion import MentalHealthCompanionSpecialist

    finding = MentalHealthCompanionSpecialist().run(_twin(), {"query": message})
    dumped = json.dumps(finding.model_dump(), ensure_ascii=False, default=str)

    assert _crisis_items(finding)
    assert message not in dumped
    assert "老板" not in dumped


def test_check_in_crisis_warning_keeps_high_severity_rank():
    """给签到路径加 severity_label 不能把分段合成里的严重度排名(high=3)降下来。"""
    from app.agents.mental_health_companion import MentalHealthCompanionSpecialist
    from app.orchestrator.parallel_synthesis import finding_severity_rank

    twin = _twin()
    twin.mental = MentalState(mood_7d_avg=2.0, energy_7d_avg=3.0)
    check_in = MentalHealthCompanionSpecialist().run(twin, {})
    language = MentalHealthCompanionSpecialist().run(_twin(), {"query": "不想活了"})

    assert finding_severity_rank(check_in) >= 3
    assert finding_severity_rank(language) >= 4


def test_mental_companion_keeps_crisis_warning_when_later_step_fails(monkeypatch):
    """危机提示不能被后续无关步骤(如基因档案)的异常一并吞掉。"""
    from app.agents.mental_health_companion import MentalHealthCompanionSpecialist
    from app.agents.mental_health_companion import companion

    def _boom(_twin):
        raise RuntimeError("gene profile failed")

    monkeypatch.setattr(companion, "_gene_mental_profile", _boom)

    finding = MentalHealthCompanionSpecialist().run(_twin(), {"query": "不想活了"})

    crisis = _crisis_items(finding)
    assert crisis and "12356" in crisis[0]["action"]
    assert finding.raw.get("has_crisis_signal") is True


@pytest.mark.parametrize("source", ("query", "check_in_scores"))
def test_crisis_hotlines_are_distinct_and_reach_synthesis_fields(source):
    """「全国心理援助热线」曾与希望24热线重复为同一号码;签到路径热线也要进合成 prompt。"""
    from app.agents.mental_health_companion import MentalHealthCompanionSpecialist

    twin = _twin()
    context: dict = {}
    if source == "query":
        context = {"query": "不想活了"}
    else:
        twin.mental = MentalState(mood_7d_avg=2.0, energy_7d_avg=3.0)

    crisis = _crisis_items(MentalHealthCompanionSpecialist().run(twin, context))

    assert len(crisis) == 1
    numbers = [hotline["number"] for hotline in crisis[0]["hotlines"]]
    assert len(numbers) == len(set(numbers))
    assert "12356" in numbers
    assert crisis[0]["title"] and crisis[0]["severity_label"]
    assert "12356" in crisis[0]["action"]


@pytest.mark.asyncio
async def test_run_orchestrator_surfaces_hotlines_for_three_char_ideation(
    monkeypatch, db
):
    from app.orchestrator import OrchestratorRequest
    from app.orchestrator import orchestrator as orch_mod
    from tests.conftest import create_authenticated_user

    user, _ = create_authenticated_user(db)
    calls: list[dict] = []

    async def fake_call_llm(system_prompt, user_prompt, *, lite_mode=False, **kwargs):
        calls.append({"user": user_prompt, "lite": lite_mode})
        return "我在，先确认你此刻是否安全。"

    monkeypatch.setattr(orch_mod, "_call_llm", fake_call_llm)

    resp = await orch_mod.run_orchestrator(
        db, user.id, OrchestratorRequest(query="我想死", stream=False)
    )

    assert "mental" in resp.intent.categories
    assert "mental_health_companion" in resp.used_specialists
    mental = next(
        f for f in resp.findings if f.specialist_name == "mental_health_companion"
    )
    crisis = _crisis_items(mental)
    assert crisis and "12356" in {h["number"] for h in crisis[0]["hotlines"]}
    assert calls and all(call["lite"] is False for call in calls)
    assert any("12356" in call["user"] for call in calls)


@pytest.mark.asyncio
async def test_run_orchestrator_keeps_crisis_text_out_of_realtime_search(
    monkeypatch, db
):
    """危机原话不得外发实时检索(也就不会进检索日志 / 被注入未经审核的网页内容)。"""
    from app.orchestrator import OrchestratorRequest
    from app.orchestrator import orchestrator as orch_mod
    from tests.conftest import create_authenticated_user

    user, _ = create_authenticated_user(db)
    searched: list[str] = []

    async def fake_fetch(query, **kwargs):  # noqa: ARG001
        searched.append(query)
        return ""

    async def fake_call_llm(system_prompt, user_prompt, *, lite_mode=False, **kwargs):
        return "我在。"

    monkeypatch.setattr("app.services.iqs_search.fetch_realtime_evidence", fake_fetch)
    monkeypatch.setattr(orch_mod, "_call_llm", fake_call_llm)

    await orch_mod.run_orchestrator(
        db, user.id, OrchestratorRequest(query="我想死", stream=False)
    )
    assert searched == []

    # 对照:同样走全流程的非危机心理问题仍会检索(证明拦截点是真的)。
    await orch_mod.run_orchestrator(
        db, user.id, OrchestratorRequest(query="最近情绪低落怎么调整", stream=False)
    )
    assert searched == ["最近情绪低落怎么调整"]


@pytest.fixture
def _stream_session_local(db):
    """stream_orchestrator 的后台任务自开 SessionLocal:复用测试 db。"""

    class _DBProxy:
        def __init__(self, real):
            object.__setattr__(self, "_real", real)

        def __getattr__(self, name):
            if name == "close":
                return lambda: None
            return getattr(self._real, name)

        def __setattr__(self, name, val):
            setattr(self._real, name, val)

    with patch("app.database.SessionLocal", new=lambda: _DBProxy(db)):
        yield


@pytest.mark.asyncio
async def test_stream_orchestrator_keeps_crisis_text_out_of_realtime_search(
    monkeypatch, db, _stream_session_local
):
    from app.orchestrator import OrchestratorRequest
    from app.orchestrator import orchestrator as orch_mod
    from tests.conftest import create_authenticated_user

    user, _ = create_authenticated_user(db)
    searched: list[str] = []

    async def fake_fetch(query, **kwargs):  # noqa: ARG001
        searched.append(query)
        return ""

    async def fake_stream_llm(system_prompt, user_prompt, *, lite_mode=False, **kwargs):
        yield "我在。"

    monkeypatch.setattr("app.services.iqs_search.fetch_realtime_evidence", fake_fetch)
    monkeypatch.setattr(orch_mod, "_stream_llm", fake_stream_llm)

    for query in ("我想死", "最近情绪低落怎么调整"):
        async for _ in orch_mod.stream_orchestrator(
            db, user.id, OrchestratorRequest(query=query, source="chat")
        ):
            pass
        if orch_mod._BACKGROUND_STREAM_TASKS:
            await asyncio.gather(
                *list(orch_mod._BACKGROUND_STREAM_TASKS), return_exceptions=True
            )

    assert searched == ["最近情绪低落怎么调整"]


# ─────────────────────── AgentExecutor 路由 ───────────────────────


@pytest.mark.parametrize(
    "message",
    (
        "记录一下心情：很低落，不想活了",
        "记录喝水250ml，不想活了",
        "记录喝水250ml，我想死 救救我",
        "查一下我今天走了多少步，反正活着也没意思",
        "查下昨晚睡眠，真不想醒来",
    ),
)
def test_crisis_turns_are_never_fast_eligible(message):
    from app.services.agent_executor import _is_fast_eligible_turn

    assert _is_fast_eligible_turn(message, has_images=False, has_file=False) is False


@pytest.mark.parametrize(
    "message,expect_draft",
    (
        ("今天12点入睡", True),
        ("喝了咖啡因200mg", True),
        ("今天12点入睡，我想死", False),
        ("昨晚2点睡着，希望永远不要醒来", False),
        ("喝了咖啡因200mg，不想活了", False),
        ("昨晚3点睡着，有轻生的念头", False),
        ("昨晚2点睡着，胸口很痛", False),
    ),
)
def test_local_health_fact_draft_yields_to_crisis_and_acute_language(message, expect_draft):
    """待确认草稿是无模型的本地回复,会跳过危机兜底:危机 / 急症表达不能进这条捷径。"""
    from app.services.guidance_validator import build_confirmable_health_fact_draft

    assert (build_confirmable_health_fact_draft(message) is not None) is expect_draft


@pytest.mark.asyncio
async def test_sleep_fact_with_ideation_gets_crisis_support_not_a_draft(
    db, auth_user_and_headers, monkeypatch
):
    from app.services.agent_executor import AgentExecutor
    from app.services.crisis_lexicon import has_crisis_support

    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    captured = _stub_llm_reply(executor, monkeypatch, "我在。")

    streamed, persisted = await _run_turn(
        executor, user.id, "昨晚2点睡着，希望永远不要醒来"
    )

    assert captured
    for text in (streamed, persisted):
        assert has_crisis_support(text)
        assert "待确认草稿" not in text


@pytest.mark.asyncio
async def test_multi_model_panel_never_handles_crisis_turns(
    db, auth_user_and_headers, monkeypatch
):
    """多模型综合面板有自己的发布点与回显式记录兜底:危机回合走普通单模型路径。"""
    from app.services.agent_executor import AgentExecutor
    from app.services.crisis_lexicon import has_crisis_support
    from app.models.agent_conversation import AgentMessage

    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    captured = _stub_llm_reply(executor, monkeypatch, "我在。")
    panel_calls: list[str] = []

    async def _panel(self, user_id, message, *args, **kwargs):  # noqa: ARG001
        panel_calls.append(message)
        yield {"event": "token", "data": {"content": "多模型综合"}}

    monkeypatch.setattr(AgentExecutor, "_run_multi_model_stream", _panel)

    streamed = []
    async for event in executor.run_stream(
        user_id=user.id,
        message="提醒我明天吃药，我想死",
        user_auth_token="test-token",
        extra_context=json.dumps({"multi_model": True}),
    ):
        if event.get("event") == "token":
            streamed.append((event.get("data") or {}).get("content", ""))
    persisted = (
        db.query(AgentMessage)
        .filter(AgentMessage.role == "assistant")
        .order_by(AgentMessage.id.desc())
        .first()
    )

    assert panel_calls == []
    assert captured
    for text in ("".join(streamed), persisted.content):
        assert has_crisis_support(text)
        assert "提醒我明天吃药，我想死" not in text


def test_siri_timeout_fallback_still_carries_crisis_support(
    client, auth_user_and_headers, monkeypatch
):
    """危机回合走质量模型更慢,Siri 25s 超时兜底文本也必须带热线。"""
    from app.services.agent_runtime_facade import CloudAgentRuntimeFacade
    from app.services.crisis_lexicon import has_crisis_support

    async def _timeout(self, **kwargs):  # noqa: ARG001
        raise asyncio.TimeoutError
        yield  # pragma: no cover - makes this an async generator

    monkeypatch.setattr(CloudAgentRuntimeFacade, "run_stream", _timeout)
    _user, headers = auth_user_and_headers

    crisis = client.post(
        "/api/v1/siri/say",
        headers={**headers, "Idempotency-Key": "siri-crisis-1"},
        json={"message": "我想死"},
    )
    ordinary = client.post(
        "/api/v1/siri/say",
        headers={**headers, "Idempotency-Key": "siri-ordinary-1"},
        json={"message": "记录饮水500ml"},
    )

    assert crisis.status_code == 200
    assert has_crisis_support(crisis.json()["text"])
    assert ordinary.status_code == 200
    assert not has_crisis_support(ordinary.json()["text"])


@pytest.mark.asyncio
async def test_realtime_search_tool_never_sends_crisis_text_out(db, monkeypatch):
    from app.services.agent_executor import AgentExecutor

    searched: list[str] = []

    async def fake_fetch(query, **kwargs):  # noqa: ARG001
        searched.append(query)
        return "【实时检索证据】..."

    monkeypatch.setattr("app.services.iqs_search.fetch_realtime_evidence", fake_fetch)
    executor = AgentExecutor(db)

    blocked = await executor._exec_realtime_search({"query": "我不想活了怎么办"})
    allowed = await executor._exec_realtime_search({"query": "2026 高血压指南更新"})

    assert searched == ["2026 高血压指南更新"]
    assert "Error" not in allowed
    assert blocked.startswith("Error:")


def test_idiom_record_turn_keeps_fast_eligibility():
    from app.services.agent_executor import _is_fast_eligible_turn

    assert _is_fast_eligible_turn(
        "忙死了，记录喝水250ml", has_images=False, has_file=False
    ) is True


def test_typed_water_preplan_yields_to_safety_language():
    """预规划饮水写入会跳过整份 system prompt(含 TRIAGE 热线 / 急症红线)。"""
    from app.services.agent_executor import _build_preplanned_simple_water_tool_call
    from app.services.agent_kernel.types import GoalSpec

    goal = GoalSpec(
        kind="simple_health_record",
        domain="water",
        operation="create",
        target_date="2026-09-30",
        target_record_type="water",
        target_values=(("amount_ml", "250"),),
        requires_verification=True,
    )

    assert _build_preplanned_simple_water_tool_call(goal, write_receipts=[]) is not None
    assert _build_preplanned_simple_water_tool_call(
        goal, write_receipts=[], safety_language=True
    ) is None


def _stub_llm_reply(executor, monkeypatch, reply_text="OK") -> list[list[dict]]:
    captured: list[list[dict]] = []

    async def _capture(messages, tools):  # noqa: ANN001 — mirrors _call_llm_stream
        captured.append(messages)
        yield {"type": "content", "text": reply_text}
        yield {"type": "finish", "finish_reason": "stop"}

    monkeypatch.setattr(executor, "_call_llm_stream", _capture)
    monkeypatch.setattr("app.services.agent_executor.settings.agent_base_url", None)
    monkeypatch.setattr("app.services.agent_executor.settings.agent_api_key", None)
    monkeypatch.setattr(
        executor, "_build_system_knowledge_prompt_context", lambda user_id, message: ""
    )
    return captured


async def _run_turn(executor, user_id, message) -> tuple[str, str]:
    """Return (streamed text, persisted assistant reply) for one turn."""
    from app.models.agent_conversation import AgentMessage

    streamed = []
    async for event in executor.run_stream(
        user_id=user_id, message=message, user_auth_token="test-token"
    ):
        if event.get("event") == "token":
            streamed.append((event.get("data") or {}).get("content", ""))
    persisted = (
        executor.db.query(AgentMessage)
        .filter(AgentMessage.role == "assistant")
        .order_by(AgentMessage.id.desc())
        .first()
    )
    return "".join(streamed), persisted.content if persisted else ""


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message",
    (
        "记录喝水250ml，不想活了",
        "记录喝水250ml，我想死 救救我",
        "记录喝水250ml，胸口很痛还出冷汗",
        "不想活了",
    ),
)
async def test_safety_turn_system_prompt_keeps_red_lines(
    db, auth_user_and_headers, monkeypatch, message
):
    from app.services.agent_executor import AgentExecutor

    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    captured = _stub_llm_reply(executor, monkeypatch)

    await _run_turn(executor, user.id, message)

    assert captured
    system_prompt = captured[0][0]
    assert system_prompt["role"] == "system"
    assert "症状级转诊红线" in system_prompt["content"]
    assert "提供专业热线" in system_prompt["content"]


@pytest.mark.asyncio
@pytest.mark.parametrize("model_reply", (CRISIS_MODEL_REPLY, "OK"))
@pytest.mark.parametrize(
    "message",
    (
        "记录喝水250ml，不想活了",
        "午餐吃了米饭，不想活了",
        "记录一下心情：很低落，不想活了",
        "记录体重60kg，活不下去了",
    ),
)
async def test_crisis_record_turn_final_reply_keeps_hotline_without_echo(
    db, auth_user_and_headers, monkeypatch, message, model_reply
):
    """模型照红线给热线而不写入时,记录兜底曾把整段回复改写成回显原话的「还没记下来」。"""
    from app.services.agent_executor import (
        _CRISIS_RECORD_NOT_SAVED_MESSAGE,
        AgentExecutor,
    )
    from app.services.crisis_lexicon import has_crisis_support

    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    captured = _stub_llm_reply(executor, monkeypatch, model_reply)

    streamed, persisted = await _run_turn(executor, user.id, message)

    assert captured, "stub model must actually run (no vacuous pass on an error path)"
    for text in (streamed, persisted):
        assert has_crisis_support(text)
        assert "12356" in text
        # 记录兜底仍 fail-closed(不谎报已记),但不再回显原话、不邀请「重试」。
        assert _CRISIS_RECORD_NOT_SAVED_MESSAGE in text
        assert "还没记下来" not in text
        assert "模型服务暂时不可用" not in text
        assert message not in text


@pytest.mark.asyncio
async def test_crisis_turn_with_rejected_meal_write_still_ends_with_support(
    db, auth_user_and_headers, monkeypatch
):
    """模型调用了写入但被拒(如饮食营养不全)时,改写后的终态回复同样必须带热线。"""
    from app.services.agent_executor import AgentExecutor
    from app.services.crisis_lexicon import has_crisis_support

    message = "午餐吃了米饭，不想活了"
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    rounds: list[int] = []

    async def _stream(messages, tools):  # noqa: ANN001 — mirrors _call_llm_stream
        rounds.append(len(rounds))
        if len(rounds) == 1:
            yield {
                "type": "tool_calls",
                "tool_calls": [{
                    "id": "call-meal",
                    "type": "function",
                    "function": {
                        "name": "health_record",
                        "arguments": json.dumps(
                            {
                                "record_type": "diet",
                                "data": {"meal_type": "lunch", "food_items": "米饭"},
                            },
                            ensure_ascii=False,
                        ),
                    },
                }],
            }
            yield {"type": "finish", "finish_reason": "tool_calls"}
            return
        yield {"type": "content", "text": "OK"}
        yield {"type": "finish", "finish_reason": "stop"}

    monkeypatch.setattr(executor, "_call_llm_stream", _stream)
    monkeypatch.setattr("app.services.agent_executor.settings.agent_base_url", None)
    monkeypatch.setattr("app.services.agent_executor.settings.agent_api_key", None)
    monkeypatch.setattr(
        executor, "_build_system_knowledge_prompt_context", lambda user_id, message: ""
    )

    streamed, persisted = await _run_turn(executor, user.id, message)

    assert rounds, "stub model must actually run"
    for text in (streamed, persisted):
        assert has_crisis_support(text)
        assert "模型服务暂时不可用" not in text
        assert message not in text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message,model_reply,expect_block",
    (
        ("不想活了", "我在，愿意听你说说发生了什么。", True),
        ("不想活了", CRISIS_MODEL_REPLY, False),
        ("记录喝水250ml", "OK", False),
    ),
)
async def test_crisis_support_is_server_owned_but_never_duplicated(
    db, auth_user_and_headers, monkeypatch, message, model_reply, expect_block
):
    from app.services.agent_executor import AgentExecutor
    from app.services.crisis_lexicon import CRISIS_SUPPORT_LEAD

    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    captured = _stub_llm_reply(executor, monkeypatch, model_reply)

    streamed, persisted = await _run_turn(executor, user.id, message)

    assert captured, "stub model must actually run (no vacuous pass on an error path)"
    for text in (streamed, persisted):
        assert text.count(CRISIS_SUPPORT_LEAD) == (1 if expect_block else 0)
        assert "模型服务暂时不可用" not in text
        if message == "不想活了":
            assert model_reply in text


@pytest.mark.asyncio
async def test_crisis_record_turn_never_routes_to_fast_model(
    db, auth_user_and_headers, monkeypatch
):
    """默认 staged=off 的生产配置下,带写入意图的危机表达也不能落到快模型 / lite prompt。"""
    from app.services.agent_executor import AgentExecutor
    from app.services.llm import model_registry as reg

    fast_id = "deepseek-v4-flash"
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    created: list[str] = []
    prompt_lite_flags: list[bool] = []

    class _Provider:
        def __init__(self, model_id):
            self.model = model_id

        async def chat_stream(self, **kwargs):  # noqa: ARG002
            yield {"type": "content", "text": "OK"}
            yield {"type": "finish", "finish_reason": "stop"}

        async def chat(self, **kwargs):  # noqa: ARG002
            return {"content": "OK", "finish_reason": "stop"}

    def _for_model(model_id):
        created.append(model_id)
        return _Provider(model_id)

    def _for_user(uid, db, **kwargs):  # noqa: ARG001
        created.append("default")
        return _Provider("default")

    def _system_prompt(*args, **kwargs):  # noqa: ARG001
        prompt_lite_flags.append(bool(kwargs.get("lite")))
        return "SYS"

    monkeypatch.setattr(reg, "pick_fast_tool_model_id", lambda **_k: fast_id)
    monkeypatch.setattr(
        "app.services.agent_executor.settings.staged_response_mode", "off"
    )
    monkeypatch.setattr("app.services.agent_executor.settings.llm_provider", "tokenplan")
    monkeypatch.setattr("app.services.agent_executor.settings.agent_base_url", None)
    monkeypatch.setattr("app.services.agent_executor.settings.agent_api_key", None)
    monkeypatch.setattr(
        "app.services.agent_executor.get_health_tools",
        lambda subset=None: [{
            "type": "function",
            "function": {
                "name": "noop",
                "description": "x",
                "parameters": {"type": "object", "properties": {}},
            },
        }],
    )
    monkeypatch.setattr(
        "app.services.llm.factory.create_provider_for_model_id", _for_model
    )
    monkeypatch.setattr("app.services.llm.factory.create_provider_for_user", _for_user)
    monkeypatch.setattr(executor, "_build_system_prompt", _system_prompt)

    async for _ in executor.run_stream(
        user_id=user.id,
        message="记录一下心情：很低落，不想活了",
        user_auth_token="test-token",
    ):
        pass

    assert created
    assert fast_id not in created
    assert executor._fast_route_simple_turn is False
    assert prompt_lite_flags and not any(prompt_lite_flags)
    # staged=off 时 done 事件不带分级元数据;高风险地板仍在所有模式生效。
    assert executor._staged_answer_task_tier == "high_stakes"
