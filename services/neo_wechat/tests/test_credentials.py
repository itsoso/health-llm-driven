"""Synthetic Linux credential metadata; native mount/ACL evidence lives in the probe."""
import errno
import os
from pathlib import Path
import stat
import struct
from types import SimpleNamespace

import pytest

from services.neo_wechat import credentials as c

UID = 12345
UNDEFINED = 0xffffffff


def acl(permission=4, uid=UID, changes=None):
    entries = [(1,permission,UNDEFINED),(2,permission,uid),(4,0,UNDEFINED),
               (16,permission,UNDEFINED),(32,0,UNDEFINED)]
    if changes:
        for index, entry in changes.items(): entries[index] = entry
    return struct.pack('<I',2) + b''.join(struct.pack('<HHI',*e) for e in entries)


def info(mode=0o440, uid=0, directory=False, nlink=1, size=12):
    return SimpleNamespace(st_mode=(stat.S_IFDIR if directory else stat.S_IFREG)|mode,
                           st_uid=uid,st_gid=999,st_nlink=nlink,st_size=size)


@pytest.mark.parametrize('directory',[False,True])
@pytest.mark.parametrize('acl_form',[False,True])
def test_only_exact_systemd_forms(directory,acl_form):
    permission = 5 if directory else 4
    mode = permission<<6 | (permission<<3 if acl_form else 0)
    result = c.validate_credential_metadata(info(mode,0 if acl_form else UID,directory),
        acl(permission) if acl_form else None, UID,directory=directory)
    assert result['access_model'] == ('root_owner_service_uid_read_acl' if acl_form else 'service_owner_read_only')


@pytest.mark.parametrize('metadata,access,default',[
    (info(0o440,UID),None,None), (info(0o400,0),None,None),
    (info(0o600,UID),None,None), (info(0o444),acl(),None),
    (info(0o440,UID),acl(),None), (info(),acl(uid=UID+1),None),
    (info(),acl(changes={2:(4,4,UNDEFINED)}),None),
    (info(),acl(changes={4:(32,4,UNDEFINED)}),None),
    (info(),acl(changes={1:(2,6,UID)}),None),
    (info(),acl(changes={3:(16,6,UNDEFINED)}),None),
    (info(),acl()+struct.pack('<HHI',2,4,UID+1),None),
    (info(),b'bad',None), (info(),b'\x03'+acl()[1:],None),
    (info(nlink=2),acl(),None), (info(size=65537),acl(),None),
    (info(),acl(),acl()), (info(mode=0o4440),acl(),None),
])
def test_adversarial_metadata_fails_closed(metadata,access,default):
    with pytest.raises(c.CredentialError,match='^unsafe_credential$'):
        c.validate_credential_metadata(metadata,access,UID,default_acl=default)


def test_directory_is_exact_and_default_acl_denied():
    for metadata,access,default in [
        (info(0o700,UID,True),None,None), (info(0o550,0,True),None,None),
        (info(0o550,0,True),acl(4),None), (info(0o550,0,True),acl(5),acl(5)),
        (info(0o500,UID,False),None,None),
    ]:
        with pytest.raises(c.CredentialError):
            c.validate_credential_metadata(metadata,access,UID,directory=True,default_acl=default)


@pytest.mark.parametrize('error,allowed',[(errno.ENODATA,True),(errno.EOPNOTSUPP,True),(errno.EIO,False),(errno.EACCES,False)])
def test_xattr_failures_are_not_silently_treated_as_absence(monkeypatch,error,allowed):
    def failed(*args): raise OSError(error,'sensitive detail')
    monkeypatch.setattr(c.os,'getxattr',failed,raising=False)
    if allowed: assert c.credential_xattr(10,'system.posix_acl_access') is None
    else:
        with pytest.raises(c.CredentialError,match='^unsafe_credential$'):
            c.credential_xattr(10,'system.posix_acl_access')


def test_read_only_mount_required(monkeypatch):
    monkeypatch.setattr(c.os,'fstat',lambda fd:info())
    monkeypatch.setattr(c,'credential_xattr',lambda fd,name:acl() if name.endswith('_access') else None)
    monkeypatch.setattr(c.os,'fstatvfs',lambda fd:SimpleNamespace(f_flag=0))
    with pytest.raises(c.CredentialError): c.credential_fd_metadata(10,UID)
    monkeypatch.setattr(c.os,'fstatvfs',lambda fd:SimpleNamespace(f_flag=os.ST_RDONLY))
    assert c.credential_fd_metadata(10,UID)['mount_read_only'] is True


@pytest.fixture
def synthetic(tmp_path,monkeypatch):
    directory = tmp_path.resolve() / 'credentials'
    directory.mkdir(mode=0o700)
    target = directory / 'synthetic'
    target.write_bytes(b'public synthetic value')
    target.chmod(0o400)
    directory.chmod(0o500)
    monkeypatch.setattr(c,'credential_xattr',lambda *args:None)
    monkeypatch.setattr(c.os,'fstatvfs',lambda fd:SimpleNamespace(f_flag=os.ST_RDONLY))
    yield directory,target
    directory.chmod(0o700)
    if target.exists() and not target.is_symlink(): target.chmod(0o600)


def test_real_bounded_reader_private_owner_with_mock_readonly_mount(synthetic):
    directory,target = synthetic
    raw,report = c.read_credential_with_metadata(directory,'synthetic')
    assert raw == b'public synthetic value'
    assert report['directory']['mode'] == '0500'
    assert report['file']['mode'] == '0400'
    assert c.read_credential(directory,'synthetic') == raw
    with pytest.raises(c.CredentialError): c.read_credential(directory,'synthetic',max_bytes=4)


def test_real_reader_exact_root_acl_with_mock_linux_metadata(synthetic,monkeypatch):
    directory,target = synthetic
    actual_fstat = os.fstat
    def root_acl_metadata(fd):
        actual = actual_fstat(fd)
        is_dir = stat.S_ISDIR(actual.st_mode)
        return info(0o550 if is_dir else 0o440,0,is_dir,actual.st_nlink,actual.st_size)
    monkeypatch.setattr(c.os,'fstat',root_acl_metadata)
    monkeypatch.setattr(c,'credential_xattr',lambda fd,name:
        acl(5 if stat.S_ISDIR(actual_fstat(fd).st_mode) else 4,os.geteuid()) if name.endswith('_access') else None)
    raw,report = c.read_credential_with_metadata(directory,'synthetic')
    assert raw == b'public synthetic value'
    assert report['file']['access_model'] == 'root_owner_service_uid_read_acl'


@pytest.mark.parametrize('name',['../synthetic','/synthetic','.','..','sub/file','bad\x00name',''])
def test_untrusted_names_rejected(synthetic,name):
    directory,_ = synthetic
    with pytest.raises(c.CredentialError): c.read_credential(directory,name)


def test_symlinks_and_hardlinks_rejected(synthetic,tmp_path):
    directory,target = synthetic
    directory.chmod(0o700)
    (directory/'link').symlink_to(target)
    os.link(target,directory/'hard')
    directory.chmod(0o500)
    for name in ('link','hard','synthetic'):
        with pytest.raises(c.CredentialError): c.read_credential(directory,name)
    shortcut = tmp_path/'shortcut'
    shortcut.symlink_to(directory,target_is_directory=True)
    with pytest.raises(c.CredentialError): c.read_credential(shortcut,'synthetic')


def test_symlink_ancestor_rejected(synthetic,tmp_path):
    directory,_ = synthetic
    parent_link = tmp_path/'parent-link'
    parent_link.symlink_to(directory.parent,target_is_directory=True)
    with pytest.raises(c.CredentialError): c.read_credential(parent_link/'credentials','synthetic')


def test_actual_writable_mount_is_rejected(synthetic,monkeypatch):
    directory,_ = synthetic
    monkeypatch.setattr(c.os,'fstatvfs',lambda fd:SimpleNamespace(f_flag=0))
    with pytest.raises(c.CredentialError,match='^unsafe_credential$'):
        c.read_credential(directory,'synthetic')


def test_fifo_rejected_without_blocking(synthetic):
    directory,_ = synthetic
    directory.chmod(0o700)
    os.mkfifo(directory/'fifo',0o400)
    directory.chmod(0o500)
    with pytest.raises(c.CredentialError): c.read_credential(directory,'fifo')


def test_broad_group_directory_rejected_before_content_read(synthetic,monkeypatch):
    directory,_ = synthetic
    directory.chmod(0o550)
    calls = []
    monkeypatch.setattr(c.os,'read',lambda *args:calls.append(args))
    with pytest.raises(c.CredentialError): c.read_credential(directory,'synthetic')
    assert calls == []


def test_short_reads_remain_bounded_and_complete(synthetic,monkeypatch):
    directory,_ = synthetic
    actual_read = os.read
    monkeypatch.setattr(c.os,'read',lambda fd,size:actual_read(fd,min(size,3)))
    assert c.read_credential(directory,'synthetic') == b'public synthetic value'


@pytest.mark.parametrize('uid',[0,-1,True,0xffffffff,'12345'])
def test_invalid_service_uid_rejected(uid):
    with pytest.raises(c.CredentialError): c.validate_credential_metadata(info(),acl(),uid)


def test_validation_remains_enforced_under_python_optimization():
    import subprocess
    import sys
    code = '''
from types import SimpleNamespace
import stat
from services.neo_wechat.credentials import validate_credential_metadata, CredentialError
info = SimpleNamespace(st_mode=stat.S_IFREG|0o444,st_uid=12345,st_gid=12345,st_nlink=1,st_size=1)
try: validate_credential_metadata(info,None,12345)
except CredentialError: raise SystemExit(0)
raise SystemExit(1)
'''
    result = subprocess.run([sys.executable,'-O','-c',code],capture_output=True,text=True)
    assert result.returncode == 0,result.stderr


def test_linux_ancestors_use_path_only_and_final_directory_is_readable(monkeypatch):
    calls = []
    path_flag = 0x200000  # Linux O_PATH; only recorded by this synthetic open.
    monkeypatch.setattr(c.os,'O_PATH',path_flag,raising=False)
    def opened(path,flags,**kwargs):
        calls.append((path,flags,kwargs.get('dir_fd')))
        return 10+len(calls)
    monkeypatch.setattr(c.os,'open',opened)
    monkeypatch.setattr(c.os,'close',lambda fd:None)
    assert c._directory_fd('/run/credentials/fixture') == 14
    assert [row[0] for row in calls] == ['/','run','credentials','fixture']
    assert all(row[1] & path_flag for row in calls[:-1])
    assert calls[-1][1] & path_flag == 0
    assert all(row[1] & os.O_NOFOLLOW and row[1] & os.O_DIRECTORY for row in calls)
    assert [row[2] for row in calls] == [None,11,12,13]


@pytest.mark.skipif(not hasattr(os,'O_PATH'),reason='Native Linux O_PATH traversal; portable flag contract tested separately')
def test_real_traverse_only_ancestor(synthetic):
    directory,_ = synthetic
    parent = directory.parent
    previous = stat.S_IMODE(parent.stat().st_mode)
    parent.chmod(0o111)
    try:
        assert c.read_credential(directory,'synthetic') == b'public synthetic value'
    finally:
        parent.chmod(previous)
