def test_download_requires_auth(client):
    res = client.get("/api/v1/upload/files/diet/test.jpg")
    assert res.status_code in (401, 403)
