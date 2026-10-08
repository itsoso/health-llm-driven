"""Lossless provider projections; authoritative tool transcripts stay intact."""

import json
import re


# Match complete quoted strings (including escapes) or non-whitespace runs.
# Only use after JSON validation: an invalid/unclosed string must stay opaque.
# Group ordinary characters into runs to avoid a Python iteration per character.
_JSON_LEXEMES = re.compile(r'"[^"\\]*(?:\\.[^"\\]*)*"|[^ \t\r\n"]+')


def _reject_constant(value: str) -> None:
    raise ValueError(f"Non-JSON constant: {value}")


def compact_tool_json(messages: list[dict]) -> list[dict]:
    """Remove JSON whitespace outside strings, without reserializing numbers.

    Ordinary prose, user text, multimodal content and call arguments are not
    rewritten. Validation does not turn missing/invalid results into success.
    Duplicate keys, escaping, numeric precision and order remain byte-exact.
    """
    projected = []
    for message in messages:
        content = message.get("content")
        if (
            message.get("role") != "tool"
            or not isinstance(content, str)
            or not content.lstrip().startswith(("{", "["))
        ):
            projected.append(message)
            continue
        try:
            json.loads(
                content, parse_int=str, parse_float=str, parse_constant=_reject_constant
            )
        except (ValueError, RecursionError):
            # Opaque or malformed output must reach the existing error policy
            # unchanged, rather than being repaired by a transport optimization.
            projected.append(message)
            continue
        projected.append({**message, "content": "".join(_JSON_LEXEMES.findall(content))})
    return projected
