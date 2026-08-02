from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.utils.runtime_data import runtime_data_dir, runtime_data_path


def test_production_runtime_data_is_outside_checkout(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("HEALTH_RUNTIME_DATA_DIR", raising=False)

    assert runtime_data_dir() == Path("/var/lib/health-app/runtime")
    assert runtime_data_path("gene_knowledge.json") == Path(
        "/var/lib/health-app/runtime/gene_knowledge.json"
    )


def test_development_runtime_data_preserves_repo_local_default(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("HEALTH_RUNTIME_DATA_DIR", raising=False)

    root = runtime_data_dir()

    assert root.name == "data"
    assert root.parent.name == "backend"
    assert runtime_data_path("knowledge_base") == root / "knowledge_base"


def test_runtime_data_override_must_be_absolute(monkeypatch, tmp_path):
    monkeypatch.setenv("HEALTH_RUNTIME_DATA_DIR", str(tmp_path))
    assert runtime_data_dir() == tmp_path

    monkeypatch.setenv("HEALTH_RUNTIME_DATA_DIR", "relative/runtime")
    with pytest.raises(ValueError, match="absolute"):
        runtime_data_dir()


def test_production_runtime_override_cannot_point_into_checkout(monkeypatch):
    from app.utils import runtime_data

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv(
        "HEALTH_RUNTIME_DATA_DIR",
        str(runtime_data._BACKEND_DATA_DIR),
    )

    with pytest.raises(ValueError, match="outside the Git checkout"):
        runtime_data_dir()


def test_runtime_data_path_rejects_traversal(monkeypatch, tmp_path):
    monkeypatch.setenv("HEALTH_RUNTIME_DATA_DIR", str(tmp_path))

    with pytest.raises(ValueError, match="single safe path component"):
        runtime_data_path("../outside")


def test_legacy_vectorstore_defaults_to_external_production_state(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("HEALTH_RUNTIME_DATA_DIR", raising=False)

    from app.services.knowledge import vectorstore

    monkeypatch.setattr(vectorstore, "CHROMA_AVAILABLE", False)
    service = vectorstore.VectorStoreService()

    assert service.persist_directory == (
        "/var/lib/health-app/runtime/knowledge_base"
    )


def test_gene_registry_default_uses_external_production_state(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("HEALTH_RUNTIME_DATA_DIR", raising=False)
    monkeypatch.delenv("HEALTH_GENE_KNOWLEDGE_PATH", raising=False)

    from app.services import gene_rules_registry

    assert gene_rules_registry.default_path() == Path(
        "/var/lib/health-app/runtime/gene_knowledge.json"
    )


@pytest.mark.parametrize(
    "configured",
    (
        "backend/data/gene_knowledge.json",
        str(
            Path(__file__).resolve().parents[1]
            / "data"
            / "gene_knowledge.json"
        ),
    ),
)
def test_production_gene_override_must_be_absolute_and_outside_checkout(
    monkeypatch,
    configured,
):
    from app.services import gene_rules_registry

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("HEALTH_GENE_KNOWLEDGE_PATH", configured)

    with pytest.raises(ValueError):
        gene_rules_registry.default_path()


def test_gene_registry_payload_write_is_atomic_and_private(
    monkeypatch, tmp_path
):
    from app.services import gene_rules_registry

    target = tmp_path / "gene_knowledge.json"
    gene_rules_registry._atomic_write_payload(target, {"version": "new"})

    assert json.loads(target.read_text(encoding="utf-8")) == {
        "version": "new"
    }
    assert target.stat().st_mode & 0o777 == 0o600
    assert list(tmp_path.glob(".gene_knowledge.json.*")) == []

    original = target.read_bytes()

    def fail_replace(source, destination):
        raise OSError("injected replace failure")

    monkeypatch.setattr(gene_rules_registry.os, "replace", fail_replace)
    with pytest.raises(OSError, match="injected"):
        gene_rules_registry._atomic_write_payload(
            target, {"version": "partial"}
        )

    assert target.read_bytes() == original
    assert list(tmp_path.glob(".gene_knowledge.json.*")) == []


def test_gene_registry_post_rename_sync_failure_keeps_memory_with_disk(
    monkeypatch,
    tmp_path,
):
    from app.services import gene_rules_registry

    target = tmp_path / "gene_knowledge.json"
    target.write_text('{"version":"old"}\n', encoding="utf-8")
    monkeypatch.setattr(gene_rules_registry, "DEFAULT_PATH", target)
    old_registry = gene_rules_registry._registry
    old_signature = gene_rules_registry._registry_signature
    gene_rules_registry._registry = gene_rules_registry.GeneRulesRegistry(
        path=target
    )
    gene_rules_registry._registry.load()
    real_fsync = gene_rules_registry.os.fsync
    fsync_calls = 0

    def fail_directory_fsync(descriptor):
        nonlocal fsync_calls
        fsync_calls += 1
        if fsync_calls == 2:
            raise OSError("injected directory fsync failure")
        return real_fsync(descriptor)

    monkeypatch.setattr(
        gene_rules_registry.os,
        "fsync",
        fail_directory_fsync,
    )
    try:
        with pytest.raises(
            gene_rules_registry.AtomicPayloadCommitError,
            match="directory fsync",
        ):
            gene_rules_registry.reload_from_payload({"version": "new"})

        assert json.loads(target.read_text(encoding="utf-8"))["version"] == (
            "new"
        )
        assert gene_rules_registry.get_registry().version == "new"
    finally:
        gene_rules_registry._registry = old_registry
        gene_rules_registry._registry_signature = old_signature


def test_gene_registry_detects_atomic_replace_from_another_worker(
    monkeypatch,
    tmp_path,
):
    from app.services import gene_rules_registry

    target = tmp_path / "gene_knowledge.json"
    target.write_text('{"version":"old"}\n', encoding="utf-8")
    monkeypatch.setattr(gene_rules_registry, "DEFAULT_PATH", target)
    old_registry = gene_rules_registry._registry
    old_signature = gene_rules_registry._registry_signature
    gene_rules_registry._registry = None
    gene_rules_registry._registry_signature = None
    try:
        assert gene_rules_registry.get_registry().version == "old"

        gene_rules_registry._atomic_write_payload(
            target,
            {"version": "new"},
        )

        assert gene_rules_registry.get_registry().version == "new"
    finally:
        gene_rules_registry._registry = old_registry
        gene_rules_registry._registry_signature = old_signature


def test_gene_registry_never_caches_new_signature_with_old_snapshot(
    monkeypatch,
    tmp_path,
):
    from app.services import gene_rules_registry

    target = tmp_path / "gene_knowledge.json"
    target.write_text('{"version":"old"}\n', encoding="utf-8")
    monkeypatch.setattr(gene_rules_registry, "DEFAULT_PATH", target)
    old_registry = gene_rules_registry._registry
    old_signature = gene_rules_registry._registry_signature
    gene_rules_registry._registry = None
    gene_rules_registry._registry_signature = None
    real_read = gene_rules_registry.os.read
    replaced = False

    def replace_after_read(descriptor, size):
        nonlocal replaced
        chunk = real_read(descriptor, size)
        if chunk and not replaced:
            replaced = True
            gene_rules_registry._atomic_write_payload(
                target,
                {"version": "new"},
            )
        return chunk

    monkeypatch.setattr(
        gene_rules_registry.os,
        "read",
        replace_after_read,
    )
    try:
        assert gene_rules_registry.get_registry().version == "old"
        assert (
            gene_rules_registry._registry_signature
            != gene_rules_registry._path_signature(target)
        )

        monkeypatch.setattr(
            gene_rules_registry.os,
            "read",
            real_read,
        )
        assert gene_rules_registry.get_registry().version == "new"
    finally:
        gene_rules_registry._registry = old_registry
        gene_rules_registry._registry_signature = old_signature
