import json
from datetime import UTC, datetime

from app.services.system_knowledge_ingest import (
    compile_dedao_ingest_artifacts,
    write_reviewed_artifacts,
)


def _jsonl(path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_dedao_compiler_emits_protocol_candidate_for_actionable_course_advice(tmp_path):
    source_root = tmp_path / "down-dedao"
    course = source_root / "冯雪·高血压医学课" / "MD"
    course.mkdir(parents=True)
    raw_excerpt = "这是一段付费课程正文，不能被原样放入 protocol artifact。"
    (course / "07 - 饮食：怎么吃才能有效降血压？.md").write_text(
        "# 饮食：怎么吃才能有效降血压？\n\n"
        "如果家庭血压偏高，先识别盐、钠、外卖、加工食品和酱料来源，"
        "再做持续 7 天的低钠替换行动，并用家庭血压趋势验证。"
        f"{raw_excerpt * 4}",
        encoding="utf-8",
    )

    result = compile_dedao_ingest_artifacts(
        source_root=source_root,
        base_artifact_dir=tmp_path / "empty-artifacts",
        course_names=["冯雪·高血压医学课"],
        now=datetime(2026, 5, 20, tzinfo=UTC),
    )

    assert result.claims
    assert result.protocols
    protocol = next(
        item
        for item in result.protocols
        if item["protocol_id"] == "protocol:cardiovascular:salt_reduction"
    )

    assert protocol["doc_type"] == "protocol"
    assert protocol["source_claims"] == ["claim:c_dedao_fengxue_gaoxueya_yixueke_salt_reduction"]
    assert protocol["verification"]["metric"] == "systolic_bp"
    assert protocol["verification"]["window_days"] == 7
    assert protocol["paid_source_policy"] == "transformed_summary_only"
    assert protocol["metadata"]["source_course"] == "冯雪·高血压医学课"
    assert protocol["metadata"]["source_chapters"][0]["title"] == "07 - 饮食：怎么吃才能有效降血压？"
    assert raw_excerpt not in json.dumps(protocol, ensure_ascii=False)
    assert result.diff["protocols_added"] >= 1


def test_write_reviewed_artifacts_merges_compiled_protocol_candidates(tmp_path):
    source_root = tmp_path / "down-dedao"
    course = source_root / "怎样获得高质量睡眠" / "MD"
    course.mkdir(parents=True)
    (course / "01 - 固定入睡和起床时间.md").write_text(
        "睡眠不足时，优先固定睡眠窗口，连续 7 天观察睡眠时长和 sleep score。",
        encoding="utf-8",
    )

    output = tmp_path / "artifacts"
    result = compile_dedao_ingest_artifacts(
        source_root=source_root,
        base_artifact_dir=output,
        course_names=["怎样获得高质量睡眠"],
        now=datetime(2026, 5, 20, tzinfo=UTC),
    )
    counts = write_reviewed_artifacts(result, output)

    protocols = _jsonl(output / "protocols.jsonl")
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))

    assert any(item["protocol_id"] == "protocol:sleep_recovery:sleep_regular_window" for item in protocols)
    assert counts["protocols"] == len(protocols)
    assert manifest["counts"]["protocols"] == len(protocols)
