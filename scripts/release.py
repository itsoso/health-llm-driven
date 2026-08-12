#!/usr/bin/env python3
"""Fail-closed source-aware release planning and orchestration."""

from __future__ import annotations

import argparse
import errno
import fcntl
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable, Mapping, Sequence

try:
    import validation_credential
except ModuleNotFoundError:
    from scripts import validation_credential


ROOT = Path(__file__).resolve().parents[1]
STATE_SCHEMA_VERSION = 2
STATE_DIRECTORY_NAME = "reva-release-state"
STATE_FILE_NAME = "release-state.json"
TRANSACTION_LOG_FILE_NAME = "release-transactions.jsonl"
LOCK_FILE_NAME = "release-publish.lock"
VALIDATION_PROFILE = "all"


class ReleaseError(RuntimeError):
    """A release invariant could not be proven."""


@dataclass(frozen=True)
class Change:
    status: str
    paths: tuple[str, ...]


@dataclass(frozen=True)
class ReleasePlan:
    base_sha: str
    target_sha: str
    changes: tuple[Change, ...]
    surfaces: tuple[str, ...]
    actions: tuple[str, ...]
    completed_actions: tuple[str, ...]
    blocked_paths: tuple[str, ...]
    publishable: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


Runner = Callable[..., subprocess.CompletedProcess[Any]]


_STATUS_RE = re.compile(r"^[ACDMRTUXB][0-9]{0,3}$")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SURFACE_ORDER = (
    "backend",
    "frontend",
    "mobile_native",
    "mobile_ota",
    "mac",
    "validation_only",
)
_VALID_ACTIONS = {
    "validate",
    "deploy_backend",
    "deploy_all",
    "mobile_ota",
    "native_build",
    "mac_build",
}
_ROOT_BACKEND_INPUTS = {
    "Dockerfile.backend",
    "docker-compose.yml",
}
_ROOT_FRONTEND_INPUTS = {"Dockerfile.frontend"}
_ROOT_MOBILE_NATIVE_INPUTS = {
    ".easignore",
    "app.json",
}
_ROOT_VALIDATION_FILES = {
    ".dockerignore",
    ".env.example",
    ".gitattributes",
    ".gitignore",
    ".npmrc",
    ".pre-commit-config.yaml",
    "AGENTS.md",
    "CHANGELOG.md",
    "CLAUDE.md",
    "README.md",
    "deploy.sh",
    "deploy-remote.sh",
    "deploy_production.sh",
    "deploy_to_server.sh",
}
_MOBILE_NATIVE_RESOURCE_PREFIXES = (
    "mobile/assets/rokid/",
    "mobile/vendor/",
)
_MOBILE_NATIVE_RESOURCE_SUFFIXES = (
    ".aab",
    ".apk",
    ".aar",
    ".dylib",
    ".framework",
    ".ipa",
    ".jar",
    ".mlmodel",
    ".mlpackage",
    ".metal",
    ".appex",
    ".bundle",
    ".so",
    ".storyboard",
    ".xcassets",
    ".xcframework",
    ".xcprivacy",
    ".xib",
)
_GIT_ENV_OVERRIDES = frozenset(
    {
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_COMMON_DIR",
        "GIT_CONFIG_COUNT",
        "GIT_CONFIG_GLOBAL",
        "GIT_CONFIG_NOSYSTEM",
        "GIT_CONFIG_PARAMETERS",
        "GIT_CONFIG_SYSTEM",
        "GIT_DIR",
        "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_WORK_TREE",
    }
)
_VALIDATION_ENV_OVERRIDES = frozenset(
    {
        *_GIT_ENV_OVERRIDES,
        "BASH_ENV",
        "ENV",
        "NODE_OPTIONS",
        "NODE_PATH",
        "NPM_CONFIG_GLOBALCONFIG",
        "NPM_CONFIG_NODE_OPTIONS",
        "NPM_CONFIG_SCRIPT_SHELL",
        "NPM_CONFIG_USERCONFIG",
        "PYTEST_ADDOPTS",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
        "PYTEST_PLUGINS",
        "PYTHONHOME",
        "PYTHONPATH",
        "PYTHONSTARTUP",
        "OTA_TRANSACTION_ID",
        "npm_config_globalconfig",
        "npm_config_node_options",
        "npm_config_script_shell",
        "npm_config_userconfig",
        "REVA_VALIDATION_ALLOW_ROOT_OVERRIDE_FOR_TESTS",
        "REVA_VALIDATION_LOG_DIR",
        "REVA_VALIDATION_ROOT",
    }
)
_MUTATION_ENV_OVERRIDES = frozenset(
    {
        *_GIT_ENV_OVERRIDES,
        "BASH_ENV",
        "ENV",
        "NODE_OPTIONS",
        "NODE_PATH",
        "NPM_CONFIG_GLOBALCONFIG",
        "NPM_CONFIG_NODE_OPTIONS",
        "NPM_CONFIG_SCRIPT_SHELL",
        "NPM_CONFIG_USERCONFIG",
        "PYTHONHOME",
        "PYTHONPATH",
        "PYTHONSTARTUP",
        "OTA_TRANSACTION_ID",
        "npm_config_globalconfig",
        "npm_config_node_options",
        "npm_config_script_shell",
        "npm_config_userconfig",
    }
)
_OTA_TEST_ENV_OVERRIDES = frozenset(
    {
        "OTA_ALLOW_DIRTY",
        "OTA_EAS_RUNNER",
        "OTA_EXPO_RUNNER",
        "OTA_TEST_AFTER_ARTIFACT_VERIFIED",
    }
)


def _git(
    repo: Path,
    *args: str,
    text: bool = True,
    check: bool = True,
) -> str | bytes:
    environment = _git_environment()
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=check,
        capture_output=True,
        text=text,
        env=environment,
    )
    return result.stdout.strip() if text else result.stdout


def _scrub_environment(
    environment: Mapping[str, str], names: Iterable[str]
) -> dict[str, str]:
    scrubbed = dict(environment)
    npm_overrides = {
        "npm_config_globalconfig",
        "npm_config_node_options",
        "npm_config_script_shell",
        "npm_config_userconfig",
    }
    for name in names:
        scrubbed.pop(name, None)
    for name in tuple(scrubbed):
        if (
            name.startswith("BASH_FUNC_")
            or name.startswith("GIT_CONFIG_KEY_")
            or name.startswith("GIT_CONFIG_VALUE_")
            or name.lower().replace("-", "_") in npm_overrides
        ):
            scrubbed.pop(name, None)
    return scrubbed


def _git_environment() -> dict[str, str]:
    return _scrub_environment(os.environ, _GIT_ENV_OVERRIDES)


def _decode_path(value: bytes) -> str:
    path = value.decode("utf-8", errors="surrogateescape")
    if not path:
        raise ReleaseError("Git change contains an empty path")
    pure = PurePosixPath(path)
    if pure.is_absolute() or ".." in pure.parts or "." in pure.parts:
        raise ReleaseError(f"Git change contains an unsafe path: {path!r}")
    return path


def parse_name_status(raw: bytes) -> tuple[Change, ...]:
    """Parse ``git diff --name-status -z`` without losing rename endpoints."""

    if not raw:
        return ()
    fields = raw.split(b"\0")
    if fields[-1] == b"":
        fields.pop()
    changes: list[Change] = []
    index = 0
    while index < len(fields):
        status = fields[index].decode("ascii", errors="strict")
        index += 1
        if not _STATUS_RE.fullmatch(status):
            raise ReleaseError(f"Unsupported Git change status: {status!r}")
        path_count = 2 if status[0] in {"R", "C"} else 1
        if index + path_count > len(fields):
            raise ReleaseError(f"Incomplete Git change record for status {status}")
        paths = tuple(
            _decode_path(value) for value in fields[index : index + path_count]
        )
        index += path_count
        changes.append(Change(status=status, paths=paths))
    return tuple(changes)


def git_changes(
    repo: Path, base: str, target: str
) -> tuple[str, str, tuple[Change, ...]]:
    repo = _repository_root(repo)
    base_sha = str(_git(repo, "rev-parse", "--verify", f"{base}^{{commit}}"))
    target_sha = str(_git(repo, "rev-parse", "--verify", f"{target}^{{commit}}"))
    if not _SHA_RE.fullmatch(base_sha) or not _SHA_RE.fullmatch(target_sha):
        raise ReleaseError("Unable to resolve an exact base and target commit")
    raw = _git(
        repo,
        "diff",
        "--name-status",
        "-z",
        "--find-renames",
        base_sha,
        target_sha,
        text=False,
    )
    assert isinstance(raw, bytes)
    return base_sha, target_sha, parse_name_status(raw)


def _is_test_or_fixture(path: str) -> bool:
    parts = PurePosixPath(path).parts
    name = parts[-1]
    return (
        "tests" in parts
        or "__tests__" in parts
        or name.startswith("test_")
        or name.endswith((".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx"))
        or name in {"pytest.ini", "jest.config.js", "jest.config.ts"}
    )


def _normalize_mobile_asset_reference(value: object, *, source: str) -> str:
    if not isinstance(value, str) or not value.startswith("./"):
        raise ReleaseError(
            f"{source} native asset reference must be a static local path"
        )
    relative = PurePosixPath(value[2:])
    if not relative.parts or ".." in relative.parts or "." in relative.parts:
        raise ReleaseError(f"{source} contains an unsafe native asset path: {value!r}")
    return str(PurePosixPath("mobile", *relative.parts))


def _local_plugin_references(value: str, *, source: str) -> set[str]:
    exact = _normalize_mobile_asset_reference(value, source=source)
    if PurePosixPath(exact).suffix:
        return {exact}
    extensions = (".js", ".ts", ".cjs", ".mjs")
    return {
        exact,
        *(f"{exact}{extension}" for extension in extensions),
        *(f"{exact}/index{extension}" for extension in extensions),
    }


def _app_json_native_assets(raw: str, *, source: str) -> set[str]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ReleaseError(f"Cannot parse {source}: {error}") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("expo", {}), dict):
        raise ReleaseError(f"{source} must contain an Expo config object")
    expo = payload.get("expo", {})
    references: list[tuple[str, object]] = []
    direct_assets: set[str] = set()

    def add(label: str, container: object, key: str) -> None:
        if isinstance(container, dict) and key in container:
            references.append((label, container[key]))

    add("icon", expo, "icon")
    splash = expo.get("splash", {}) if isinstance(expo, dict) else {}
    add("splash.image", splash, "image")
    android = expo.get("android", {}) if isinstance(expo, dict) else {}
    add("android.icon", android, "icon")
    add("android.googleServicesFile", android, "googleServicesFile")
    android_splash = android.get("splash", {}) if isinstance(android, dict) else {}
    for key in ("image", "mdpi", "hdpi", "xhdpi", "xxhdpi", "xxxhdpi"):
        add(f"android.splash.{key}", android_splash, key)
    android_splash_dark = (
        android_splash.get("dark", {}) if isinstance(android_splash, dict) else {}
    )
    for key in ("image", "mdpi", "hdpi", "xhdpi", "xxhdpi", "xxxhdpi"):
        add(f"android.splash.dark.{key}", android_splash_dark, key)
    adaptive = android.get("adaptiveIcon", {}) if isinstance(android, dict) else {}
    for key in ("foregroundImage", "backgroundImage", "monochromeImage"):
        add(f"android.adaptiveIcon.{key}", adaptive, key)
    notification = expo.get("notification", {}) if isinstance(expo, dict) else {}
    add("notification.icon", notification, "icon")
    ios = expo.get("ios", {}) if isinstance(expo, dict) else {}
    add("ios.googleServicesFile", ios, "googleServicesFile")
    ios_icon = ios.get("icon") if isinstance(ios, dict) else None
    if isinstance(ios_icon, dict):
        for key in ("light", "dark", "tinted"):
            add(f"ios.icon.{key}", ios_icon, key)
    else:
        add("ios.icon", ios, "icon")
    ios_splash = ios.get("splash", {}) if isinstance(ios, dict) else {}
    for key in ("image", "tabletImage"):
        add(f"ios.splash.{key}", ios_splash, key)
    ios_splash_dark = ios_splash.get("dark", {}) if isinstance(ios_splash, dict) else {}
    for key in ("image", "tabletImage"):
        add(f"ios.splash.dark.{key}", ios_splash_dark, key)
    web = expo.get("web", {}) if isinstance(expo, dict) else {}
    add("web.favicon", web, "favicon")
    web_splash = web.get("splash", {}) if isinstance(web, dict) else {}
    add("web.splash.image", web_splash, "image")
    updates = expo.get("updates", {}) if isinstance(expo, dict) else {}
    add(
        "updates.codeSigningCertificate",
        updates,
        "codeSigningCertificate",
    )
    locales = expo.get("locales", {}) if isinstance(expo, dict) else {}
    if isinstance(locales, dict):
        for locale, value in locales.items():
            if isinstance(value, str):
                references.append((f"locales.{locale}", value))

    def add_local_values(label: str, value: object) -> None:
        if isinstance(value, str) and value.startswith("./"):
            references.append((label, value))
        elif isinstance(value, list):
            for index, item in enumerate(value):
                add_local_values(f"{label}[{index}]", item)
        elif isinstance(value, dict):
            for key, item in value.items():
                add_local_values(f"{label}.{key}", item)

    plugins = expo.get("plugins", []) if isinstance(expo, dict) else []
    if isinstance(plugins, list):
        for index, plugin in enumerate(plugins):
            if isinstance(plugin, str):
                if plugin.startswith("./"):
                    direct_assets.update(
                        _local_plugin_references(
                            plugin, source=f"{source}:plugins[{index}]"
                        )
                    )
                continue
            if not isinstance(plugin, list) or not plugin:
                continue
            name = plugin[0]
            if not isinstance(name, str):
                continue
            options = plugin[1] if len(plugin) > 1 else None
            add_local_values(f"plugins[{index}].{name}", options)
            if name.startswith("./"):
                direct_assets.update(
                    _local_plugin_references(name, source=f"{source}:plugins[{index}]")
                )
            if not isinstance(options, dict):
                continue
            if name == "expo-notifications":
                add(f"plugins[{index}].expo-notifications.icon", options, "icon")
            elif name == "expo-splash-screen":
                add(f"plugins[{index}].expo-splash-screen.image", options, "image")
                for platform_name in ("dark", "ios", "android"):
                    platform_options = options.get(platform_name, {})
                    add(
                        f"plugins[{index}].expo-splash-screen.{platform_name}.image",
                        platform_options,
                        "image",
                    )
    return direct_assets | {
        _normalize_mobile_asset_reference(value, source=f"{source}:{label}")
        for label, value in references
    }


@dataclass(frozen=True)
class _JsToken:
    kind: str
    value: str


_JS_IDENTIFIER_START = re.compile(r"[A-Za-z_$]")
_JS_IDENTIFIER_PART = re.compile(r"[A-Za-z0-9_$]")
_NATIVE_CONFIG_PATHS = frozenset(
    {
        ("icon",),
        ("ios", "icon"),
        ("ios", "icon", "light"),
        ("ios", "icon", "dark"),
        ("ios", "icon", "tinted"),
        ("ios", "googleServicesFile"),
        ("android", "icon"),
        ("android", "googleServicesFile"),
        ("splash", "image"),
        ("ios", "splash", "image"),
        ("android", "splash", "image"),
        ("android", "splash", "mdpi"),
        ("android", "splash", "hdpi"),
        ("android", "splash", "xhdpi"),
        ("android", "splash", "xxhdpi"),
        ("android", "splash", "xxxhdpi"),
        ("android", "splash", "dark", "image"),
        ("android", "splash", "dark", "mdpi"),
        ("android", "splash", "dark", "hdpi"),
        ("android", "splash", "dark", "xhdpi"),
        ("android", "splash", "dark", "xxhdpi"),
        ("android", "splash", "dark", "xxxhdpi"),
        ("ios", "splash", "tabletImage"),
        ("ios", "splash", "dark", "image"),
        ("ios", "splash", "dark", "tabletImage"),
        ("android", "adaptiveIcon", "foregroundImage"),
        ("android", "adaptiveIcon", "backgroundImage"),
        ("android", "adaptiveIcon", "monochromeImage"),
        ("notification", "icon"),
        ("web", "favicon"),
        ("web", "splash", "image"),
        ("updates", "codeSigningCertificate"),
    }
)
_NATIVE_CONFIG_CONTAINERS = frozenset(
    {
        (),
        ("ios",),
        ("ios", "icon"),
        ("ios", "splash"),
        ("ios", "splash", "dark"),
        ("android",),
        ("android", "splash"),
        ("android", "splash", "dark"),
        ("android", "adaptiveIcon"),
        ("splash",),
        ("notification",),
        ("web",),
        ("web", "splash"),
        ("updates",),
        ("plugins",),
        ("locales",),
    }
)
_PLUGIN_ASSET_PATHS = {
    "expo-notifications": frozenset({("icon",)}),
    "expo-splash-screen": frozenset(
        {
            ("image",),
            ("dark", "image"),
            ("ios", "image"),
            ("android", "image"),
        }
    ),
}
_EXPO_ROOT_CONFIG_KEYS = frozenset(
    {
        "name",
        "slug",
        "icon",
        "ios",
        "android",
        "splash",
        "notification",
        "web",
        "plugins",
        "updates",
        "locales",
        "extra",
    }
)
_AUDITED_APP_CONFIG_SHA256 = frozenset(
    {
        # mobile/app.config.ts at the reviewed release-pipeline baseline.
        "8473ce0fa1743eb1a44e004b8250a321bc1d00b0f4677ca55dc9cb76a82bd8d4",
    }
)


def _tokenize_app_config(raw: str, *, source: str) -> list[_JsToken]:
    tokens: list[_JsToken] = []
    index = 0
    while index < len(raw):
        char = raw[index]
        if char.isspace():
            index += 1
            continue
        if raw.startswith("//", index):
            newline = raw.find("\n", index + 2)
            index = len(raw) if newline < 0 else newline + 1
            continue
        if raw.startswith("/*", index):
            end = raw.find("*/", index + 2)
            if end < 0:
                raise ReleaseError(f"{source} contains an unterminated comment")
            index = end + 2
            continue
        if char in {"'", '"', "`"}:
            quote = char
            cursor = index + 1
            value: list[str] = []
            while cursor < len(raw):
                current = raw[cursor]
                if current == "\\":
                    raise ReleaseError(
                        f"{source} cannot prove escaped native asset strings"
                    )
                if current == quote:
                    break
                value.append(current)
                cursor += 1
            if cursor >= len(raw):
                raise ReleaseError(f"{source} contains an unterminated string")
            kind = "template" if quote == "`" else "string"
            tokens.append(_JsToken(kind, "".join(value)))
            index = cursor + 1
            continue
        if _JS_IDENTIFIER_START.fullmatch(char):
            cursor = index + 1
            while cursor < len(raw) and _JS_IDENTIFIER_PART.fullmatch(raw[cursor]):
                cursor += 1
            tokens.append(_JsToken("identifier", raw[index:cursor]))
            index = cursor
            continue
        if raw.startswith("...", index):
            tokens.append(_JsToken("punct", "..."))
            index += 3
            continue
        tokens.append(_JsToken("punct", char))
        index += 1
    return tokens


def _app_config_native_assets(raw: str, *, source: str) -> set[str]:
    if hashlib.sha256(raw.encode("utf-8")).hexdigest() in _AUDITED_APP_CONFIG_SHA256:
        return set()
    tokens = _tokenize_app_config(raw, source=source)
    pairs: dict[int, int] = {}
    stack: list[tuple[str, int]] = []
    closer = {"{": "}", "[": "]", "(": ")"}
    for index, token in enumerate(tokens):
        if token.value in closer:
            stack.append((token.value, index))
        elif token.value in closer.values():
            if not stack or closer[stack[-1][0]] != token.value:
                raise ReleaseError(f"{source} contains unbalanced delimiters")
            _opening, opening_index = stack.pop()
            pairs[opening_index] = index
    if stack:
        raise ReleaseError(f"{source} contains unbalanced delimiters")

    assets: set[str] = set()
    visited: set[int] = set()
    proved_root_config = False

    def relative_plugin_path(path: tuple[str, ...]) -> tuple[str, ...]:
        if "plugins" not in path:
            return path
        return path[path.index("plugins") + 1 :]

    def is_native_path(path: tuple[str, ...], plugin: str | None) -> bool:
        if plugin:
            return relative_plugin_path(path) in _PLUGIN_ASSET_PATHS.get(
                plugin, frozenset()
            )
        return path in _NATIVE_CONFIG_PATHS or (len(path) == 2 and path[0] == "locales")

    def could_contain_native(path: tuple[str, ...], plugin: str | None) -> bool:
        if plugin:
            return True
        return path in _NATIVE_CONFIG_CONTAINERS

    def fail_unknown(path: tuple[str, ...]) -> None:
        label = ".".join(path) or "<computed>"
        raise ReleaseError(f"{source} cannot prove native asset references for {label}")

    def value_end(start: int, end: int) -> int:
        cursor = start
        while cursor < end:
            token = tokens[cursor]
            if token.value in {",", ";"}:
                return cursor
            if token.value in pairs:
                cursor = pairs[cursor] + 1
                continue
            cursor += 1
        return end

    def unwrap_parentheses(start: int, end: int) -> tuple[int, int]:
        while start < end and tokens[start].value == "(":
            matching = pairs.get(start)
            if matching != end - 1:
                break
            start += 1
            end -= 1
        return start, end

    def config_passthrough_path(start: int, end: int) -> tuple[str, ...] | None:
        start, end = unwrap_parentheses(start, end)
        if start >= end or tokens[start].value != "config":
            return None
        cursor = start + 1
        parts: list[str] = []
        while cursor < end:
            if tokens[cursor].value == ".":
                cursor += 1
            elif (
                cursor + 1 < end
                and tokens[cursor].value == "?"
                and tokens[cursor + 1].value == "."
            ):
                cursor += 2
            else:
                break
            if cursor >= end or tokens[cursor].kind != "identifier":
                return None
            parts.append(tokens[cursor].value)
            cursor += 1
        if cursor < end:
            if (
                cursor + 4 != end
                or tokens[cursor].value != "?"
                or tokens[cursor + 1].value != "?"
                or tokens[cursor + 2].value != "{"
                or pairs.get(cursor + 2) != end - 1
            ):
                return None
        return tuple(parts)

    def is_exact_object(start: int, end: int) -> bool:
        start, end = unwrap_parentheses(start, end)
        return (
            start < end and tokens[start].value == "{" and pairs.get(start) == end - 1
        )

    def is_literal_object_spread(start: int, end: int) -> bool:
        start, end = unwrap_parentheses(start, end)
        if is_exact_object(start, end):
            return True
        question: int | None = None
        colon: int | None = None
        cursor = start
        while cursor < end:
            if tokens[cursor].value in pairs:
                cursor = pairs[cursor] + 1
                continue
            if tokens[cursor].value == "?" and question is None:
                question = cursor
            elif tokens[cursor].value == ":" and question is not None:
                colon = cursor
                break
            cursor += 1
        return (
            question is not None
            and colon is not None
            and is_exact_object(question + 1, colon)
            and is_exact_object(colon + 1, end)
        )

    def record_scalar(start: int, end: int, path: tuple[str, ...]) -> None:
        start, end = unwrap_parentheses(start, end)
        if end - start == 1 and tokens[start].kind == "string":
            assets.add(
                _normalize_mobile_asset_reference(
                    tokens[start].value, source=f"{source}:{'.'.join(path)}"
                )
            )
            return
        if config_passthrough_path(start, end) == path:
            return
        fail_unknown(path)

    def walk_range(
        start: int,
        end: int,
        path: tuple[str, ...],
        plugin: str | None,
    ) -> None:
        if plugin:
            for token in tokens[start:end]:
                if token.kind == "string" and token.value.startswith("./"):
                    assets.add(
                        _normalize_mobile_asset_reference(
                            token.value, source=f"{source}:plugins.{plugin}"
                        )
                    )
        cursor = start
        while cursor < end:
            token = tokens[cursor]
            if token.value == "{" and cursor in pairs:
                walk_object(cursor, path, plugin)
                cursor = pairs[cursor] + 1
            elif token.value == "[" and cursor in pairs:
                walk_array(cursor, path, plugin)
                cursor = pairs[cursor] + 1
            else:
                cursor += 1

    def walk_array(
        opening: int,
        path: tuple[str, ...],
        plugin: str | None,
    ) -> None:
        if opening in visited:
            return
        visited.add(opening)
        end = pairs[opening]
        cursor = opening + 1
        if plugin is not None:
            while cursor < end:
                token = tokens[cursor]
                if token.value == ",":
                    cursor += 1
                    continue
                if token.kind == "string":
                    if token.value.startswith("./"):
                        assets.add(
                            _normalize_mobile_asset_reference(
                                token.value,
                                source=f"{source}:plugins.{plugin}",
                            )
                        )
                    cursor += 1
                    continue
                if token.value == "{" and cursor in pairs:
                    walk_object(cursor, path, plugin)
                    cursor = pairs[cursor] + 1
                    continue
                if token.value == "[" and cursor in pairs:
                    walk_array(cursor, path, plugin)
                    cursor = pairs[cursor] + 1
                    continue
                if token.value in {"true", "false", "null"} or token.value in {
                    "-",
                    ".",
                    *tuple("0123456789"),
                }:
                    cursor += 1
                    continue
                fail_unknown((*path, f"plugins.{plugin}"))
            return
        if path == ("plugins",) and plugin is None:
            while cursor < end:
                token = tokens[cursor]
                if token.value == ",":
                    cursor += 1
                    continue
                if token.kind == "string":
                    if token.value.startswith("./"):
                        assets.update(
                            _local_plugin_references(
                                token.value, source=f"{source}:plugins"
                            )
                        )
                    cursor += 1
                    continue
                if token.value == "[" and cursor in pairs:
                    tuple_end = pairs[cursor]
                    name_index = cursor + 1
                    if name_index >= tuple_end or tokens[name_index].kind != "string":
                        fail_unknown(("plugins", "<name>"))
                    plugin_name = tokens[name_index].value
                    if plugin_name.startswith("./"):
                        assets.update(
                            _local_plugin_references(
                                plugin_name, source=f"{source}:plugins"
                            )
                        )
                    comma = name_index + 1
                    if comma < tuple_end and tokens[comma].value == ",":
                        options_start = comma + 1
                        options_end = value_end(options_start, tuple_end)
                        if (
                            options_start < options_end
                            and tokens[options_start].value == "{"
                        ):
                            walk_object(
                                options_start,
                                ("plugins",),
                                plugin_name,
                            )
                        else:
                            fail_unknown(("plugins", plugin_name))
                    visited.add(cursor)
                    cursor = tuple_end + 1
                    continue
                fail_unknown(("plugins", "<entry>"))
            return
        first_plugin = (
            tokens[cursor].value
            if cursor < end and tokens[cursor].kind == "string"
            else None
        )
        if first_plugin is not None:
            comma = cursor + 1
            if comma < end and tokens[comma].value == ",":
                options_start = comma + 1
                options_end = value_end(options_start, end)
                if options_start < options_end and tokens[options_start].value == "{":
                    walk_object(options_start, path, first_plugin)
                elif "plugins" in path:
                    fail_unknown((*path, first_plugin))
        while cursor < end:
            if tokens[cursor].value == "[" and cursor in pairs:
                nested_end = pairs[cursor]
                walk_array(cursor, path, plugin)
                cursor = nested_end + 1
                continue
            if tokens[cursor].value == "{" and cursor in pairs:
                walk_object(cursor, path, plugin)
                cursor = pairs[cursor] + 1
                continue
            cursor += 1

    def walk_object(
        opening: int,
        path: tuple[str, ...],
        plugin: str | None,
    ) -> None:
        nonlocal proved_root_config
        if opening in visited:
            return
        visited.add(opening)
        end = pairs[opening]
        cursor = opening + 1
        property_start = True
        while cursor < end:
            token = tokens[cursor]
            if token.value in {",", ";"}:
                property_start = True
                cursor += 1
                continue
            if property_start and token.value == "[" and cursor in pairs:
                computed_end = pairs[cursor]
                if (
                    computed_end + 1 < end
                    and tokens[computed_end + 1].value == ":"
                    and could_contain_native(path, plugin)
                ):
                    fail_unknown(path)
            if property_start and token.value == "...":
                start = cursor + 1
                stop = value_end(start, end)
                if could_contain_native(path, plugin):
                    passthrough = config_passthrough_path(start, stop)
                    if passthrough != path and not is_literal_object_spread(
                        start, stop
                    ):
                        expression = " ".join(
                            token.value for token in tokens[start:stop]
                        )[:120]
                        fail_unknown((*path, f"<spread:{expression}>"))
                    if not path and plugin is None:
                        proved_root_config = True
                walk_range(start, stop, path, plugin)
                cursor = stop
                property_start = False
                continue
            if property_start and token.kind in {"identifier", "string"}:
                key = token.value
                if cursor + 1 < end and tokens[cursor + 1].value == ":":
                    if not path and plugin is None and key in _EXPO_ROOT_CONFIG_KEYS:
                        proved_root_config = True
                    start = cursor + 2
                    stop = value_end(start, end)
                    child_path = (*path, key)
                    if plugin is not None:
                        scalar = tokens[start:stop]
                        if len(scalar) == 1 and scalar[0].kind == "string":
                            if scalar[0].value.startswith("./"):
                                assets.add(
                                    _normalize_mobile_asset_reference(
                                        scalar[0].value,
                                        source=f"{source}:plugins.{plugin}.{key}",
                                    )
                                )
                        elif start < stop and tokens[start].value == "{":
                            walk_object(start, child_path, plugin)
                        elif start < stop and tokens[start].value == "[":
                            walk_array(start, child_path, plugin)
                        elif not all(
                            item.value in {"true", "false", "null", "-", "."}
                            or item.value in set("0123456789")
                            for item in scalar
                        ):
                            fail_unknown((*child_path, f"plugins.{plugin}"))
                        cursor = stop
                        property_start = False
                        continue
                    if is_native_path(child_path, plugin):
                        if (
                            start < stop
                            and tokens[start].value == "{"
                            and child_path == ("ios", "icon")
                        ):
                            walk_object(start, child_path, plugin)
                        else:
                            record_scalar(start, stop, child_path)
                    elif start < stop:
                        if tokens[start].value == "{":
                            walk_object(start, child_path, plugin)
                        elif tokens[start].value == "[":
                            walk_array(start, child_path, plugin)
                        elif could_contain_native(child_path, plugin):
                            if config_passthrough_path(start, stop) != child_path:
                                fail_unknown(child_path)
                        else:
                            walk_range(start, stop, child_path, plugin)
                    cursor = stop
                    property_start = False
                    continue
                if plugin is not None:
                    fail_unknown((*path, f"plugins.{plugin}.{key}"))
                if (
                    is_native_path((*path, key), plugin)
                    or could_contain_native((*path, key), plugin)
                ) and (cursor + 1 == end or tokens[cursor + 1].value in {",", "}"}):
                    fail_unknown((*path, key))
                if key in {"get", "set"} and could_contain_native(path, plugin):
                    fail_unknown((*path, f"<{key}ter>"))
            if token.value == "{" and cursor in pairs:
                walk_object(cursor, path, plugin)
                cursor = pairs[cursor] + 1
                continue
            if token.value == "[" and cursor in pairs:
                walk_array(cursor, path, plugin)
                cursor = pairs[cursor] + 1
                continue
            property_start = False
            cursor += 1

    export_starts: list[int] = []
    for index in range(len(tokens)):
        if (
            tokens[index].value == "export"
            and index + 1 < len(tokens)
            and tokens[index + 1].value == "default"
        ):
            export_starts.append(index + 2)
        elif (
            tokens[index].value == "module"
            and index + 3 < len(tokens)
            and tokens[index + 1].value == "."
            and tokens[index + 2].value == "exports"
            and tokens[index + 3].value == "="
        ):
            export_starts.append(index + 4)
    if len(export_starts) != 1:
        fail_unknown(())
    opening = export_starts[0]
    if opening >= len(tokens) or tokens[opening].value != "{":
        fail_unknown(())
    closing = pairs.get(opening)
    if closing is None or any(token.value != ";" for token in tokens[closing + 1 :]):
        fail_unknown(())
    walk_object(opening, (), None)
    if not proved_root_config:
        fail_unknown(())
    return assets


def _show_optional(repo: Path, revision: str, path: str) -> str | None:
    environment = _git_environment()
    completed = subprocess.run(
        ["git", "-C", str(repo), "show", f"{revision}:{path}"],
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )
    if completed.returncode == 0:
        return completed.stdout
    if (
        "does not exist" in completed.stderr
        or "exists on disk, but not in" in completed.stderr
    ):
        return None
    raise ReleaseError(
        f"Cannot inspect {path} at {revision}: {completed.stderr.strip()}"
    )


def _native_mobile_assets_for_refs(
    repo: Path, revisions: Iterable[str]
) -> frozenset[str]:
    assets: set[str] = set()
    for revision in dict.fromkeys(revisions):
        app_json = _show_optional(repo, revision, "mobile/app.json")
        if app_json is not None:
            assets.update(
                _app_json_native_assets(app_json, source=f"mobile/app.json@{revision}")
            )
        for config_path in ("mobile/app.config.js", "mobile/app.config.ts"):
            dynamic = _show_optional(repo, revision, config_path)
            if dynamic is not None:
                assets.update(
                    _app_config_native_assets(
                        dynamic, source=f"{config_path}@{revision}"
                    )
                )
    return frozenset(assets)


def _working_tree_native_mobile_assets() -> frozenset[str]:
    config = ROOT / "mobile/app.json"
    if not config.is_file():
        return frozenset()
    return frozenset(
        _app_json_native_assets(
            config.read_text(encoding="utf-8"), source="mobile/app.json"
        )
    )


def classify_path(
    path: str, *, native_mobile_assets: frozenset[str] | None = None
) -> str | None:
    """Classify a repository path; ``None`` means fail-closed/unknown."""

    native_mobile_files = {
        "mobile/app.json",
        "mobile/app.config.js",
        "mobile/app.config.ts",
        "mobile/.easignore",
        "mobile/eas.json",
        "mobile/package.json",
        "mobile/package-lock.json",
        "mobile/yarn.lock",
        "mobile/pnpm-lock.yaml",
        "mobile/react-native.config.js",
    }
    native_mobile_prefixes = (
        "apps/watch/",
        "apps/rokid-pushup-glasses/",
        "mobile/android/",
        "mobile/ios/",
        "mobile/modules/",
        "mobile/native/",
        "mobile/patches/",
        "mobile/plugins/",
    )
    if path in native_mobile_files or path.startswith(native_mobile_prefixes):
        return "mobile_native"

    path_parts = PurePosixPath(path).parts
    if path.startswith(_MOBILE_NATIVE_RESOURCE_PREFIXES) or (
        path.startswith("mobile/")
        and any(
            part.lower().endswith(_MOBILE_NATIVE_RESOURCE_SUFFIXES)
            for part in path_parts
        )
    ):
        return "mobile_native"

    referenced_assets = (
        _working_tree_native_mobile_assets()
        if native_mobile_assets is None
        else native_mobile_assets
    )
    if path in referenced_assets:
        return "mobile_native"

    if path in _ROOT_MOBILE_NATIVE_INPUTS:
        return "mobile_native"

    if _is_test_or_fixture(path):
        return "validation_only"

    validation_prefixes = (
        ".agents/",
        ".claude/",
        ".cursor/",
        ".github/",
        "artifacts/",
        "design/",
        "designs/",
        "docs/",
        "harness/",
        "scripts/",
    )
    if path in _ROOT_VALIDATION_FILES or path.startswith(validation_prefixes):
        return "validation_only"

    if path.startswith("apps/mac/"):
        return "mac"

    if path.startswith("mobile/") or path.startswith("packages/shared/"):
        return "mobile_ota"

    if path.startswith("frontend/") or path in _ROOT_FRONTEND_INPUTS:
        return "frontend"

    if path.startswith("backend/") or path in _ROOT_BACKEND_INPUTS:
        return "backend"

    return None


def build_plan(
    changes: Iterable[Change],
    *,
    base_sha: str,
    target_sha: str,
    completed_actions: Iterable[str] = (),
    native_mobile_assets: frozenset[str] | None = None,
) -> ReleasePlan:
    changes_tuple = tuple(changes)
    surfaces_seen: set[str] = set()
    blocked_paths: set[str] = set()
    for change in changes_tuple:
        for path in change.paths:
            surface = classify_path(path, native_mobile_assets=native_mobile_assets)
            if surface is None:
                blocked_paths.add(path)
            else:
                surfaces_seen.add(surface)

    if not surfaces_seen and not blocked_paths:
        surfaces_seen.add("validation_only")
    if surfaces_seen - {"validation_only"}:
        surfaces_seen.discard("validation_only")
    surfaces = tuple(surface for surface in _SURFACE_ORDER if surface in surfaces_seen)

    actions: list[str] = ["validate"]
    if "frontend" in surfaces_seen:
        actions.append("deploy_all")
    elif "backend" in surfaces_seen:
        actions.append("deploy_backend")
    if "mobile_native" in surfaces_seen:
        actions.append("native_build")
    elif "mobile_ota" in surfaces_seen:
        actions.append("mobile_ota")
    if "mac" in surfaces_seen:
        actions.append("mac_build")

    normalized_completed = tuple(
        action
        for action in dict.fromkeys(completed_actions)
        if action in _VALID_ACTIONS and action != "validate"
    )
    actions = [
        action
        for action in actions
        if action == "validate" or action not in normalized_completed
    ]
    publishable = not blocked_paths and not ({"mobile_native", "mac"} & surfaces_seen)
    return ReleasePlan(
        base_sha=base_sha,
        target_sha=target_sha,
        changes=changes_tuple,
        surfaces=surfaces,
        actions=tuple(actions),
        completed_actions=normalized_completed,
        blocked_paths=tuple(sorted(blocked_paths)),
        publishable=publishable,
    )


def _repository_root(repo: Path) -> Path:
    try:
        return Path(str(_git(repo.resolve(), "rev-parse", "--show-toplevel"))).resolve()
    except (OSError, subprocess.CalledProcessError) as error:
        raise ReleaseError(f"Not a Git worktree: {repo}") from error


def _git_common_dir(repo: Path) -> Path:
    root = _repository_root(repo)
    try:
        common = str(
            _git(root, "rev-parse", "--path-format=absolute", "--git-common-dir")
        )
        path = Path(common)
    except subprocess.CalledProcessError:
        common = str(_git(root, "rev-parse", "--git-common-dir"))
        path = Path(common)
        if not path.is_absolute():
            path = root / path
    return path.resolve()


def _owner_repository(repo: Path) -> Path:
    common = _git_common_dir(repo)
    if common.name == ".git" and (common.parent / ".git").exists():
        return common.parent.resolve()
    return _repository_root(repo)


def release_state_dir(repo: Path) -> Path:
    common = _git_common_dir(repo)
    state_dir = common / STATE_DIRECTORY_NAME
    try:
        state_dir.mkdir(mode=0o700, exist_ok=True)
    except OSError as error:
        raise ReleaseError(
            f"Cannot create shared release state: {state_dir}"
        ) from error
    mode = state_dir.lstat().st_mode
    if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
        raise ReleaseError(f"Unsafe shared release state path: {state_dir}")
    os.chmod(state_dir, 0o700)
    return state_dir


def _state_path(repo: Path) -> Path:
    return _git_common_dir(repo) / STATE_DIRECTORY_NAME / STATE_FILE_NAME


def _transaction_log_path(repo: Path) -> Path:
    return _git_common_dir(repo) / STATE_DIRECTORY_NAME / TRANSACTION_LOG_FILE_NAME


def write_release_state(repo: Path, state: Mapping[str, Any]) -> Path:
    directory = release_state_dir(repo)
    destination = directory / STATE_FILE_NAME
    if destination.is_symlink():
        raise ReleaseError(
            f"Refusing to replace symlinked release state: {destination}"
        )
    payload = dict(state)
    payload["schema_version"] = STATE_SCHEMA_VERSION
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".release-state.", dir=directory
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        os.chmod(destination, 0o600)
        directory_fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return destination


def read_release_state(repo: Path) -> dict[str, Any]:
    path = _state_path(repo)
    if not path.exists():
        return {}
    metadata = path.lstat()
    mode = metadata.st_mode
    if (
        stat.S_ISLNK(mode)
        or not stat.S_ISREG(mode)
        or stat.S_IMODE(mode) != 0o600
        or metadata.st_nlink != 1
    ):
        raise ReleaseError(f"Unsafe shared release state file: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ReleaseError(f"Corrupt shared release state file: {path}") from error
    if not isinstance(value, dict):
        raise ReleaseError(f"Invalid shared release state payload: {path}")
    if value.get("schema_version") == 1:
        return {}
    if value.get("schema_version") != STATE_SCHEMA_VERSION:
        raise ReleaseError(f"Unsupported shared release state schema: {path}")
    return value


_TRANSACTION_EVENT_KEYS = frozenset(
    {
        "schema_version",
        "event",
        "event_at",
        "transaction_id",
        "base_sha",
        "target_sha",
        "stage",
        "status",
        "attempt",
        "started_at",
        "finished_at",
        "elapsed_seconds",
        "log_path",
        "failed_stage",
        "completed_surfaces",
        "pending_surfaces",
        "safe_retry_command",
    }
)


def _append_transaction_event(repo: Path, event: Mapping[str, Any]) -> Path:
    unexpected = set(event) - _TRANSACTION_EVENT_KEYS
    if unexpected:
        raise ReleaseError(
            "Refusing unsafe release transaction event fields: "
            + ", ".join(sorted(unexpected))
        )
    directory = release_state_dir(repo)
    destination = directory / TRANSACTION_LOG_FILE_NAME
    if destination.is_symlink():
        raise ReleaseError(f"Unsafe release transaction log: {destination}")
    payload = dict(event)
    payload["schema_version"] = STATE_SCHEMA_VERSION
    payload.setdefault("event_at", datetime.now(timezone.utc).isoformat())
    encoded = (
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(destination, flags, 0o600)
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_nlink != 1
        ):
            raise ReleaseError(f"Unsafe release transaction log: {destination}")
        view = memoryview(encoded)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short write to release transaction log")
            view = view[written:]
        os.fsync(descriptor)
    except ReleaseError:
        raise
    except OSError as error:
        raise ReleaseError(
            f"Cannot append private release transaction log: {destination}"
        ) from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
    return destination


@contextmanager
def release_publish_lock(repo: Path):
    """Hold one nonblocking, repository-wide production publish lock."""

    directory = release_state_dir(repo)
    destination = directory / LOCK_FILE_NAME
    if destination.is_symlink():
        raise ReleaseError(f"Unsafe release publish lock: {destination}")
    flags = os.O_RDWR | os.O_CREAT
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor: int | None = None
    locked = False
    try:
        try:
            descriptor = os.open(destination, flags, 0o600)
        except OSError as error:
            raise ReleaseError(f"Unsafe release publish lock: {destination}") from error
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_nlink != 1
        ):
            raise ReleaseError(f"Unsafe release publish lock: {destination}")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            if error.errno in {errno.EACCES, errno.EAGAIN}:
                raise ReleaseError(
                    "Another release publish transaction is already active"
                ) from error
            raise ReleaseError(
                f"Cannot acquire release publish lock: {destination}"
            ) from error
        locked = True
        yield destination
    finally:
        if descriptor is not None:
            if locked:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)


def _worktree_status(repo: Path) -> str:
    return str(_git(repo, "status", "--porcelain", "--untracked-files=all"))


def _branch_name(repo: Path) -> str:
    return str(
        _git(
            repo,
            "symbolic-ref",
            "--quiet",
            "--short",
            "HEAD",
            check=False,
        )
    )


def _remote_main_sha(repo: Path) -> str:
    output = str(_git(repo, "ls-remote", "origin", "refs/heads/main"))
    rows = [line.split() for line in output.splitlines() if line.strip()]
    if len(rows) != 1 or len(rows[0]) != 2 or not _SHA_RE.fullmatch(rows[0][0]):
        raise ReleaseError("Unable to verify the unique origin/main commit")
    return rows[0][0]


def assert_release_source(release_path: Path) -> str:
    release_path = _repository_root(release_path)
    dirty = _worktree_status(release_path)
    if dirty:
        raise ReleaseError(f"Release worktree is dirty; refusing cleanup:\n{dirty}")
    branch = _branch_name(release_path)
    if branch not in {"", "main"}:
        raise ReleaseError(f"Release worktree is on forbidden branch {branch}")
    head = str(_git(release_path, "rev-parse", "HEAD"))
    local_main = str(_git(release_path, "rev-parse", "refs/remotes/origin/main"))
    remote_main = _remote_main_sha(release_path)
    if not _SHA_RE.fullmatch(head) or head != local_main or head != remote_main:
        raise ReleaseError(
            "Release source must equal both local and remote origin/main: "
            f"head={head[:12]} local={local_main[:12]} remote={remote_main[:12]}"
        )
    return head


def ensure_release_worktree(
    repo: Path,
    *,
    release_path: Path | None = None,
) -> Path:
    source = _repository_root(repo)
    owner = _owner_repository(source)
    destination = (
        release_path.resolve()
        if release_path is not None
        else Path(f"{owner}.release").resolve()
    )

    if destination.exists():
        try:
            destination_root = _repository_root(destination)
        except ReleaseError as error:
            raise ReleaseError(
                f"Release path exists but is not a registered worktree: {destination}"
            ) from error
        if destination_root != destination:
            raise ReleaseError(f"Release path is not a worktree root: {destination}")
        if _git_common_dir(destination) != _git_common_dir(source):
            raise ReleaseError(
                f"Release path belongs to a different repository: {destination}"
            )
        dirty = _worktree_status(destination)
        if dirty:
            raise ReleaseError(
                f"Release worktree is dirty; refusing cleanup or reset:\n{dirty}"
            )
        branch = _branch_name(destination)
        if branch not in {"", "main"}:
            raise ReleaseError(
                f"Release worktree is on forbidden branch {branch}; refusing checkout"
            )

    _git(source, "fetch", "--quiet", "origin", "main")
    local_main = str(_git(source, "rev-parse", "refs/remotes/origin/main"))
    remote_main = _remote_main_sha(source)
    if local_main != remote_main:
        raise ReleaseError("Fetched origin/main does not match the remote main SHA")

    if not destination.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        _git(
            source,
            "worktree",
            "add",
            "--detach",
            str(destination),
            local_main,
        )
    else:
        _git(destination, "checkout", "--detach", local_main)

    assert_release_source(destination)
    return destination


def _validation_commands() -> list[dict[str, Any]]:
    return [
        {
            "name": "validation:all",
            "argv": ["bash", "scripts/run-all-tests.sh"],
            "cwd": ".",
            "blocking": True,
        }
    ]


def _running_in_ci() -> bool:
    return os.environ.get("CI", "").strip().lower() not in {"", "0", "false", "no"}


def _new_validation_log(repo: Path, profile: str) -> Path:
    try:
        state_dir = validation_credential.validation_state_dir(repo)
        logs_dir = state_dir / "logs"
        if logs_dir.is_symlink():
            raise ValueError(f"refusing symlinked validation log directory: {logs_dir}")
        logs_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        if logs_dir.is_symlink() or not logs_dir.is_dir():
            raise ValueError(f"validation log path is not a directory: {logs_dir}")
        logs_dir.chmod(0o700)
        run_dir = Path(tempfile.mkdtemp(prefix="release-validation-", dir=logs_dir))
        run_dir.chmod(0o700)
        return run_dir / f"{profile}.log"
    except (OSError, RuntimeError, ValueError) as error:
        raise ReleaseError(f"Cannot create private validation log: {error}") from error


def _print_validation_log(log_path: Path) -> None:
    try:
        output = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        raise ReleaseError(f"Cannot read validation log {log_path}: {error}") from error
    if output:
        print(output, end="" if output.endswith("\n") else "\n")


def run_validation(
    plan: ReleasePlan,
    repo: Path,
    *,
    runner: Runner = subprocess.run,
) -> Path | None:
    del plan
    repo = _repository_root(repo)
    profile = VALIDATION_PROFILE
    commands = _validation_commands()
    command = commands[0]["argv"]
    in_ci = _running_in_ci()
    credential_file: Path | None = None
    toolchain: Mapping[str, str] | None = None

    if in_ci:
        print(
            "[release] validation credential bypass: "
            "CI requires commit-specific validation"
        )
    else:
        try:
            credential_file = validation_credential.credential_path(repo, profile)
            toolchain = validation_credential.collect_toolchain(repo)
            verdict = validation_credential.verify_credential(
                repo=repo,
                path=credential_file,
                profile_name=profile,
                profile_version=validation_credential.PROFILE_VERSION,
                commands=commands,
                toolchain=toolchain,
            )
        except (OSError, RuntimeError, ValueError) as error:
            raise ReleaseError(
                f"Validation credential check failed closed: {error}"
            ) from error
        if verdict.reusable:
            print(
                f"[release] validation credential hit: profile={profile} "
                f"reason={verdict.reason}"
            )
            return None
        print(
            f"[release] validation credential miss: profile={profile} "
            f"reason={verdict.reason}"
        )

    log_path = _new_validation_log(repo, profile)
    print(f"[release] validation running: profile={profile} log={log_path}")
    validation_env = _scrub_environment(os.environ, _VALIDATION_ENV_OVERRIDES)
    validation_env["REVA_VALIDATION_EXPECTED_ROOT"] = str(repo)
    try:
        with log_path.open("x", encoding="utf-8") as log_handle:
            log_path.chmod(0o600)
            completed = runner(
                command,
                cwd=repo,
                check=True,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                text=True,
                env=validation_env,
            )
        if completed.returncode != 0:
            raise subprocess.CalledProcessError(completed.returncode, command)
    except subprocess.CalledProcessError as error:
        setattr(error, "validation_log_path", str(log_path))
        print(f"[release] validation failed: profile={profile} log={log_path}")
        _print_validation_log(log_path)
        raise

    _print_validation_log(log_path)
    if in_ci:
        print(
            f"[release] validation passed: profile={profile}; "
            "tree credential not issued in CI"
        )
        return log_path

    assert credential_file is not None
    assert toolchain is not None
    try:
        credential = validation_credential.build_credential(
            repo=repo,
            profile_name=profile,
            profile_version=validation_credential.PROFILE_VERSION,
            commands=commands,
            logs={commands[0]["name"]: log_path},
            toolchain=toolchain,
        )
        validation_credential.write_credential_atomic(credential_file, credential)
    except (OSError, RuntimeError, ValueError) as error:
        raise ReleaseError(
            f"Validation passed but credential issue failed closed: {error}"
        ) from error
    print(
        f"[release] validation credential issued: profile={profile} "
        f"path={credential_file}"
    )
    return log_path


_TRANSACTION_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_TRANSACTION_STATUSES = frozenset({"running", "failed", "succeeded"})
_STAGE_STATUSES = frozenset({"running", "failed", "succeeded", "interrupted"})
_RELEASE_STATE_KEYS = frozenset(
    {
        "schema_version",
        "updated_at",
        "transaction_id",
        "base_sha",
        "target_sha",
        "status",
        "attempt",
        "started_at",
        "finished_at",
        "elapsed_seconds",
        "failed_stage",
        "completed_actions",
        "completed_surfaces",
        "pending_surfaces",
        "stages",
        "safe_retry_command",
    }
)
_STAGE_RECORD_KEYS = frozenset(
    {
        "stage",
        "status",
        "attempt",
        "started_at",
        "finished_at",
        "elapsed_seconds",
        "log_path",
    }
)


def _valid_iso_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _validate_resumable_state(
    state: Mapping[str, Any], base_sha: str, target_sha: str
) -> None:
    try:
        if set(state) - _RELEASE_STATE_KEYS:
            raise ValueError("unexpected release state fields")
        transaction_id = state["transaction_id"]
        status = state["status"]
        attempt = state["attempt"]
        completed_actions = state["completed_actions"]
        completed_surfaces = state["completed_surfaces"]
        pending_surfaces = state["pending_surfaces"]
        failed_stage = state["failed_stage"]
        stages = state["stages"]
        retry_command = state["safe_retry_command"]
        started_at = state["started_at"]
        finished_at = state.get("finished_at")
        elapsed_seconds = state.get("elapsed_seconds")
        if state["base_sha"] != base_sha or state["target_sha"] != target_sha:
            raise ValueError("reference mismatch")
        if not isinstance(transaction_id, str) or not _TRANSACTION_ID_RE.fullmatch(
            transaction_id
        ):
            raise ValueError("invalid transaction id")
        if status not in _TRANSACTION_STATUSES:
            raise ValueError("invalid transaction status")
        if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1:
            raise ValueError("invalid transaction attempt")
        if not _valid_iso_timestamp(started_at):
            raise ValueError("invalid transaction start")
        if not isinstance(completed_actions, list) or any(
            not isinstance(item, str)
            or item not in _VALID_ACTIONS
            or item == "validate"
            for item in completed_actions
        ):
            raise ValueError("invalid completed actions")
        if len(completed_actions) != len(set(completed_actions)):
            raise ValueError("duplicate completed actions")
        for surfaces in (completed_surfaces, pending_surfaces):
            if not isinstance(surfaces, list) or any(
                not isinstance(item, str) or item not in _SURFACE_ORDER
                for item in surfaces
            ):
                raise ValueError("invalid surface list")
            if len(surfaces) != len(set(surfaces)):
                raise ValueError("duplicate surfaces")
        if set(completed_surfaces) & set(pending_surfaces):
            raise ValueError("overlapping surfaces")
        if failed_stage is not None and failed_stage not in _VALID_ACTIONS:
            raise ValueError("invalid failed stage")
        if status == "failed" and failed_stage is None:
            raise ValueError("missing failed stage")
        if status != "failed" and failed_stage is not None:
            raise ValueError("unexpected failed stage")
        if status == "succeeded" and pending_surfaces:
            raise ValueError("successful transaction has pending surfaces")
        if status == "running":
            if finished_at is not None or elapsed_seconds is not None:
                raise ValueError("running transaction has completion timing")
        else:
            if not _valid_iso_timestamp(finished_at):
                raise ValueError("invalid transaction finish")
            if (
                not isinstance(elapsed_seconds, (int, float))
                or isinstance(elapsed_seconds, bool)
                or elapsed_seconds < 0
            ):
                raise ValueError("invalid transaction elapsed time")
        if not isinstance(stages, list):
            raise ValueError("invalid stage list")
        for stage in stages:
            if not isinstance(stage, dict):
                raise ValueError("invalid stage record")
            if set(stage) - _STAGE_RECORD_KEYS:
                raise ValueError("unexpected stage fields")
            if stage.get("stage") not in _VALID_ACTIONS:
                raise ValueError("invalid stage name")
            if stage.get("status") not in _STAGE_STATUSES:
                raise ValueError("invalid stage status")
            stage_attempt = stage.get("attempt")
            if (
                not isinstance(stage_attempt, int)
                or isinstance(stage_attempt, bool)
                or stage_attempt < 1
                or stage_attempt > attempt
            ):
                raise ValueError("invalid stage attempt")
            if not _valid_iso_timestamp(stage.get("started_at")):
                raise ValueError("invalid stage start")
            if stage["status"] == "running":
                if "finished_at" in stage or "elapsed_seconds" in stage:
                    raise ValueError("running stage has completion timing")
            else:
                if not _valid_iso_timestamp(stage.get("finished_at")):
                    raise ValueError("invalid stage finish")
                elapsed = stage.get("elapsed_seconds")
                if (
                    not isinstance(elapsed, (int, float))
                    or isinstance(elapsed, bool)
                    or elapsed < 0
                ):
                    raise ValueError("invalid stage elapsed time")
            log_path = stage.get("log_path")
            if log_path is not None and (
                not isinstance(log_path, str) or not Path(log_path).is_absolute()
            ):
                raise ValueError("invalid stage log path")
        successful_actions = {
            stage["stage"]
            for stage in stages
            if stage["status"] == "succeeded" and stage["stage"] != "validate"
        }
        if set(completed_actions) != successful_actions:
            raise ValueError("completed actions lack successful stage proof")
        if (
            not isinstance(retry_command, list)
            or not retry_command
            or any(not isinstance(part, str) or not part for part in retry_command)
        ):
            raise ValueError("invalid safe retry command")
        if "--message" in retry_command:
            raise ValueError("retry command contains a message")
        expected_options = {
            "--base": base_sha,
            "--target": target_sha,
            "--release-worktree": None,
            "--env-file": None,
            "--repo": None,
        }
        for option, expected in expected_options.items():
            if retry_command.count(option) != 1:
                raise ValueError("retry command option mismatch")
            index = retry_command.index(option)
            if index + 1 >= len(retry_command):
                raise ValueError("retry command option has no value")
            if expected is not None and retry_command[index + 1] != expected:
                raise ValueError("retry command reference mismatch")
        if retry_command.count("publish") != 1:
            raise ValueError("retry command is not publish")
    except (KeyError, TypeError, ValueError):
        raise ReleaseError("Corrupt resumable release state") from None


def _matching_resumable_state(
    repo: Path, base_sha: str, target_sha: str
) -> dict[str, Any] | None:
    state = read_release_state(repo)
    if not state:
        return None
    if state.get("base_sha") != base_sha or state.get("target_sha") != target_sha:
        return None
    _validate_resumable_state(state, base_sha, target_sha)
    return state


def _state_completed_actions(
    repo: Path, base_sha: str, target_sha: str
) -> tuple[str, ...]:
    state = _matching_resumable_state(repo, base_sha, target_sha)
    if state is None:
        return ()
    return tuple(state["completed_actions"])


def _safe_retry_command(
    *,
    repo: Path,
    owner_repo: Path,
    base_sha: str,
    target_sha: str,
    env_file: Path,
) -> list[str]:
    return [
        sys.executable,
        str(repo / "scripts/release.py"),
        "publish",
        "--repo",
        str(owner_repo),
        "--base",
        base_sha,
        "--target",
        target_sha,
        "--release-worktree",
        str(repo),
        "--env-file",
        str(env_file),
    ]


def _surfaces_for_completed_actions(
    plan: ReleasePlan, completed_actions: Iterable[str]
) -> list[str]:
    actions = set(completed_actions)
    surfaces: set[str] = set()
    if "deploy_backend" in actions and "backend" in plan.surfaces:
        surfaces.add("backend")
    if "deploy_all" in actions:
        surfaces.update(set(plan.surfaces) & {"backend", "frontend"})
    if "mobile_ota" in actions and "mobile_ota" in plan.surfaces:
        surfaces.add("mobile_ota")
    return [surface for surface in _SURFACE_ORDER if surface in surfaces]


def _elapsed_between(started_at: str, finished_at: str) -> float:
    started = datetime.fromisoformat(started_at)
    finished = datetime.fromisoformat(finished_at)
    return round(max(0.0, (finished - started).total_seconds()), 6)


def _begin_release_transaction(
    plan: ReleasePlan,
    repo: Path,
    *,
    owner_repo: Path,
    env_file: Path,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    retry_command = _safe_retry_command(
        repo=repo,
        owner_repo=owner_repo,
        base_sha=plan.base_sha,
        target_sha=plan.target_sha,
        env_file=env_file,
    )
    prior = _matching_resumable_state(repo, plan.base_sha, plan.target_sha)
    resumable = prior is not None
    if resumable:
        assert prior is not None
        if prior["safe_retry_command"] != retry_command:
            raise ReleaseError(
                "Release retry parameters differ from the resumable transaction"
            )
        stages = [dict(stage) for stage in prior["stages"]]
        uncertain_mutations = [
            stage["stage"]
            for stage in stages
            if stage["status"] == "running" and stage["stage"] != "validate"
        ]
        if uncertain_mutations:
            raise ReleaseError(
                "Interrupted mutating release stage requires manual reconciliation: "
                + ", ".join(uncertain_mutations)
            )
        for stage in stages:
            if stage["status"] == "running":
                stage["status"] = "interrupted"
                stage["finished_at"] = now
                stage["elapsed_seconds"] = _elapsed_between(stage["started_at"], now)
        transaction_id = prior["transaction_id"]
        attempt = prior["attempt"] + 1
        started_at = prior["started_at"]
        prior_completed = list(prior["completed_actions"])
    else:
        stages = []
        transaction_id = uuid.uuid4().hex
        attempt = 1
        started_at = now
        prior_completed = []
    completed_actions = list(dict.fromkeys([*prior_completed, *plan.completed_actions]))
    completed_surfaces = _surfaces_for_completed_actions(plan, completed_actions)
    pending_surfaces = [
        surface for surface in plan.surfaces if surface not in completed_surfaces
    ]
    state: dict[str, Any] = {
        "schema_version": STATE_SCHEMA_VERSION,
        "transaction_id": transaction_id,
        "base_sha": plan.base_sha,
        "target_sha": plan.target_sha,
        "status": "running",
        "attempt": attempt,
        "started_at": started_at,
        "failed_stage": None,
        "completed_actions": completed_actions,
        "completed_surfaces": completed_surfaces,
        "pending_surfaces": pending_surfaces,
        "stages": stages,
        "safe_retry_command": retry_command,
    }
    write_release_state(repo, state)
    _append_transaction_event(
        repo,
        {
            "event": "transaction_started",
            "transaction_id": transaction_id,
            "base_sha": plan.base_sha,
            "target_sha": plan.target_sha,
            "status": "running",
            "attempt": attempt,
            "started_at": now,
            "completed_surfaces": completed_surfaces,
            "pending_surfaces": pending_surfaces,
            "safe_retry_command": retry_command,
        },
    )
    return state


def _start_release_stage(
    repo: Path, state: dict[str, Any], stage: str
) -> tuple[dict[str, Any], float]:
    started_at = datetime.now(timezone.utc).isoformat()
    record = {
        "stage": stage,
        "status": "running",
        "attempt": state["attempt"],
        "started_at": started_at,
    }
    state["stages"].append(record)
    state["status"] = "running"
    state["failed_stage"] = None
    write_release_state(repo, state)
    _append_transaction_event(
        repo,
        {
            "event": "stage_started",
            "transaction_id": state["transaction_id"],
            "base_sha": state["base_sha"],
            "target_sha": state["target_sha"],
            "stage": stage,
            "status": "running",
            "attempt": state["attempt"],
            "started_at": started_at,
        },
    )
    return record, time.monotonic()


def _finish_release_stage(
    repo: Path,
    state: dict[str, Any],
    record: dict[str, Any],
    started_monotonic: float,
    *,
    status: str,
    log_path: str | None = None,
) -> None:
    finished_at = datetime.now(timezone.utc).isoformat()
    elapsed = round(max(0.0, time.monotonic() - started_monotonic), 6)
    record["status"] = status
    record["finished_at"] = finished_at
    record["elapsed_seconds"] = elapsed
    if log_path is not None:
        record["log_path"] = log_path
    write_release_state(repo, state)
    event: dict[str, Any] = {
        "event": f"stage_{status}",
        "transaction_id": state["transaction_id"],
        "base_sha": state["base_sha"],
        "target_sha": state["target_sha"],
        "stage": record["stage"],
        "status": status,
        "attempt": state["attempt"],
        "started_at": record["started_at"],
        "finished_at": finished_at,
        "elapsed_seconds": elapsed,
        "completed_surfaces": state["completed_surfaces"],
        "pending_surfaces": state["pending_surfaces"],
    }
    if log_path is not None:
        event["log_path"] = log_path
    _append_transaction_event(repo, event)


def _mark_action_completed(
    plan: ReleasePlan, state: dict[str, Any], action: str
) -> None:
    if action != "validate" and action not in state["completed_actions"]:
        state["completed_actions"].append(action)
    completed = set(state["completed_surfaces"])
    if action == "validate" and plan.surfaces == ("validation_only",):
        completed.add("validation_only")
    elif action == "deploy_backend" and "backend" in plan.surfaces:
        completed.add("backend")
    elif action == "deploy_all":
        completed.update(set(plan.surfaces) & {"backend", "frontend"})
    elif action == "mobile_ota" and "mobile_ota" in plan.surfaces:
        completed.add("mobile_ota")
    state["completed_surfaces"] = [
        surface for surface in _SURFACE_ORDER if surface in completed
    ]
    state["pending_surfaces"] = [
        surface
        for surface in plan.surfaces
        if surface not in state["completed_surfaces"]
    ]


def _safe_failure_reason(error: Exception) -> str:
    if isinstance(error, ReleaseError) and "dirty" in str(error).lower():
        return "release_source_dirty"
    if isinstance(error, subprocess.CalledProcessError):
        return "command_failed"
    return "stage_failed"


def _fail_release_transaction(
    repo: Path,
    state: dict[str, Any],
    record: dict[str, Any],
    started_monotonic: float,
    error: Exception,
) -> ReleaseError:
    log_path_value = getattr(error, "validation_log_path", None)
    log_path = str(log_path_value) if log_path_value else None
    state["status"] = "failed"
    state["failed_stage"] = record["stage"]
    state["finished_at"] = datetime.now(timezone.utc).isoformat()
    state["elapsed_seconds"] = _elapsed_between(
        state["started_at"], state["finished_at"]
    )
    _finish_release_stage(
        repo,
        state,
        record,
        started_monotonic,
        status="failed",
        log_path=log_path,
    )
    failed_record = state["stages"][-1]
    _append_transaction_event(
        repo,
        {
            "event": "transaction_failed",
            "transaction_id": state["transaction_id"],
            "base_sha": state["base_sha"],
            "target_sha": state["target_sha"],
            "status": "failed",
            "attempt": state["attempt"],
            "finished_at": state["finished_at"],
            "elapsed_seconds": state["elapsed_seconds"],
            "failed_stage": state["failed_stage"],
            "completed_surfaces": state["completed_surfaces"],
            "pending_surfaces": state["pending_surfaces"],
            "safe_retry_command": state["safe_retry_command"],
            **({"log_path": log_path} if log_path is not None else {}),
        },
    )
    summary = (
        "Release transaction failed: "
        f"transaction_id={state['transaction_id']} "
        f"failed_stage={state['failed_stage']} "
        f"reason={_safe_failure_reason(error)} "
        f"elapsed_seconds={failed_record['elapsed_seconds']} "
        f"log={log_path or 'none'} "
        "completed_surfaces="
        f"{','.join(state['completed_surfaces']) or 'none'} "
        "pending_surfaces="
        f"{','.join(state['pending_surfaces']) or 'none'} "
        "safe_retry_command="
        + json.dumps(state["safe_retry_command"], ensure_ascii=False)
    )
    return ReleaseError(summary)


def _succeed_release_transaction(repo: Path, state: dict[str, Any]) -> None:
    state["status"] = "succeeded"
    state["failed_stage"] = None
    state["finished_at"] = datetime.now(timezone.utc).isoformat()
    state["elapsed_seconds"] = _elapsed_between(
        state["started_at"], state["finished_at"]
    )
    write_release_state(repo, state)
    _append_transaction_event(
        repo,
        {
            "event": "transaction_succeeded",
            "transaction_id": state["transaction_id"],
            "base_sha": state["base_sha"],
            "target_sha": state["target_sha"],
            "status": "succeeded",
            "attempt": state["attempt"],
            "finished_at": state["finished_at"],
            "elapsed_seconds": state["elapsed_seconds"],
            "completed_surfaces": state["completed_surfaces"],
            "pending_surfaces": state["pending_surfaces"],
            "safe_retry_command": state["safe_retry_command"],
        },
    )


def publish_plan(
    plan: ReleasePlan,
    repo: Path,
    *,
    owner_repo: Path,
    message: str,
    env_file: Path | None = None,
    runner: Runner = subprocess.run,
    _lock_held: bool = False,
) -> None:
    repo = _repository_root(repo)
    owner_repo = _repository_root(owner_repo)
    if not _lock_held:
        with release_publish_lock(repo):
            return publish_plan(
                plan,
                repo,
                owner_repo=owner_repo,
                message=message,
                env_file=env_file,
                runner=runner,
                _lock_held=True,
            )
    if not plan.publishable:
        details = ", ".join(plan.blocked_paths) or ", ".join(plan.surfaces)
        raise ReleaseError(f"Release requires manual routing before publish: {details}")
    unsafe_overrides = sorted(
        name for name in _OTA_TEST_ENV_OVERRIDES if os.environ.get(name)
    )
    if unsafe_overrides:
        raise ReleaseError(
            "Production release refuses OTA test/debug override(s): "
            + ", ".join(unsafe_overrides)
        )
    assert_release_source(repo)
    environment = _scrub_environment(os.environ, _MUTATION_ENV_OVERRIDES)
    deploy_env = env_file or Path(
        environment.get("DEPLOY_ENV_FILE", str(owner_repo / ".env"))
    )
    deploy_env = deploy_env.resolve()
    environment["DEPLOY_ENV_FILE"] = str(deploy_env)
    state = _begin_release_transaction(
        plan,
        repo,
        owner_repo=owner_repo,
        env_file=deploy_env,
    )
    environment["OTA_TRANSACTION_ID"] = state["transaction_id"]

    for action in plan.actions:
        if action != "validate" and action in state["completed_actions"]:
            continue
        stage_record, stage_started = _start_release_stage(repo, state, action)
        log_path: str | None = None
        try:
            if action == "validate":
                validation_log = run_validation(plan, repo, runner=runner)
                if validation_log is not None:
                    log_path = str(validation_log)
                assert_release_source(repo)
            else:
                assert_release_source(repo)
                if action == "deploy_backend":
                    command = [str(repo / "deploy.sh"), "--backend", "--yes"]
                elif action == "deploy_all":
                    command = [str(repo / "deploy.sh"), "--all", "--yes"]
                elif action == "mobile_ota":
                    command = [
                        str(repo / "scripts/mobile-ota.sh"),
                        "production",
                        message,
                    ]
                else:
                    raise ReleaseError(f"Action is not safely publishable: {action}")
                completed = runner(
                    command,
                    cwd=repo,
                    check=True,
                    env=environment,
                )
                if completed.returncode != 0:
                    raise subprocess.CalledProcessError(completed.returncode, command)
        except Exception as error:
            raise _fail_release_transaction(
                repo, state, stage_record, stage_started, error
            ) from None
        _mark_action_completed(plan, state, action)
        _finish_release_stage(
            repo,
            state,
            stage_record,
            stage_started,
            status="succeeded",
            log_path=log_path,
        )
    if state["pending_surfaces"]:
        raise ReleaseError(
            "Release transaction finished actions with pending surfaces: "
            + ", ".join(state["pending_surfaces"])
        )
    _succeed_release_transaction(repo, state)


def _plan_for_refs(
    repo: Path,
    base: str,
    target: str,
    *,
    include_partial_state: bool,
) -> ReleasePlan:
    base_sha, target_sha, changes = git_changes(repo, base, target)
    completed = (
        _state_completed_actions(repo, base_sha, target_sha)
        if include_partial_state
        else ()
    )
    native_assets = _native_mobile_assets_for_refs(repo, (base_sha, target_sha))
    return build_plan(
        changes,
        base_sha=base_sha,
        target_sha=target_sha,
        completed_actions=completed,
        native_mobile_assets=native_assets,
    )


def _print_plan(plan: ReleasePlan) -> None:
    print(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "validate", "publish"):
        command = subparsers.add_parser(name)
        command.add_argument("--repo", type=Path, default=ROOT)
        command.add_argument("--base", required=True, help="trusted baseline ref")
        command.add_argument("--target", default="origin/main")
        command.add_argument("--release-worktree", type=Path)
        if name == "publish":
            command.add_argument("--message", default="source-aware production release")
            command.add_argument("--env-file", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        repo = _repository_root(args.repo)
        if args.command == "plan":
            plan = _plan_for_refs(
                repo, args.base, args.target, include_partial_state=True
            )
            _print_plan(plan)
            return 0 if plan.publishable else 2

        if args.command == "validate":
            release_repo = ensure_release_worktree(
                repo, release_path=args.release_worktree
            )
            target_sha = str(_git(release_repo, "rev-parse", args.target))
            exact_main = assert_release_source(release_repo)
            if target_sha != exact_main:
                raise ReleaseError(
                    "Validation/publish target must be exact origin/main"
                )
            plan = _plan_for_refs(
                release_repo,
                args.base,
                exact_main,
                include_partial_state=True,
            )
            _print_plan(plan)
            run_validation(plan, release_repo)
            return 0

        with release_publish_lock(repo):
            release_repo = ensure_release_worktree(
                repo, release_path=args.release_worktree
            )
            target_sha = str(_git(release_repo, "rev-parse", args.target))
            exact_main = assert_release_source(release_repo)
            if target_sha != exact_main:
                raise ReleaseError(
                    "Validation/publish target must be exact origin/main"
                )
            plan = _plan_for_refs(
                release_repo,
                args.base,
                exact_main,
                include_partial_state=True,
            )
            _print_plan(plan)
            if not plan.publishable:
                return 2
            publish_plan(
                plan,
                release_repo,
                owner_repo=_owner_repository(repo),
                message=args.message,
                env_file=args.env_file,
                _lock_held=True,
            )
        return 0
    except (ReleaseError, subprocess.CalledProcessError, OSError) as error:
        print(f"release error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
