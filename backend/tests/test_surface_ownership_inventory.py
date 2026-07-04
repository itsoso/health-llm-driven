"""Surface ownership inventory governance checks."""

from pathlib import Path


def test_surface_ownership_inventory_covers_core_surfaces_and_mobile_entries():
    repo_root = Path(__file__).resolve().parents[2]
    doc = repo_root / "docs/specs/active/2026-06-26-surface-ownership-inventory.md"

    text = doc.read_text(encoding="utf-8")

    for surface in [
        "Mobile",
        "Apple Watch",
        "Rokid",
        "Mac",
        "Web",
        "MCP",  # MCP 作为受控扩展保留
        "Backend",
    ]:
        assert surface in text

    for entry in ["Today", "Agenda", "Capture", "Programs", "Review"]:
        assert entry in text

    for disposition in ["Keep", "Converge", "Archive"]:
        assert disposition in text
