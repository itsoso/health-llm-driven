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
        if any(name in step.get("name", "") for name in ("Publish one bound", "Prepare exact OTA artifact")):
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
        "os.mkdir('/opt/reva-release', 0o755)"
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
    assert stage["if"] == "always()"
    assert (
        upload["if"]
        == "always() && steps.ota-audit.outcome == 'success'"
    )
    assert stage["id"] == "ota-audit"
    assert (
        upload["uses"]
        == "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02"
    )
    assert upload["with"]["include-hidden-files"] is False
    assert upload["with"]["if-no-files-found"] == "ignore"
    assert set(upload["with"]["path"].splitlines()) == {
        "/opt/reva-release/audit/ota-diagnostic.json",
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
            "runtime": "1.3.5",
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
            "runtime": "1.3.5",
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


def test_canonical_git_creation_is_sealed_under_inherited_group_umask(tmp_path):
    import stat

    body = named('Materialize exact canonical')['run']
    shell = body.split("/bin/bash --noprofile --norc -eu -c '", 1)[1].split("' reva-bootstrap", 1)[0]
    # Execute the exact producer prefix through git init, without network fetch.
    prefix = shell.split('cd /opt/reva-release/source', 1)[0]
    source = tmp_path / 'source'
    assert not source.exists()
    prefix = prefix.replace('/opt/reva-release/source', str(source))
    result = subprocess.run(['/bin/bash', '--noprofile', '--norc', '-eu', '-c', 'umask 0002\n' + prefix],
                            env={'PATH':'/usr/bin:/bin','HOME':str(tmp_path),'GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null'}, capture_output=True)
    assert result.returncode == 0
    assert stat.S_IMODE(source.stat().st_mode) == 0o755
    assert stat.S_IMODE((source / '.git').stat().st_mode) == 0o755
    assert stat.S_IMODE((source / '.git/config').stat().st_mode) == 0o644


def test_every_locked_dependency_producer_sets_umask_inside_root_shell(tmp_path):
    import shlex
    import stat
    import sys

    body = named('Install locked CLI')['run']
    commands = body.replace('\\\n', '').splitlines()
    producers = [shlex.split(line) for line in commands if line.strip()]
    assert len(producers) == 8
    for index, argv in enumerate(producers):
        assert argv[:3] == ['/usr/bin/sudo','/usr/bin/env','-i']
        # Keep the actual root-child shell/forwarding wrapper, replacing only
        # its executable with a filesystem producer having npm bin-links semantics.
        shell_index = argv.index('/bin/bash')
        child = argv[shell_index:shell_index + 6]
        assert child[:4] == ['/bin/bash','--noprofile','--norc','-eu']
        assert child[4] == '-c'
        out = tmp_path / str(index)
        code = "import os,pathlib; p=pathlib.Path(__import__('sys').argv[1]); p.mkdir(); (p/'file').write_text('x'); (p/'bin').write_text('x'); mask=os.umask(0); os.umask(mask); (p/'bin').chmod(0o777 & ~mask)"
        command = [*child, 'reva-locked-tools', sys.executable, '-c', code, str(out)]
        result = subprocess.run(['/bin/bash','-c','umask 0002; exec "$@"','test-parent',*command], capture_output=True)
        assert result.returncode == 0
        assert [stat.S_IMODE((out / name).stat().st_mode) for name in ('file','bin')] == [0o644,0o755]
        assert stat.S_IMODE(out.stat().st_mode) == 0o755


def fresh_source_helpers(monkeypatch):
    import os
    from types import SimpleNamespace
    ns = embedded_functions(named('Materialize exact canonical'))
    original = os.fstat
    def root_metadata(fd):
        s = original(fd)
        return SimpleNamespace(st_uid=0, st_gid=0, st_mode=s.st_mode, st_dev=s.st_dev, st_ino=s.st_ino)
    monkeypatch.setattr(ns['os'], 'fstat', root_metadata)
    return ns


@pytest.mark.parametrize('existing', ['directory', 'symlink'])
def test_fresh_canonical_source_rejects_existing_without_mutation(tmp_path, monkeypatch, existing):
    ns = fresh_source_helpers(monkeypatch)
    target = tmp_path / 'source'
    if existing == 'directory':
        target.mkdir(); (target / 'keep').write_text('unchanged')
    else:
        target.symlink_to(tmp_path, target_is_directory=True)
    before = target.lstat()
    with pytest.raises((FileExistsError, ValueError)):
        ns['create_canonical_source'](tmp_path)
    assert target.lstat() == before


def test_fresh_canonical_source_only_accepts_enodata(tmp_path, monkeypatch):
    import errno
    ns = fresh_source_helpers(monkeypatch)
    def denied(*args):
        raise OSError(errno.EACCES, 'static test')
    monkeypatch.setattr(ns['os'], 'removexattr', denied, raising=False)
    with pytest.raises(OSError):
        ns['create_canonical_source'](tmp_path)


def test_fresh_canonical_source_removes_real_linux_default_acl(tmp_path, monkeypatch):
    import os
    import stat
    import struct
    import sys
    if sys.platform != 'linux':
        pytest.skip('real Linux POSIX default ACL required; macOS is not evidence')
    ns = fresh_source_helpers(monkeypatch)
    # Linux POSIX ACL xattr v2, owner/group/other all rwx. No setfacl dependency.
    acl = struct.pack('<I', 2) + b''.join(struct.pack('<HHI', tag, 7, 0xffffffff) for tag in (1,4,32))
    os.setxattr(tmp_path, 'system.posix_acl_default', acl)
    old = os.umask(0o022)
    try:
        baseline = tmp_path / 'baseline'
        baseline.mkdir()
        assert stat.S_IMODE(baseline.stat().st_mode) == 0o777
        result = ns['create_canonical_source'](tmp_path)
        assert result['inherited_default_acl'] is True
        source = tmp_path / 'source'
        assert stat.S_IMODE(source.stat().st_mode) == 0o755
        assert 'system.posix_acl_default' not in os.listxattr(source)
        child = source / 'child'; child.mkdir()
        (child / 'file').write_text('safe')
        assert stat.S_IMODE(child.stat().st_mode) == 0o755
        assert stat.S_IMODE((child / 'file').stat().st_mode) == 0o644
        assert os.getxattr(tmp_path, 'system.posix_acl_default') == acl
    finally:
        os.umask(old)


def test_fresh_canonical_source_rejects_writable_parent(tmp_path, monkeypatch):
    ns = fresh_source_helpers(monkeypatch)
    tmp_path.chmod(0o777)
    with pytest.raises(ValueError, match='untrusted canonical parent'):
        ns['create_canonical_source'](tmp_path)
    assert not (tmp_path / 'source').exists()


def test_fresh_canonical_source_rejects_linked_parent(tmp_path, monkeypatch):
    ns = fresh_source_helpers(monkeypatch)
    link = tmp_path / 'linked'; link.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(OSError):
        ns['create_canonical_source'](link)
    assert not (tmp_path / 'source').exists()


def test_source_metadata_diagnostics_precede_credentials():
    steps = workflow()['jobs']['ota']['steps']
    before_node = next(i for i, s in enumerate(steps) if s.get('name') == 'Fixed Node toolchain')
    after_checkout = steps.index(named('Canonical source metadata after_checkout'))
    after_dependencies = steps.index(named('Canonical source metadata after_dependencies'))
    assert after_checkout < before_node
    assert steps.index(named('Install locked CLI')) < after_dependencies < steps.index(named('Read-only publisher'))
    for stage in ('after_checkout', 'after_dependencies'):
        body = named('Canonical source metadata ' + stage)['run']
        assert "'role': 'source'" in body and "'phase': '" + stage + "'" in body
        assert 'os.getxattr' in body and 'print(json.dumps' in body
        assert 'fchmod' not in body and 'removexattr' not in body and 'secrets.' not in body


@pytest.mark.parametrize('operation', ['removexattr', 'getxattr'])
@pytest.mark.parametrize('code_name', ['EACCES', 'EIO', 'ENOTSUP'])
def test_fresh_canonical_acl_unknown_errors_are_blocking(tmp_path, monkeypatch, operation, code_name):
    import errno
    ns = fresh_source_helpers(monkeypatch)
    monkeypatch.setattr(ns['os'], 'removexattr', lambda *a: None, raising=False)
    def failed(*args):
        raise OSError(getattr(errno, code_name), 'fixed synthetic failure')
    monkeypatch.setattr(ns['os'], operation, failed, raising=False)
    with pytest.raises(OSError) as caught:
        ns['create_canonical_source'](tmp_path)
    assert caught.value.errno == getattr(errno, code_name)


def test_fresh_canonical_enodata_creates_exact_mode_without_touching_parent(tmp_path, monkeypatch):
    import errno
    import stat
    ns = fresh_source_helpers(monkeypatch)
    def absent(*args):
        raise OSError(errno.ENODATA, 'no default ACL')
    monkeypatch.setattr(ns['os'], 'removexattr', absent, raising=False)
    monkeypatch.setattr(ns['os'], 'getxattr', absent, raising=False)
    parent_before = tmp_path.stat().st_mode
    result = ns['create_canonical_source'](tmp_path)
    assert result['inherited_default_acl'] is False
    assert stat.S_IMODE((tmp_path / 'source').stat().st_mode) == 0o755
    assert tmp_path.stat().st_mode == parent_before


def test_vendor_admission_only_follows_all_uncredentialed_gates():
    steps = workflow()['jobs']['ota']['steps']
    admission = named('Prepare exact OTA artifact')
    assert admission['if'] == "inputs.target == 'validate'"
    assert steps.index(named('Read-only publisher context')) < steps.index(admission)
    assert admission['env'] == {'TARGET_SHA': '${{ inputs.sha }}', 'EXPO_TOKEN': '${{ secrets.REVA_RELEASE_EXPO_TOKEN }}'}
    assert '--prepare' in admission['run'] and '--preflight' not in admission['run']
    assert 'trusted_release_gate.py' in admission['run']
    assert 'env -i' in admission['run'] and '-I -S -B' in admission['run']
    assert 'RELEASE_KEY' not in str(admission) and 'RELEASE_HOST_KEYS' not in str(admission)


@pytest.mark.parametrize('mutation', ['none', 'phase', 'reason', 'secret', 'success'])
def test_early_safe_diagnostic_audit_is_strictly_closed(mutation):
    ns = embedded_functions(named('Stage validated OTA audit'))
    value = {'sha': 'c'*40, 'state': 'BLOCKED', 'phase': 'baseline', 'reason': 'command_failed'}
    if mutation == 'phase': value['phase'] = 'https://private.example'
    if mutation == 'reason': value['reason'] = 'SECRET'
    if mutation == 'secret': value['stderr'] = 'SECRET'
    if mutation == 'success': value['state'] = 'ADMISSION_PASSED'
    records = {'ota-diagnostic.json': value}
    if mutation == 'none':
        assert ns['validate_records'](records, 'c'*40) == records
    else:
        with pytest.raises(ValueError): ns['validate_records'](records, 'c'*40)


def test_every_publisher_diagnostic_round_trips_through_audit_whitelist():
    import importlib.util
    spec = importlib.util.spec_from_file_location('ota_safe_diagnostic_contract', ROOT / 'scripts/trusted_ota_publish.py')
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    validate = embedded_functions(named('Stage validated OTA audit'))['validate_records']
    for phase in m.DIAGNOSTIC_PHASES - {'admission', 'preparation'}:
        for reason in m.DIAGNOSTIC_REASONS - {'verified'}:
            records = {'ota-diagnostic.json': m.diagnostic('c'*40, 'BLOCKED', phase, reason)}
            assert validate(records, 'c'*40) == records
    records = {'ota-diagnostic.json': m.diagnostic('c'*40, 'ADMISSION_PASSED', 'admission', 'verified')}
    assert validate(records, 'c'*40) == records


def test_preparation_diagnostic_round_trip_does_not_allow_false_success():
    validate = embedded_functions(named("Stage validated OTA audit"))["validate_records"]
    value = {"sha": "c" * 40, "state": "PREPARATION_PASSED", "phase": "preparation", "reason": "verified"}
    assert validate({"ota-diagnostic.json": value}, "c" * 40)
    for changes in ({"phase": "vendor-publish"}, {"reason": "command_failed"}, {"state": "BLOCKED"}):
        with pytest.raises(ValueError):
            validate({"ota-diagnostic.json": {**value, **changes}}, "c" * 40)
