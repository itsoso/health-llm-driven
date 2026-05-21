from app.services.supplement_evidence import (
    SUPPLEMENT_EVIDENCE_CATALOG_VERSION,
    get_supplement_evidence_profile,
    get_unresolved_supplement_source_ids,
    list_supplement_evidence_catalog,
    list_supplement_evidence_sources,
)


def test_all_supplement_evidence_sources_resolve():
    assert get_unresolved_supplement_source_ids() == []


def test_catalog_expands_creatine_source_details():
    catalog = list_supplement_evidence_catalog()
    creatine = next(item for item in catalog if item["key"] == "creatine")

    assert creatine["evidence_level"] == "A"
    assert "issn:creatine-position-stand" in creatine["sources"]
    assert any(
        source["source_id"] == "issn:creatine-position-stand"
        and source["authority_level"] == "high"
        and source["url"].startswith("https://")
        for source in creatine["source_details"]
    )


def test_source_registry_contains_reviewed_reference_metadata_only():
    sources = list_supplement_evidence_sources()

    assert sources
    assert all(source["review_status"] == "reviewed" for source in sources)
    assert all(source["license_scope"] == "public_reference" for source in sources)
    assert all(source["url"].startswith("https://") for source in sources)
    for source in sources:
        assert "content" not in source
        assert "raw_text" not in source
        assert "full_text" not in source


def test_profile_lookup_accepts_key_display_name_and_alias():
    by_key = get_supplement_evidence_profile("vitamin_d")
    by_display_name = get_supplement_evidence_profile("维生素 D3")
    by_alias = get_supplement_evidence_profile("vitamin d3")

    assert by_key is not None
    assert by_display_name is not None
    assert by_alias is not None
    assert by_key["key"] == by_display_name["key"] == by_alias["key"] == "vitamin_d"
    assert by_key["source_details"]


def test_catalog_version_is_public_contract():
    assert SUPPLEMENT_EVIDENCE_CATALOG_VERSION == "supplement_evidence_mvp_v1"
