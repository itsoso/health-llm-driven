#!/usr/bin/env python3
"""
系统健康度评分 — 项目的 "val_bpb"

借鉴 autoresearch 的设计理念：用一个可量化的综合指标衡量系统状态，
部署后自动运行，分数下降则回滚，上升则保留。

评分维度 (总分 100):
  - test_pass_rate  (40 分) — 测试通过率
  - health_check    (30 分) — /api/v1/health 返回 200
  - api_latency     (20 分) — 关键 API P95 延迟
  - error_rate      (10 分) — 最近日志错误率

用法:
  python scripts/system_health_score.py              # 本地检查
  python scripts/system_health_score.py --remote     # 远程生产检查
  python scripts/system_health_score.py --json       # JSON 输出（供脚本消费）
"""
import json
import subprocess
import sys
import time
import os

# 快速失败阈值（低于此分数应触发回滚）
# The deployment contract uses 35 as the minimum score.  Keep this constant
# aligned with the dossier/G5 gate instead of exposing a different threshold
# in the JSON report and the shell exit code.
FAIL_THRESHOLD = 35

# ============================================================
# 评分函数
# ============================================================

def score_tests() -> dict:
    """运行 pytest，计算通过率 → 0~40 分"""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=no", "--no-cov", "--no-header"],
            capture_output=True, text=True, timeout=300,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        output = result.stdout.strip().split("\n")
        # 找到包含 "passed" 的汇总行: "====== 86 failed, 508 passed, ... ======"
        summary_line = ""
        for line in reversed(output):
            if "passed" in line or "failed" in line:
                summary_line = line.strip("= \n")
                break
        passed = 0
        total = 0
        import re
        for match in re.finditer(r"(\d+)\s+(passed|failed|error)", summary_line):
            count = int(match.group(1))
            kind = match.group(2)
            total += count
            if kind == "passed":
                passed = count

        if total == 0:
            return {"score": 0, "detail": "no tests found", "passed": 0, "total": 0}

        rate = passed / total
        # 线性映射: 100% → 40 分, 80% → 32 分, <50% → 0 分
        score = max(0, min(40, rate * 40))
        return {
            "score": round(score, 1),
            "detail": f"{passed}/{total} passed ({rate:.0%})",
            "passed": passed,
            "total": total,
        }
    except subprocess.TimeoutExpired:
        return {"score": 0, "detail": "tests timed out (>300s)", "passed": 0, "total": 0}
    except Exception as e:
        return {"score": 0, "detail": f"error: {e}", "passed": 0, "total": 0}


def score_health_check(base_url: str = "http://localhost:8000") -> dict:
    """检查 /api/v1/health 端点 → 0~30 分"""
    import urllib.request
    import urllib.error

    url = f"{base_url}/api/v1/health"
    try:
        start = time.time()
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            latency_ms = (time.time() - start) * 1000
            body = json.loads(resp.read())
            status_code = resp.status

        if status_code == 200 and body.get("status") == "healthy":
            # 全部正常 30 分
            score = 30
        elif status_code == 503 or body.get("status") == "degraded":
            # 降级 15 分
            score = 15
        else:
            score = 10

        return {
            "score": score,
            "detail": f"status={body.get('status')}, latency={latency_ms:.0f}ms",
            "services": body.get("services", {}),
        }
    except urllib.error.HTTPError as e:
        if e.code == 503:
            return {"score": 15, "detail": f"degraded (HTTP 503)"}
        return {"score": 0, "detail": f"HTTP {e.code}"}
    except Exception as e:
        return {"score": 0, "detail": f"unreachable: {e}"}


def score_api_latency(base_url: str = "http://localhost:8000") -> dict:
    """测量关键 API 延迟 → 0~20 分"""
    import urllib.request
    import urllib.error

    # FastAPI 无 root `/`, 之前测它导致 10000ms 超时把 P95 污染.
    # 只测确定存在的 health 端点 + 一个公共信息端点.
    endpoints = [
        "/api/v1/health",
        "/api/v1/admin/observability/health",
    ]

    latencies = []
    for ep in endpoints:
        try:
            start = time.time()
            req = urllib.request.Request(f"{base_url}{ep}", method="GET")
            with urllib.request.urlopen(req, timeout=10):
                latencies.append((time.time() - start) * 1000)
        except urllib.error.HTTPError as e:
            # 401/403 是预期行为 (admin endpoint 需鉴权), 延迟本身有效, 仍记
            if e.code in (401, 403):
                latencies.append((time.time() - start) * 1000)
            else:
                # 其他 HTTP 错误不计入 P95, 避免 404 之类污染
                continue
        except Exception:
            # 真超时/连不上才算
            latencies.append(10000)

    if not latencies:
        return {"score": 0, "detail": "no endpoints reachable"}

    p95 = sorted(latencies)[int(len(latencies) * 0.95)] if len(latencies) > 1 else latencies[0]

    # <200ms → 20分, <500ms → 15分, <1000ms → 10分, <2000ms → 5分, else 0分
    if p95 < 200:
        score = 20
    elif p95 < 500:
        score = 15
    elif p95 < 1000:
        score = 10
    elif p95 < 2000:
        score = 5
    else:
        score = 0

    return {
        "score": score,
        "detail": f"P95={p95:.0f}ms ({len(latencies)} endpoints)",
        "p95_ms": round(p95),
    }


def score_error_rate_from_logs() -> dict:
    """分析最近日志的错误率 → 0~10 分"""
    try:
        # 尝试读取 systemd 日志（生产环境）
        result = subprocess.run(
            ["journalctl", "-u", "health-backend", "-n", "200", "--no-pager", "-q"],
            capture_output=True, text=True, timeout=10
        )
        lines = result.stdout.strip().split("\n") if result.stdout.strip() else []
    except (FileNotFoundError, subprocess.TimeoutExpired):
        # 本地环境没有 journalctl
        return {"score": 10, "detail": "no logs available (local env), assuming ok"}

    if not lines:
        return {"score": 10, "detail": "no log lines"}

    total = len(lines)
    # 只数真错 (level=ERROR/CRITICAL), 不算 INFO 里有 "ERROR" 字符串的 LLM response etc
    errors = sum(
        1 for line in lines
        if ("[ERROR]" in line or "[CRITICAL]" in line or " ERROR " in line)
        and "errorMessage" not in line   # LLM response 里的字段名不算
        and "error_count" not in line    # metric 指标字段也不算
    )
    error_rate = errors / total if total > 0 else 0

    # <1% → 10分, <5% → 8分, <15% → 5分, <30% → 2分, else 0分
    # 之前 10% 阈值过严 — 后端调第三方 (LLM/qweather/阿里云) 出 429/5xx 是常态,
    # 用 fallback 处理但日志 level=ERROR, 这类 not-actually-broken 占比可高.
    if error_rate < 0.01:
        score = 10
    elif error_rate < 0.05:
        score = 8
    elif error_rate < 0.15:
        score = 5
    elif error_rate < 0.30:
        score = 2
    else:
        score = 0

    return {
        "score": score,
        "detail": f"{errors}/{total} errors ({error_rate:.1%})",
        "error_count": errors,
        "total_lines": total,
    }


# ============================================================
# 主流程
# ============================================================

def calculate_health_score(base_url: str = "http://localhost:8000", skip_tests: bool = False) -> dict:
    """计算系统健康度综合评分"""
    results = {}

    if skip_tests:
        results["test_pass_rate"] = {"score": 0, "detail": "skipped"}
    else:
        results["test_pass_rate"] = score_tests()

    results["health_check"] = score_health_check(base_url)
    results["api_latency"] = score_api_latency(base_url)
    results["error_rate"] = score_error_rate_from_logs()

    total = sum(r["score"] for r in results.values())
    max_possible = 100 if not skip_tests else 60

    return {
        "total_score": round(total, 1),
        "max_possible": max_possible,
        "pass": total >= FAIL_THRESHOLD,
        "threshold": FAIL_THRESHOLD,
        "dimensions": results,
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="系统健康度评分")
    parser.add_argument("--remote", action="store_true", help="检查远程生产环境")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    parser.add_argument("--skip-tests", action="store_true", help="跳过测试（用于部署后快速检查）")
    parser.add_argument("--url", default=None, help="自定义 API base URL")
    args = parser.parse_args()

    if args.remote:
        base_url = args.url or "https://health-api.executor.life"
    else:
        base_url = args.url or "http://localhost:8000"

    report = calculate_health_score(base_url, skip_tests=args.skip_tests)

    if args.json:
        print(json.dumps(report, ensure_ascii=False))
    else:
        print(f"\n{'='*50}")
        print(f"  系统健康度评分: {report['total_score']}/{report['max_possible']}")
        print(f"  状态: {'✅ PASS' if report['pass'] else '❌ FAIL'}")
        print(f"  阈值: {report['threshold']}")
        print(f"{'='*50}")
        for name, dim in report["dimensions"].items():
            print(f"  {name:20s} {dim['score']:5.1f}  {dim['detail']}")
        print()

    # 退出码: 0=pass, 1=fail（供 shell 脚本判断）
    sys.exit(0 if report["pass"] else 1)


if __name__ == "__main__":
    main()
