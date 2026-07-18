from app.services.telegram_inbound import classify_intent


def test_telegram_record_noun_query_is_not_record_route():
    assert classify_intent("今天我的饮食的记录，帮我列个表格出来。") == "query"


def test_telegram_contrastive_correction_is_query_route():
    assert classify_intent("不是记录，是列出我今天吃的所有东西。") == "query"


def test_telegram_clear_record_command_still_records():
    assert classify_intent("记录午餐吃了牛肉面") == "record"
