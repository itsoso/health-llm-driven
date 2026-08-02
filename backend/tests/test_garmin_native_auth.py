from app.services.data_collection.garmin_connect import GarminConnectService


def test_client_factory_supports_garminconnect_03_native_client() -> None:
    service = GarminConnectService("nobody@example.com", "not-a-real-password")

    client = service._create_patched_client(verify_login=False)

    assert hasattr(client, "client")
    assert not hasattr(client, "garth")
    assert callable(client.client.dumps)
    assert callable(client.client.loads)
    assert client.client.is_authenticated is False
