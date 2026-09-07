"""Validate bounded server RPC output before a release job can be green."""

import argparse
import json
import re
import sys


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
    parser.add_argument("--state", required=True, choices=("SUCCEEDED", "CLAIMED"))
    args = parser.parse_args()
    try:
        if not sys.flags.isolated or re.fullmatch(r"[0-9a-f]{40}", args.sha) is None:
            raise ValueError("invalid execution boundary")
        raw = sys.stdin.read(4097)
        if len(raw) > 4096:
            raise ValueError("oversized receipt")
        receipt = json.loads(raw, object_pairs_hook=unique)
        if receipt != {"sha": args.sha, "state": args.state}:
            raise ValueError("wrong server receipt")
    except (ValueError, TypeError):
        print("Untrusted release receipt", file=sys.stderr)
        return 1
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
