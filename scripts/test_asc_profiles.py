import importlib.util
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / ".claude/skills/mobile-testflight-release/scripts/asc_profiles.py"
)
SPEC = importlib.util.spec_from_file_location("asc_profiles", MODULE_PATH)
assert SPEC and SPEC.loader
asc_profiles = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(asc_profiles)


class _Response:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body


def test_empty_success_response_decodes_to_none() -> None:
    assert asc_profiles._decode_response(_Response(b"")) is None


def test_json_success_response_is_preserved() -> None:
    assert asc_profiles._decode_response(_Response(b'{"data": []}')) == {"data": []}
