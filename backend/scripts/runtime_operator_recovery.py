#!/usr/bin/env python3
"""Run through authenticated Linux root access. Review, then resume exact state."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['review', 'resume'])
    args = parser.parse_args()
    import os
    if sys.platform != 'linux' or os.geteuid() != 0:
        raise PermissionError('authenticated_server_root_required')
    from app.services.agent_runtime_operator import ServerRuntimeRecovery, require_server_operator
    require_server_operator()
    from app.database import SessionLocal
    with SessionLocal() as db:
        recovery = ServerRuntimeRecovery(db)
        if args.action == 'review':
            result = recovery.review()
        else:
            raw = sys.stdin.read(4097)
            if len(raw) > 4096:
                raise ValueError('operator_review_too_large')
            reviewed = json.loads(raw)
            transition = recovery.resume(reviewed)
            result = {'changed': transition.changed, 'status': transition.status, 'unknown_runs_preserved': True}
        print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # No SQL/connection string or health payload in command failure output.
        print(json.dumps({'status': 'failed', 'error_type': type(error).__name__}), file=sys.stderr)
        raise SystemExit(1)
