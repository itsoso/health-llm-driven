# -*- coding: utf-8 -*-
"""Guarantee post-write SafetyGuardian notices survive model synthesis.

The agent loop appends "⚠️ 安全提示: <titles>" to a write tool result. When a
quality model writes the final reply it may paraphrase or drop that line; cards
still stream, but text-only clients would lose the warning. The executor uses
this helper to put any dropped notice back deterministically (tighten-only).
"""
from __future__ import annotations


def missing_post_write_safety_text(reply: str, notices: list[str]) -> str:
    """Post-write safety notices the final reply does not already carry.

    A notice counts as present only when every alert title in it appears in the
    reply; model paraphrase that drops a title gets the deterministic line back.
    """
    missing = []
    for notice in dict.fromkeys(notices or []):
        body = notice.split(":", 1)[-1].strip()
        titles = [t.strip() for t in body.split(";") if t.strip()] or [body]
        if not all(title in (reply or "") for title in titles):
            missing.append(notice)
    return "\n".join(missing)
