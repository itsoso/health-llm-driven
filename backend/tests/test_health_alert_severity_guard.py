"""Static guard: every health_alert push must declare its severity.

2026-05-01 → 2026-09-30 outage: the Garmin-sync Safety Guardian inline push and
AnomalyDetectionService.send_alerts called PushService.send_notification for
notification_type="health_alert" without ``severity=``. The implicit "info" then
ranked below the default H1-B alert_severity_threshold ("warning") and every push
was dropped — five months of lost safety alerts, green tests throughout (their
tests mocked PushService away).

PushService now fails open (loudly) on a missing/unknown health_alert severity,
but a fallback tier is a guess. This guard makes omission impossible to merge:
  - health_alert calls (literal "health_alert" or NotificationType.HEALTH_ALERT[.value])
    must pass an explicit, non-None ``severity=``;
  - calls whose notification_type is computed (could be health_alert) must too;
  - ``**kwargs`` splats are rejected (the type and severity cannot be verified);
  - a string-literal severity must be a tier PushService knows.
"""
import ast
from pathlib import Path

from app.services.notification.push_service import _SEVERITY_ORDER

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"

# send_notification(user_id, notification_type, title, content, data, channels,
#                   respect_quiet_hours, severity, ...) on a bound PushService.
_TYPE_POS = 1
_SEVERITY_POS = 7
_HEALTH_ALERT_ATTRS = {"NotificationType.HEALTH_ALERT", "NotificationType.HEALTH_ALERT.value"}


def _notification_type_kind(node: ast.expr | None) -> str:
    """'health_alert' | 'other' (a known non-health_alert literal) | 'dynamic'."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return "health_alert" if node.value == "health_alert" else "other"
    if isinstance(node, ast.Attribute) and ast.unparse(node).startswith("NotificationType."):
        return "health_alert" if ast.unparse(node) in _HEALTH_ALERT_ATTRS else "other"
    return "dynamic"


def find_violations(source: str, filename: str = "<src>") -> tuple[list[str], list[str]]:
    """Return (violations, health_alert_call_sites) for one module's source."""
    violations: list[str] = []
    health_alert_sites: list[str] = []
    for node in ast.walk(ast.parse(source, filename=filename)):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "send_notification"
        ):
            continue
        where = f"{filename}:{node.lineno}"
        if any(kw.arg is None for kw in node.keywords):
            violations.append(f"{where}: **kwargs splat hides notification_type/severity")
            continue
        kwargs = {kw.arg: kw.value for kw in node.keywords}
        ntype = kwargs.get("notification_type")
        if ntype is None and len(node.args) > _TYPE_POS:
            ntype = node.args[_TYPE_POS]
        severity = kwargs.get("severity")
        if severity is None and len(node.args) > _SEVERITY_POS:
            severity = node.args[_SEVERITY_POS]

        kind = _notification_type_kind(ntype)
        if kind == "health_alert":
            health_alert_sites.append(where)
        missing = severity is None or (isinstance(severity, ast.Constant) and severity.value is None)
        if kind != "other" and missing:
            violations.append(
                f"{where}: {kind} push without explicit severity= "
                f"(implicit tier is dropped by the H1-B threshold)"
            )
        if (
            isinstance(severity, ast.Constant)
            and isinstance(severity.value, str)
            and severity.value.strip().lower() not in _SEVERITY_ORDER
        ):
            violations.append(f"{where}: unknown severity literal {severity.value!r}")
    return violations, health_alert_sites


def _scan_app() -> tuple[list[str], list[str]]:
    violations: list[str] = []
    sites: list[str] = []
    for path in sorted(APP.rglob("*.py")):
        found, ha_sites = find_violations(path.read_text(encoding="utf-8"), str(path.relative_to(ROOT)))
        violations.extend(found)
        sites.extend(ha_sites)
    return violations, sites


def test_every_health_alert_push_in_app_declares_a_known_severity():
    violations, _ = _scan_app()
    assert violations == [], "\n".join(violations)


def test_scan_sees_both_call_site_forms():
    """Non-vacuity: one real canary per detection form.

    tasks/notifications.py (evaluate_and_push_safety) uses the "health_alert" literal;
    anomaly_detection_service (an outage producer) uses NotificationType.HEALTH_ALERT.value.
    """
    _, sites = _scan_app()
    files = {site.rsplit(":", 1)[0] for site in sites}
    assert "app/tasks/notifications.py" in files, sites
    assert "app/services/anomaly_detection_service.py" in files, sites


class TestGuardSelfCheck:
    """The guard must fail on the exact shapes that caused the outage."""

    def test_flags_literal_health_alert_without_severity(self):
        src = 'svc.send_notification(user_id=1, notification_type="health_alert", title="t", content="c")'
        violations, sites = find_violations(src)
        assert sites and len(violations) == 1

    def test_flags_enum_health_alert_without_severity(self):
        src = (
            "await svc.send_notification(user_id=1, "
            "notification_type=NotificationType.HEALTH_ALERT.value, title='t', content='c')"
        )
        assert len(find_violations(src)[0]) == 1

    def test_flags_explicit_none_severity(self):
        src = 'svc.send_notification(user_id=1, notification_type="health_alert", title="t", content="c", severity=None)'
        assert len(find_violations(src)[0]) == 1

    def test_flags_dynamic_type_without_severity(self):
        src = "svc.send_notification(user_id=1, notification_type=ntype, title='t', content='c')"
        assert len(find_violations(src)[0]) == 1

    def test_flags_kwargs_splat(self):
        assert len(find_violations("svc.send_notification(**payload)")[0]) == 1

    def test_flags_misspelled_severity_literal(self):
        src = 'svc.send_notification(user_id=1, notification_type="reminder", title="t", content="c", severity="critcal")'
        assert len(find_violations(src)[0]) == 1

    def test_accepts_explicit_severity_keyword_and_positional(self):
        keyword = (
            'svc.send_notification(user_id=1, notification_type="health_alert", '
            'title="t", content="c", severity=alert.severity.label)'
        )
        positional = 'svc.send_notification(1, "health_alert", "t", "c", None, None, True, "critical")'
        assert find_violations(keyword)[0] == []
        assert find_violations(positional)[0] == []

    def test_non_health_alert_literal_may_omit_severity(self):
        src = 'svc.send_notification(user_id=1, notification_type="reminder", title="t", content="c")'
        assert find_violations(src) == ([], [])
