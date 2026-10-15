"""Synthetic APNs transport -> Expo remote content.data contract."""
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from app.services.notification.ios_push import IOSPushService


@pytest.mark.asyncio
@pytest.mark.parametrize('silent', [False, True])
@pytest.mark.parametrize('reserved', [False, True])
async def test_remote_data_is_readable_by_expo_and_legacy_clients(silent, reserved):
    service = IOSPushService.__new__(IOSPushService)
    service.use_sandbox = True
    service.bundle_id = 'test.bundle'
    client = AsyncMock()
    client.post.return_value = MagicMock(status_code=200, headers={'apns-id': 'synthetic'})
    context = AsyncMock()
    context.__aenter__.return_value = client
    data = {'deep_link': '/workout-detail?id=123', 'screen': 'workout', 'kind': 'workout_ready'}
    if reserved:
        data.update({'aps': {'alert': 'must not replace visible copy'}, 'body': 'custom metadata'})
    original = dict(data)
    with patch.object(IOSPushService, 'is_configured', new_callable=PropertyMock, return_value=True), patch.object(service, '_generate_jwt_token', return_value='synthetic'), patch('app.services.notification.ios_push.httpx.AsyncClient', return_value=context):
        if silent:
            result = await service.send_silent_push('synthetic-device', data)
        else:
            result = await service.send_push('synthetic-device', '新消息', '打开查看', data=data)
    assert result['success']
    payload = client.post.call_args.kwargs['json']
    # Expo NotificationRecords.swift reads userInfo["body"] for remote notifications.
    assert payload['body'] == data
    assert payload['deep_link'] == data['deep_link']
    assert data == original
    if silent:
        assert payload['aps'] == {'content-available': 1}
    else:
        assert payload['aps']['alert'] == {'title': '新消息', 'body': '打开查看'}
