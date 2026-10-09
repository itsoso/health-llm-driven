"""Eval-only lossless interning of repeated missing-field metadata.

Applies only to the provider's verified read projection. Never edits execution
results, the Pi transcript, facts, row order or authority state.
"""
from copy import deepcopy
import json

_STATES = {"not_returned", "null_in_result", "empty_in_result", "unsupported_value"}
_INSTRUCTION = (
    "\n证据编码：每个查询的unknown_field_sets是该查询专属的字段缺口字典列表；"
    "记录的unknown_fields_ref是从0开始的索引，等价于该记录完整的unknown_fields。"
    "引用仅共享缺口字典，不能合并记录、已知字段或数值。"
)


def _wire(value):
    return json.dumps(value, ensure_ascii=False)


def intern_unknown_fields(evidence):
    if not isinstance(evidence, dict) or evidence.get("version") != "composed-read-evidence.v1":
        return evidence
    queries = evidence.get("queries")
    if not isinstance(queries, list):
        return evidence
    for query in queries:
        if not isinstance(query, dict) or "unknown_field_sets" in query or not isinstance(query.get("records"), list):
            return evidence
        for row in query["records"]:
            if not isinstance(row, dict) or "unknown_fields_ref" in row:
                return evidence
            unknown = row.get("unknown_fields")
            if (not isinstance(unknown, dict)
                or any(not isinstance(k, str) or not isinstance(v, str) or v not in _STATES
                       for k, v in unknown.items())):
                return evidence
    compact = deepcopy(evidence)
    for query in compact["queries"]:
        before = deepcopy(query)
        sets, indexes = [], {}
        for row in query["records"]:
            unknown = row.pop("unknown_fields")
            key = json.dumps(unknown, sort_keys=True)
            if key not in indexes:
                indexes[key] = len(sets)
                sets.append(unknown)
            row["unknown_fields_ref"] = indexes[key]
        query["unknown_field_sets"] = sets
        if len(_wire(query).encode()) >= len(_wire(before).encode()):
            query.clear()
            query.update(before)
    # Include the decoding instruction in the saving test. One-row queries and
    # small/no savings retain their existing representation and prompt verbatim.
    if len((_wire(compact) + _INSTRUCTION).encode()) >= len(_wire(evidence).encode()):
        return evidence
    return compact


def install_read_evidence_format(executor):
    original = executor._composed_synthesis_messages

    def project(*args, **kwargs):
        messages = original(*args, **kwargs)
        if messages is None:
            return None
        data = json.loads(messages[1]["content"])
        compact = intern_unknown_fields(data["read_evidence"])
        if compact == data["read_evidence"]:
            return messages
        data["read_evidence"] = compact
        projected = deepcopy(messages)
        projected[0]["content"] += _INSTRUCTION
        projected[1]["content"] = _wire(data)
        return projected

    executor._composed_synthesis_messages = project
