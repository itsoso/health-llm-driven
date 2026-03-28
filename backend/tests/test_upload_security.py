def test_download_nonexistent_file_returns_404(client):
    """测试下载不存在的文件返回404"""
    res = client.get("/api/v1/upload/files/diet/test.jpg")
    assert res.status_code == 404
