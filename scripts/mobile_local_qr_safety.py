"""Fail-closed, macOS ad-hoc IPA checks and explicit public-file assembly.

No credential creation, Apple login, profile installation, or network publication.
Invoke from the reviewed local QR entrypoint, never on an unreviewed worktree.
"""

import argparse
import datetime as dt
import hashlib
import html
import json
import plistlib
import re
import shutil
import stat
import subprocess
import tempfile
import urllib.parse
import zipfile
from pathlib import Path, PurePosixPath

TEAM = "QA2U724DAN"
BUNDLE = "life.executor.health"
UPDATES_URL = "https://u.expo.dev/911ea84f-bc7e-4a12-90cf-33966b6f7398"
PUBLIC_ROOT = "https://health.executor.life/mobile-install/ios"


class UnsafeIPA(ValueError):
    """An unsupported or unverifiable artifact must not be published."""


def require(condition, reason):
    if not condition:
        raise UnsafeIPA(reason)


def validate_publish_id(value):
    require(
        bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}", value))
        and value != "latest",
        "invalid build ID",
    )


def extract_ipa(ipa, destination):
    with zipfile.ZipFile(ipa) as archive:
        files = archive.infolist()
        require(
            len(files) <= 100000 and sum(f.file_size for f in files) <= 2 * 1024**3,
            "IPA exceeds extraction budget",
        )
        seen = set()
        for entry in files:
            name = PurePosixPath(entry.filename)
            require(
                not name.is_absolute()
                and ".." not in name.parts
                and "\\" not in entry.filename,
                "unsafe IPA path",
            )
            canonical = str(name).casefold()
            require(canonical not in seen, "duplicate IPA member")
            seen.add(canonical)
            require(
                not stat.S_ISLNK(entry.external_attr >> 16),
                "IPA symlink is unsupported",
            )
        archive.extractall(destination)


def verify_app(app, *, version, channel, runner=subprocess.run, now=None):
    require(
        channel in {"production", "rokid-production"}, "not a production update channel"
    )
    require(
        not list(app.rglob("*.appex")) and not list(app.rglob("*.app")),
        "nested application requires separate release review",
    )
    info = plistlib.loads((app / "Info.plist").read_bytes())
    expo = plistlib.loads((app / "Expo.plist").read_bytes())
    require(info.get("CFBundleIdentifier") == BUNDLE, "bundle mismatch")
    require(info.get("CFBundleShortVersionString") == version, "version mismatch")
    build = info.get("CFBundleVersion", "")
    require(
        isinstance(build, str)
        and bool(re.fullmatch(r"[0-9]+(?:\.[0-9]+){0,2}", build)),
        "invalid build number",
    )
    require(expo.get("EXUpdatesRuntimeVersion") == version, "runtime mismatch")
    require(
        expo.get("EXUpdatesRequestHeaders", {}).get("expo-channel-name") == channel,
        "update channel mismatch",
    )
    require(expo.get("EXUpdatesURL") == UPDATES_URL, "update project mismatch")
    require(expo.get("EXUpdatesEnabled", True) is True, "updates disabled")
    requirement = f'=anchor apple generic and certificate leaf[subject.OU] = "{TEAM}" and identifier "{BUNDLE}"'
    runner(
        [
            "/usr/bin/codesign",
            "--verify",
            "--deep",
            "--strict",
            "--test-requirement",
            requirement,
            str(app),
        ],
        check=True,
        capture_output=True,
    )
    ent = plistlib.loads(
        runner(
            ["/usr/bin/codesign", "-d", "--entitlements", ":-", str(app)],
            check=True,
            capture_output=True,
        ).stdout
    )
    profile = plistlib.loads(
        runner(
            [
                "/usr/bin/security",
                "cms",
                "-D",
                "-i",
                str(app / "embedded.mobileprovision"),
            ],
            check=True,
            capture_output=True,
        ).stdout
    )
    expected = {
        "application-identifier": f"{TEAM}.{BUNDLE}",
        "com.apple.developer.team-identifier": TEAM,
        "get-task-allow": False,
        "aps-environment": "production",
        "com.apple.developer.healthkit": True,
    }
    for name, value in expected.items():
        require(
            name in ent and ent[name] == value,
            f"application entitlement mismatch: {name}",
        )
        require(
            name in profile.get("Entitlements", {})
            and profile["Entitlements"][name] == value,
            f"profile entitlement mismatch: {name}",
        )
    require(profile.get("TeamIdentifier") == [TEAM], "profile team mismatch")
    expiration = profile.get("ExpirationDate")
    require(isinstance(expiration, dt.datetime), "profile expiration missing")
    current = now or dt.datetime.now(dt.timezone.utc)
    require(expiration.replace(tzinfo=dt.timezone.utc) > current, "profile expired")
    devices = profile.get("ProvisionedDevices")
    require(
        isinstance(devices, list)
        and len(devices) > 0
        and all(isinstance(x, str) and x for x in devices),
        "not an ad-hoc profile",
    )
    require(
        not profile.get("ProvisionsAllDevices"), "enterprise distribution unsupported"
    )
    with tempfile.TemporaryDirectory(prefix="reva-ipa-certificate-") as directory:
        prefix = str(Path(directory) / "certificate")
        runner(
            ["/usr/bin/codesign", "-d", "--extract-certificates", prefix, str(app)],
            check=True,
            capture_output=True,
        )
        require(
            Path(prefix + "0").read_bytes() in profile.get("DeveloperCertificates", []),
            "profile does not authorize signing certificate",
        )
    return {
        "bundle": BUNDLE,
        "version": version,
        "build": build,
        "title": info.get("CFBundleDisplayName", "小巴健康"),
        "runtime": version,
        "channel": channel,
        "device_count": len(devices),
    }


def digest(path):
    checksum = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def check_receipt(ipa, receipt, sha):
    require(
        Path(receipt).is_file() and not Path(receipt).is_symlink(),
        "existing IPA needs its original release receipt",
    )
    data = json.loads(Path(receipt).read_text())
    require(
        data.get("source_sha") == sha and data.get("ipa_sha256") == digest(ipa),
        "IPA provenance mismatch",
    )


def write_receipt(ipa, receipt, sha, metadata):
    require(bool(re.fullmatch(r"[a-f0-9]{40}", sha)), "invalid source SHA")
    with Path(receipt).open("x") as handle:
        json.dump(
            {"source_sha": sha, "ipa_sha256": digest(ipa), "metadata": metadata},
            handle,
            sort_keys=True,
        )


def assemble_public(ipa, output, *, build_id, metadata):
    validate_publish_id(build_id)
    require(
        Path(ipa).is_file() and not Path(ipa).is_symlink(), "IPA must be a regular file"
    )
    output.mkdir(mode=0o755)
    shutil.copyfile(ipa, output / "app.ipa")
    base = f"{PUBLIC_ROOT}/{build_id}"
    manifest_url = f"{base}/manifest.plist"
    install_url = "itms-services://?action=download-manifest&url=" + urllib.parse.quote(
        manifest_url, safe=""
    )
    manifest = {
        "items": [
            {
                "assets": [{"kind": "software-package", "url": f"{base}/app.ipa"}],
                "metadata": {
                    "bundle-identifier": metadata["bundle"],
                    "bundle-version": metadata["build"],
                    "kind": "software",
                    "title": metadata["title"],
                },
            }
        ]
    }
    (output / "manifest.plist").write_bytes(plistlib.dumps(manifest))
    title = html.escape(metadata["title"])
    (output / "install.html").write_text(
        f'<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title><body><h1>{title}</h1><p>{html.escape(metadata["version"])} ({html.escape(metadata["build"])})</p><img src="qr.png" alt="安装二维码"><p><a href="{html.escape(install_url)}">在 iPhone 上安装</a></p><p>仅适用于此分发描述文件已注册的设备。</p></body></html>',
        encoding="utf-8",
    )
    (output / "install-url.txt").write_text(install_url + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["validate-config", "verify-ios-ipa"])
    parser.add_argument("--build-id", required=True)
    parser.add_argument("--server", default="health")
    parser.add_argument("--ipa", type=Path)
    parser.add_argument("--version")
    parser.add_argument("--channel")
    parser.add_argument("--sha")
    parser.add_argument("--require-receipt", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--public-dir", type=Path)
    args = parser.parse_args()
    validate_publish_id(args.build_id)
    require(
        bool(
            re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9_.-]*(?:@[A-Za-z0-9][A-Za-z0-9_.-]*)?",
                args.server,
            )
        ),
        "invalid SSH destination",
    )
    if args.command == "validate-config":
        return
    require(
        args.ipa is not None and args.ipa.is_file() and not args.ipa.is_symlink(),
        "IPA missing",
    )
    if args.require_receipt:
        check_receipt(args.ipa, args.require_receipt, args.sha)
    with tempfile.TemporaryDirectory(prefix="reva-ipa-verify-") as temporary:
        directory = Path(temporary)
        extract_ipa(args.ipa, directory)
        apps = list((directory / "Payload").glob("*.app"))
        require(len(apps) == 1, "expected one application")
        metadata = verify_app(apps[0], version=args.version, channel=args.channel)
    write_receipt(args.ipa, args.receipt, args.sha, metadata)
    assemble_public(
        args.ipa, args.public_dir, build_id=args.build_id, metadata=metadata
    )
    print(json.dumps(metadata, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (
        UnsafeIPA,
        OSError,
        ValueError,
        subprocess.CalledProcessError,
        zipfile.BadZipFile,
    ):
        raise SystemExit(
            "Local QR safety validation failed; no artifact may be published."
        )
