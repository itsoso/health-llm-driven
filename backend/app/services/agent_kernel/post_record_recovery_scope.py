"""Closed product recovery action: material, evidence and answer horizon differ.

This proves a read request, never that the described workout was persisted or
belongs to a particular event. Unknown material/clauses cannot grant authority.
"""
import re

_EXERCISE = r'(?:俯卧撑|深蹲|平板支撑|引体向上|仰卧起坐|波比跳|开合跳|跳绳|跑步|骑行|步行|游泳|瑜伽|力量训练|拉伸|运动|pushups|pushup|squats|plank|running|cycling|walking|swimming|yoga)'
_AMOUNT = r'[0-9]{1,5}(?:组|次|分钟)'
_PROMPT = re.compile(
    rf'基于我刚记录的运动(?:（{_EXERCISE}·(?:已完成|{_AMOUNT}(?:·{_AMOUNT}){{0,2}})）)?，'
    r'结合最近恢复、睡眠和心率数据，给我今天剩余时间的恢复建议[。.]?', re.I,
)


def is_post_record_recovery_request(text: str) -> bool:
    return _PROMPT.fullmatch(re.sub(r'[ \t]+', '', str(text or ''))) is not None


def has_post_record_recovery_reference(text: str) -> bool:
    # Restrictive only: incomplete/modified card actions must not fall through
    # to broad health_analysis or unrelated personal record reads.
    normalized = re.sub(r'\s+', '', str(text or ''))
    return bool(re.search(r'刚记录.*运动|运动.*刚记录', normalized)
                and re.search(r'恢复|睡眠|心率', normalized))


def post_record_recovery_scope_contract_payload():
    from app.services.agent_kernel.health_semantics import (
        authorization_behavior_digest, authorization_grammar_digest,
        authorization_module_behavior_names,
    )
    return {
        'version': 'post-record-recovery-scope-v1',
        'grammar': authorization_grammar_digest(globals()),
        'behavior': authorization_behavior_digest(
            globals(), authorization_module_behavior_names(globals(), __name__)),
    }
