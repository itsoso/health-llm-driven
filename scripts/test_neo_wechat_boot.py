"""Fixed boot-link filesystem tests in synthetic temporary directories only."""
import os
import stat

import pytest

from scripts import neo_wechat_boot as boot


@pytest.fixture
def setup(tmp_path):
    wants = tmp_path / 'multi-user.target.wants'
    wants.mkdir(mode=0o755)
    os.chmod(wants, 0o755)
    fd = os.open(wants, os.O_RDONLY | os.O_DIRECTORY)
    info = os.fstat(fd)
    events = []
    links = boot.BootLinks(fd, (info.st_dev, info.st_ino), guard=lambda: None,
        before_effect=lambda step, unit: events.append((step, unit)),
        owner_uid=os.getuid(), owner_gid=os.getgid(),
        startup_permission=boot._synthetic_boot_permission_for_tests(wants))
    try:
        yield wants, links, events
    finally:
        os.close(fd)


def test_enables_only_two_fixed_links_and_returns_ownership_receipt(setup):
    wants, links, events = setup
    receipt = links.enable()
    assert list(receipt) == ['neo-wechat.service', 'neo-wechat.socket']
    assert set(p.name for p in wants.iterdir()) == set(receipt)
    for unit, value in receipt.items():
        assert value['target'] == '/etc/systemd/system/' + unit
        assert stat.S_ISLNK(value['mode']) and value['uid'] == os.getuid()
        assert value['nlink'] == 1
        assert os.readlink(wants / unit) == value['target']
    assert events == [('enable_boot', unit) for unit in receipt]
    assert links.snapshot(receipt) == receipt


def test_disables_only_original_owned_links_and_preserves_other_units(setup):
    wants, links, events = setup
    receipt = links.enable()
    other = wants / 'health-backend.service'
    other.symlink_to('/synthetic/health.service')
    links.disable(receipt)
    assert list(wants.iterdir()) == [other]
    assert events[-2:] == [('disable_boot', unit) for unit in receipt]


@pytest.mark.parametrize('kind', ['file', 'foreign_link', 'same_target_link'])
def test_enable_rejects_any_preexisting_link_before_effect(setup, kind):
    wants, links, events = setup
    path = wants / 'neo-wechat.socket'
    if kind == 'file':
        path.write_text('synthetic')
    else:
        path.symlink_to('/elsewhere' if kind == 'foreign_link' else '/etc/systemd/system/neo-wechat.socket')
    with pytest.raises(boot.BootError, match='precondition'):
        links.enable()
    assert events == []
    assert not (wants / 'neo-wechat.service').is_symlink()


def test_disable_rejects_replacement_even_with_same_target_before_any_unlink(setup):
    wants, links, events = setup
    receipt = links.enable()
    original = wants / 'neo-wechat.socket'
    original.rename(wants / 'held-original')
    original.symlink_to('/etc/systemd/system/neo-wechat.socket')
    with pytest.raises(boot.BootError, match='precondition'):
        links.disable(receipt)
    assert (wants / 'neo-wechat.service').is_symlink()
    assert len(events) == 2


def test_fsync_failure_preserves_partial_link_and_forbids_retry(setup, monkeypatch):
    wants, links, events = setup
    def fail(_fd):
        raise OSError('synthetic-sensitive')
    monkeypatch.setattr(boot.os, 'fsync', fail)
    with pytest.raises(boot.BootError, match='uncertain'):
        links.enable()
    assert (wants / 'neo-wechat.service').is_symlink()
    assert not (wants / 'neo-wechat.socket').is_symlink()
    with pytest.raises(boot.BootError, match='precondition'):
        links.enable()


def test_guard_or_intent_failure_is_sanitized_without_effect(setup):
    wants, links, _events = setup
    def fail(*_args):
        raise RuntimeError('synthetic-sensitive')
    links.before_effect = fail
    with pytest.raises(boot.BootError) as error:
        links.enable()
    assert str(error.value) == 'boot_links_uncertain'
    assert not list(wants.iterdir())


def test_wrong_parent_permissions_fail_before_effect(setup):
    wants, links, events = setup
    os.chmod(wants, 0o775)
    with pytest.raises(boot.BootError, match='precondition'):
        links.enable()
    assert not events


def test_foreign_receipt_names_cannot_select_path(setup):
    wants, links, events = setup
    with pytest.raises(boot.BootError, match='precondition'):
        links.disable({'../outside': {}})
    assert not events and not list(wants.iterdir())


def test_default_startup_permission_blocks_even_with_successful_callback(setup):
    wants, links, events = setup
    links.startup_permission = None
    with pytest.raises(boot.BootError, match='precondition'):
        links.enable()
    assert boot.startup_allowed() is False
    assert not events and not list(wants.iterdir())


def test_raw_completion_dictionary_never_grants_startup(setup):
    wants, links, events = setup
    links.startup_permission = {'completed': True, 'fsync_confirmed': True}
    with pytest.raises(boot.BootError, match='precondition'):
        links.enable()
    assert not events and not list(wants.iterdir())
