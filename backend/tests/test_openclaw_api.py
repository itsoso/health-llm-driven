"""OpenClaw Channel API 测试"""
import pytest
from unittest.mock import patch, AsyncMock

from app.models.openclaw import OpenClawConversation, OpenClawMessage


class TestOpenClawSend:
    """POST /openclaw/send 非流式对话"""

    def test_send_message_returns_reply(self, client, db, auth_user_and_headers):
        """发送消息应返回完整回复"""
        user, headers = auth_user_and_headers

        async def mock_stream(*args, **kwargs):
            yield {"event": "token", "data": {"content": "你好"}}
            yield {"event": "token", "data": {"content": "世界"}}
            yield {"event": "done", "data": {"conversation_id": 1, "message_id": 1}}

        with patch(
            "app.api.openclaw.OpenClawService"
        ) as MockService:
            instance = MockService.return_value
            instance.send_message_stream = mock_stream
            res = client.post(
                "/api/v1/openclaw/send",
                json={"message": "测试消息"},
                headers=headers,
            )

        assert res.status_code == 200
        data = res.json()
        assert data["reply"] == "你好世界"
        assert data["conversation_id"] == 1

    def test_send_empty_message_rejected(self, client, db, auth_user_and_headers):
        """空消息应返回 400"""
        _, headers = auth_user_and_headers
        res = client.post(
            "/api/v1/openclaw/send",
            json={"message": "   "},
            headers=headers,
        )
        assert res.status_code == 400


class TestOpenClawConversations:
    """对话列表和详情"""

    def _create_conversation(self, db, user_id, title="测试对话"):
        conv = OpenClawConversation(user_id=user_id, title=title)
        db.add(conv)
        db.commit()
        db.refresh(conv)
        return conv

    def _add_message(self, db, conversation_id, role="assistant", content="回复"):
        msg = OpenClawMessage(
            conversation_id=conversation_id, role=role, content=content
        )
        db.add(msg)
        db.commit()
        db.refresh(msg)
        return msg

    def test_list_conversations(self, client, db, auth_user_and_headers):
        """GET /openclaw/conversations 返回对话列表"""
        user, headers = auth_user_and_headers
        self._create_conversation(db, user.id, "对话1")
        self._create_conversation(db, user.id, "对话2")

        res = client.get("/api/v1/openclaw/conversations", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)
        assert len(data) == 2

    def test_list_conversations_empty(self, client, db, auth_user_and_headers):
        """无对话时返回空列表"""
        _, headers = auth_user_and_headers
        res = client.get("/api/v1/openclaw/conversations", headers=headers)
        assert res.status_code == 200
        assert res.json() == []

    def test_delete_conversation(self, client, db, auth_user_and_headers):
        """DELETE /openclaw/conversations/{id} 删除对话"""
        user, headers = auth_user_and_headers
        conv = self._create_conversation(db, user.id)

        res = client.delete(
            f"/api/v1/openclaw/conversations/{conv.id}", headers=headers
        )
        assert res.status_code == 200
        assert res.json()["ok"] is True

    def test_delete_nonexistent_conversation(self, client, db, auth_user_and_headers):
        """删除不存在的对话返回 404"""
        _, headers = auth_user_and_headers
        res = client.delete(
            "/api/v1/openclaw/conversations/99999", headers=headers
        )
        assert res.status_code == 404


class TestOpenClawRating:
    """消息评价"""

    def _setup_message(self, db, user_id):
        conv = OpenClawConversation(user_id=user_id, title="评价测试")
        db.add(conv)
        db.commit()
        db.refresh(conv)
        msg = OpenClawMessage(
            conversation_id=conv.id, role="assistant", content="测试回复"
        )
        db.add(msg)
        db.commit()
        db.refresh(msg)
        return msg

    def test_rate_message_thumbs_up(self, client, db, auth_user_and_headers):
        """评价消息 thumbs up"""
        user, headers = auth_user_and_headers
        msg = self._setup_message(db, user.id)

        res = client.post(
            f"/api/v1/openclaw/messages/{msg.id}/rate",
            json={"rating": 1},
            headers=headers,
        )
        assert res.status_code == 200
        assert res.json()["rating"] == 1

    def test_rate_message_thumbs_down(self, client, db, auth_user_and_headers):
        """评价消息 thumbs down"""
        user, headers = auth_user_and_headers
        msg = self._setup_message(db, user.id)

        res = client.post(
            f"/api/v1/openclaw/messages/{msg.id}/rate",
            json={"rating": -1},
            headers=headers,
        )
        assert res.status_code == 200
        assert res.json()["rating"] == -1

    def test_rate_invalid_value(self, client, db, auth_user_and_headers):
        """无效评价值应返回 422"""
        user, headers = auth_user_and_headers
        msg = self._setup_message(db, user.id)

        res = client.post(
            f"/api/v1/openclaw/messages/{msg.id}/rate",
            json={"rating": 5},
            headers=headers,
        )
        assert res.status_code == 422

    def test_rate_nonexistent_message(self, client, db, auth_user_and_headers):
        """评价不存在的消息返回 404"""
        _, headers = auth_user_and_headers
        res = client.post(
            "/api/v1/openclaw/messages/99999/rate",
            json={"rating": 1},
            headers=headers,
        )
        assert res.status_code == 404
