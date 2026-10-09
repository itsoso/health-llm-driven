"""Daily insights must stay on Token Plan, including caches and failure recovery."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_tokenplan_failure_never_recovers_to_another_provider():
    from app.services.llm.factory import create_tokenplan_provider

    provider = SimpleNamespace(provider_name='tokenplan', model='test-model',
                               chat=AsyncMock(side_effect=RuntimeError('unavailable')))
    original_chat = provider.chat
    with patch('app.services.llm.factory.create_llm_provider', return_value=provider) as create, \
         patch('app.services.llm.usage_tracker._enforce_monthly_token_quota'), \
         patch('app.services.llm.usage_tracker.record_usage'), \
         patch('app.services.llm.recovery.try_recover_chat', new_callable=AsyncMock) as recover:
        wrapped = create_tokenplan_provider()
        with pytest.raises(RuntimeError):
            await wrapped.chat(messages=[{'role': 'user', 'content': 'test@example.com'}])
        create.assert_called_once_with('tokenplan')
        recover.assert_not_called()
        assert 'test@example.com' not in str(original_chat.call_args)
        assert provider._pii_wrapped


def test_daily_service_does_not_construct_global_provider():
    from app.services.daily_recommendation import DailyRecommendationService
    with patch('app.services.llm_health_analyzer.get_llm_provider', side_effect=AssertionError('legacy route')), \
         patch('app.services.daily_insights_analyzer.create_tokenplan_provider', return_value=SimpleNamespace(model='test')) as create:
        service = DailyRecommendationService()
        assert service.analyzer.is_available()
        create.assert_called_once()


@pytest.mark.asyncio
async def test_invalid_json_is_not_success_or_exposed_raw_health_content():
    from app.services.daily_insights_analyzer import TokenPlanHealthAnalyzer
    with patch('app.services.daily_insights_analyzer.create_tokenplan_provider', return_value=SimpleNamespace(model='test')), \
         patch('app.services.llm_health_analyzer.LLMHealthAnalyzer.analyze_daily_health', new_callable=AsyncMock,
               return_value={'available': True, 'error': 'parse', 'raw_response': 'sensitive'}):
        result = await TokenPlanHealthAnalyzer().analyze_daily_health()
    assert result['available'] is False
    assert result['provider'] == 'tokenplan'
    assert 'raw_response' not in result
    assert 'parse' not in result['error']


def test_cache_requires_matching_tokenplan_model_and_success():
    from app.services.daily_insights_analyzer import recommendations_cache_matches, analysis_route
    route = analysis_route(True)
    period = {'status': 'success', '_analysis_route': route,
              'llm_analysis': {'available': True, 'provider': 'tokenplan'}}
    result = {'one_day': period, 'seven_day': period}
    assert recommendations_cache_matches(result, True)
    assert not recommendations_cache_matches(result, False)
    assert not recommendations_cache_matches({'one_day': {'status': 'success'}, 'seven_day': period}, True)
    assert not recommendations_cache_matches({'one_day': {**period, 'llm_analysis': {'available': False}}, 'seven_day': period}, True)
    assert not recommendations_cache_matches({'one_day': {**period, '_analysis_route': {**route, 'model': 'old'}}, 'seven_day': period}, True)


@pytest.mark.asyncio
async def test_database_old_provider_cache_is_replaced_for_only_current_user(db):
    from app.models.user import User
    from app.models.daily_recommendation import DailyRecommendation
    from app.services.daily_recommendation import DailyRecommendationService
    from app.utils.timezone import get_china_today
    today = get_china_today()
    users = [User(name='Synthetic test user', username=f'tokenplan-cache-{i}', email=f'cache{i}@example.test', hashed_password='test') for i in range(2)]
    db.add_all(users)
    db.flush()
    old = {'status': 'success', 'ai_insights': {'health_summary': 'legacy'}}
    rows = [DailyRecommendation(user_id=u.id, recommendation_date=today, analysis_date=today,
                               one_day_recommendation=old, seven_day_recommendation=old) for u in users]
    db.add_all(rows)
    db.commit()
    service = DailyRecommendationService()
    generated = {'status': 'success', 'llm_analysis': {'available': True, 'provider': 'tokenplan'}}
    with patch.object(service, 'get_latest_data', return_value=SimpleNamespace(record_date=today)), \
         patch.object(service, 'generate_one_day_recommendation', new_callable=AsyncMock, return_value=dict(generated)) as one, \
         patch.object(service, 'generate_seven_day_recommendation', new_callable=AsyncMock, return_value=dict(generated)) as seven:
        result = await service.get_or_generate_recommendations(db, users[0].id)
        assert not result['cached']
        cached = await service.get_or_generate_recommendations(db, users[0].id)
        assert cached['cached']
        assert one.await_count == seven.await_count == 1
    db.refresh(rows[1])
    assert rows[1].one_day_recommendation == old


@pytest.mark.asyncio
async def test_redis_legacy_result_is_not_returned_by_me_endpoint():
    from app.api import daily_recommendation as api
    from app.services.daily_insights_analyzer import analysis_route
    route = analysis_route()
    period = {'status': 'success', '_analysis_route': route,
              'llm_analysis': {'available': True, 'provider': 'tokenplan'}}
    fresh = {'status': 'success', 'one_day': period, 'seven_day': period, 'cached': False}
    legacy = {'one_day': {'status': 'success'}, 'seven_day': {'status': 'success'}}
    service = SimpleNamespace(get_or_generate_recommendations=AsyncMock(return_value=fresh))
    redis_client = SimpleNamespace(set=lambda *a, **k: True, delete=lambda *a: None)
    with patch.object(api, 'get_cached_daily_recommendation', return_value=legacy), \
         patch.object(api, 'DailyRecommendationService', return_value=service), \
         patch.object(api, 'cache_daily_recommendation') as cache, \
         patch('redis.from_url', return_value=redis_client):
        result = await api.get_my_recommendations(True, SimpleNamespace(id=7), object())
    assert result['one_day']['llm_analysis']['provider'] == 'tokenplan'
    service.get_or_generate_recommendations.assert_awaited_once()
    assert cache.call_args.args[0] == 7


@pytest.mark.asyncio
async def test_seven_day_uses_actual_ai_schema_and_tokenplan_advice(db):
    from app.models.user import User
    from app.models.daily_health import GarminData
    from app.services.daily_recommendation import DailyRecommendationService
    from app.utils.timezone import get_china_today
    user = User(name='Synthetic test user', username='tokenplan-week', email='week@example.test', hashed_password='test')
    db.add(user)
    db.flush()
    db.add(GarminData(user_id=user.id, record_date=get_china_today(), sleep_score=70, steps=6000))
    db.commit()
    analyzer = SimpleNamespace(analyze_daily_health=AsyncMock(return_value={
        'available': True, 'provider': 'tokenplan', 'today_actions': [],
        'health_summary': 'weekly summary', 'key_insights': ['insight'], 'today_focus': 'focus',
        'sleep_advice': 'sleep advice',
    }))
    service = DailyRecommendationService()
    service._analyzer = analyzer
    result = await service.generate_seven_day_recommendation(db, user.id)
    assert result['ai_insights']['health_summary'] == 'weekly summary'
    assert result['ai_insights']['key_insights'] == ['insight']
    assert result['ai_insights']['today_focus'] == 'focus'
    assert result['ai_advice']['sleep'] == 'sleep advice'
    analyzer.analyze_daily_health.assert_awaited_once()


@pytest.mark.asyncio
async def test_daily_summary_never_calls_legacy_rag_or_embeddings(db):
    from app.services.daily_recommendation import DailyRecommendationService
    from app.services.knowledge.rag_pipeline import rag_pipeline
    service = DailyRecommendationService()
    service._analyzer = SimpleNamespace(analyze_daily_health=AsyncMock(return_value={
        'available': True, 'provider': 'tokenplan', 'today_actions': [],
        'health_summary': 'synthetic summary',
    }))
    with patch.object(service, 'generate_daily_summary', return_value={
        'status': 'success', '_rule_analysis': {}, '_recent_data': [],
        'priority_recommendations': [],
    }), patch.object(service, 'get_environment_data', new_callable=AsyncMock, return_value=None), \
         patch.object(rag_pipeline, 'enhance_daily_advice', side_effect=AssertionError('legacy egress')) as legacy:
        result = await service.generate_daily_summary_with_llm(db, 777)
    assert result['ai_insights']['health_summary'] == 'synthetic summary'
    assert result['knowledge_enhanced'] is False
    legacy.assert_not_called()
