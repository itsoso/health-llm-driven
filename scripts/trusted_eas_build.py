"""Emit only an exact finished production iOS build ID; never vendor payloads."""

import argparse
import json
from pathlib import Path
import re
import sys

UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate field")
        result[key] = value
    return result


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--id")
    args = parser.parse_args()
    try:
        if not sys.flags.isolated or re.fullmatch(r"[0-9a-f]{40}", args.sha) is None:
            raise ValueError("invalid boundary")
        raw = sys.stdin.read(1000001)
        if len(raw) > 1000000:
            raise ValueError("oversized metadata")
        build = json.loads(raw, object_pairs_hook=unique)
        if isinstance(build, list) and len(build) == 1:
            build = build[0]
        expected = {"gitCommitHash": args.sha, "status": "FINISHED", "platform": "IOS",
                    "distribution": "STORE", "buildProfile": "production"}
        if not isinstance(build, dict) or any(build.get(key) != value for key, value in expected.items()):
            raise ValueError("wrong artifact")
        config = json.loads((Path(__file__).resolve().parents[1] / "mobile/app.json").read_text())["expo"]
        project = build.get("app")
        if (not isinstance(project, dict)
                or project.get("id") != config["extra"]["eas"]["projectId"]
                or build.get("appIdentifier") != config["ios"]["bundleIdentifier"]):
            raise ValueError("wrong project")
        build_id = build.get("id")
        if not isinstance(build_id, str) or re.fullmatch(UUID, build_id) is None:
            raise ValueError("invalid identity")
        if args.id is not None and args.id != build_id:
            raise ValueError("wrong identity")
    except (ValueError, TypeError, KeyError, OSError, RecursionError):
        print("Untrusted EAS build metadata; upload blocked", file=sys.stderr)
        return 1
    print(build_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
