"""Import-time smoke tests.

故意不依赖 conftest fixtures — 这些测试要在 conftest 自己坏掉的时候也能跑。
跑的是最低限度的事：`from main import app` 能不能过，app 对象存不存在。

历史教训：`main.py` 曾在 module 级别 `Base.metadata.create_all(bind=engine)`，
一旦 DB 不可达（CI 没有 Postgres），conftest `from main import app` 直接
ImportError，整个 pytest 套件零测试执行、无差别红。这个文件就是为了在那种情况
也能留下一个明确信号。
"""
import os


def test_app_imports_without_db():
    """验证 app 可以在没有真实 DB 的情况下 import。"""
    # 指向一个几乎肯定连不上的地址；create_engine 本身是 lazy 的，
    # 真正的连接应该推迟到 startup 事件里。
    os.environ.setdefault("SECRET_KEY", "test-secret-key-32-chars-minimum!!")
    os.environ.setdefault("GARMIN_ENCRYPTION_KEY", "mI4nYXirjGlbHD7sFogYlqPQJzirU04mUsS5LyDS0SU=")

    from main import app  # noqa: E402

    assert app is not None
    assert hasattr(app, "router")
