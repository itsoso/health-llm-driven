"""The hosted OTA publisher must fail closed and never retry vendor writes."""

import copy
import importlib.util
import json
from pathlib import Path

import pytest


def load():
    spec = importlib.util.spec_from_file_location(
        "ota_publisher_test", Path(__file__).with_name("trusted_ota_publish.py")
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def build(m, *, identifier=None, sha=None):
    return {
        "id": identifier or m.NATIVE_BUILD,
        "status": "FINISHED",
        "platform": "IOS",
        "distribution": "STORE",
        "buildProfile": "production",
        "gitCommitHash": sha or m.NATIVE_SHA,
        "appIdentifier": m.BUNDLE,
        "app": {"id": m.PROJECT},
        "updateChannel": {"name": "production"},
        "runtime": {"version": m.RUNTIME},
        "fingerprint": {"hash": "a" * 40},
        "isForIosSimulator": False,
    }


def channel(m):
    branch = "11111111-1111-4111-8111-111111111111"
    return {
        "currentPage": {
            "id": "22222222-2222-4222-8222-222222222222",
            "name": "production",
            "isPaused": False,
            "branchMapping": json.dumps(
                {
                    "version": 0,
                    "data": [{"branchId": branch, "branchMappingLogic": "true"}],
                }
            ),
            "updateBranches": [
                {"id": branch, "name": "production", "updateGroups": []}
            ],
        }
    }


def update(m):
    return [
        {
            "id": "33333333-3333-4333-8333-333333333333",
            "group": "44444444-4444-4444-8444-444444444444",
            "runtimeVersion": m.RUNTIME,
            "platform": "ios",
            "branch": "production",
            "gitCommitHash": "c" * 40,
            "isRollBackToEmbedded": False,
            "message": "trusted OTA " + "c" * 40,
        }
    ]


def test_native_fingerprint_cohort_must_be_complete_and_same():
    m = load()
    base = build(m)
    other = build(m, identifier="55555555-5555-4555-8555-555555555555", sha="b" * 40)
    assert m.validate_builds(base, [base, other]) == "a" * 40


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "different",
        "limit",
        "duplicate",
        "wrong_native",
        "wrong_project",
        "wrong_profile",
        "wrong_runtime",
        "wrong_channel",
        "no_base",
        "simulator",
    ],
)
def test_incompatible_or_incomplete_native_cohort_blocks(mutation):
    m = load()
    base = build(m)
    cohort = [copy.deepcopy(base)]
    if mutation == "missing":
        base["fingerprint"] = None
    elif mutation == "different":
        cohort[0]["fingerprint"]["hash"] = "b" * 40
    elif mutation == "limit":
        cohort = [base] * 100
    elif mutation == "duplicate":
        cohort = [base, base]
    elif mutation == "wrong_native":
        base["gitCommitHash"] = "b" * 40
    elif mutation == "wrong_project":
        cohort[0]["app"]["id"] = "other"
    elif mutation == "wrong_profile":
        cohort[0]["buildProfile"] = "watch-production"
    elif mutation == "wrong_runtime":
        cohort[0]["runtime"]["version"] = "other"
    elif mutation == "wrong_channel":
        cohort[0]["updateChannel"]["name"] = "preview"
    elif mutation == "no_base":
        cohort = []
    elif mutation == "simulator":
        cohort[0]["isForIosSimulator"] = True
    with pytest.raises(m.PublishError):
        m.validate_builds(base, cohort)


def test_production_channel_must_have_one_unconditional_branch():
    m = load()
    assert m.validate_channel(channel(m))["branch_name"] == "production"


@pytest.mark.parametrize(
    "mutation",
    [
        "paused",
        "rollout",
        "other_branch",
        "multiple",
        "mismatch",
        "malformed",
        "duplicate_json",
    ],
)
def test_channel_rollout_or_mapping_change_blocks(mutation):
    m = load()
    data = channel(m)
    c = data["currentPage"]
    if mutation == "paused":
        c["isPaused"] = True
    elif mutation == "rollout":
        c["branchMapping"] = json.dumps(
            {
                "version": 0,
                "data": [
                    {
                        "branchId": c["updateBranches"][0]["id"],
                        "branchMappingLogic": {"percent": 10},
                    }
                ],
            }
        )
    elif mutation == "other_branch":
        c["updateBranches"][0]["name"] = "other"
    elif mutation == "multiple":
        c["updateBranches"].append(copy.deepcopy(c["updateBranches"][0]))
    elif mutation == "mismatch":
        c["updateBranches"][0]["id"] = "55555555-5555-4555-8555-555555555555"
    elif mutation == "malformed":
        c["branchMapping"] = "[]"
    elif mutation == "duplicate_json":
        c["branchMapping"] = '{"version":1,"version":0,"data":[]}'
    with pytest.raises(m.PublishError):
        m.validate_channel(data)


@pytest.mark.parametrize(
    "key,value",
    [
        ("NODE_OPTIONS", "--require /tmp/evil"),
        ("INCLUDE_WATCH_APP", "1"),
        ("APP_VARIANT", "preview"),
        ("EXPO_PUBLIC_API_URL", "https://evil.test"),
        ("SENTRY_AUTH_TOKEN", "secret"),
    ],
)
def test_remote_environment_cannot_change_native_flags_or_export_inputs(key, value):
    m = load()
    data = {
        "data": {
            "app": {
                "byId": {
                    "id": m.PROJECT,
                    "environmentVariablesIncludingSensitive": [
                        {
                            "name": key,
                            "value": value,
                            "type": "STRING",
                            "visibility": "PUBLIC",
                        }
                    ],
                    "ownerAccount": {"environmentVariablesIncludingSensitive": []},
                }
            }
        }
    }
    with pytest.raises(m.PublishError):
        m.validate_environment(data)


def test_fixed_remote_environment_is_allowed_but_never_merged_into_process():
    m = load()
    data = {
        "data": {
            "app": {
                "byId": {
                    "id": m.PROJECT,
                    "environmentVariablesIncludingSensitive": [
                        {
                            "name": "APP_VARIANT",
                            "value": "production",
                            "type": "STRING",
                            "visibility": "PUBLIC",
                        }
                    ],
                    "ownerAccount": {"environmentVariablesIncludingSensitive": []},
                }
            }
        }
    }
    assert m.validate_environment(data) == {"APP_VARIANT": "production"}


@pytest.mark.parametrize(
    "mutation",
    [
        "multiple",
        "wrong_sha",
        "wrong_platform",
        "wrong_runtime",
        "wrong_branch",
        "rollback",
        "group",
    ],
)
def test_update_receipt_must_match_exact_publication(mutation):
    m = load()
    u = update(m)
    if mutation == "multiple":
        u *= 2
    elif mutation == "wrong_sha":
        u[0]["gitCommitHash"] = "b" * 40
    elif mutation == "wrong_platform":
        u[0]["platform"] = "android"
    elif mutation == "wrong_runtime":
        u[0]["runtimeVersion"] = "wrong"
    elif mutation == "wrong_branch":
        u[0]["branch"] = "wrong"
    elif mutation == "rollback":
        u[0]["isRollBackToEmbedded"] = True
    elif mutation == "group":
        u[0]["group"] = "latest"
    with pytest.raises(m.PublishError):
        m.validate_update(u, "c" * 40)


class Fake:
    def __init__(self, m, tmp_path):
        self.m = m
        self.root = tmp_path
        self.events = []
        self.vendor_calls = 0
        self.proof = {"launch": "a" * 43, "assets": []}
        self.channel_calls = 0
        self.fail = None

    def gate(self):
        self.events.append("gate")

    def validate_source(self):
        self.events.append("source")

    def eas(self, args, tag):
        self.events.append(tag)
        if tag == "baseline":
            return build(self.m)
        if tag == "cohort":
            return [build(self.m)]
        if tag.startswith("channel"):
            self.channel_calls += 1
            c = channel(self.m)
            if self.fail == "channel" and self.channel_calls > 1:
                c["currentPage"]["id"] = "99999999-9999-4999-8999-999999999999"
            return c
        if tag == "publish":
            self.vendor_calls += 1
            if self.fail == "vendor":
                raise self.m.PublishError("unknown vendor outcome")
            return update(self.m)
        if tag == "readback":
            u = update(self.m)
            if self.fail == "readback":
                u[0]["id"] = "55555555-5555-4555-8555-555555555555"
            return u
        raise AssertionError(tag)

    def environment(self):
        self.events.append("environment")
        return {}

    def export(self):
        self.events.append("export")

    def artifact(self):
        return copy.deepcopy(self.proof)

    def write(self, name, data):
        self.events.append("write:" + name)

    def rpc(self, name, payload):
        self.events.append(name)
        if self.fail == name:
            raise self.m.PublishError("RPC unknown")
        return {
            "sha": "c" * 40,
            "state": "CLAIMED" if name == "claim-ota" else "SUCCEEDED",
        }


def test_claim_precedes_single_publish_and_exact_readback_precedes_finish(tmp_path):
    m = load()
    f = Fake(m, tmp_path)
    result = m.publish(f, "c" * 40)
    assert result["state"] == "SUCCEEDED" and f.vendor_calls == 1
    assert (
        f.events.index("claim-ota")
        < f.events.index("publish")
        < f.events.index("readback")
        < f.events.index("finish-ota")
    )
    assert "write:ota-claim.json" in f.events and "write:ota-receipt.json" in f.events


@pytest.mark.parametrize(
    "failure", ["claim-ota", "vendor", "readback", "channel", "finish-ota"]
)
def test_unknown_publication_never_retries_or_forges_success(tmp_path, failure):
    m = load()
    f = Fake(m, tmp_path)
    f.fail = failure
    with pytest.raises(m.PublishError):
        m.publish(f, "c" * 40)
    assert f.vendor_calls <= 1
    assert "write:ota-receipt.json" not in f.events
    if failure in ("claim-ota", "channel"):
        assert f.vendor_calls == 0


def test_child_environment_discards_startup_hooks_and_export_hides_token(monkeypatch):
    m = load()
    monkeypatch.setenv("NODE_OPTIONS", "--require malicious")
    monkeypatch.setenv("PYTHONPATH", "/tmp/evil")
    monkeypatch.setenv("BASH_ENV", "/tmp/evil")
    env = m.environment("token")
    assert env["EXPO_TOKEN"] == "token"
    assert not {"NODE_OPTIONS", "PYTHONPATH", "BASH_ENV"} & set(env)
    assert "EXPO_TOKEN" not in m.environment(None)


def test_real_adapter_subprocess_is_fixed_and_retains_vendor_logs(
    tmp_path, monkeypatch
):
    m = load()
    monkeypatch.setattr(m, "ROOT", tmp_path)
    monkeypatch.setattr(m, "SOURCE", tmp_path / "source")
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        kwargs["stdout"].write(json.dumps(update(m)).encode())
        kwargs["stderr"].write(b"vendor log retained privately")
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(m.subprocess, "run", fake_run)
    adapter = m.Adapter("c" * 40, None, "secret-token")
    result = adapter.eas(["update", "--channel", "production"], "publish")
    assert result == update(m)
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[:2] == [str(m.NODE), str(m.EAS)]
    assert kwargs["env"]["EXPO_TOKEN"] == "secret-token"
    assert kwargs["cwd"] == tmp_path / "source/mobile"
    assert kwargs["check"] is False
    assert (
        tmp_path / "publish.stderr"
    ).read_bytes() == b"vendor log retained privately"
    assert (tmp_path / "publish.stdout").stat().st_mode & 0o777 == 0o600
    with pytest.raises(m.PublishError):
        adapter.eas(["update", "--channel", "production"], "publish")
    assert len(calls) == 1


@pytest.mark.parametrize("failure", ["exit", "timeout"])
def test_real_adapter_never_retries_failed_vendor_process(
    tmp_path, monkeypatch, failure
):
    m = load()
    monkeypatch.setattr(m, "ROOT", tmp_path)
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        kwargs["stdout"].write(b"partial potentially accepted receipt")
        kwargs["stderr"].write(b"secret-bearing vendor diagnostic")
        if failure == "timeout":
            raise m.subprocess.TimeoutExpired(args, 1)
        return type("Result", (), {"returncode": 1})()

    monkeypatch.setattr(m.subprocess, "run", fake_run)
    adapter = m.Adapter("c" * 40, None, "secret-token")
    with pytest.raises(m.PublishError) as error:
        adapter.eas(["update"], "publish")
    assert "secret" not in str(error.value)
    assert len(calls) == 1
    assert (
        tmp_path / "publish.stdout"
    ).read_bytes() == b"partial potentially accepted receipt"
    assert (tmp_path / "publish.stderr").stat().st_mode & 0o777 == 0o600


def test_fixed_rpc_never_receives_expo_token_or_caller_ssh_configuration(monkeypatch):
    m = load()
    adapter = m.Adapter("c" * 40, None, "secret-token")
    calls = []

    def run(args, tag, **kwargs):
        calls.append((args, tag, kwargs))
        return json.dumps({"sha": "c" * 40, "state": "CLAIMED"}).encode()

    monkeypatch.setattr(adapter, "run", run)
    assert adapter.rpc("claim-ota", {"sha": "c" * 40})["state"] == "CLAIMED"
    args, tag, kwargs = calls[0]
    assert args[:3] == ["/usr/bin/ssh", "-F", "/dev/null"]
    assert "IdentityAgent=none" in args and "ClearAllForwardings=yes" in args
    assert args[-2:] == ["root@39.98.206.178", "claim-ota " + "c" * 40]
    assert kwargs.get("with_token", False) is False
    assert json.loads(kwargs["data"]) == {"sha": "c" * 40}


def test_export_process_never_receives_vendor_credential(monkeypatch):
    m = load()
    adapter = m.Adapter("c" * 40, None, "secret-token")
    calls = []
    monkeypatch.setattr(m.os.path, "lexists", lambda p: False)
    monkeypatch.setattr(
        adapter, "run", lambda args, tag, **kw: calls.append((args, tag, kw))
    )
    adapter.export()
    assert len(calls) == 1 and calls[0][0][:2] == [str(m.NODE), str(m.EXPO)]
    assert calls[0][2].get("with_token", False) is False


def test_cohort_uses_two_bounded_pages_and_rejects_full_second_page(tmp_path):
    m = load()
    f = Fake(m, tmp_path)
    original = f.eas
    seen = []
    first = [build(m)] + [
        build(m, identifier=f"{i:08x}-1111-4111-8111-111111111111")
        for i in range(1, 50)
    ]
    last = [build(m, identifier="99999999-9999-4999-8999-999999999999")]

    def eas(args, tag):
        seen.append((tag, args))
        if tag == "cohort":
            return first
        if tag == "cohort-next":
            return last
        return original(args, tag)

    f.eas = eas
    assert m.publish(f, "c" * 40)["state"] == "SUCCEEDED"
    args = next(args for tag, args in seen if tag == "cohort-next")
    assert (
        args[args.index("--limit") + 1] == "50"
        and args[args.index("--offset") + 1] == "50"
    )
    f2 = Fake(m, tmp_path)
    original2 = f2.eas
    f2.eas = lambda args, tag: (
        first if tag in ("cohort", "cohort-next") else original2(args, tag)
    )
    with pytest.raises(m.PublishError):
        m.publish(f2, "c" * 40)
    assert f2.vendor_calls == 0


def test_preclaim_payload_binds_validated_production_branch_and_artifact(tmp_path):
    m = load()
    f = Fake(m, tmp_path)
    claims = []
    original = f.rpc

    def rpc(name, value):
        if name == "claim-ota":
            claims.append(value)
        return original(name, value)

    f.rpc = rpc
    m.publish(f, "c" * 40)
    assert len(claims) == 1
    assert claims[0]["branch_id"] == m.validate_channel(channel(m))["branch_id"]
    assert claims[0]["branch_name"] == "production"
    assert claims[0]["artifact"] == f.proof


def test_preflight_needs_no_credentials_or_publication_calls(monkeypatch, capsys):
    from types import SimpleNamespace
    m = load()
    calls = []
    contract = SimpleNamespace(validate_source=lambda root, sha: calls.append(('source', root, sha)))
    def context(sha, *, require_credentials=True):
        calls.append(('context', sha, require_credentials))
        assert require_credentials is False
        return contract
    monkeypatch.setattr(m, 'context', context)
    monkeypatch.setattr(m, 'publish', lambda *a: pytest.fail('preflight must never publish'))
    monkeypatch.setattr(m, 'Adapter', lambda *a: pytest.fail('preflight must never construct credential adapter'))
    monkeypatch.delenv('EXPO_TOKEN', raising=False)
    monkeypatch.setattr(m.sys, 'argv', ['publisher', '--sha', 'c'*40, '--preflight'])
    assert m.cli() == 0
    assert calls == [('context', 'c'*40, False), ('source', m.SOURCE, 'c'*40)]
    assert json.loads(capsys.readouterr().out) == {'state':'PREFLIGHT_PASSED','phase':'native_source','reason':'context_and_source_verified'}


@pytest.mark.parametrize('phase, error, reason', [
    ('context', 'root-owned publisher path required', 'publisher_path_untrusted'),
    ('context', 'secret vendor credential payload', 'publisher_context_unavailable'),
    ('source', 'native or unknown mobile input changed', 'native_source_incompatible'),
    ('source', 'dirty runtime source', 'runtime_source_dirty'),
    ('source', 'secret vendor credential payload', 'native_source_unavailable'),
])
def test_preflight_emits_only_static_diagnostics(monkeypatch, capsys, phase, error, reason):
    from types import SimpleNamespace
    m = load()
    def fail():
        raise (m.PublishError(error) if phase == 'context' else ValueError(error))
    contract = SimpleNamespace(validate_source=lambda *a: fail())
    monkeypatch.setattr(m, 'context', lambda *a, **k: fail() if phase == 'context' else contract)
    monkeypatch.setattr(m.sys, 'argv', ['publisher', '--sha', 'c'*40, '--preflight'])
    assert m.cli() == 1
    captured = capsys.readouterr()
    assert 'secret' not in captured.err + captured.out
    assert json.loads(captured.err) == {'state':'BLOCKED','phase':'publisher_context' if phase=='context' else 'native_source','reason':reason}


def test_publish_runs_preflight_before_credentials_and_retains_full_context(monkeypatch):
    from types import SimpleNamespace
    m = load()
    calls=[]
    contract=SimpleNamespace(validate_source=lambda *a:calls.append('source'))
    def context(sha, *, require_credentials=True):
        calls.append('private-context' if require_credentials else 'public-context')
        if require_credentials:
            raise m.PublishError('private publisher file requires mode 0600')
        return contract
    monkeypatch.setattr(m,'context',context)
    monkeypatch.setattr(m,'publish',lambda *a:pytest.fail('private checks must not be bypassed'))
    monkeypatch.setattr(m.sys,'argv',['publisher','--sha','c'*40])
    assert m.cli() == 1
    assert calls == ['public-context','source','private-context']


def test_preflight_uses_real_native_contract_and_still_blocks_changed_package(monkeypatch, capsys):
    m = load()
    spec = importlib.util.spec_from_file_location('ota_preflight_native_test', Path(__file__).with_name('trusted_ota.py'))
    contract = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(contract)
    calls=[]
    def git(root, *args):
        calls.append(args)
        if args == ('rev-parse', 'HEAD'):
            return ('c'*40+'\n').encode()
        if args[0] == 'status' or args[0] == 'merge-base':
            return b''
        if args[0] == 'diff':
            return b'mobile/package.json\n'
        pytest.fail('native incompatibility must fail before any later read')
    monkeypatch.setattr(contract, 'git', git)
    monkeypatch.setattr(m, 'context', lambda *a, **k: contract)
    monkeypatch.setattr(m, 'Adapter', lambda *a: pytest.fail('native incompatibility must not reach vendor adapter'))
    monkeypatch.setattr(m.sys,'argv',['publisher','--sha','c'*40,'--preflight'])
    assert m.cli() == 1
    assert json.loads(capsys.readouterr().err)['reason'] == 'native_source_incompatible'
    assert ('merge-base', '--is-ancestor', m.NATIVE_SHA, 'c'*40) in calls
    assert contract.NATIVE_SHA == m.NATIVE_SHA == 'cad1fd1d33621532e587b265e79f737dfb06d1fe'


def test_preflight_failure_blocks_publish_before_credential_lookup(monkeypatch):
    m = load()
    calls=[]
    def fail(sha, *, require_credentials=True):
        calls.append(require_credentials)
        raise m.PublishError('publisher code differs from reviewed commit')
    monkeypatch.setattr(m,'context',fail)
    original_get = m.os.environ.get
    def get(key, *args):
        if key == 'EXPO_TOKEN':
            pytest.fail('credentials read before preflight passed')
        return original_get(key, *args)
    monkeypatch.setattr(m.os.environ, 'get', get)
    monkeypatch.setattr(m.sys,'argv',['publisher','--sha','c'*40])
    assert m.cli() == 1
    assert calls == [False]


def runner_context_fixture(tmp_path, monkeypatch):
    """Actual context/secure/source code over a synthetic sealed hosted layout."""
    from types import SimpleNamespace
    m=load()
    root=tmp_path/'runner'
    source=root/'source'
    scripts=Path(__file__).parent
    contents={
        source/'scripts'/name:(scripts/name).read_bytes()
        for name in ('trusted_ota_publish.py','trusted_ota.py','trusted_release_gate.py')
    }
    contents.update({
        source/'.git/config':b'[core]\n',
        source/'mobile/app.json':json.dumps({'expo':{'version':m.RUNTIME,'runtimeVersion':{'policy':'appVersion'},'extra':{'eas':{'projectId':m.PROJECT}}}}).encode(),
        root/'node/bin/node':b'fixed node',
        source/'scripts/release-tools/node_modules/eas-cli/bin/run':b'fixed eas',
        source/'mobile/node_modules/expo/bin/cli':b'fixed expo',
        source/'scripts/release-tools/package-lock.json':json.dumps({'packages':{'node_modules/eas-cli':{'version':'23.2.0'}}}).encode(),
        source/'scripts/release-tools/node_modules/eas-cli/package.json':b'{"version":"23.2.0"}',
    })
    for path,data in contents.items():
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(data)
    for key,value in {'ROOT':root,'SOURCE':source,'NODE':root/'node/bin/node','EAS':source/'scripts/release-tools/node_modules/eas-cli/bin/run','EXPO':source/'mobile/node_modules/expo/bin/cli','__file__':str(source/'scripts/trusted_ota_publish.py')}.items():
        monkeypatch.setattr(m,key,value)
    monkeypatch.setattr(m,'sys',SimpleNamespace(platform='linux',executable='/usr/bin/python3',flags=SimpleNamespace(isolated=1,no_site=1,dont_write_bytecode=1)))
    monkeypatch.setattr(m.os,'geteuid',lambda:0)
    original_lstat=Path.lstat
    faults={}
    def lstat(path):
        info=original_lstat(path)
        values={'st_uid':0,'st_mode':info.st_mode & ~0o022,'st_nlink':info.st_nlink}
        values.update(faults.get(path,{}))
        return SimpleNamespace(**values)
    monkeypatch.setattr(Path,'lstat',lstat)
    calls=[]
    def run(args,**kwargs):
        calls.append(args)
        assert args[0]=='/usr/bin/git', 'preflight must never invoke vendor or SSH'
        assert kwargs['env'].get('EXPO_TOKEN') is None
        if 'show' in args:
            ref=args[-1]
            if ':scripts/' in ref:
                output=contents[source/'scripts'/ref.split(':scripts/',1)[1]]
            else:
                assert ref=='c'*40+':mobile/app.json'
                output=json.dumps({'expo':{'version':m.RUNTIME,'runtimeVersion':m.RUNTIME,'extra':{'eas':{'projectId':m.PROJECT}}}}).encode()
        elif 'rev-parse' in args:
            output=('c'*40+'\n').encode()
        else:
            assert 'status' in args or 'merge-base' in args or 'diff' in args
            output=b''
        return SimpleNamespace(stdout=output)
    monkeypatch.setattr(m.subprocess,'run',run)
    monkeypatch.setattr(m.urllib.request,'urlopen',lambda *a,**k:pytest.fail('preflight must not use network'))
    original_get=m.os.environ.get
    def get(key,*args):
        if key=='EXPO_TOKEN':pytest.fail('preflight must not read provider credential')
        return original_get(key,*args)
    monkeypatch.setattr(m.os.environ,'get',get)
    # Importlib must not leave bytecode in the synthetic checkout either.
    import sys
    monkeypatch.setattr(sys,'dont_write_bytecode',True)
    return m,faults,calls


def test_real_context_preflight_works_without_key_or_token_but_publish_context_requires_key(tmp_path,monkeypatch):
    m,faults,calls=runner_context_fixture(tmp_path,monkeypatch)
    assert not (m.ROOT/'key').exists()
    m.preflight('c'*40)
    assert any('merge-base' in args for args in calls)
    with pytest.raises(FileNotFoundError):
        m.context('c'*40)
    for name in ('key','known_hosts'):
        path=m.ROOT/name
        path.write_text('synthetic fixture only')
        path.chmod(0o600)
    m.context('c'*40)
    (m.ROOT/'key').chmod(0o644)
    with pytest.raises(m.PublishError,match='mode 0600'):
        m.context('c'*40)


@pytest.mark.parametrize('fault',['platform','uid','interpreter','isolated','site','bytecode','canonical','file_uid','file_writable','parent_writable','file_symlink','file_hardlink','cache','commondir','code_bytes'])
def test_real_context_preflight_rejects_unsafe_runner(tmp_path,monkeypatch,fault):
    import stat
    m,faults,calls=runner_context_fixture(tmp_path,monkeypatch)
    script=m.SOURCE/'scripts/trusted_ota_publish.py'
    if fault=='platform':m.sys.platform='darwin'
    elif fault=='uid':monkeypatch.setattr(m.os,'geteuid',lambda:1001)
    elif fault=='interpreter':m.sys.executable='/untrusted/python'
    elif fault=='isolated':m.sys.flags.isolated=0
    elif fault=='site':m.sys.flags.no_site=0
    elif fault=='bytecode':m.sys.flags.dont_write_bytecode=0
    elif fault=='canonical':m.__file__='/tmp/copied-publisher.py'
    elif fault=='file_uid':faults[script]={'st_uid':1001}
    elif fault=='file_writable':faults[script]={'st_mode':stat.S_IFREG|0o666}
    elif fault=='parent_writable':faults[m.ROOT]={'st_mode':stat.S_IFDIR|0o777}
    elif fault=='file_symlink':faults[script]={'st_mode':stat.S_IFLNK|0o777}
    elif fault=='file_hardlink':faults[script]={'st_nlink':2}
    elif fault=='cache':(m.SOURCE/'scripts/__pycache__').mkdir()
    elif fault=='commondir':(m.SOURCE/'.git/commondir').write_text('/untrusted')
    elif fault=='code_bytes':script.write_text('different code')
    with pytest.raises(m.PreflightError) as caught:
        m.preflight('c'*40)
    assert caught.value.phase=='publisher_context'
    assert caught.value.reason in {*m._CONTEXT_REASONS.values(),'publisher_context_unavailable'}
