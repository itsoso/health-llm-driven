"""Read-only projections of existing family records; never move record ownership."""

import logging
from sqlalchemy.orm import Session, selectinload
from app.models.medical_exam import MedicalExam
from app.models.illness import IllnessEpisode
from app.schemas.medical_exam import MedicalExamResponse
from app.schemas.illness import IllnessEpisodeResponse, IllnessUpdateResponse
from app.services.family_access import require_family_access
from app.utils.number_format import format_display_number

logger = logging.getLogger(__name__)


def read_family_records(db: Session, actor_id: int, target_id: int, limit: int):
    member, target = require_family_access(db, actor_id, target_id)
    exams = (
        db.query(MedicalExam)
        .options(selectinload(MedicalExam.items))
        .filter(
            MedicalExam.user_id == target_id,
        )
        .order_by(MedicalExam.exam_date.desc(), MedicalExam.id.desc())
        .limit(limit)
        .all()
    )
    episodes = (
        db.query(IllnessEpisode)
        .options(selectinload(IllnessEpisode.updates))
        .filter(
            IllnessEpisode.user_id == target_id,
        )
        .order_by(IllnessEpisode.start_date.desc(), IllnessEpisode.id.desc())
        .limit(limit)
        .all()
    )
    reports = []
    for exam in exams:
        payload = MedicalExamResponse.model_validate(exam).model_dump(mode="json")
        for item in payload["items"]:
            item["display_value"] = (
                str(format_display_number(item["value"]))
                if item["value"] is not None
                else item["value_text"] or "—"
            )
        reports.append(payload)
    illnesses = []
    for episode in episodes:
        payload = IllnessEpisodeResponse.model_validate(episode).model_dump(mode="json")
        # Defense in depth for historical mismatched update ownership.
        payload["updates"] = [
            IllnessUpdateResponse.model_validate(update).model_dump(mode="json")
            for update in episode.updates
            if update.user_id == target_id
        ]
        illnesses.append(payload)
    logger.info("family_records_read actor_id=%s subject_id=%s", actor_id, target_id)
    return {
        "member": {
            "user_id": target.id,
            "name": target.name,
            "nickname": member.nickname,
            "relationship_type": member.relationship_type,
        },
        "reports": reports,
        "episodes": illnesses,
        "limit": limit,
    }
