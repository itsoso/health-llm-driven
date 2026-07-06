"""Agent conversation history API tests."""

from app.models.agent_conversation import AgentConversation, AgentMessage
from app.models.user import User
from app.api.agent import _merge_card_descriptors


def _create_user(db, suffix: str) -> User:
    user = User(
        username=f"agent_history_{suffix}",
        email=f"agent_history_{suffix}@example.com",
        hashed_password="x",
        name=f"Agent History {suffix}",
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _create_conversation(db, user_id: int, title: str = "测试对话") -> AgentConversation:
    conv = AgentConversation(user_id=user_id, title=title, session_key=f"test-{user_id}")
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


def _add_message(db, conversation_id: int, role: str, content: str) -> AgentMessage:
    msg = AgentMessage(conversation_id=conversation_id, role=role, content=content)
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def test_agent_conversations_list_returns_user_history_with_last_user_message(
    client, db, auth_user_and_headers
):
    user, headers = auth_user_and_headers
    conv = _create_conversation(db, user.id, "代谢健康问题")
    _add_message(db, conv.id, "assistant", "你好")
    _add_message(db, conv.id, "user", "最近血糖怎么样？")

    other = _create_user(db, "other")
    other_conv = _create_conversation(db, other.id, "其他人的对话")
    _add_message(db, other_conv.id, "user", "不能泄露")

    res = client.get("/api/v1/agent/conversations", headers=headers)

    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["offset"] == 0
    items = data["items"]
    assert len(items) == 1
    assert items[0]["id"] == conv.id
    assert items[0]["title"] == "代谢健康问题"
    assert items[0]["last_message"] == "最近血糖怎么样？"


def test_agent_send_collects_first_party_executor_stream(client, auth_user_and_headers, monkeypatch):
    _, headers = auth_user_and_headers

    async def fake_run_stream(self, **kwargs):
        assert kwargs["message"] == "小程序非流式入口"
        assert kwargs["conversation_id"] is None
        yield {"event": "token", "data": {"content": "已接入"}}
        yield {"event": "token", "data": {"content": "第一方 Agent"}}
        yield {
            "event": "done",
            "data": {"conversation_id": 123, "message_id": 456, "elapsed_ms": 17},
        }

    monkeypatch.setattr(
        "app.services.agent_executor.AgentExecutor.run_stream",
        fake_run_stream,
    )

    res = client.post(
        "/api/v1/agent/send",
        headers=headers,
        json={"message": "小程序非流式入口"},
    )

    assert res.status_code == 200
    body = res.json()
    # 老字段零变化(additive meta 上线后契约不回退)。
    assert body["reply"] == "已接入第一方 Agent"
    assert body["conversation_id"] == 123
    assert body["message_id"] == 456
    assert body["mode"] == "agent"
    assert body["elapsed_ms"] == 17
    # 纯附加 meta 恒存在(即使没模型/成本也给结构,值为 None)。
    assert "meta" in body and isinstance(body["meta"], dict)
    assert set(body["meta"].keys()) == {
        "model", "rounds", "usage", "cost_estimate", "latency", "tools_used"
    }


def test_agent_conversations_pagination_offset_and_total(client, db, auth_user_and_headers):
    """翻页:total 反映全部,limit/offset 切出当前页,不与其它页重叠。"""
    user, headers = auth_user_and_headers
    for i in range(5):
        conv = AgentConversation(user_id=user.id, title=f"对话{i}", session_key=f"pg-{user.id}-{i}")
        db.add(conv)
    db.commit()

    page1 = client.get("/api/v1/agent/conversations?limit=2&offset=0", headers=headers).json()
    assert page1["total"] == 5
    assert page1["limit"] == 2 and page1["offset"] == 0
    assert len(page1["items"]) == 2

    page2 = client.get("/api/v1/agent/conversations?limit=2&offset=2", headers=headers).json()
    assert page2["total"] == 5
    assert len(page2["items"]) == 2

    page3 = client.get("/api/v1/agent/conversations?limit=2&offset=4", headers=headers).json()
    assert len(page3["items"]) == 1  # 余 1 条

    ids = [c["id"] for c in page1["items"] + page2["items"] + page3["items"]]
    assert len(set(ids)) == 5  # 三页无重叠、无遗漏


def test_agent_conversation_detail_returns_messages(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    conv = _create_conversation(db, user.id, "训练计划")
    first = _add_message(db, conv.id, "user", "明天怎么跑？")
    second = _add_message(db, conv.id, "assistant", "先做 Zone 2。")

    res = client.get(f"/api/v1/agent/conversations/{conv.id}", headers=headers)

    assert res.status_code == 200
    data = res.json()
    assert data["id"] == conv.id
    assert data["title"] == "训练计划"
    assert [m["id"] for m in data["messages"]] == [first.id, second.id]
    assert data["messages"][0]["role"] == "user"
    assert data["messages"][1]["content"] == "先做 Zone 2。"


def test_agent_conversation_detail_returns_persisted_card_meta(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    conv = _create_conversation(db, user.id, "知识卡片")
    msg = _add_message(db, conv.id, "assistant", "已结合知识库回答。")
    msg.meta = {
        "cards": [
            {
                "type": "system_knowledge_evidence",
                "data": {"entity": {"title": "MTHFR"}, "claims": []},
            }
        ]
    }
    db.commit()

    res = client.get(f"/api/v1/agent/conversations/{conv.id}", headers=headers)

    assert res.status_code == 200
    data = res.json()
    assert data["messages"][0]["meta"]["cards"][0]["type"] == "system_knowledge_evidence"


def test_merge_card_descriptors_preserves_existing_and_deduplicates():
    existing = [{"type": "system_knowledge_evidence", "data": {"entity": {"title": "MTHFR"}}}]
    inline = [{"type": "menu_share", "data": {"title": "分享", "items": []}}]

    merged = _merge_card_descriptors(inline, existing, existing)

    assert [card["type"] for card in merged] == ["menu_share", "system_knowledge_evidence"]


def test_agent_conversation_detail_enforces_user_isolation(client, db, auth_user_and_headers):
    _, headers = auth_user_and_headers
    other = _create_user(db, "isolated")
    other_conv = _create_conversation(db, other.id, "其他人的对话")

    res = client.get(f"/api/v1/agent/conversations/{other_conv.id}", headers=headers)

    assert res.status_code == 404


def test_agent_conversation_delete_removes_owned_conversation(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    conv = _create_conversation(db, user.id, "要删除的对话")
    _add_message(db, conv.id, "user", "删除我")

    res = client.delete(f"/api/v1/agent/conversations/{conv.id}", headers=headers)

    assert res.status_code == 200
    assert res.json()["ok"] is True
    assert db.query(AgentConversation).filter(AgentConversation.id == conv.id).first() is None


def test_agent_conversation_title_update_renames_owned_conversation(
    client, db, auth_user_and_headers
):
    user, headers = auth_user_and_headers
    conv = _create_conversation(db, user.id, "分析我最近的代谢健康")

    res = client.patch(
        f"/api/v1/agent/conversations/{conv.id}",
        headers=headers,
        json={"title": "5月代谢复盘"},
    )

    assert res.status_code == 200
    assert res.json()["title"] == "5月代谢复盘"
    db.refresh(conv)
    assert conv.title == "5月代谢复盘"


def test_agent_conversation_title_update_enforces_user_isolation(
    client, db, auth_user_and_headers
):
    _, headers = auth_user_and_headers
    other = _create_user(db, "rename_isolated")
    other_conv = _create_conversation(db, other.id, "其他人的对话")

    res = client.patch(
        f"/api/v1/agent/conversations/{other_conv.id}",
        headers=headers,
        json={"title": "不该成功"},
    )

    assert res.status_code == 404
    db.refresh(other_conv)
    assert other_conv.title == "其他人的对话"


def test_agent_message_rate_toggles_owned_message(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    conv = _create_conversation(db, user.id, "评价对话")
    msg = _add_message(db, conv.id, "assistant", "可评价的回复")

    res = client.post(
        f"/api/v1/agent/messages/{msg.id}/rate",
        headers=headers,
        json={"rating": 1},
    )
    assert res.status_code == 200
    assert res.json()["rating"] == 1
    db.refresh(msg)
    assert msg.rating == 1

    res2 = client.post(
        f"/api/v1/agent/messages/{msg.id}/rate",
        headers=headers,
        json={"rating": 1},
    )
    assert res2.status_code == 200
    assert res2.json()["rating"] is None
    db.refresh(msg)
    assert msg.rating is None


def test_agent_message_rate_enforces_user_isolation(client, db, auth_user_and_headers):
    _, headers = auth_user_and_headers
    other = _create_user(db, "rate_isolated")
    other_conv = _create_conversation(db, other.id, "别人的回复")
    other_msg = _add_message(db, other_conv.id, "assistant", "不可评价")

    res = client.post(
        f"/api/v1/agent/messages/{other_msg.id}/rate",
        headers=headers,
        json={"rating": 1},
    )

    assert res.status_code == 404


# ---------------------------------------------------------------------------
# /agent/send 保活流式聚合回归(2026-07-06)
# 实锤:重量级深分析回合 >60s 被 main.py 请求超时中间件杀成 504。
# 修法:超窗切 chunked JSON(前导空白保活 + 末尾完整对象)。
# 测试把时间尺度压缩:中间件 1s + 回合 2.5s,修复前必 504、修复后 200。
# ---------------------------------------------------------------------------


def test_agent_send_slow_turn_streams_keepalive_not_504(
    client, auth_user_and_headers, monkeypatch
):
    import asyncio
    import json as jsonlib

    import main as main_module
    from app.api import agent as agent_api

    _, headers = auth_user_and_headers
    monkeypatch.setattr(main_module, "REQUEST_TIMEOUT", 1)
    monkeypatch.setattr(agent_api, "AGENT_SEND_KEEPALIVE_SECONDS", 0.1)

    async def fake_run_stream(self, **kwargs):
        yield {"event": "token", "data": {"content": "深度"}}
        await asyncio.sleep(2.5)  # > 中间件 1s:修复前 wait_for 在这里杀成 504
        yield {"event": "token", "data": {"content": "分析结论"}}
        yield {
            "event": "done",
            "data": {"conversation_id": 7, "message_id": 8, "elapsed_ms": 2500},
        }

    monkeypatch.setattr(
        "app.services.agent_executor.AgentExecutor.run_stream", fake_run_stream
    )

    res = client.post(
        "/api/v1/agent/send",
        headers=headers,
        json={"message": "慢回合保活回归"},
    )

    assert res.status_code == 200, f"长回合不应再 504/500: {res.status_code} {res.text[:200]}"
    raw = res.text
    # 确实吐过保活前导空白(证明流式路径生效,而非碰巧快窗完成)
    assert raw != raw.lstrip(), "长回合应含保活前导空白"
    assert set(raw[: len(raw) - len(raw.lstrip())]) <= {" ", "\t", "\r", "\n"}
    # 前导空白后仍是合法完整 JSON(RFC 8259 允许前导 ws → 现有客户端零感知)
    body = jsonlib.loads(raw)
    # 老字段零变化;additive meta 也随保活路径一起回(与快窗一致)。
    assert body["reply"] == "深度分析结论"
    assert body["conversation_id"] == 7
    assert body["message_id"] == 8
    assert body["mode"] == "agent"
    assert body["elapsed_ms"] == 2500
    assert isinstance(body.get("meta"), dict)


def test_agent_send_error_after_stream_started_yields_error_envelope(
    client, auth_user_and_headers, monkeypatch
):
    """流开始后(200 已定格)失败 → in-body error 字段,不再是 HTTP 500。"""
    import asyncio
    import json as jsonlib

    from app.api import agent as agent_api

    _, headers = auth_user_and_headers
    monkeypatch.setattr(agent_api, "AGENT_SEND_KEEPALIVE_SECONDS", 0.1)

    async def fake_run_stream(self, **kwargs):
        yield {"event": "token", "data": {"content": "半截"}}
        await asyncio.sleep(0.5)
        yield {"event": "error", "data": {"message": "上游 LLM 断连"}}

    monkeypatch.setattr(
        "app.services.agent_executor.AgentExecutor.run_stream", fake_run_stream
    )

    res = client.post(
        "/api/v1/agent/send",
        headers=headers,
        json={"message": "流后错误 envelope"},
    )

    assert res.status_code == 200
    body = jsonlib.loads(res.text)
    assert isinstance(body.get("error"), str) and body["error"]
    assert body["reply"] == ""
    assert body["mode"] == "agent"


def test_agent_send_fast_error_keeps_http_500(client, auth_user_and_headers, monkeypatch):
    """快窗内失败保持历史语义:HTTP 500 + detail,契约不变。"""

    async def fake_run_stream(self, **kwargs):
        yield {"event": "error", "data": {"message": "配置错误"}}

    monkeypatch.setattr(
        "app.services.agent_executor.AgentExecutor.run_stream", fake_run_stream
    )
    _, headers = auth_user_and_headers

    res = client.post(
        "/api/v1/agent/send",
        headers=headers,
        json={"message": "快窗错误保持500"},
    )

    assert res.status_code == 500
    assert res.json()["detail"]


def test_agent_send_hard_cap_cancels_turn_and_reports_timeout(
    client, auth_user_and_headers, monkeypatch
):
    """硬上限兜底:真卡死的回合被取消(不吊死 worker)+ in-body 超时报错。"""
    import asyncio
    import json as jsonlib

    from app.api import agent as agent_api

    _, headers = auth_user_and_headers
    monkeypatch.setattr(agent_api, "AGENT_SEND_KEEPALIVE_SECONDS", 0.1)
    monkeypatch.setattr(agent_api, "AGENT_SEND_HARD_CAP_SECONDS", 0.5)

    cancelled = {"flag": False}

    async def fake_run_stream(self, **kwargs):
        yield {"event": "token", "data": {"content": "卡"}}
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            cancelled["flag"] = True
            raise

    monkeypatch.setattr(
        "app.services.agent_executor.AgentExecutor.run_stream", fake_run_stream
    )

    res = client.post(
        "/api/v1/agent/send",
        headers=headers,
        json={"message": "硬上限取消回合"},
    )

    assert res.status_code == 200
    body = jsonlib.loads(res.text)
    assert "超时" in (body.get("error") or "")
    assert cancelled["flag"], "硬上限触发后底层回合必须被真实取消"


def test_agent_conversations_search_matches_title_and_content(
    client, db, auth_user_and_headers
):
    """search 同时命中标题与消息正文;user-isolation 不破。"""
    user, headers = auth_user_and_headers
    # A: 命中标题
    conv_title = _create_conversation(db, user.id, "睡眠质量复盘")
    _add_message(db, conv_title.id, "user", "帮我看看最近怎么样")
    # B: 标题不含关键词, 但消息正文含
    conv_body = _create_conversation(db, user.id, "随便聊聊")
    _add_message(db, conv_body.id, "user", "我的睡眠总是很浅")
    # C: 都不含
    conv_miss = _create_conversation(db, user.id, "训练计划")
    _add_message(db, conv_miss.id, "user", "今天练腿")
    # 他人含关键词 — 必须被隔离
    other = _create_user(db, "search_other")
    other_conv = _create_conversation(db, other.id, "睡眠问题")
    _add_message(db, other_conv.id, "user", "睡不好")

    res = client.get("/api/v1/agent/conversations?search=睡眠", headers=headers)
    assert res.status_code == 200
    data = res.json()
    ids = {it["id"] for it in data["items"]}
    assert conv_title.id in ids  # 标题命中
    assert conv_body.id in ids   # 正文命中
    assert conv_miss.id not in ids
    assert other_conv.id not in ids  # 用户隔离
    assert data["total"] == 2


def test_agent_conversations_search_no_duplicate_rows_on_multi_message_match(
    client, db, auth_user_and_headers
):
    """一条对话里多条消息都命中关键词 → 结果仍只出现一次(EXISTS 而非 join)。"""
    user, headers = auth_user_and_headers
    conv = _create_conversation(db, user.id, "健康问答")
    _add_message(db, conv.id, "user", "血压有点高")
    _add_message(db, conv.id, "assistant", "血压需要持续监测")
    _add_message(db, conv.id, "user", "血压怎么降")

    res = client.get("/api/v1/agent/conversations?search=血压", headers=headers)
    data = res.json()
    ids = [it["id"] for it in data["items"]]
    assert ids.count(conv.id) == 1
    assert data["total"] == 1
