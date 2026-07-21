"""体检 PDF 文本解析的服务端自动分段 + 合并测试

只覆盖 pdf_parser.MedicalReportPDFParser.parse_with_llm 的文本切块/合并路径,
通过 monkeypatch _parse_exam_chunk 避开真 LLM 调用。
"""
import pytest

from app.services.pdf_parser import MedicalReportPDFParser


def _parser_with_client():
    """构造一个 parser 并伪装 client 已就绪(parse_with_llm 会校验 self.client)。"""
    parser = MedicalReportPDFParser()
    parser.client = object()  # 非 None 即可,真实 LLM 走的是被 monkeypatch 的 helper
    return parser


def test_single_chunk_no_merge_change():
    """单块(<CHUNK_CHARS): 只调一次 _parse_exam_chunk,结果就是该块(无合并改变)。"""
    parser = _parser_with_client()
    calls = []
    fixed = {
        "patient_name": "张三",
        "patient_gender": "male",
        "items": [{"item_name": "白细胞", "category": "blood_routine_wbc", "value": 6.0}],
        "conclusions": [{"category": "normal", "title": "血常规正常"}],
        "overall_assessment": "总体良好",
    }

    def fake_chunk(chunk):
        calls.append(chunk)
        return fixed

    parser._parse_exam_chunk = fake_chunk

    text = "短报告内容\n第二行"  # 远小于 CHUNK_CHARS
    result = parser.parse_with_llm(text)

    assert len(calls) == 1
    assert calls[0] == text  # 单块路径把整段(≤MAX_TEXT_CHARS)原样传入
    # 单块路径合并后必须 == 该块本身,字典内容不被改写
    assert result is fixed


def test_multi_chunk_split_and_merge_union_dedup():
    """超大报告: 切成 N 块,每块都调 _parse_exam_chunk,合并为各块并集且去重。"""
    parser = _parser_with_client()

    # 造一个 > CHUNK_CHARS 的文本,且每行都短(确保有大量换行供自然切点)
    line = "检查项目行" + "x" * 90 + "\n"  # 约 100 字符/行
    text = line * 900  # 约 9 万字符,在总上限内且远超 CHUNK_CHARS

    chunk_args = []
    # 每块返回带 1 个重复项 + 1 个唯一项,验证去重与并集
    shared_item = {"item_name": "血红蛋白", "category": "blood_routine_hgb", "value": 140}
    shared_conclusion = {"category": "normal", "title": "总体正常"}

    def fake_chunk(chunk):
        idx = len(chunk_args)
        chunk_args.append(chunk)
        return {
            # scalar: 只有第 1 块给名字,后面给空 → 取首个非空
            "patient_name": "李四" if idx == 0 else "",
            "patient_gender": None if idx == 0 else "female",  # 首块空 → 取后续首个非空
            # overall_assessment: 长度递增,取最长
            "overall_assessment": "评" * (idx + 1),
            "items": [
                shared_item,  # 每块都有 → 应去重保留一条
                {"item_name": f"项目{idx}", "category": "labs", "value": idx},  # 唯一
            ],
            "conclusions": [
                shared_conclusion,  # 每块都有 → 去重
                {"category": "needs_attention", "title": f"结论{idx}"},  # 唯一
            ],
        }

    parser._parse_exam_chunk = fake_chunk

    result = parser.parse_with_llm(text)

    n_chunks = len(chunk_args)
    assert n_chunks >= 2, "超大文本必须被切成多块"
    # 每块都被处理
    assert len(chunk_args) == n_chunks
    # 每块 ≤ CHUNK_CHARS
    for c in chunk_args:
        assert len(c) <= parser.CHUNK_CHARS
    # 无损可重组:各块顺序拼接 == 原文(不丢字符 = 不丢检查项)
    assert "".join(chunk_args) == text
    # 自然边界:除最后一块外,块的结束位置紧邻一个换行(切点取 rfind '\n'),
    # 即下一块以换行开头 → 没有检查项被切成两半
    for c in chunk_args[:-1]:
        # 该块末字符不是换行(换行被留给下一块开头),但块边界处必为换行 → 不切断行
        assert c == "" or not c.endswith("\n")
    for c in chunk_args[1:]:
        assert c.startswith("\n"), "切点应落在换行处,下一块以换行开头,不切断检查项"

    # items 并集去重: 1 个共享 + N 个唯一
    item_keys = {(i["item_name"], i["category"]) for i in result["items"]}
    assert ("血红蛋白", "blood_routine_hgb") in item_keys
    assert len(result["items"]) == 1 + n_chunks  # 共享 1 + 每块唯一 1
    # 共享项只出现一次
    hgb_count = sum(
        1 for i in result["items"]
        if (i["item_name"], i["category"]) == ("血红蛋白", "blood_routine_hgb")
    )
    assert hgb_count == 1

    # conclusions 并集去重
    assert len(result["conclusions"]) == 1 + n_chunks
    conc_count = sum(
        1 for c in result["conclusions"]
        if (c["category"], c["title"]) == ("normal", "总体正常")
    )
    assert conc_count == 1

    # scalar 取首个非空
    assert result["patient_name"] == "李四"  # 首块给了
    assert result["patient_gender"] == "female"  # 首块 None → 取后续首个非空
    # overall_assessment 取最长(最后一块最长)
    assert result["overall_assessment"] == "评" * n_chunks


def test_chunk_failure_retries_then_raises_no_data_loss():
    """某块两次都失败 → 整体 raise(绝不静默跳过一段丢检查项)。"""
    parser = _parser_with_client()

    line = "x" * 99 + "\n"
    text = line * 1000  # > CHUNK_CHARS,触发分段

    attempts = {"count": 0}

    def always_fail(chunk):
        attempts["count"] += 1
        raise RuntimeError("LLM 解析失败模拟")

    parser._parse_exam_chunk = always_fail

    with pytest.raises(ValueError) as exc_info:
        parser.parse_with_llm(text)

    # 第一块失败后重试 1 次 → 至少调用 2 次,然后整体 raise
    assert attempts["count"] >= 2
    assert "解析失败" in str(exc_info.value)


def test_chunk_failure_recovers_on_retry():
    """某块第一次失败、重试成功 → 不应 raise,数据完整合并。"""
    parser = _parser_with_client()

    line = "x" * 99 + "\n"
    text = line * 1000  # > CHUNK_CHARS

    state = {"failed_once": False}

    def flaky(chunk):
        # 仅让第一块的第一次失败一次
        if not state["failed_once"]:
            state["failed_once"] = True
            raise RuntimeError("transient")
        return {
            "items": [{"item_name": "项目", "category": "labs", "value": 1}],
            "conclusions": [],
        }

    parser._parse_exam_chunk = flaky

    result = parser.parse_with_llm(text)
    # 重试成功,合并产出 items
    assert any(i["item_name"] == "项目" for i in result["items"])


def test_total_text_cap_rejects_without_silent_truncation():
    """Medical data over the cap fails loudly instead of silently dropping pages."""
    parser = _parser_with_client()

    line = "x" * 99 + "\n"
    text = line * 5000  # 50 万字符,远超 MAX_TEXT_CHARS

    seen = []

    def fake_chunk(chunk):
        seen.append(chunk)
        return {"items": [], "conclusions": []}

    parser._parse_exam_chunk = fake_chunk

    with pytest.raises(ValueError, match="超过 100000 字限制"):
        parser.parse_with_llm(text)

    assert seen == []
