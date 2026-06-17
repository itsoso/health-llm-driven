"""王牌⑤ 腕上语音记症状 → SafetyGuardian 确定性裁决(全场安全 stakes 最高)。

覆盖 docs/design-watch-voice-symptom.md §测试计划 1-11,钉三条最高优先不变量:
- **不漏报**(under-alarm 是医疗危险):评估抛错绝不吞成「已记录无告警」——
  置 evaluation_failed,症状**仍 committed 进库**,返回明确就医引导。
- **请求内禁 build_twin**:用 AST 断言 record_symptom 链路无 build_twin 真实调用;
  并构造**只 flush 未 commit** 的 HealthProblem red line → 报对应症状仍命中,
  证明评估走 request db(同一 session)而非自开 SessionLocal。
- **R4 不诊断 / critical 真命中才升级**:critical 措辞不含确诊/治愈,给就医动作;
  普通不适不误升 critical;user_id 隔离。

真实响应 shape(QA 实测,据此断言):
- severity 是嵌套对象 {value:int, label:str, label_zh:str},取 alert["severity"]["label"]。
- 三态:命中 → {symptom_id, alerts:[...], message};无命中 → {alerts:[], message:"...未触发..."};
  评估失败 → {alerts:[], evaluation_failed:True, message含就医}(成功分支无 evaluation_failed 字段)。
"""
import ast
import re
import uuid
from pathlib import Path

import pytest

import app.api.watch as watch_api
from app.models.health_problem import HealthProblem
from app.models.symptom_entry import SymptomEntry
from app.models.user import User
from app.services.auth import auth_service

_ENDPOINT = "/api/v1/watch/symptoms"


# ── fixtures ──────────────────────────────────────────────────────────
def _mk_user(db) -> User:
    u = User(
        username=f"ws_{uuid.uuid4().hex[:6]}",
        email=f"ws_{uuid.uuid4().hex[:6]}@x.com",
        hashed_password="x",
        name="ws",
        is_active=True,
        is_approved=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {auth_service.create_access_token({'sub': str(user.id)})}"}


def _post(client, user, text):
    return client.post(_ENDPOINT, json={"text": text}, headers=_headers(user))


def _symptom_rows(db, user_id: int):
    return db.query(SymptomEntry).filter(SymptomEntry.user_id == user_id).all()


def _add_red_line(db, user_id, *, risk_level, condition, action, commit=True):
    """登记一条 active HealthProblem 带个性化红线。commit=False → 只 flush(测 request db)。"""
    p = HealthProblem(
        user_id=user_id,
        name="胃溃疡(Hp 阴性)",
        risk_level=risk_level,
        status="active",
        red_lines=[{"condition": condition, "action": action}],
    )
    db.add(p)
    if commit:
        db.commit()
        db.refresh(p)
    else:
        db.flush()  # 仅 flush:行未 commit,但同一 request session 可见
    return p


# ── 1-4: 急症 critical(symptoms.py 真命中)──────────────────────────────
@pytest.mark.parametrize(
    "label,text",
    [
        ("cardiac", "胸口闷,左臂放射痛还冒冷汗"),
        ("abdomen", "肚子剧烈腹痛难忍,还有点黑便"),
        ("stroke", "突然嘴歪、说话不清,半身没力气"),
        ("dyspnea", "突然呼吸困难,喘不上气,无法平卧"),
    ],
)
def test_acute_emergency_returns_critical(client, db, label, text):
    """1-4: 四类急症 → critical;action 含就医/120;title 非诊断;落 1 条 SymptomEntry。"""
    user = _mk_user(db)
    r = _post(client, user, text)
    assert r.status_code == 200, r.text
    body = r.json()

    # 嵌套 severity 对象,取 label
    crit = [a for a in body["alerts"] if a["severity"]["label"] == "critical"]
    assert crit, f"{label} 应至少一条 critical,实得 {body['alerts']}"
    top = crit[0]
    assert top["severity"]["value"] == 4
    # action 引导就医
    assert re.search(r"就医|120|急救|急诊", top["action"] or "")
    # title 非诊断措辞(R4)
    assert not re.search(r"确诊|你患有|治愈|保证", top["title"])

    # 评估成功分支:无 evaluation_failed 字段
    assert "evaluation_failed" not in body

    # 恰好 1 条 SymptomEntry 落库
    rows = _symptom_rows(db, user.id)
    assert len(rows) == 1
    assert rows[0].description == text
    assert rows[0].source == "apple_watch"
    assert rows[0].body_part == "general"


# ── 5: 普通不适不误升 critical ─────────────────────────────────────────
def test_mild_discomfort_not_escalated(client, db):
    """5: 「有点累」→ alerts 空或非 critical,不误升 critical;仍落 1 条症状。"""
    user = _mk_user(db)
    r = _post(client, user, "今天有点累,想早点睡")
    assert r.status_code == 200, r.text
    body = r.json()
    assert all(a["severity"]["label"] != "critical" for a in body["alerts"]), body["alerts"]
    assert "evaluation_failed" not in body
    assert len(_symptom_rows(db, user.id)) == 1


# ── 6: 个性化红线命中(P0)→ critical + 红线 action ──────────────────────
def test_personalized_red_line_hits_critical(client, db):
    """6: active HealthProblem P0 red_lines[黑便] + 报「黑便」→ problem_red_lines 命中,
    severity critical,action 含红线 action。"""
    user = _mk_user(db)
    _add_red_line(
        db,
        user.id,
        risk_level="P0",
        condition="黑便",
        action="立即就医做胃镜",
    )
    r = _post(client, user, "今早发现黑便")
    assert r.status_code == 200, r.text
    body = r.json()

    rl_alerts = [
        a for a in body["alerts"]
        if a["severity"]["label"] == "critical" and "立即就医做胃镜" in (a["action"] or "")
    ]
    assert rl_alerts, f"应命中 P0 红线 critical,实得 {body['alerts']}"
    assert len(_symptom_rows(db, user.id)) == 1


# ── 7: 不漏报 —— 评估整体抛错绝不冒充安全 ──────────────────────────────
def test_total_evaluation_failure_does_not_under_alarm(client, db, monkeypatch):
    """7: monkeypatch evaluate_rules_with_status **整体**抛错 →
    - 响应 evaluation_failed True(非静默空 alerts 冒充安全);
    - **alerts 非空**:含 fail-safe advisory(severity≥HIGH、action 引导就医),
      只渲染 alerts[0] 的客户端也看得到安全提示(加层不减层,客户端无关);
    - 症状仍 committed 进库(DB rows==1,非回滚假 id);
    - message 含就医引导;
    - 断言:绝不返回「看似安全的空 alerts」当作安全。
    """
    user = _mk_user(db)

    def _boom(_twin):
        raise RuntimeError("规则引擎炸了")

    # watch.py 现用 `from ...engine import evaluate_rules_with_status`,patch 模块级别名
    monkeypatch.setattr(watch_api, "evaluate_rules_with_status", _boom)

    r = _post(client, user, "胸口闷,左臂放射痛还冒冷汗")
    assert r.status_code == 200, r.text
    body = r.json()

    # 关键①:evaluation_failed 必须显式 True —— 不能静默冒充安全
    assert body.get("evaluation_failed") is True, body
    # 关键②:alerts 非空,含 fail-safe advisory —— 不依赖客户端读 flag
    assert body["alerts"], "评估失败时 alerts 不能为空(必须有 fail-safe advisory)"
    adv = body["alerts"][0]  # severity 降序,advisory 至少 HIGH,排在最前
    assert adv["severity"]["value"] >= 3, adv  # ≥ HIGH
    assert re.search(r"就医|120", adv["action"] or ""), adv
    # R4:advisory 不诊断
    assert not re.search(r"确诊|你患有|治愈|保证", f"{adv['title']} {adv['action']}"), adv

    assert re.search(r"就医", body["message"])
    assert "symptom_id" in body and body["symptom_id"]

    # 症状仍真实 committed(非回滚假 id):查库 == 1 行,且 id 与返回一致
    rows = _symptom_rows(db, user.id)
    assert len(rows) == 1
    assert rows[0].id == body["symptom_id"]
    assert rows[0].description == "胸口闷,左臂放射痛还冒冷汗"


# ── 7b: 不漏报 —— **单条**急症规则崩溃绝不退化成绿灯(DANGEROUS 根因)──────
def test_single_rule_failure_does_not_under_alarm(client, db, monkeypatch):
    """7b(核心对抗用例):engine 的 per-rule try/except 把单条急症规则的崩溃吞成
    「跳过」,evaluate_rules 仍返回(可能为空的)alerts、不抛异常。若只在「整体抛异常」
    时置 evaluation_failed,则:cardiac 规则崩 → alerts 退化成空 → 响应「未触发安全规则」
    = 真心脏事件被静默退化成绿灯(under-alarm = 医疗危险)。

    修后断言:
    - evaluation_failed 必须 True(看到了 failed > 0);
    - alerts **非空**且含 fail-safe advisory(severity≥HIGH、action 含就医/120);
    - **绝不是**「空 alerts + 未触发安全规则」的绿灯。
    """
    user = _mk_user(db)

    from app.agents.safety_guardian.engine import registry

    # 只让 acute_cardiac_event 这一条规则抛错(替换 registry 里它的函数),
    # 其余 58 条照常跑 —— 精确复现「单条急症规则部分失败」。
    def _boom(_twin):
        raise RuntimeError("cardiac 规则单条炸了")

    original = list(registry._rules)
    patched = [(n, _boom if n == "acute_cardiac_event" else f) for n, f in original]
    assert any(n == "acute_cardiac_event" for n, _ in original), "未找到 cardiac 规则"
    monkeypatch.setattr(registry, "_rules", patched)

    # 喂真心脏主诉:cardiac 规则本应命中 critical,但它崩了
    r = _post(client, user, "胸口闷,左臂放射痛还冒冷汗")
    assert r.status_code == 200, r.text
    body = r.json()

    # 关键①:单条失败也必须置 evaluation_failed —— 这正是 DANGEROUS 修复点
    assert body.get("evaluation_failed") is True, (
        "单条急症规则崩溃必须置 evaluation_failed,绝不能退化成绿灯", body,
    )
    # 关键②:不是「空 alerts + 未触发安全规则」的绿灯
    assert body["alerts"], "单条规则失败时 alerts 不能为空(必须有 fail-safe advisory)"
    assert "未触发安全规则" not in body.get("message", ""), body
    # 关键③:含 fail-safe advisory,severity≥HIGH,action 引导就医,且不诊断(R4)
    advs = [a for a in body["alerts"]
            if a["severity"]["value"] >= 3 and re.search(r"就医|120", a["action"] or "")]
    assert advs, f"应含 severity≥HIGH 的就医 advisory,实得 {body['alerts']}"
    for a in advs:
        assert not re.search(r"确诊|你患有|治愈|保证", f"{a['title']} {a['action']}"), a

    # 症状仍真实落库
    rows = _symptom_rows(db, user.id)
    assert len(rows) == 1
    assert rows[0].id == body["symptom_id"]


# ── 7d: 不漏报 —— 个性化红线**填充**失败绝不退化成绿灯(本刀 DANGEROUS 根因)──
def test_red_line_fill_failure_does_not_under_alarm(client, db, monkeypatch):
    """7d(本刀核心对抗用例):红线**填充**(builder._fill_problem_red_lines)崩溃
    绝不退化成绿灯。

    根因链:_fill_problem_red_lines 默认自带内部 try/except 吞异常 → 填充失败静默留空
    problem_red_lines → health_problem_red_line 规则 `if not red_lines: return []` 早返回、
    不抛异常 → 引擎 failed 仍 0 → evaluation_failed=False → 绿灯。对「只有个性化红线能
    命中、symptoms.py 没写死」的主诉(视物重影)= 个性化安全层静默不响 = under-alarm。

    构造:
    - 先登记一条 active HealthProblem,red_lines condition「视物重影」(P0)→ 命中即 critical;
    - monkeypatch health_problem_service.list_problems 抛错(模拟会话异常/DB 抖动/列漂移);
    - 主诉「这两天看东西有重影」—— symptoms.py 任何关键词都不命中(已实测 failed=0、空 alerts),
      唯一能命中它的就是这条个性化红线。

    修后断言:
    - evaluation_failed 必须 True(填充失败被感知,非静默留空);
    - alerts **非空**且含 fail-safe advisory(severity≥HIGH、action 含就医/120),
      **绝不是**「空 alerts + 未触发安全规则」的绿灯;
    - 通用急症层在填充失败时仍能跑(下方 7e 单独证 backstop);
    - 症状仍真实落库。
    """
    user = _mk_user(db)
    _add_red_line(
        db,
        user.id,
        risk_level="P0",
        condition="视物重影",
        action="立即就医排查神经/眼科急症",
    )

    from app.services import health_problem_service

    def _boom(*_a, **_k):
        raise RuntimeError("红线查询炸了(会话异常 / red_lines 列漂移)")

    # 填充点:helper 内 `prob_svc.list_problems(...)` → patch 模块级函数
    monkeypatch.setattr(health_problem_service, "list_problems", _boom)

    # 视物重影:symptoms.py 不命中(已实测),只有上面那条个性化红线能命中 —— 但它填充崩了
    r = _post(client, user, "这两天看东西有重影")
    assert r.status_code == 200, r.text
    body = r.json()

    # 关键①:红线填充失败也必须置 evaluation_failed —— 这正是本刀 DANGEROUS 修复点
    assert body.get("evaluation_failed") is True, (
        "个性化红线填充失败必须置 evaluation_failed,绝不能退化成绿灯", body,
    )
    # 关键②:不是「空 alerts + 未触发安全规则」的绿灯
    assert body["alerts"], "红线填充失败时 alerts 不能为空(必须有 fail-safe advisory)"
    assert "未触发安全规则" not in body.get("message", ""), body
    # 关键③:含 fail-safe advisory,severity≥HIGH,action 引导就医,且不诊断(R4)
    advs = [a for a in body["alerts"]
            if a["severity"]["value"] >= 3 and re.search(r"就医|120", a["action"] or "")]
    assert advs, f"应含 severity≥HIGH 的就医 advisory,实得 {body['alerts']}"
    for a in advs:
        assert not re.search(r"确诊|你患有|治愈|保证", f"{a['title']} {a['action']}"), a
    # message 引导就医,绝不绿灯
    assert re.search(r"就医", body["message"]), body

    # 症状仍真实落库(填充失败不丢已 flush 的症状)
    rows = _symptom_rows(db, user.id)
    assert len(rows) == 1
    assert rows[0].id == body["symptom_id"]
    assert rows[0].description == "这两天看东西有重影"


# ── 7e: 红线填充失败时,通用急症规则仍跑(backstop 不被一起拖死)──────────
def test_red_line_fill_failure_still_runs_generic_acute_rules(client, db, monkeypatch):
    """7e:红线填充失败 → evaluation_failed,但**不 return**:symptoms.py 通用急症仍兜底。

    构造:同 7d 让红线填充崩,但主诉换成 symptoms.py 真命中的急症(心脏事件主诉)。
    断言:
    - evaluation_failed True(填充确实崩了);
    - 通用 cardiac critical **仍在** alerts 里(证明填充失败没把通用层一起 short-circuit);
    - fail-safe advisory 也在(加层不减层)。
    若实现里「填充失败就 return、不跑 evaluate_rules」,这条会红 —— 通用急症被一起漏报。
    """
    user = _mk_user(db)

    from app.services import health_problem_service

    def _boom(*_a, **_k):
        raise RuntimeError("红线查询炸了")

    monkeypatch.setattr(health_problem_service, "list_problems", _boom)

    # symptoms.py acute_cardiac_event 真命中的主诉
    r = _post(client, user, "胸口闷,左臂放射痛还冒冷汗")
    assert r.status_code == 200, r.text
    body = r.json()

    assert body.get("evaluation_failed") is True, body
    # 通用 cardiac critical 仍跑出来(backstop 没被填充失败拖死)
    cardiac = [a for a in body["alerts"]
               if a["severity"]["label"] == "critical" and "心脏" in (a["title"] or "")]
    assert cardiac, f"填充失败时通用急症(cardiac)仍应命中,实得 {body['alerts']}"
    # fail-safe advisory 也注入(填充失败的诚实标注)
    assert any(a["title"] == "安全评估未完成" for a in body["alerts"]), body


# ── 7c: 正常路径无规则失败 → failed==0、无 evaluation_failed、行为不变 ─────
def test_normal_path_no_rule_failure(client, db):
    """7c: 不打补丁的正常路径 —— 真心脏主诉照常命中 critical,
    响应无 evaluation_failed 字段,无 fail-safe advisory(rule_id meta),
    证明新增的 failed 计数在无失败时为 0、行为零变化。"""
    user = _mk_user(db)
    r = _post(client, user, "胸口闷,左臂放射痛还冒冷汗")
    assert r.status_code == 200, r.text
    body = r.json()

    # 正常路径:无 evaluation_failed 字段
    assert "evaluation_failed" not in body, body
    # 照常命中真 critical(cardiac 规则正常跑)
    assert any(a["severity"]["label"] == "critical" for a in body["alerts"]), body
    # 不注入 fail-safe advisory(标题「安全评估未完成」不应出现)
    assert all(a["title"] != "安全评估未完成" for a in body["alerts"]), body


# ── 8: 空 / 纯空白 / 超长 → 400,不落空症状 ────────────────────────────
@pytest.mark.parametrize("bad", ["", "   ", "\n\t  ", "症" * 501])
def test_invalid_text_400_no_empty_entry(client, db, bad):
    """8: 空 / 纯空白 / >500 → 400;DB 0 行(不落空 SymptomEntry)。"""
    user = _mk_user(db)
    r = _post(client, user, bad)
    assert r.status_code == 400, r.text
    assert len(_symptom_rows(db, user.id)) == 0


def test_max_len_boundary_accepted(client, db):
    """8 边界:恰好 500 字 → 接受(>500 才 400),落 1 条。"""
    user = _mk_user(db)
    r = _post(client, user, "症" * 500)
    assert r.status_code == 200, r.text
    assert len(_symptom_rows(db, user.id)) == 1


# ── 9: 无 token → 401 ─────────────────────────────────────────────────
def test_no_token_401(client, db):
    """9: 无 Authorization → 401。"""
    r = client.post(_ENDPOINT, json={"text": "胸口闷"})
    assert r.status_code == 401, r.text


# ── 10a: 禁 build_twin(AST 静态断言)──────────────────────────────────
def test_record_symptom_does_not_call_build_twin_ast():
    """10a: AST 解析 watch.py,断言 record_symptom 函数体内无 build_twin 真实调用。
    允许 docstring/注释里出现 'build_twin' 字样(那不是调用)。"""
    src = Path(watch_api.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)

    fn = next(
        (n for n in ast.walk(tree)
         if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "record_symptom"),
        None,
    )
    assert fn is not None, "未找到 record_symptom"

    called = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name):
                called.add(f.id)
            elif isinstance(f, ast.Attribute):
                called.add(f.attr)
    assert "build_twin" not in called, f"record_symptom 不得调用 build_twin,实得调用 {called}"


# ── 10b: 禁 build_twin(行为证明)—— 只 flush 未 commit 的红线仍命中 ─────
def test_uncommitted_red_line_still_hits_via_request_db(client, db):
    """10b: 构造只 flush 未 commit 的 HealthProblem red line → 报对应症状仍命中。
    若走 build_twin 自开的新 SessionLocal,看不到未 commit 的红线 → 不会命中;
    命中即证明评估走的是 request db(client 覆盖 get_db,与本 db 同一 session)。"""
    user = _mk_user(db)
    _add_red_line(
        db,
        user.id,
        risk_level="P0",
        condition="呕血",
        action="立即拨打120去急诊",
        commit=False,  # 关键:只 flush,不 commit
    )
    # 确认确实未 commit(仍在事务内)
    assert db.query(HealthProblem).filter(HealthProblem.user_id == user.id).first() is not None

    r = _post(client, user, "刚才呕血了")
    assert r.status_code == 200, r.text
    body = r.json()
    hit = [
        a for a in body["alerts"]
        if "立即拨打120去急诊" in (a["action"] or "")
    ]
    assert hit, f"未 commit 的红线应经 request db 命中,实得 {body['alerts']}"


# ── 11: 措辞安全 —— 所有 critical alert 不诊断、引导就医 ──────────────────
def test_critical_wording_non_diagnostic_and_actionable(client, db):
    """11: 所有 critical alert 的 title+action 不含 确诊/你患有/治愈/保证;
    含 可能/建议/就医/120 之一。"""
    user = _mk_user(db)
    _add_red_line(db, user.id, risk_level="P0", condition="黑便", action="立即就医做胃镜")

    # 禁诊断措辞:确诊/你患有/治愈/保证。其中「确诊」是「下确诊结论」之义;
    # 用负向后顾排除良性短语「明确诊断」(= 在明确诊断前不要进食,合法非诊断医嘱,
    # '明[确诊]断' 仅是字面子串碰撞,不是诊断断言)。
    forbidden = re.compile(r"(?<!明)确诊|你患有|治愈|保证")
    required = re.compile(r"可能|建议|就医|120")

    for text in ["胸口闷,左臂放射痛还冒冷汗", "突然嘴歪、说话不清,半身没力气", "今早发现黑便"]:
        body = _post(client, user, text).json()
        crit = [a for a in body["alerts"] if a["severity"]["label"] == "critical"]
        assert crit, f"{text} 应有 critical"
        for a in crit:
            combined = f"{a['title']} {a['action']}"
            assert not forbidden.search(combined), f"critical 措辞含禁词: {combined}"
            assert required.search(combined), f"critical 措辞缺就医引导: {combined}"


# ── 12: user_id 隔离 —— A 不命中 B 的红线,症状落 A 不落 B ────────────────
def test_user_isolation_red_line_and_entry(client, db):
    """12: B 登记红线[黑便];A 用 A 的 token 报「黑便」→ 不命中 B 红线;
    症状落 A 不落 B。"""
    user_a = _mk_user(db)
    user_b = _mk_user(db)
    _add_red_line(db, user_b.id, risk_level="P0", condition="黑便", action="B专属立即就医做胃镜")

    r = _post(client, user_a, "今早发现黑便")
    assert r.status_code == 200, r.text
    body = r.json()

    # A 不应命中 B 的专属红线 action
    assert all("B专属" not in (a["action"] or "") for a in body["alerts"]), body["alerts"]

    # 症状落 A 不落 B
    assert len(_symptom_rows(db, user_a.id)) == 1
    assert len(_symptom_rows(db, user_b.id)) == 0


# ── 补充:无命中三态确认(中性 message 含「未触发」)─────────────────────
def test_no_match_neutral_message(client, db):
    """无命中态:alerts:[] + message 含「未触发安全规则」,无 evaluation_failed。"""
    user = _mk_user(db)
    body = _post(client, user, "今天有点累").json()
    assert body["alerts"] == [] or all(
        a["severity"]["label"] != "critical" for a in body["alerts"]
    )
    if body["alerts"] == []:
        assert "未触发安全规则" in body["message"]
    assert "evaluation_failed" not in body
