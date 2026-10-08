"""Exercise hostile dispatch before the fresh-hosted credential boundary."""

from pathlib import Path
import subprocess
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def workflow():
    return yaml.safe_load((ROOT / ".github/workflows/trusted-ota.yml").read_text())


@pytest.mark.parametrize(
    "changes",
    [
        {"TARGET_SHA": "main"},
        {"TARGET_SHA": "$(touch /tmp/untrusted-ota)"},
        {"GITHUB_SHA": "b" * 40},
        {"GITHUB_REF": "refs/pull/1/head"},
        {"GITHUB_REPOSITORY": "attacker/fork"},
    ],
)
def test_bad_dispatch_fails_before_any_external_command(changes):
    step = workflow()["jobs"]["ota"]["steps"][0]
    prefix = step["run"].split("/usr/bin/sudo", 1)[0]
    result = subprocess.run(
        ["/bin/bash", "--noprofile", "--norc", "-eu", "-c", prefix + "\necho REACHED"],
        env={
            "PATH": "/nonexistent",
            "TARGET_SHA": "a" * 40,
            "GITHUB_SHA": "a" * 40,
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_REPOSITORY": "itsoso/health-llm-driven",
            **changes,
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "REACHED" not in result.stdout


def test_hosted_ota_never_uses_developer_checkout_or_cached_deps():
    w = workflow()
    on = w.get("on", w.get(True))
    assert set(on) == {"workflow_dispatch"}
    assert on["workflow_dispatch"]["inputs"]["target"]["default"] == "validate"
    assert w["permissions"] == {"contents": "read", "actions": "read"}
    assert w["concurrency"] == {
        "group": "reva-production-release",
        "cancel-in-progress": False,
    }
    job = w["jobs"]["ota"]
    assert job["runs-on"] == "ubuntu-24.04"
    assert job["environment"] == "release-production"
    for step in job["steps"]:
        if "Publish one bound" in step.get("name", ""):
            continue
        assert "secrets." not in str(step)
        assert "actions/checkout" not in str(step)
        assert "actions/cache" not in str(step)
    install = next(s for s in job["steps"] if "Install locked CLI" in s.get("name", ""))
    assert "--ignore-scripts" in install["run"] and "compat.test.cjs" in install["run"]
    publish = next(s for s in job["steps"] if "Publish one bound" in s.get("name", ""))
    assert publish["if"] == "inputs.target == 'publish'"
    assert "env -i" in publish["run"] and "-I -S -B" in publish["run"]
    assert "trusted_ota_publish.py" in publish["run"]
    assert "mobile-ota.sh" not in publish["run"]
    assert "--allow-dirty" not in str(w)


def named(fragment):
    return next(
        s for s in workflow()["jobs"]["ota"]["steps"] if fragment in s.get("name", "")
    )


def embedded_functions(step):
    """Load only pure/helper definitions from fixed inline Python, never its root entry."""
    import ast
    import json
    import os
    import re
    import stat

    source = step["run"].split("<<'PY'\n", 1)[1].split("\nPY", 1)[0]
    module = ast.parse(source)
    functions = ast.Module(
        body=[
            n
            for n in module.body
            if isinstance(n, (ast.FunctionDef, ast.Import, ast.ImportFrom))
        ],
        type_ignores=[],
    )
    namespace = {"Path": Path, "json": json, "os": os, "re": re, "stat": stat}
    exec(compile(functions, "workflow-inline-test", "exec"), namespace)
    return namespace


def test_node_hardening_and_commands_use_only_fixed_pinned_toolchain():
    steps = workflow()["jobs"]["ota"]["steps"]
    harden = named("Harden fixed Node")
    install = named("Install locked CLI")
    assert steps.index(harden) < steps.index(install)
    assert "/usr/bin/python3 -I -S -B" in harden["run"]
    assert "chown" in harden["run"] and "0o022" in harden["run"]
    assert "command -v" not in install["run"] and "node_bin=" not in install["run"]
    assert "/opt/hostedtoolcache/node/22.13.0/x64/bin/node" in install["run"]
    assert "/lib/node_modules/npm/bin/npm-cli.js" in install["run"]
    assert "--cache /opt/reva-release/npm-cache" in install["run"]


def test_hosted_opt_is_sealed_before_canonical_checkout():
    first = workflow()["jobs"]["ota"]["steps"][0]["run"]
    assert first.index("seal_bootstrap_directory(Path('/opt'))") < first.index(
        "/usr/bin/install -d"
    )
    # Later checks must still reject a writable ancestor, not waive it.
    assert "Path('/'), Path('/opt')" in named("Harden fixed Node")["run"]


def test_bootstrap_seals_writable_hosted_directory_by_descriptor(tmp_path, monkeypatch):
    import os
    import types

    ns = embedded_functions(workflow()["jobs"]["ota"]["steps"][0])
    directory = tmp_path / "opt"
    directory.mkdir(mode=0o777)
    directory.chmod(0o777)
    real_fstat = os.fstat
    ownership = []

    def root_stat(fd):
        value = real_fstat(fd)
        return types.SimpleNamespace(
            st_uid=0, st_gid=0, st_dev=value.st_dev, st_ino=value.st_ino,
            st_mode=value.st_mode,
        )

    monkeypatch.setattr(os, "fchown", lambda fd, uid, gid: ownership.append((uid, gid)))
    monkeypatch.setattr(os, "fstat", root_stat)
    ns["seal_bootstrap_directory"](directory)
    assert ownership == [(0, 0)]
    assert directory.stat().st_mode & 0o777 == 0o755


@pytest.mark.parametrize("kind", ["symlink", "file"])
def test_bootstrap_rejects_non_directory_without_mutation(tmp_path, monkeypatch, kind):
    import os

    ns = embedded_functions(workflow()["jobs"]["ota"]["steps"][0])
    target = tmp_path / "target"
    target.mkdir()
    path = tmp_path / "opt"
    if kind == "symlink":
        path.symlink_to(target, target_is_directory=True)
    else:
        path.write_text("not a directory")
    monkeypatch.setattr(os, "fchown", lambda *args: pytest.fail("must not mutate"))
    with pytest.raises((OSError, ValueError)):
        ns["seal_bootstrap_directory"](path)


@pytest.mark.parametrize("failure", ["replacement", "ownership", "mode"])
def test_bootstrap_fails_closed_if_sealing_not_proven(tmp_path, monkeypatch, failure):
    import os
    import types

    ns = embedded_functions(workflow()["jobs"]["ota"]["steps"][0])
    path = tmp_path / "opt"
    path.mkdir()
    real_fstat = os.fstat
    calls = []

    def observed_stat(fd):
        value = real_fstat(fd)
        calls.append(fd)
        after = len(calls) > 1
        return types.SimpleNamespace(
            st_uid=123 if after and failure == "ownership" else 0, st_gid=0,
            st_dev=value.st_dev,
            st_ino=value.st_ino + (1 if after and failure == "replacement" else 0),
            st_mode=value.st_mode | (0o022 if after and failure == "mode" else 0),
        )

    monkeypatch.setattr(os, "fchown", lambda *args: None)
    monkeypatch.setattr(os, "fstat", observed_stat)
    with pytest.raises(ValueError, match="sealing failed"):
        ns["seal_bootstrap_directory"](path)
    # The descriptor is closed on failure, too.
    with pytest.raises(OSError):
        real_fstat(calls[0])


def test_node_hardening_rejects_external_symlink_before_chown(tmp_path):
    ns = embedded_functions(named("Harden fixed Node"))
    tool = tmp_path / "tool"
    tool.mkdir()
    (tool / "bin").mkdir()
    outside = tmp_path / "outside"
    outside.write_text("untrusted")
    (tool / "bin/node").symlink_to(outside)
    with pytest.raises(ValueError):
        ns["inspect_toolchain"](tool)


def test_failure_artifact_is_fixed_whitelist_and_pinned_action():
    stage = named("Stage validated OTA audit")
    upload = named("Preserve OTA audit")
    assert stage["if"] == "always() && inputs.target == 'publish'"
    assert (
        upload["if"]
        == "always() && inputs.target == 'publish' && steps.ota-audit.outcome == 'success'"
    )
    assert stage["id"] == "ota-audit"
    assert (
        upload["uses"]
        == "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02"
    )
    assert upload["with"]["include-hidden-files"] is False
    assert upload["with"]["if-no-files-found"] == "ignore"
    assert set(upload["with"]["path"].splitlines()) == {
        "/opt/reva-release/audit/ota-claim.json",
        "/opt/reva-release/audit/ota-preflight.json",
        "/opt/reva-release/audit/ota-vendor-receipt.json",
        "/opt/reva-release/audit/ota-receipt.json",
    }
    assert "*" not in upload["with"]["path"]
    assert (
        "stdout" not in upload["with"]["path"]
        and "stderr" not in upload["with"]["path"]
    )


def valid_records():
    sha = "a" * 40
    branch = "11111111-1111-4111-8111-111111111111"
    ids = {
        "sha": sha,
        "group_id": "22222222-2222-4222-8222-222222222222",
        "update_id": "33333333-3333-4333-8333-333333333333",
    }
    return sha, {
        "ota-claim.json": {
            "sha": sha,
            "project": "911ea84f-bc7e-4a12-90cf-33966b6f7398",
            "runtime": "1.3.4",
            "platform": "ios",
            "channel": "production",
            "branch_id": branch,
            "branch_name": "production",
            "artifact": {"launch": "x" * 43, "assets": ["y" * 43]},
        },
        "ota-preflight.json": {
            "sha": sha,
            "native_fingerprint": "b" * 40,
            "mapping": {
                "channel_id": "44444444-4444-4444-8444-444444444444",
                "branch_id": branch,
                "branch_name": "production",
            },
        },
        "ota-vendor-receipt.json": ids,
        "ota-receipt.json": {
            **ids,
            "state": "SUCCEEDED",
            "runtime": "1.3.4",
            "project": "911ea84f-bc7e-4a12-90cf-33966b6f7398",
            "channel": "production",
            "platform": "ios",
            "branch_id": branch,
        },
    }


def test_audit_export_allows_partial_known_receipts_without_secret_fields():
    ns = embedded_functions(named("Stage validated OTA audit"))
    sha, records = valid_records()
    assert ns["validate_records"](records, sha) == records
    partial = {k: v for k, v in records.items() if k != "ota-receipt.json"}
    assert ns["validate_records"](partial, sha) == partial
    assert ns["validate_records"]({}, sha) == {}


@pytest.mark.parametrize(
    "mutation",
    [
        "extra_secret",
        "unknown_file",
        "wrong_sha",
        "branch_mismatch",
        "receipt_mismatch",
        "invalid_hash",
        "invalid_enum",
        "extra_mapping",
    ],
)
def test_audit_export_rejects_secret_injection_and_unbound_metadata(mutation):
    ns = embedded_functions(named("Stage validated OTA audit"))
    sha, records = valid_records()
    if mutation == "extra_secret":
        records["ota-claim.json"]["token"] = "sensitive"
    elif mutation == "unknown_file":
        records["publish.stderr"] = {"secret": "sensitive"}
    elif mutation == "wrong_sha":
        records["ota-preflight.json"]["sha"] = "b" * 40
    elif mutation == "branch_mismatch":
        records["ota-receipt.json"]["branch_id"] = (
            "99999999-9999-4999-8999-999999999999"
        )
    elif mutation == "receipt_mismatch":
        records["ota-receipt.json"]["group_id"] = "99999999-9999-4999-8999-999999999999"
    elif mutation == "invalid_hash":
        records["ota-claim.json"]["artifact"]["launch"] = "private token"
    elif mutation == "invalid_enum":
        records["ota-receipt.json"]["channel"] = "private token"
    elif mutation == "extra_mapping":
        records["ota-preflight.json"]["mapping"]["token"] = "private"
    with pytest.raises(ValueError):
        ns["validate_records"](records, sha)


def test_all_inline_shell_programs_parse_without_execution():
    for step in workflow()["jobs"]["ota"]["steps"]:
        if "run" not in step:
            continue
        result = subprocess.run(
            ["/bin/bash", "--noprofile", "--norc", "-n"],
            input=step["run"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (step["name"], result.stderr)


def test_node_inventory_accepts_internal_npm_link_and_rejects_hardlinks(tmp_path):
    import os

    ns = embedded_functions(named("Harden fixed Node"))
    root = tmp_path / "tool"
    root.mkdir()
    (root / "bin").mkdir()
    (root / "lib").mkdir()
    target = root / "lib/npm-cli.js"
    target.write_text("trusted toolchain placeholder")
    (root / "bin/npm").symlink_to("../lib/npm-cli.js")
    found = ns["inspect_toolchain"](root)
    assert {path for path, _ in found} == {
        root,
        root / "bin",
        root / "lib",
        target,
        root / "bin/npm",
    }
    os.link(target, root / "lib/hardlink.js")
    with pytest.raises(ValueError):
        ns["inspect_toolchain"](root)


def test_ota_verifies_signature_backport_before_claim_and_credentials():
    steps = workflow()["jobs"]["ota"]["steps"]
    index = next(i for i, step in enumerate(steps) if "Install locked CLI" in step.get("name", ""))
    body = steps[index]["run"]
    for root in ("scripts/release-tools", "mobile"):
        install = f"ci --prefix /opt/reva-release/source/{root} --ignore-scripts"
        verify = f"/opt/hostedtoolcache/node/22.13.0/x64/bin/node /opt/reva-release/source/scripts/node-forge-backport.cjs --root /opt/reva-release/source/{root} --apply"
        assert body.index(install) < body.index(verify)
        guard = verify.replace("scripts/node-forge-backport.cjs", "frontend/scripts/braces-depth-guard.cjs")
        assert body.index(install) < body.index(guard)
        commands = [line.strip() for line in body.replace("\\\n", "").splitlines()]
        assert any(line.startswith('/usr/bin/sudo /usr/bin/env -i PATH=/opt/hostedtoolcache/node/22.13.0/x64/bin:/usr/bin:/bin HOME=/root')
                   and line.endswith(guard) for line in commands)
    assert "secrets." not in str(steps[index])
    first_secret = next(i for i, step in enumerate(steps) if "secrets." in str(step))
    assert index < first_secret


def test_validate_executes_real_credential_free_publisher_preflight_before_publish():
    steps=workflow()['jobs']['ota']['steps']
    preflight=named('Read-only publisher context and native source preflight')
    assert 'if' not in preflight
    assert steps.index(named('Install locked CLI')) < steps.index(preflight) < steps.index(named('Publish one bound'))
    assert preflight['env'] == {'TARGET_SHA':'${{ inputs.sha }}'}
    assert 'secrets.' not in str(preflight)
    run=preflight['run']
    assert '/usr/bin/env -i PATH=/usr/bin:/bin HOME=/root' in run
    assert '/usr/bin/python3 -I -S -B /opt/reva-release/source/scripts/trusted_ota_publish.py' in run
    assert '--sha "$TARGET_SHA" --preflight' in run
    assert 'EXPO_TOKEN' not in run and 'RELEASE_KEY' not in run and 'ssh ' not in run
