"""scrub_pii unit tests (review #3, 2026-05-12)."""

from app.services.llm.pii_scrub import scrub_pii, scrub_messages


def test_phone_redacted():
    text = "我的手机是 13800138000 麻烦记一下"
    out, hits = scrub_pii(text)
    assert "[PHONE]" in out
    assert "13800138000" not in out
    assert hits == {"phone": 1}


def test_idcard_redacted():
    text = "身份证 110101199003079876"
    out, hits = scrub_pii(text)
    assert "[IDCARD]" in out
    assert "199003079876" not in out
    assert hits == {"idcard": 1}


def test_email_redacted():
    text = "联系 john.doe+tag@example.co.jp 谢谢"
    out, hits = scrub_pii(text)
    assert "[EMAIL]" in out
    assert "john.doe" not in out
    assert hits == {"email": 1}


def test_idcard_takes_precedence_over_bankcard():
    """18 位 (含末位 X) 必须当 idcard, 不被 bankcard 16-19 位规则吃掉."""
    text = "身份证 11010119900307987X 不是银行卡"
    out, hits = scrub_pii(text)
    assert "[IDCARD]" in out
    assert "[BANKCARD]" not in out
    assert hits.get("idcard") == 1
    assert "bankcard" not in hits


def test_no_pii_passes_through():
    text = "我 LDL 3.5 mmol/L, MTHFR C677T = TT, 服用甲基叶酸"
    out, hits = scrub_pii(text)
    assert out == text
    assert hits == {}


def test_multi_message_aggregate_hits():
    msgs = [
        {"role": "user", "content": "电话 13900139000"},
        {"role": "assistant", "content": "好的"},
        {"role": "user", "content": "邮箱 a@b.com 也记一下"},
    ]
    new_msgs, total = scrub_messages(msgs)
    assert "[PHONE]" in new_msgs[0]["content"]
    assert "[EMAIL]" in new_msgs[2]["content"]
    assert total == {"phone": 1, "email": 1}


def test_multimodal_text_part_scrubbed():
    msgs = [{
        "role": "user",
        "content": [
            {"type": "text", "text": "号码 13800138000"},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}},
        ],
    }]
    new_msgs, total = scrub_messages(msgs)
    text_part = new_msgs[0]["content"][0]
    assert "[PHONE]" in text_part["text"]
    assert total == {"phone": 1}


def test_long_digits_inside_word_not_matched():
    """避免把 SNP rsid 等当 phone/idcard."""
    text = "rs1234567890 是基因位点 ID"
    out, hits = scrub_pii(text)
    assert out == text
    assert hits == {}


def test_empty_input_safe():
    assert scrub_pii("") == ("", {})
    assert scrub_pii(None) == (None, {})
    assert scrub_messages([]) == ([], {})
    assert scrub_messages(None) == (None, {})
