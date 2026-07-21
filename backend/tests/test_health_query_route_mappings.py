"""agent_executor 静态 API 路径 ↔ 注册路由 防漂移闸。

背景(2026-07-02):health_query 的 dimension→URL 映射里 4 条路径指向不存在的路由
(water/records/me/today、weight/records/me/recent、garmin-analysis/me/stress、
/exercise/me),对应查询维度一直静默 404 —— 工具把错误文本喂回 LLM,用户拿到
"Error: API 返回 404" 或模型的道歉/编造。路由改名/删除时手写映射不会跟着动,
所以把"每条静态映射必须命中注册路由"钉成测试。

匹配口径:从 agent_executor.py 源码提取所有引号内以注册路由一级前缀开头的绝对
路径(f-string 变量段归一为 {X},去 query),逐条断言存在于 api_router 路由表
(同样归一)。前缀白名单取自真实路由表,不会误伤 /api/v1 示例文本或前端路径。
"""
from __future__ import annotations

import re
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "app" / "services" / "agent_executor.py"


def _normalize(path: str) -> str:
    path = path.split("?")[0]
    return re.sub(r"\{[^}]+\}", "{X}", path)


def test_agent_executor_static_api_paths_all_exist():
    from main import app

    # Validate against the fully assembled production schema.  FastAPI 0.139+
    # keeps included routers as lazy ``_IncludedRouter`` entries without a
    # ``path`` attribute, so walking ``app.routes`` silently misses them.
    routes = {
        _normalize(re.sub(r"^/api/v1", "", path))
        for path in app.openapi()["paths"]
        if path.startswith("/api/v1/")
    }
    prefixes = {p.split("/")[1] for p in routes if p.count("/") >= 1 and p != "/"}

    src = _SRC.read_text(encoding="utf-8")
    # 引号内的绝对路径(含 f-string 花括号段);排除以 /api 开头的示例文本
    candidates = set()
    for m in re.finditer(r"[\"'](/[a-z0-9\-]+(?:/[^\"'\s]*)?)[\"']", src):
        p = m.group(1)
        seg = p.split("/")[1]
        if seg in prefixes:
            candidates.add(_normalize(p))

    assert candidates, "未提取到任何静态 API 路径 —— 提取正则可能失效,修测试别删闸"

    broken = sorted(p for p in candidates if p not in routes)
    assert not broken, (
        f"agent_executor 引用了 {len(broken)} 条不存在的 API 路径(工具会静默 404):{broken}。"
        "修 agent_executor 的映射,或若路由确实改名,同步两处。"
    )
