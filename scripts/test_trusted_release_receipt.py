import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("trusted_release_receipt.py")
SHA = "a" * 40


@pytest.mark.parametrize("body", [
    "", "not-json", '{"sha":"' + SHA + '","state":"SUCCEEDED","state":"CLAIMED"}',
    json.dumps({"sha": "b" * 40, "state": "SUCCEEDED"}),
    json.dumps({"sha": SHA, "state": "STARTED"}),
    json.dumps({"sha": SHA, "state": "SUCCEEDED", "untrusted": "payload"}),
])
def test_untrusted_or_wrong_identity_receipt_is_rejected(body):
    result = subprocess.run([sys.executable, "-I", str(SCRIPT), "--sha", SHA, "--state", "SUCCEEDED"],
                            input=body, text=True, capture_output=True, check=False)
    assert result.returncode != 0
    assert result.stdout == ""


@pytest.mark.parametrize("state", ["SUCCEEDED", "CLAIMED", "CHECKED"])
def test_exact_server_identity_receipt_is_accepted(state):
    result = subprocess.run([sys.executable, "-I", str(SCRIPT), "--sha", SHA, "--state", state],
                            input=json.dumps({"sha": SHA, "state": state}), text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"sha": SHA, "state": state}
