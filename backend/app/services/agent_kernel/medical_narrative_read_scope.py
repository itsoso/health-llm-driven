"""Closed first-person imaging report requests, never medical conclusions.

The complete utterance must be consumed. The returned keyword only selects
stored reports of the authenticated principal; it is not evidence that an
examination happened or that its OCR summary matches the original image.
"""
from dataclasses import dataclass
import re

_SELF = r'(?:我(?:自己|本人|个人)?的|本人(?:的)?)'
_BODY = r'(?P<side>左|右|双侧|双)?(?P<body>肩|膝|髋|肘|腕|踝)(?:关节|盖)?'
_MODALITY = r'(?:MRI|核磁共振|磁共振|核磁)'
_DIRECT = re.compile(
    rf'(?:请)?(?:查看|查询|调出|看看)(?:一下)?{_SELF}{_BODY}{_MODALITY}(?:检查)?报告', re.I,
)
_QUESTIONS = re.compile(
    rf'{_SELF}{_BODY}(?:现在|目前)(?:有什么样的|是什么|是怎样的|有什么)状况[？?]'
    rf'(?:医院)?(?:有没有做过{_MODALITY}|做过{_MODALITY}吗)[？?]'
    r'(?:诊断|检查)结果(?:是怎么样的|是什么|怎么样|如何)[？?]?', re.I,
)


@dataclass(frozen=True)
class MedicalNarrativeReadScope:
    anatomy: str
    modality: str = 'MRI'

    def query_args(self) -> dict[str, str]:
        return {'dimension': 'medical_exam', 'keyword': self.anatomy}


def resolve_medical_narrative_read_scope(text: str) -> MedicalNarrativeReadScope | None:
    if not isinstance(text, str) or len(text) > 500:
        return None
    normalized = re.sub(r'\s+', '', text).rstrip('。.!！')
    match = _DIRECT.fullmatch(normalized) or _QUESTIONS.fullmatch(normalized)
    if match is None:
        return None
    # Bilateral/general requests may match either side. A stated single side
    # is retained and must not silently broaden into its opposite side.
    side = match['side'] if match['side'] in {'左', '右'} else ''
    return MedicalNarrativeReadScope(side + match['body'])


def medical_narrative_read_scope_contract_payload() -> dict[str, str]:
    from app.services.agent_kernel.health_semantics import (
        authorization_behavior_digest, authorization_grammar_digest,
        authorization_module_behavior_names,
    )
    return {
        'version': 'medical-narrative-read-v1',
        'grammar': authorization_grammar_digest(globals()),
        'behavior': authorization_behavior_digest(
            globals(), authorization_module_behavior_names(globals(), __name__)),
    }
