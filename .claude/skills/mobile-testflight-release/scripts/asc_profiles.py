#!/usr/bin/env python3
"""Deprecated compatibility entry point; production ASC mutation is disabled."""

from __future__ import annotations

import sys


MESSAGE = (
    "asc_profiles.py 已禁用：旧入口会读取本地 ASC 密钥并修改 provisioning profile。"
    "自动 production 原生构建当前也已冻结；不得绕过受控入口直接调用供应商 CLI。"
    "构建、TestFlight 和 App Review 必须分别通过人工 Gate。"
)


def main() -> int:
    print(MESSAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
