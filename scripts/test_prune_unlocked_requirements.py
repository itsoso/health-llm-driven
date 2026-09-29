from pathlib import Path
from types import SimpleNamespace
import importlib.util
import pytest


def load():
    path = Path(__file__).resolve().parents[1] / 'backend/scripts/prune_unlocked_requirements.py'
    spec = importlib.util.spec_from_file_location('prune_lock', path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_prune_preserves_lock_and_normalizes_names(tmp_path):
    lock = tmp_path / 'lock'
    lock.write_text('pip==26.2\nfoo-bar==1.0\n')
    distributions = [SimpleNamespace(metadata={'Name': name}) for name in ('pip','Foo_Bar','pypdf','paramiko','pytest','ecdsa','setuptools')]
    assert load().unlocked(lock, distributions) == ['ecdsa','paramiko','pypdf','pytest','setuptools']


@pytest.mark.parametrize('body', ['foo==1\n', 'pip>=26\n','pip==26;python_version>3\n'])
def test_prune_refuses_incomplete_or_ambiguous_lock(tmp_path, body):
    lock = tmp_path / 'lock'
    lock.write_text(body)
    with pytest.raises(ValueError):
        load().unlocked(lock, [])
