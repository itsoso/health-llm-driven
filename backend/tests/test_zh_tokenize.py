"""Tests for the jieba-backed Chinese tokenizer used by System KB retrieval."""

from app.services import zh_tokenize


def test_seg_text_splits_multiword_chinese():
    # The whole point: a multi-word clause becomes space-separated words.
    out = zh_tokenize.seg_text("高血压运动建议")
    tokens = out.split()
    assert "高血压" in tokens
    assert "运动" in tokens
    assert "建议" in tokens


def test_seg_text_keeps_drug_names_intact():
    # Drug names must never be split (userdict seeded from ddi.DRUG_ALIASES etc.).
    for name in ("司美格鲁肽", "二甲双胍", "阿托伐他汀", "奥美拉唑"):
        tokens = zh_tokenize.seg_text(f"我在吃{name}").split()
        assert name in tokens, f"{name} should stay one token, got {tokens}"


def test_seg_text_empty_returns_empty():
    assert zh_tokenize.seg_text("") == ""
    assert zh_tokenize.seg_text("   ") == ""
    assert zh_tokenize.seg_text(None) == ""  # type: ignore[arg-type]


def test_check_available_is_true_when_installed():
    # jieba is a hard dependency in this repo; the startup probe must succeed.
    assert zh_tokenize.check_zh_tokenizer_available() is True


def test_drug_userdict_is_nonempty():
    terms = zh_tokenize._collect_drug_terms()
    # Should collect a meaningful set of >=3-char Chinese drug names.
    assert len(terms) > 30
    assert all(len(t) >= 3 for t in terms)
    assert "二甲双胍" in terms
