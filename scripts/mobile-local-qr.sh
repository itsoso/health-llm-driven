#!/usr/bin/env bash
# Produce offline inspection evidence for an already-built iOS IPA.
#
# This compatibility name no longer describes an install path: an OTA install
# manifest requires independently hosted exact bytes over HTTPS. Hosting,
# install QR generation, signing, device install, and upload all belong to the
# repository-external release Gate.

# Sourcing is inert: the complete implementation is inside a direct-execution
# block, so a caller cannot override a terminating builtin and fall through.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
if [[ "$#" -eq 1 && ( "$1" == "-h" || "$1" == "--help" ) ]]; then
  builtin printf '%s\n' \
    'Usage: ./scripts/mobile-local-qr.sh --no-upload --ipa EXISTING' \
    'Creates offline IPA metadata and an inspection report only.' \
    'No install manifest, QR, signing, device install, or upload is performed.'
  exit 0
elif [[ "$#" -eq 3 && "$1" == "--no-upload" && "$2" == "--ipa" &&
        -n "$3" && "$3" != --* ]]; then
  set -euo pipefail

  /usr/bin/python3 - "${BASH_SOURCE[0]}" "$3" <<'PY'
from __future__ import annotations

import hashlib
import html
import json
import os
from pathlib import Path
import plistlib
import shutil
import sys
import zipfile


script_path = Path(sys.argv[1]).resolve(strict=True)
ipa_path = Path(sys.argv[2]).expanduser().resolve(strict=True)
if not ipa_path.is_file():
    raise SystemExit(f"IPA not found: {ipa_path}")

digest = hashlib.sha256()
size = 0
with ipa_path.open("rb") as handle:
    while chunk := handle.read(1024 * 1024):
        digest.update(chunk)
        size += len(chunk)
sha256 = digest.hexdigest()

try:
    with zipfile.ZipFile(ipa_path) as archive:
        candidates = [
            info
            for info in archive.infolist()
            if len(Path(info.filename).parts) == 3
            and Path(info.filename).parts[0] == "Payload"
            and Path(info.filename).parts[1].endswith(".app")
            and Path(info.filename).parts[2] == "Info.plist"
        ]
        if len(candidates) != 1:
            raise ValueError("expected exactly one root app Info.plist")
        info = candidates[0]
        if info.file_size > 2 * 1024 * 1024:
            raise ValueError("root app Info.plist exceeds the inspection limit")
        plist = plistlib.loads(archive.read(info))
except (OSError, ValueError, zipfile.BadZipFile, plistlib.InvalidFileException) as error:
    raise SystemExit(f"Invalid IPA: {error}") from error

bundle_id = plist.get("CFBundleIdentifier")
version = plist.get("CFBundleShortVersionString")
build = plist.get("CFBundleVersion")
if not all(isinstance(value, str) and value for value in (bundle_id, version, build)):
    raise SystemExit("Invalid IPA: required app identity fields are missing")

repo_root = script_path.parent.parent
output_dir = repo_root / "artifacts" / "ios-ipa-inspection" / sha256[:16]
output_dir.mkdir(parents=True, exist_ok=True)
output_ipa = output_dir / ipa_path.name
if not output_ipa.exists() or not output_ipa.samefile(ipa_path):
    temporary_ipa = output_dir / f".{ipa_path.name}.{os.getpid()}.tmp"
    shutil.copyfile(ipa_path, temporary_ipa)
    os.replace(temporary_ipa, output_ipa)

payload = {
    "schema_version": 1,
    "purpose": "offline_ipa_inspection",
    "installable": False,
    "ipa_file": output_ipa.name,
    "ipa_sha256": sha256,
    "ipa_size": size,
    "bundle_id": bundle_id,
    "version": version,
    "build": build,
}


def replace_text(path: Path, content: str) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("x", encoding="utf-8") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


replace_text(
    output_dir / "inspection.json",
    json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
)
replace_text(
    output_dir / "inspection.html",
    f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Offline IPA inspection</title></head>
<body>
  <main>
    <h1>Offline IPA inspection</h1>
    <p>This bundle is evidence only. It does not install or publish the app.</p>
    <dl>
      <dt>IPA</dt><dd>{html.escape(output_ipa.name)}</dd>
      <dt>SHA-256</dt><dd><code>{sha256}</code></dd>
      <dt>Size</dt><dd>{size} bytes</dd>
      <dt>Bundle ID</dt><dd>{html.escape(bundle_id)}</dd>
      <dt>Version</dt><dd>{html.escape(version)} ({html.escape(build)})</dd>
    </dl>
  </main>
</body>
</html>
""",
)

print(f"Offline inspection bundle: {output_dir}")
print(f"IPA: {output_ipa}")
print(f"SHA-256: {sha256}")
print(f"Metadata: {output_dir / 'inspection.json'}")
print(f"Report: {output_dir / 'inspection.html'}")
print("No install manifest, QR, device install, or upload was created.")
PY
else
  builtin printf '%s\n' \
    'Production QR/install publishing is frozen.' \
    'The only local mode is: --no-upload --ipa EXISTING' >&2
  exit 78
fi
fi
