"""Fail-closed admission for duplicate trusted release workflow dispatches."""

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SHA = "a" * 40


def module():
    path = ROOT / "scripts/release_dispatch_admission.py"
    spec = importlib.util.spec_from_file_location("release_dispatch_admission", path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def run(*, run_id=12, workflow="trusted-ota", target="publish", **changes):
    values = {
        "id": run_id,
        "workflow_id": 370218159 if workflow == "trusted-ota" else 352404554,
        "path": f".github/workflows/{workflow}.yml",
        "head_sha": SHA,
        "head_branch": "main",
        "event": "workflow_dispatch",
        "run_attempt": 1,
        "name": (
            "Trusted OTA" if workflow == "trusted-ota" else "Trusted release"
        )
        + f" · {target} · {SHA}",
        "status": "in_progress",
        "conclusion": None,
    }
    values.update(changes)
    return values


def payload(*runs, total_count=None):
    return {
        "total_count": len(runs) if total_count is None else total_count,
        "workflow_runs": list(runs),
    }


def test_unique_current_dispatch_is_admitted():
    admission = module()
    result = admission.admit(
        workflow="trusted-ota",
        target="publish",
        sha=SHA,
        run_id=12,
        run_attempt=1,
        get_json=lambda _: payload(run()),
    )
    assert result == {
        "state": "ADMITTED",
        "workflow": "trusted-ota",
        "target": "publish",
        "sha": SHA,
        "run_id": 12,
    }


def test_inventory_query_is_fixed_to_exact_workflow_main_event_and_sha():
    admission = module()
    paths = []
    admission.admit(
        workflow="trusted-ota",
        target="publish",
        sha=SHA,
        run_id=12,
        run_attempt=1,
        get_json=lambda path: paths.append(path) or payload(run()),
    )
    assert paths == [
        "/actions/workflows/370218159/runs?branch=main&event=workflow_dispatch"
        f"&head_sha={SHA}&per_page=100"
    ]


@pytest.mark.parametrize("status,conclusion", [
    ("queued", None),
    ("in_progress", None),
    ("completed", "success"),
    ("completed", "failure"),
    ("completed", "cancelled"),
])
def test_any_prior_exact_dispatch_blocks_without_retry(status, conclusion):
    admission = module()
    prior = run(run_id=11, status=status, conclusion=conclusion)
    with pytest.raises(admission.AdmissionError, match="prior exact dispatch exists"):
        admission.admit(
            workflow="trusted-ota",
            target="publish",
            sha=SHA,
            run_id=12,
            run_attempt=1,
            get_json=lambda _: payload(run(), prior),
        )


def test_validate_and_publish_are_distinct_keys():
    admission = module()
    prior_validate = run(run_id=11, target="validate", status="completed", conclusion="success")
    result = admission.admit(
        workflow="trusted-ota",
        target="publish",
        sha=SHA,
        run_id=12,
        run_attempt=1,
        get_json=lambda _: payload(run(), prior_validate),
    )
    assert result["state"] == "ADMITTED"


def test_lowest_exact_run_wins_when_a_later_duplicate_is_already_queued():
    admission = module()
    later = run(run_id=13, status="queued", conclusion=None)
    result = admission.admit(
        workflow="trusted-ota",
        target="publish",
        sha=SHA,
        run_id=12,
        run_attempt=1,
        get_json=lambda _: payload(run(), later),
    )
    assert result["run_id"] == 12


@pytest.mark.parametrize("mutation", [
    {"workflow_id": 1},
    {"path": ".github/workflows/other.yml"},
    {"head_sha": "b" * 40},
    {"head_branch": "feature"},
    {"event": "push"},
    {"run_attempt": 2},
    {"name": "Trusted OTA"},
    {"status": []},
    {"conclusion": []},
])
def test_current_run_identity_drift_is_rejected(mutation):
    admission = module()
    with pytest.raises(admission.AdmissionError):
        admission.admit(
            workflow="trusted-ota",
            target="publish",
            sha=SHA,
            run_id=12,
            run_attempt=1,
            get_json=lambda _: payload(run(**mutation)),
        )


def test_rerun_attempt_is_never_admitted():
    admission = module()
    with pytest.raises(admission.AdmissionError, match="first attempt required"):
        admission.admit(
            workflow="trusted-release",
            target="backend",
            sha=SHA,
            run_id=12,
            run_attempt=2,
            get_json=lambda _: pytest.fail("rerun must fail before network"),
        )


@pytest.mark.parametrize("runs,total_count", [
    ([], 0),
    ([run(), run()], 2),
    ([run()], 2),
])
def test_missing_duplicate_or_truncated_inventory_is_rejected(runs, total_count):
    admission = module()
    with pytest.raises(admission.AdmissionError):
        admission.admit(
            workflow="trusted-ota",
            target="publish",
            sha=SHA,
            run_id=12,
            run_attempt=1,
            get_json=lambda _: payload(*runs, total_count=total_count),
        )


def test_api_failure_is_sanitized_and_never_leaks_secret():
    admission = module()

    def fail(_):
        raise RuntimeError("SECRET github response")

    with pytest.raises(admission.AdmissionError) as caught:
        admission.admit(
            workflow="trusted-ota",
            target="publish",
            sha=SHA,
            run_id=12,
            run_attempt=1,
            get_json=fail,
        )
    assert "SECRET" not in str(caught.value)


def test_bounded_api_retry_does_not_expose_provider_error(monkeypatch):
    import urllib.error

    admission = module()
    sleeps = []
    monkeypatch.setattr(admission.time, "sleep", sleeps.append)
    monkeypatch.setattr(
        admission.urllib.request,
        "urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(urllib.error.URLError("SECRET provider body")),
    )
    with pytest.raises(admission.AdmissionError) as caught:
        admission.get_json("/actions/workflows/370218159/runs?per_page=100", "token")
    assert sleeps == [2, 4]
    assert "SECRET" not in str(caught.value)


@pytest.mark.parametrize("token", ["", "token\n", "x" * 4097, "token with space"])
def test_token_stdin_is_bounded_and_strict(token):
    import io

    admission = module()
    with pytest.raises(admission.AdmissionError):
        admission.read_token(io.StringIO(token))


@pytest.mark.parametrize("workflow,target", [
    ("trusted-ota", "backend"),
    ("trusted-release", "publish"),
    ("unknown", "backend"),
])
def test_unknown_workflow_target_pairs_fail_before_network(workflow, target):
    admission = module()
    with pytest.raises(admission.AdmissionError):
        admission.admit(
            workflow=workflow,
            target=target,
            sha=SHA,
            run_id=12,
            run_attempt=1,
            get_json=lambda _: pytest.fail("invalid pair must not read GitHub"),
        )
