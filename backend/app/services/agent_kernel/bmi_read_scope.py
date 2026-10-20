"""Closed first-person BMI read; subject proof grants no arbitrary read scope."""
import re

_PATTERN = re.compile(r'(?:请)?(?:(?:帮我|给我)?(?:算|算算|计算|查看)(?:一下)?(?:我|我自己)的\s*(?:BMI|体质指数)|(?:我|我自己)的\s*(?:BMI|体质指数)(?:是多少|是什么|多少))[？?。！!]*', re.I)

def is_bmi_read_request(text: str) -> bool:
    return bool(isinstance(text, str) and _PATTERN.fullmatch(text.strip()))


def bmi_query_authorized(snapshot, args: dict) -> bool:
    return (is_bmi_read_request(snapshot.envelope.text)
            and type(snapshot.context.user_id) is int and snapshot.context.user_id > 0
            and type(snapshot.envelope.user_id) is int
            and snapshot.envelope.user_id == snapshot.context.user_id
            and args == {'dimension': 'bmi'})


def bmi_read_scope_contract_payload() -> dict:
    from app.services.agent_kernel.health_semantics import authorization_behavior_digest
    return {'version': 'bmi-read-v1', 'pattern': _PATTERN.pattern,
            'behavior': authorization_behavior_digest(globals(), ('is_bmi_read_request', 'bmi_query_authorized'))}
