#!/usr/bin/env python3
"""
观察期数据看板 — 让"个人工具"的使用数据可见

对照 STRATEGY-2026.md §七 原则: 数据显示的痛点 = 这周要修的东西.
不新增 feature, 不加监控组件, 纯 SQL + 打印. Sentry 卡在选型时的短期替代.

用法:
  python scripts/observation_dashboard.py                 # 默认 7 天窗口
  python scripts/observation_dashboard.py --days 14
  python scripts/observation_dashboard.py --user 1        # 限定单用户
  python scripts/observation_dashboard.py --json          # JSON 输出
  python scripts/observation_dashboard.py --remote        # 走 SSH 跑线上

CLI 与 admin UI (`/api/v1/admin/observability/dashboard`) 共用同一份聚合逻辑,
代码在 `app/services/observability_service.py`.

模块:
  A. Open-Loop Manager 推送有效性 (弱点 G)
  B. Clinical Journal SOAP 覆盖率 (阶段 3)
  C. Memory / KG 增长 (Sprint 5)
  D. Doctor Weekly Report 推送状态 (阶段 4)
  E. ActionCard 信用循环 (信任循环)
  F. Safety Guardian 告警命中 (阶段 1)
  G. tool_validator 命中 (弱点 B, 尾部 journalctl 探针, 仅线上)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# 脚本从 backend/scripts/ 运行; 把 backend/ 加入 sys.path
HERE = Path(__file__).resolve().parent
BACKEND_ROOT = HERE.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.observability_service import (  # noqa: E402
    actionable_suggestions,
    collect_dashboard,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _get_session():
    from app.database import SessionLocal  # type: ignore
    return SessionLocal()


# ============================================================
# 打印
# ============================================================

def _p(title: str):
    print(f"\n{'=' * 58}")
    print(f" {title}")
    print("=" * 58)


def _kv(k, v):
    print(f"  {k:<24} {v}")


def _section_dict(d: dict, indent: int = 2):
    for k, v in d.items():
        print(f"{' ' * indent}{k:<24} {v}")


def render_text(report: dict, days: int, user_id: int | None):
    user_hint = f"user_id={user_id}" if user_id else "全量用户"
    print(f"\n📊 观察期看板  · 过去 {days} 天  · {user_hint}  · {_utc_now().isoformat()}")

    _p("A. Open-Loop Manager 推送")
    ol = report["open_loop"]
    _kv("推送总数", ol["total_sent"])
    _kv("投递失败", ol["delivery_fail"])
    _kv("平均分数", ol["avg_score"] if ol["avg_score"] is not None else "—")
    _kv("最近一条", ol["last_sent"] or "—")
    if ol["by_kind"]:
        print("  按 kind:")
        _section_dict(ol["by_kind"], indent=4)
    if ol["by_action"]:
        print("  按用户反馈:")
        _section_dict(ol["by_action"], indent=4)

    _p("B. Clinical Journal SOAP")
    cj = report["clinical_journal"]
    _kv("SOAP 条数", cj["total_entries"])
    _kv("完整率 (四字段都有)", f"{cj['complete_soap_pct']}%" if cj["complete_soap_pct"] is not None else "—")
    _kv("活跃 case 数", cj["active_case_threads"])
    _kv("最近一条", cj["last_entry"] or "—")
    if cj["by_creator"]:
        print("  按来源:")
        _section_dict(cj["by_creator"], indent=4)
    if cj["by_theme"]:
        print("  按主题:")
        _section_dict(cj["by_theme"], indent=4)

    _p("C. Memory / KG (Sprint 5)")
    mk = report["memory_kg"]
    _kv("Fact 总数", f"{mk['facts_total']} (+{mk['facts_new']} 窗口内)")
    _kv("Entity 总数", f"{mk['entities_total']} (+{mk['entities_new']} 窗口内)")
    _kv("Relation 总数", f"{mk['relations_total']} (+{mk['relations_new']} 窗口内)")
    if mk["facts_by_tier"]:
        print("  Fact 按 tier:")
        _section_dict(mk["facts_by_tier"], indent=4)
    if mk["entities_by_type"]:
        print("  Entity 按 type:")
        _section_dict(mk["entities_by_type"], indent=4)
    if mk["relations_top_predicates"]:
        print("  Relation Top predicates:")
        _section_dict(mk["relations_top_predicates"], indent=4)

    _p("D. Doctor Weekly Report")
    dr = report["doctor_report"]
    _kv("周报 SOAP 落盘", dr["total_attempts"])
    _kv("覆盖用户数", dr["unique_users"])
    _kv("最近一次", dr["last_attempt"] or "—")

    _p("E. ActionCard 信用循环")
    ac = report["action_card"]
    _kv("窗口新建", ac["created_in_window"])
    _kv("窗口已评分", ac["graded_in_window"])
    _kv("平均 accuracy", ac["avg_accuracy"] if ac["avg_accuracy"] is not None else "—")
    if ac["by_specialist"]:
        print("  按 specialist:")
        _section_dict(ac["by_specialist"], indent=4)

    _p("F. Safety Guardian 告警")
    sg = report["safety_guardian"]
    _kv("评估次数", sg["evaluations"])
    _kv("告警总数 (alerts_count 累计)", sg["total_alerts_raised"])

    _p("G. tool_validator (需 --remote)")
    tv = report.get("tool_validator", {"skipped": True, "reason": "local run"})
    if tv.get("skipped"):
        _kv("skipped", tv.get("reason", ""))
    else:
        _kv("coerced", tv.get("coerced"))
        _kv("rejected", tv.get("rejected"))
        _kv("journalctl 行数", tv.get("log_lines"))

    _p("💡 行动建议 (自动)")
    for line in actionable_suggestions(report):
        print(f"  {line}")


# ============================================================
# main
# ============================================================

def run_remote(days: int, user_id: int | None, as_json: bool) -> int:
    """SSH 到生产机跑本脚本自己."""
    cmd_parts = [
        "cd /opt/health-app/backend && source venv/bin/activate &&",
        "python scripts/observation_dashboard.py",
        f"--days {days}",
    ]
    if user_id:
        cmd_parts.append(f"--user {user_id}")
    if as_json:
        cmd_parts.append("--json")
    cmd_parts.append("--include-journal")

    remote_cmd = " ".join(cmd_parts)
    print(f"[remote] ssh root@39.98.206.178 \"{remote_cmd}\"", file=sys.stderr)
    result = subprocess.run(
        ["ssh", "root@39.98.206.178", remote_cmd],
        text=True,
    )
    return result.returncode


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--user", type=int, default=None, help="仅统计该 user_id")
    p.add_argument("--json", action="store_true")
    p.add_argument("--remote", action="store_true", help="通过 SSH 跑线上")
    p.add_argument("--include-journal", action="store_true", help="本地也扫 journalctl (一般 --remote 时自动带)")
    args = p.parse_args()

    if args.remote:
        rc = run_remote(args.days, args.user, args.json)
        sys.exit(rc)

    db = _get_session()
    try:
        report = collect_dashboard(
            db, days=args.days, user_id=args.user,
            include_journalctl=args.include_journal,
        )
    finally:
        db.close()

    if args.json:
        print(json.dumps({
            "generated_at": _utc_now().isoformat(),
            "window_days": args.days,
            "user_id": args.user,
            "report": report,
        }, ensure_ascii=False, indent=2))
    else:
        render_text(report, args.days, args.user)


if __name__ == "__main__":
    main()
