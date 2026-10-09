"""Read-only backend admission using the actual production revision and receipt.

No caller-selected baseline, endpoint, repository or policy path is accepted.
Unknown/ineligible changes retain the existing full CI gate.
"""
import argparse
import configparser
import types
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

STATE = Path("/var/lib/reva-release")
PRODUCTION = Path("/opt/health-app")
_ROOT_UID = 0
_ORIGIN = "https://github.com/itsoso/health-llm-driven.git"


class AdmissionError(Exception):
    pass


def admit(sha, source, gate, scope, production_evidence):
    before = production_evidence()
    base, receipt = before
    bound = (isinstance(base, str) and re.fullmatch(r"[0-9a-f]{40}", base)
             and receipt == {"sha": base, "state": "SUCCEEDED"})
    plan = scope.evaluate_git_scope(source, base, sha) if bound else {"target": "full"}
    if plan.get("target") == "backend-v1":
        result = gate.verify_release(sha, sha, target="backend-v1")
    else:
        result = gate.verify_release(sha, sha)
    if production_evidence() != before:
        raise AdmissionError("production evidence changed during admission")
    return result


def _metadata(metadata, *, directory=False, hardlinks=False):
    correct_type = stat.S_ISDIR(metadata.st_mode) if directory else stat.S_ISREG(metadata.st_mode)
    if (not correct_type or metadata.st_uid != _ROOT_UID or metadata.st_mode & 0o022
            or (not directory and not hardlinks and metadata.st_nlink != 1)):
        raise AdmissionError("unsafe canonical metadata")


def _secure_ancestors(path):
    for ancestor in path.parents:
        _metadata(ancestor.lstat(), directory=True)


def secure(path, *, directory=False, hardlinks=False):
    path = Path(path)
    if not path.is_absolute():
        raise AdmissionError("absolute canonical path required")
    _secure_ancestors(path)
    metadata = path.lstat()
    _metadata(metadata, directory=directory, hardlinks=hardlinks)
    return metadata


def _identity(metadata):
    return (metadata.st_dev, metadata.st_ino, metadata.st_mode, metadata.st_uid,
            metadata.st_gid, metadata.st_nlink, metadata.st_size,
            metadata.st_mtime_ns, metadata.st_ctime_ns)


def read_secure(path, *, limit):
    """Read bounded bytes through a no-follow descriptor with stable identity."""
    path = Path(path)
    before = secure(path)
    if before.st_size > limit:
        raise AdmissionError("oversized canonical proof")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        opened = os.fstat(fd)
        _metadata(opened)
        if _identity(opened) != _identity(before):
            raise AdmissionError("canonical proof changed while opening")
        chunks, size = [], 0
        while True:
            data = os.read(fd, min(65536, limit + 1 - size))
            if not data:
                break
            chunks.append(data)
            size += len(data)
            if size > limit:
                raise AdmissionError("oversized canonical proof")
        after = os.fstat(fd)
        _metadata(after)
        if (_identity(after) != _identity(before)
                or _identity(secure(path)) != _identity(before)):
            raise AdmissionError("canonical proof changed while reading")
        return b"".join(chunks)
    finally:
        os.close(fd)


def git(repo, *args, _raw=False):
    env = {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null",
           "GIT_NO_REPLACE_OBJECTS": "1", "GIT_TERMINAL_PROMPT": "0",
           "GIT_OPTIONAL_LOCKS": "0", "LC_ALL": "C"}
    result = subprocess.run(["/usr/bin/git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false",
                             "-C", str(repo), *args], env=env, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            check=True, timeout=30).stdout
    if len(result) > 2_000_000:
        raise AdmissionError("oversized Git evidence")
    return result if _raw else result.decode("utf-8").strip()


def _walk_error(error):
    raise AdmissionError("Git metadata unavailable") from None


def _object_store(objects):
    secure(objects, directory=True)
    for name in ("alternates", "http-alternates"):
        if os.path.lexists(objects / "info" / name):
            raise AdmissionError("production object cache must not chain alternates")
    for root, directories, files in os.walk(objects, followlinks=False, onerror=_walk_error):
        root = Path(root)
        secure(root, directory=True)
        for name in directories:
            secure(root / name, directory=True)
        for name in files:
            secure(root / name, hardlinks=True)


def validate_git_metadata(repo, *, source=False):
    """Root-controlled Git inputs, matching the existing canonical bootstrap."""
    secure(repo, directory=True)
    directory = repo / ".git"
    secure(directory, directory=True)
    for forbidden in ("commondir", "gitdir", "info/grafts"):
        if os.path.lexists(directory / forbidden):
            raise AdmissionError("indirect Git metadata forbidden")
    raw = read_secure(directory / "config", limit=65536)
    config = configparser.ConfigParser(interpolation=None)
    config.read_string(raw.decode("utf-8"))
    allowed = {"core": {"repositoryformatversion", "filemode", "bare", "logallrefupdates", "ignorecase", "precomposeunicode"},
               'remote "origin"': {"url", "fetch"}}
    origins = {_ORIGIN} if source else {_ORIGIN, "git@github.com:itsoso/health-llm-driven.git"}
    invalid = bool(config.defaults()) or config.get('remote "origin"', 'url', fallback='') not in origins
    for section in config.sections():
        branch = re.fullmatch(r'branch "([A-Za-z0-9][A-Za-z0-9._/-]*)"', section)
        if branch:
            name = branch[1]
            valid_name = (not name.endswith('.') and '..' not in name
                          and all(part and not part.startswith('.') and not part.endswith('.lock')
                                  for part in name.split('/')))
            invalid |= (not valid_name or (source and name != 'main')
                        or set(config[section]) != {'remote', 'merge'}
                        or config.get(section, 'remote', fallback='') != 'origin'
                        or config.get(section, 'merge', fallback='') != 'refs/heads/' + name)
        else:
            invalid |= section not in allowed or bool(set(config[section]) - allowed.get(section, set()))
        invalid |= any(any(ord(char) < 32 or ord(char) == 127 for char in value)
                       for value in config[section].values())
    if invalid:
        raise AdmissionError("noncanonical Git configuration")
    for name in ("HEAD", "index", "packed-refs", "shallow"):
        if os.path.lexists(directory / name):
            secure(directory / name)
        elif name == "HEAD":
            raise AdmissionError("missing Git HEAD")
    refs = directory / "refs"
    if os.path.lexists(refs):
        secure(refs, directory=True)
        for root, directories, files in os.walk(refs, followlinks=False,
                                                onerror=_walk_error):
            for name in directories:
                secure(Path(root) / name, directory=True)
            for name in files:
                secure(Path(root) / name)
    objects = directory / "objects"
    alternate = objects / "info/alternates"
    if source and os.path.lexists(alternate):
        if read_secure(alternate, limit=1024) != (str(PRODUCTION / ".git/objects") + "\n").encode():
            raise AdmissionError("noncanonical source object alternate")
        _object_store(PRODUCTION / ".git/objects")
        # The source store itself must still have only safe metadata. Its one
        # permitted alternate was bound above to the fixed production store.
        for root, directories, files in os.walk(objects, followlinks=False, onerror=_walk_error):
            secure(Path(root), directory=True)
            for name in directories:
                secure(Path(root) / name, directory=True)
            for name in files:
                secure(Path(root) / name, hardlinks=True)
        if os.path.lexists(objects / "info/http-alternates"):
            raise AdmissionError("HTTP object alternate forbidden")
    else:
        _object_store(objects)


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise AdmissionError("duplicate evidence field")
        result[key] = value
    return result


def production_evidence():
    if not os.path.lexists(PRODUCTION):
        return None, None  # Initial installation still requires full CI.
    validate_git_metadata(PRODUCTION)
    base = git(PRODUCTION, "rev-parse", "HEAD^{commit}")
    if not re.fullmatch(r"[0-9a-f]{40}", base):
        raise AdmissionError("invalid production revision")
    if git(PRODUCTION, "status", "--porcelain", "--untracked-files=no"):
        raise AdmissionError("production source is dirty")
    path = STATE / base / "completed.json"
    if not os.path.lexists(path):
        return base, None  # No success proof never authorizes the fast lane.
    raw = read_secure(path, limit=16384)
    return base, json.loads(raw, object_pairs_hook=unique)


def load(name, source, sha):
    if name not in {"trusted_release_gate", "backend_release_scope"}:
        raise AdmissionError("unknown canonical helper")
    path = source / "scripts" / (name + ".py")
    raw = read_secure(path, limit=2_000_000)
    if raw != git(source, "show", sha + ":scripts/" + name + ".py", _raw=True):
        raise AdmissionError("helper differs from canonical source")
    # -B prevents writes, not reads, of pyc. Compile the verified bytes directly
    # so even a valid, ignored bytecode cache cannot substitute executable code.
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), module.__dict__)
    return module


def main():
    try:
        parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
        parser.add_argument("--sha", required=True)
        args = parser.parse_args()
        if os.geteuid() != 0 or not sys.flags.isolated or not re.fullmatch(r"[0-9a-f]{40}", args.sha):
            raise AdmissionError("isolated root and exact SHA required")
        entry = Path(__file__).absolute()
        source = entry.parent.parent
        if source not in (STATE / "bootstrap" / args.sha / "source", STATE / args.sha / "source"):
            raise AdmissionError("canonical source required")
        validate_git_metadata(source, source=True)
        if read_secure(entry, limit=2_000_000) != git(source, "show", args.sha + ":scripts/trusted_backend_admission.py", _raw=True):
            raise AdmissionError("admission source differs from canonical revision")
        if git(source, "rev-parse", "HEAD^{commit}") != args.sha or git(source, "status", "--porcelain", "--untracked-files=all"):
            raise AdmissionError("canonical source differs")
        result = admit(args.sha, source, load("trusted_release_gate", source, args.sha),
                       load("backend_release_scope", source, args.sha), production_evidence)
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception:
        print("backend admission: source, production evidence or CI rejected", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
