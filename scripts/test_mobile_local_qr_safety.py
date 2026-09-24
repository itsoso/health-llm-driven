import copy
import datetime as dt
import importlib.util
import json
import plistlib
import subprocess
import zipfile
from pathlib import Path

import pytest


@pytest.fixture
def guard():
    spec = importlib.util.spec_from_file_location(
        "mobile_local_qr_safety", Path(__file__).with_name("mobile_local_qr_safety.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def package(tmp_path):
    app = tmp_path / "Payload" / "app.app"
    app.mkdir(parents=True)
    info = {
        "CFBundleIdentifier": "life.executor.health",
        "CFBundleShortVersionString": "1.3.4",
        "CFBundleVersion": "272",
        "CFBundleDisplayName": "小巴健康",
    }
    expo = {
        "EXUpdatesRuntimeVersion": "1.3.4",
        "EXUpdatesRequestHeaders": {"expo-channel-name": "production"},
        "EXUpdatesURL": "https://u.expo.dev/911ea84f-bc7e-4a12-90cf-33966b6f7398",
    }
    ent = {
        "application-identifier": "QA2U724DAN.life.executor.health",
        "com.apple.developer.team-identifier": "QA2U724DAN",
        "get-task-allow": False,
        "aps-environment": "production",
        "com.apple.developer.healthkit": True,
    }
    profile = {
        "TeamIdentifier": ["QA2U724DAN"],
        "ExpirationDate": dt.datetime(2030, 1, 1, tzinfo=dt.timezone.utc).replace(
            tzinfo=None
        ),
        "ProvisionedDevices": ["not-a-real-device"],
        "DeveloperCertificates": [b"test-certificate"],
        "Entitlements": copy.deepcopy(ent),
    }
    for name, data in [("Info.plist", info), ("Expo.plist", expo)]:
        (app / name).write_bytes(plistlib.dumps(data))
    (app / "embedded.mobileprovision").write_bytes(b"synthetic-profile")
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        output = b""
        if args[:2] == ["/usr/bin/security", "cms"]:
            output = plistlib.dumps(profile)
        elif "--entitlements" in args:
            output = plistlib.dumps(ent)
        elif "--extract-certificates" in args:
            prefix = args[args.index("--extract-certificates") + 1]
            Path(prefix + "0").write_bytes(b"test-certificate")
        return subprocess.CompletedProcess(args, 0, stdout=output, stderr=b"")

    return app, info, expo, ent, profile, run, calls


def verify(guard, package):
    app, _, _, _, _, run, _ = package
    return guard.verify_app(app, version="1.3.4", channel="production", runner=run)


def test_valid_adhoc_requires_apple_anchor_and_reports_no_devices(guard, package):
    result = verify(guard, package)
    assert result["version"] == "1.3.4"
    assert result["device_count"] == 1
    assert "not-a-real-device" not in json.dumps(result)
    calls = package[-1]
    assert any(
        "--verify" in c
        and "--deep" in c
        and "--strict" in c
        and any("anchor apple generic" in x for x in c)
        for c in calls
    )
    requirement_call = next(c for c in calls if "--test-requirement" in c)
    assert requirement_call[
        requirement_call.index("--test-requirement") + 1
    ].startswith("=anchor ")


def test_nested_application_needs_its_own_signing_review(guard, package):
    (package[0] / "Plugins" / "extension.appex").mkdir(parents=True)
    with pytest.raises(guard.UnsafeIPA, match="nested application"):
        verify(guard, package)


@pytest.mark.parametrize(
    "which,key,value",
    [
        (3, "get-task-allow", True),
        (3, "aps-environment", "development"),
        (3, "com.apple.developer.healthkit", False),
        (3, "application-identifier", "OTHER.life.executor.health"),
        (
            4,
            "ExpirationDate",
            dt.datetime(2020, 1, 1, tzinfo=dt.timezone.utc).replace(tzinfo=None),
        ),
        (4, "ProvisionedDevices", []),
        (4, "ProvisionsAllDevices", True),
        (4, "DeveloperCertificates", [b"wrong-certificate"]),
    ],
)
def test_rejects_non_distribution_or_mismatched_profile(
    guard, package, which, key, value
):
    package[which][key] = value
    with pytest.raises(guard.UnsafeIPA):
        verify(guard, package)


@pytest.mark.parametrize(
    "filename,key,value",
    [
        ("Info.plist", "CFBundleIdentifier", "life.executor.health.preview"),
        ("Info.plist", "CFBundleShortVersionString", "1.3.3"),
        ("Info.plist", "CFBundleVersion", ""),
        ("Expo.plist", "EXUpdatesRuntimeVersion", "1.3.3"),
        ("Expo.plist", "EXUpdatesRequestHeaders", {"expo-channel-name": "preview"}),
        ("Expo.plist", "EXUpdatesURL", "https://attacker.invalid/updates"),
    ],
)
def test_rejects_wrong_bundle_version_runtime_channel(
    guard, package, filename, key, value
):
    path = package[0] / filename
    data = plistlib.loads(path.read_bytes())
    data[key] = value
    path.write_bytes(plistlib.dumps(data))
    with pytest.raises(guard.UnsafeIPA):
        verify(guard, package)


def test_signature_failure_is_not_hidden(guard, package):
    def reject(args, **kwargs):
        raise subprocess.CalledProcessError(1, args)

    modified = (*package[:5], reject, package[6])
    with pytest.raises((guard.UnsafeIPA, subprocess.CalledProcessError)):
        verify(guard, modified)


@pytest.mark.parametrize(
    "member", ["../outside", "/tmp/outside", "Payload/../../outside"]
)
def test_rejects_zip_traversal(guard, tmp_path, member):
    ipa = tmp_path / "bad.ipa"
    with zipfile.ZipFile(ipa, "w") as z:
        z.writestr(member, b"bad")
    with pytest.raises(guard.UnsafeIPA):
        guard.extract_ipa(ipa, tmp_path / "extract")


@pytest.mark.parametrize("kind", ["symlink", "case-collision"])
def test_rejects_ipa_symlinks_and_macos_case_collisions(guard, tmp_path, kind):
    ipa = tmp_path / "bad.ipa"
    with zipfile.ZipFile(ipa, "w") as z:
        if kind == "symlink":
            entry = zipfile.ZipInfo("Payload/app.app/linked")
            entry.create_system = 3
            entry.external_attr = 0o120777 << 16
            z.writestr(entry, "/private/unrelated")
        else:
            z.writestr("Payload/app.app/Info.plist", "one")
            z.writestr("Payload/app.app/info.plist", "two")
    with pytest.raises(guard.UnsafeIPA):
        guard.extract_ipa(ipa, tmp_path / "extract")


@pytest.mark.parametrize(
    "value", ["../other", "x';touch /tmp/pwn;#", "$(id)", "x/y", "", "latest"]
)
def test_rejects_unsafe_publish_id(guard, value):
    with pytest.raises(guard.UnsafeIPA):
        guard.validate_publish_id(value)


def test_public_assembly_never_copies_private_files(guard, tmp_path):
    private = tmp_path / "private"
    private.mkdir()
    ipa = private / "app.ipa"
    ipa.write_bytes(b"synthetic-ipa")
    (private / "xcodebuild.log").write_text("private")
    (private / ".env").write_text("private")
    (private / "archive").mkdir()
    output = tmp_path / "public"
    guard.assemble_public(
        ipa,
        output,
        build_id="20260924-safe",
        metadata={
            "bundle": "life.executor.health",
            "version": "1.3.4",
            "build": "272",
            "title": "小巴健康",
        },
    )
    assert {p.name for p in output.iterdir()} == {
        "app.ipa",
        "manifest.plist",
        "install.html",
        "install-url.txt",
    }


def test_existing_ipa_requires_exact_source_and_digest_receipt(guard, tmp_path):
    ipa = tmp_path / "app.ipa"
    ipa.write_bytes(b"synthetic")
    receipt = tmp_path / "receipt.json"
    with pytest.raises(guard.UnsafeIPA):
        guard.check_receipt(ipa, receipt, "a" * 40)
    guard.write_receipt(ipa, receipt, "a" * 40, {"version": "1.3.4"})
    guard.check_receipt(ipa, receipt, "a" * 40)
    with pytest.raises(guard.UnsafeIPA):
        guard.check_receipt(ipa, receipt, "b" * 40)
    ipa.write_bytes(b"changed")
    with pytest.raises(guard.UnsafeIPA):
        guard.check_receipt(ipa, receipt, "a" * 40)
