"""ProgramTemplate catalog API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.user import User
from app.services.program_templates import list_templates, start_template_program

router = APIRouter(prefix="/program-templates", tags=["program-templates"])


@router.get("")
def list_program_templates(
    current_user: User = Depends(get_current_user_required),
):
    return {"templates": list_templates(), "count": len(list_templates())}


@router.post("/{template_id}/start")
def start_program_template(
    template_id: str,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    try:
        return start_template_program(db, user_id=current_user.id, template_id=template_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
