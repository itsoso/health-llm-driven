"""Phase 1.1: 测试 5 维度 LLM 并行调用"""
import asyncio
import json
import pytest
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.health_analysis import HealthAnalysisService
from app.models.user import User


@pytest.fixture
def test_user(db):
    user = User(
        name="并行测试用户",
        birth_date=date(1990, 5, 15),
        gender="男",
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def service():
    return HealthAnalysisService()


@pytest.fixture
def mock_health_data():
    """构造包含所有维度所需字段的健康数据"""
    base_date = date.today()
    return {
        "user": {"name": "测试", "gender": "男", "birth_date": "1990-05-15"},
        "basic_health": {
            "height": 175, "weight": 70, "bmi": 22.9,
            "systolic_bp": 120, "diastolic_bp": 80,
        },
        "medical_exams": [],
        "diseases": [],
        "garmin_data": [
            {
                "record_date": (base_date - timedelta(days=i)).isoformat(),
                "avg_heart_rate": 72 + i % 5,
                "resting_heart_rate": 58 + i % 3,
                "hrv": 45 + i % 10,
                "sleep_score": 75 + i % 8,
                "total_sleep_duration": 420 + i * 5,
                "deep_sleep_duration": 90 + i % 15,
                "rem_sleep_duration": 80 + i % 10,
                "body_battery_charged": 60 + i % 20,
                "stress_level": 30 + i % 10,
                "steps": 8000 + i * 100,
            }
            for i in range(30)
        ],
        "_twin_blob": "HRV=50, RHR=60, sleep_score=80",
        "_safety_alerts": [],
    }


def _make_dimension_json(label: str, score: int = 75) -> str:
    """生成一个合法的维度分析 JSON 响应"""
    return json.dumps({
        "score": score,
        "risk_level": "normal",
        "findings": [f"{label}指标正常"],
        "recommendations": [f"继续保持{label}方面的良好习惯"],
        "evidence_level": "B",
    }, ensure_ascii=False)


# ─────────────────── 核心测试 ───────────────────


class TestAnalyzeDimensionAsync:
    """测试单个维度的 async 分析"""

    @pytest.mark.asyncio
    async def test_single_dimension_returns_parsed_json(self, service):
        """async 维度分析应正确解析 LLM 返回的 JSON"""
        mock_provider = AsyncMock()
        mock_provider.chat.return_value = _make_dimension_json("心血管", 82)

        dim_config = service.ANALYSIS_DIMENSIONS["cardiovascular"]
        result = await service._analyze_dimension_async(
            mock_provider, "cardiovascular", dim_config,
            {"garmin_data": [], "_twin_blob": "", "_safety_alerts": []},
            {"insufficient_data": True},
        )

        assert result["score"] == 82
        assert result["risk_level"] == "normal"
        assert result["label"] == "心血管"
        assert len(result["findings"]) > 0

    @pytest.mark.asyncio
    async def test_dimension_handles_markdown_wrapped_json(self, service):
        """LLM 可能在 JSON 外包裹 ```json 代码块"""
        mock_provider = AsyncMock()
        wrapped = "```json\n" + _make_dimension_json("睡眠恢复", 68) + "\n```"
        mock_provider.chat.return_value = wrapped

        dim_config = service.ANALYSIS_DIMENSIONS["sleep_recovery"]
        result = await service._analyze_dimension_async(
            mock_provider, "sleep_recovery", dim_config,
            {"garmin_data": [], "_twin_blob": "", "_safety_alerts": []},
            {"insufficient_data": True},
        )

        assert result["score"] == 68
        assert result["label"] == "睡眠恢复"

    @pytest.mark.asyncio
    async def test_dimension_fallback_on_invalid_json(self, service):
        """LLM 返回非 JSON 时应优雅降级"""
        mock_provider = AsyncMock()
        mock_provider.chat.return_value = "心血管状况良好，建议继续运动。存在偏高的问题。"

        dim_config = service.ANALYSIS_DIMENSIONS["cardiovascular"]
        result = await service._analyze_dimension_async(
            mock_provider, "cardiovascular", dim_config,
            {"garmin_data": [], "_twin_blob": "", "_safety_alerts": []},
            {"insufficient_data": True},
        )

        assert result["score"] == 60  # 降级默认分
        assert result["risk_level"] == "caution"
        assert result["label"] == "心血管"
        assert "raw_response" in result

    @pytest.mark.asyncio
    async def test_dimension_propagates_exception(self, service):
        """provider 异常应向上传播（由 gather 捕获）"""
        mock_provider = AsyncMock()
        mock_provider.chat.side_effect = RuntimeError("LLM timeout")

        dim_config = service.ANALYSIS_DIMENSIONS["fitness"]
        with pytest.raises(RuntimeError, match="LLM timeout"):
            await service._analyze_dimension_async(
                mock_provider, "fitness", dim_config,
                {"garmin_data": [], "_twin_blob": "", "_safety_alerts": []},
                {"insufficient_data": True},
            )


class TestParallelDimensionExecution:
    """测试 5 维度并行执行"""

    @pytest.mark.asyncio
    async def test_all_five_dimensions_run_concurrently(self, service):
        """5 个维度应全部并发执行并返回结果"""
        call_order = []

        async def mock_chat(**kwargs):
            # 从 system prompt 里提取维度标签
            system_msg = kwargs.get("messages", [{}])[0].get("content", "")
            label = system_msg.split("你是")[1].split("领域")[0] if "你是" in system_msg else "unknown"
            call_order.append(label)
            await asyncio.sleep(0.01)  # 模拟网络延迟
            return _make_dimension_json(label, 70)

        mock_provider = AsyncMock()
        mock_provider.chat = mock_chat

        tasks = {
            dim_key: service._analyze_dimension_async(
                mock_provider, dim_key, dim_config,
                {"garmin_data": [], "_twin_blob": "", "_safety_alerts": []},
                {"insufficient_data": True},
            )
            for dim_key, dim_config in service.ANALYSIS_DIMENSIONS.items()
        }
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        result_dict = dict(zip(tasks.keys(), results))

        # 全部 5 个维度应返回结果
        assert len(result_dict) == 5
        for key, result in result_dict.items():
            assert not isinstance(result, Exception), f"{key} 失败: {result}"
            assert result["score"] == 70

    @pytest.mark.asyncio
    async def test_partial_failure_doesnt_block_others(self, service):
        """单个维度失败不应阻塞其他维度"""
        call_count = 0

        async def mock_chat(**kwargs):
            nonlocal call_count
            call_count += 1
            system_msg = kwargs.get("messages", [{}])[0].get("content", "")
            if "代谢" in system_msg:
                raise RuntimeError("代谢维度 LLM 超时")
            return _make_dimension_json("ok", 80)

        mock_provider = AsyncMock()
        mock_provider.chat = mock_chat

        tasks = {
            dim_key: service._analyze_dimension_async(
                mock_provider, dim_key, dim_config,
                {"garmin_data": [], "_twin_blob": "", "_safety_alerts": []},
                {"insufficient_data": True},
            )
            for dim_key, dim_config in service.ANALYSIS_DIMENSIONS.items()
        }
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        result_dict = dict(zip(tasks.keys(), results))

        # 代谢维度应返回异常
        assert isinstance(result_dict["metabolic"], RuntimeError)
        # 其他 4 个应成功
        for key, result in result_dict.items():
            if key != "metabolic":
                assert not isinstance(result, Exception), f"{key} 不应失败"
                assert result["score"] == 80
        # 5 个维度全部被调用
        assert call_count == 5


class TestAnalyzeHealthStructuredIntegration:
    """测试 analyze_health_structured 端到端（mock LLM + Twin）"""

    def test_structured_analysis_returns_all_dimensions(self, db, test_user, service):
        """结构化分析应包含全部 5 个维度 + 综合评分"""
        mock_provider = AsyncMock()
        mock_provider.chat.return_value = _make_dimension_json("test", 75)

        with patch.object(service, '_get_provider', return_value=mock_provider), \
             patch('app.twin.builder.build_twin', side_effect=ImportError("skip")), \
             patch('app.agents.safety_guardian.evaluate_safety', side_effect=ImportError("skip")):
            # 注入: 让 Twin/Safety 失败降级
            result = service.analyze_health_structured(db, test_user.id, force_refresh=True)

        assert result["structured"] is True
        assert "total_score" in result
        assert len(result["dimensions"]) == 5
        for dim_key in service.ANALYSIS_DIMENSIONS:
            assert dim_key in result["dimensions"]

    def test_structured_analysis_handles_all_llm_failures(self, db, test_user, service):
        """所有 LLM 调用失败时应返回全部 error 维度而非崩溃"""
        mock_provider = AsyncMock()
        mock_provider.chat.side_effect = RuntimeError("全部超时")

        with patch.object(service, '_get_provider', return_value=mock_provider), \
             patch('app.twin.builder.build_twin', side_effect=ImportError("skip")):
            result = service.analyze_health_structured(db, test_user.id, force_refresh=True)

        assert result["structured"] is True
        assert result["total_score"] == 0
        for dim_key, dim_result in result["dimensions"].items():
            assert dim_result["score"] is None
            assert "error" in dim_result

    def test_structured_analysis_mixed_success_failure(self, db, test_user, service):
        """部分维度成功、部分失败时评分应只基于成功的维度"""
        call_idx = 0

        async def mock_chat(**kwargs):
            nonlocal call_idx
            call_idx += 1
            if call_idx % 2 == 0:
                raise RuntimeError("偶数调用失败")
            return _make_dimension_json("ok", 80)

        mock_provider = AsyncMock()
        mock_provider.chat = mock_chat

        with patch.object(service, '_get_provider', return_value=mock_provider), \
             patch('app.twin.builder.build_twin', side_effect=ImportError("skip")):
            result = service.analyze_health_structured(db, test_user.id, force_refresh=True)

        assert result["structured"] is True
        scored = [d for d in result["dimensions"].values() if d.get("score") is not None]
        failed = [d for d in result["dimensions"].values() if "error" in d]
        assert len(scored) > 0
        assert len(failed) > 0
        assert result["total_score"] > 0  # 至少有部分成功


class TestSyncAnalyzeDimensionStillWorks:
    """确保旧的同步 _analyze_dimension 仍然可用（向后兼容）"""

    def test_sync_dimension_still_works(self, service):
        """旧的同步方法应继续工作"""
        mock_provider = AsyncMock()
        mock_provider.chat.return_value = _make_dimension_json("心血管", 85)

        dim_config = service.ANALYSIS_DIMENSIONS["cardiovascular"]
        result = service._analyze_dimension(
            mock_provider, "cardiovascular", dim_config,
            {"garmin_data": [], "_twin_blob": "", "_safety_alerts": []},
            {"insufficient_data": True},
        )

        assert result["score"] == 85
        assert result["label"] == "心血管"
