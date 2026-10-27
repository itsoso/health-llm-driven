#!/usr/bin/env python3
"""One fixed GitHub read credential refresh for the sealed a8 incident.

Inspection is read-only and does not claim live CI verification. Apply requires
its digest, explicit fixed authorization and one bounded JSON stdin credential.
Only the existing trusted CI gate consumes the token; it never enters argv,
environment, audit records or diagnostic output. App identity and permission
provenance belong to the separately reviewed mint provider, not token syntax.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time

ATTEMPT = 'exam-a8-read-credential-v1'
FAILED = 'a8cd1e7635eb697c0f0bc528382c98b3602893c3'
OLD_SHA256 = 'e3b759a2e51b676de917501d2466f0f6de793c6d3bf9ddaa95b62fd1239e02a8'
REPOSITORY = 'itsoso/health-llm-driven'
CREDENTIAL = Path('/etc/reva-github-api/credential.json')
STATE = Path('/var/lib/reva-release')
SYSTEM_PYTHON = '/usr/bin/python3.12'
MAX_INPUT = 8192
MAX_TOKEN = 4096
ENV = {'PATH':'/usr/bin:/bin', 'HOME':'/nonexistent', 'LC_ALL':'C',
       'GIT_CONFIG_NOSYSTEM':'1', 'GIT_CONFIG_GLOBAL':'/dev/null',
       'GIT_CONFIG_SYSTEM':'/dev/null', 'GIT_NO_REPLACE_OBJECTS':'1',
       'GIT_OPTIONAL_LOCKS':'0', 'GIT_TERMINAL_PROMPT':'0'}
IDENTITY_FIELDS = ('st_dev','st_ino','st_uid','st_gid','st_mode','st_nlink',
                   'st_size','st_mtime_ns','st_ctime_ns')
DIRECTORY_FIELDS = ('st_dev','st_ino','st_uid','st_gid','st_mode')


class CredentialError(RuntimeError):
    """Static messages only; never include OS, JSON or subprocess exceptions."""


def need(condition, message='fixed credential evidence rejected'):
    if not condition:
        raise CredentialError(message)


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def identity(info, fields=IDENTITY_FIELDS):
    return {key:getattr(info,key) for key in fields}


def unique(pairs):
    value = dict(pairs)
    need(len(value) == len(pairs), 'duplicate incoming credential fields')
    return value


def validate_incoming(value, now):
    need(isinstance(value, dict) and set(value) == {'repository','token','expires_at'}, 'invalid incoming credential')
    need(value['repository'] == REPOSITORY and type(value['expires_at']) is int and
         120 <= value['expires_at'] - now <= 3600 and
         isinstance(value['token'], str) and 1 <= len(value['token']) <= MAX_TOKEN and
         re.fullmatch('[A-Za-z0-9_.-]+', value['token']) is not None, 'invalid or expired incoming credential')
    return value


def read_incoming(stream, *, now=None):
    try:
        raw = stream.read(MAX_INPUT + 1)
        need(isinstance(raw, bytes) and 0 < len(raw) <= MAX_INPUT, 'invalid incoming credential size')
        return validate_incoming(json.loads(raw, object_pairs_hook=unique), time.time() if now is None else now)
    except CredentialError:
        raise
    except Exception:
        raise CredentialError('incoming credential unavailable or malformed') from None


class SecureDirectory:
    """Retain every directory descriptor and verify the original linked chain."""
    def __init__(self, path, *, _anchor=Path('/'), _owner_uid=0):
        self.path, self.anchor, self.owner = Path(path), Path(_anchor), _owner_uid
        self.chain = []
        self.parts = Path(os.path.relpath(self.path, self.anchor)).parts
        need(self.path.is_absolute() and self.anchor.is_absolute() and
             not any(part in ('','..') for part in self.parts), 'invalid protected directory')
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        try:
            fd = os.open(self.anchor, flags)
            self.chain.append((fd, os.fstat(fd)))
            for part in self.parts:
                if part == '.':
                    continue
                fd = os.open(part, flags, dir_fd=fd)
                self.chain.append((fd, os.fstat(fd)))
            self.fd = fd
            self.check()
        except Exception:
            self.close()
            raise CredentialError('protected directory unavailable or unsafe') from None

    def check(self):
        try:
            for index, (fd, before) in enumerate(self.chain):
                current = os.fstat(fd)
                need(stat.S_ISDIR(current.st_mode) and current.st_uid == self.owner and not current.st_mode & 0o022)
                need(identity(before, DIRECTORY_FIELDS) == identity(current, DIRECTORY_FIELDS))
                named = (os.stat(self.anchor, follow_symlinks=False) if index == 0 else
                         os.stat(self.parts[index-1], dir_fd=self.chain[index-1][0], follow_symlinks=False))
                need(identity(named, DIRECTORY_FIELDS) == identity(current, DIRECTORY_FIELDS), 'protected directory linkage changed')
        except CredentialError:
            raise
        except Exception:
            raise CredentialError('protected directory changed') from None

    def exists(self, name):
        self.check()
        try:
            os.stat(name, dir_fd=self.fd, follow_symlinks=False)
            return True
        except FileNotFoundError:
            return False
        except Exception:
            raise CredentialError('protected entry unavailable') from None

    def read(self, name):
        self.check()
        fd = None
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=self.fd)
            before = os.fstat(fd)
            need(stat.S_ISREG(before.st_mode) and before.st_uid == self.owner and
                 stat.S_IMODE(before.st_mode) == 0o600 and before.st_nlink == 1 and
                 0 < before.st_size <= MAX_INPUT, 'unsafe protected credential file')
            chunks = []
            remaining = MAX_INPUT + 1
            while remaining:
                chunk = os.read(fd, remaining)
                if not chunk: break
                chunks.append(chunk); remaining -= len(chunk)
            raw = b''.join(chunks)
            after = os.fstat(fd)
            named = os.stat(name, dir_fd=self.fd, follow_symlinks=False)
            need(len(raw) == before.st_size and identity(before) == identity(after) == identity(named), 'protected credential changed during read')
            self.check()
            return raw, identity(after)
        except CredentialError:
            raise
        except Exception:
            raise CredentialError('protected credential unavailable') from None
        finally:
            if fd is not None: os.close(fd)

    def write_once(self, name, raw):
        self.check()
        fd = None
        try:
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=self.fd)
            with os.fdopen(fd, 'wb') as stream:
                fd = None
                stream.write(raw); stream.flush(); os.fsync(stream.fileno())
            self.check(); os.fsync(self.fd)
        except Exception:
            raise CredentialError('protected audit write failed') from None
        finally:
            if fd is not None: os.close(fd)

    def close(self):
        for fd, _ in reversed(self.chain): os.close(fd)
        self.chain = []

    def __enter__(self): return self
    def __exit__(self, *args): self.close()


class CredentialStore:
    def __init__(self, path, *, _anchor=Path('/'), _owner_uid=0):
        self.path = Path(path)
        self.directory = SecureDirectory(self.path.parent, _anchor=_anchor, _owner_uid=_owner_uid)
        self.anchor, self.owner = Path(_anchor), _owner_uid

    def original(self):
        raw, proof = self.directory.read(self.path.name)
        need(digest(raw) == OLD_SHA256, 'original credential pin differs')
        return {'sha256':digest(raw), 'identity':proof}

    def replace(self, incoming, expected, check):
        directory = self.directory
        need(self.original() == expected, 'original credential changed')
        raw = encoded(incoming)
        temporary = '.credential.' + ATTEMPT + '.tmp'
        fd = None; created = None
        try:
            directory.check()
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                         0o600, dir_fd=directory.fd)
            created = os.fstat(fd)
            with os.fdopen(fd, 'wb') as stream:
                fd = None
                stream.write(raw); stream.flush(); os.fsync(stream.fileno())
            written, temporary_identity = directory.read(temporary)
            need(written == raw and temporary_identity['st_dev'] == created.st_dev and
                 temporary_identity['st_ino'] == created.st_ino, 'incoming credential temporary readback differs')
            check()
            need(self.original() == expected, 'original credential changed before replacement')
            final_temporary, final_identity = directory.read(temporary)
            need(final_temporary == raw and final_identity == temporary_identity, 'incoming credential temporary changed')
            directory.check()
            os.replace(temporary, self.path.name, src_dir_fd=directory.fd, dst_dir_fd=directory.fd)
            os.fsync(directory.fd)
            observed, _ = directory.read(self.path.name)
            need(observed == raw, 'credential replacement readback differs')
            return digest(raw)
        except Exception:
            raise CredentialError('credential replacement failed; inspect fixed attempt') from None
        finally:
            if fd is not None: os.close(fd)
            if created is not None:
                try:
                    current = os.stat(temporary, dir_fd=directory.fd, follow_symlinks=False)
                except FileNotFoundError:
                    current = None
                if current is not None:
                    need(current.st_dev == created.st_dev and current.st_ino == created.st_ino,
                         'credential temporary identity changed; retain attempt')
                    os.unlink(temporary, dir_fd=directory.fd); os.fsync(directory.fd)

    def __enter__(self): return self
    def __exit__(self, *args): self.directory.close()


def run_gate(source, sha, token):
    """Existing canonical TLS/API/CI checks, with no token-bearing env or argv."""
    try:
        subprocess.run([SYSTEM_PYTHON,'-I','-S','-B',str(source / 'scripts/trusted_release_gate.py'),
                        '--token-stdin','--sha',sha,'--workflow-sha',sha,'--observed-main',sha],
                       input=token.encode('ascii'), env=ENV, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, check=True, timeout=90)
    except Exception:
        raise CredentialError('incoming credential failed exact current-main CI gate') from None


def refresh(adapter, store, incoming, audit, gate, evidence_sha256=None, *, accept=False, now=time.time):
    """Inspect without a token. One apply consumes a fresh credential only after CI."""
    need((evidence_sha256 is not None) == accept, 'digest and fixed authorization required together')
    need(evidence_sha256 is None or re.fullmatch('[a-f0-9]{64}', evidence_sha256), 'invalid inspection digest')
    audit = Path(audit)
    with SecureDirectory(audit.parent, _anchor=store.anchor, _owner_uid=store.owner) as parent:
        need(not parent.exists(audit.name), 'fixed credential attempt already exists; retry forbidden')
        try:
            original = adapter.snapshot(); adapter.stopped()
            old = store.original()
            need(adapter.snapshot() == original, 'incident changed during inspection'); adapter.stopped()
            evidence = {'attempt':ATTEMPT, 'recovery_sha':adapter.recovery_sha, 'failed_sha':FAILED,
                        'original':original, 'original_credential':old}
            inspected = digest(encoded(evidence))
            if evidence_sha256 is None:
                need(incoming is None, 'inspection accepts no credential')
                return {'state':'INSPECTED', 'attempt':ATTEMPT, 'evidence_sha256':inspected,
                        'recovery_sha':adapter.recovery_sha, 'ci_verified':False}
            need(evidence_sha256 == inspected, 'inspection digest changed')
            validate_incoming(incoming, now())
            gate()
            validate_incoming(incoming, now())
            need(adapter.snapshot() == original, 'incident changed after CI gate'); adapter.stopped()
            need(store.original() == old, 'original credential changed after CI gate')
        except Exception:
            raise CredentialError('credential inspection or pre-apply gate rejected') from None
        parent.check()
        os.mkdir(audit.name, 0o700, dir_fd=parent.fd); os.fsync(parent.fd)
        with SecureDirectory(audit, _anchor=store.anchor, _owner_uid=store.owner) as record:
            phase = 'intent'
            try:
                record.write_once('intent.json', encoded({**evidence, 'evidence_sha256':inspected,
                    'incoming_sha256':digest(encoded(incoming)), 'incoming_expires_at':incoming['expires_at'],
                    'ci_verified':True}))
                def guard():
                    need(adapter.snapshot() == original, 'incident changed before credential replacement')
                    adapter.stopped(); validate_incoming(incoming, now()); record.check(); parent.check()
                phase = 'replacement'
                new_hash = store.replace(incoming, old, guard)
                phase = 'postcheck'
                guard()
                result = {'state':'CREDENTIAL_REPLACED', 'attempt':ATTEMPT,
                          'recovery_sha':adapter.recovery_sha, 'failed_sha':FAILED,
                          'evidence_sha256':inspected, 'credential_sha256':new_hash,
                          'credential_expires_at':incoming['expires_at'], 'ci_verified':True,
                          'original_incident_preserved':True, 'services_changed':False,
                          'database_changed':False}
                phase = 'completed'
                record.write_once('completed.json', encoded(result))
                return result
            except BaseException:
                record.write_once('failure.json', encoded({'state':'NEEDS_OPERATOR', 'attempt':ATTEMPT,
                    'phase':phase, 'automatic_retry_forbidden':True}))
                raise CredentialError('fixed credential attempt failed; preserve evidence and do not retry') from None


def context(sha):
    need(os.geteuid() == 0 and sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode
         and not sys.flags.optimize and sys.executable == SYSTEM_PYTHON and
         'SSH_ORIGINAL_COMMAND' not in os.environ, 'isolated root system operator required')
    need(isinstance(sha,str) and re.fullmatch('[a-f0-9]{40}',sha))
    source = STATE / 'bootstrap' / sha / 'source'
    entry = source / 'scripts/exam_recovery_credential.py'
    need(Path(__file__).absolute() == entry, 'canonical credential operator path required')
    dependency = entry.with_name('exam_release_recovery.py')
    for path in [*reversed(entry.parents), entry, dependency]:
        info = path.lstat()
        need(info.st_uid == 0 and not info.st_mode & 0o022 and
             (stat.S_ISDIR(info.st_mode) if path in entry.parents else stat.S_ISREG(info.st_mode) and info.st_nlink == 1))
    need(not os.path.lexists(entry.parent / '__pycache__'), 'cached credential operator rejected')
    spec = importlib.util.spec_from_file_location('exam_credential_incident', dependency)
    recovery = importlib.util.module_from_spec(spec)
    exec(compile(dependency.read_bytes(), str(dependency), 'exec', dont_inherit=True), recovery.__dict__)
    checked, bootstrap, server = recovery.context(sha, verify_ci=False)
    need(checked == source)
    return recovery, source, bootstrap, server


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--sha', required=True)
    parser.add_argument('--evidence-sha256')
    parser.add_argument('--accept-exam-a8-read-credential-v1', action='store_true')
    args = parser.parse_args()
    need((args.evidence_sha256 is not None) == args.accept_exam_a8_read_credential_v1)
    recovery, source, bootstrap, server = context(args.sha)
    os.umask(0o077)
    core = recovery.load(source/'scripts/recover_contained_services.py','exam_credential_core',bootstrap)
    reset = recovery.load(source/'scripts/trusted_review_reset.py','exam_credential_reset',bootstrap)
    token_path = bootstrap.BUSINESS_LEASE / 'token'
    reset._secure_lease_path(server, token_path, private=True)
    raw = token_path.read_bytes()
    need(re.fullmatch(rb'[A-Za-z0-9._:-]{1,200}\n', raw))
    lease_token = raw[:-1].decode('ascii')
    launcher = STATE / 'launcher.lock'
    bootstrap.secure(launcher, private=True)
    fd = os.open(launcher, os.O_RDWR | os.O_NOFOLLOW)
    build = None; adapter = None
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        build = bootstrap._acquire_existing_build_lock(FAILED)
        def check():
            bootstrap._assert_original_lock(launcher, fd)
            core._check_original_build_lock(bootstrap, FAILED, build)
        check(); bootstrap._recovery_process_proof()
        adapter = recovery.Adapter(source,bootstrap,server,core,lease_token,check)
        incoming = read_incoming(sys.stdin.buffer) if args.accept_exam_a8_read_credential_v1 else None
        with CredentialStore(CREDENTIAL) as store:
            result = refresh(adapter,store,incoming,STATE/ATTEMPT,
                lambda:run_gate(source,args.sha,incoming['token']),args.evidence_sha256,
                accept=args.accept_exam_a8_read_credential_v1)
        check(); print(json.dumps(result,sort_keys=True)); return 0
    finally:
        if adapter is not None: adapter.close()
        if build is not None: os.close(build)
        os.close(fd)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception:
        print('EXAM_CREDENTIAL_RECOVERY_BLOCKED: preserve original incident and fixed attempt evidence',file=sys.stderr)
        raise SystemExit(70) from None
