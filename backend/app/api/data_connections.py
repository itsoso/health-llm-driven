"""Data connection, consent, provenance, and connector policy API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.user import User
from app.services.data_connections import (
    create_consent_grant,
    list_connection_summaries,
    revoke_data_connection,
    serialize_consent_grant,
    serialize_data_connection,
    upsert_data_connection,
)

router = APIRouter(prefix="/data-connections", tags=["data-connections"])


class DataConnectionCreate(BaseModel):
    provider: str = Field(..., min_length=1, max_length=80)
    provider_type: str = Field(..., min_length=1, max_length=40)
    display_name: str = Field(..., min_length=1, max_length=160)
    scopes: list[str] = Field(default_factory=list)
    token_status: str = Field("none", max_length=30)
    source_ref: str | None = Field(None, max_length=200)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConsentGrantCreate(BaseModel):
    grantee_type: str = Field(..., min_length=1, max_length=40)
    grantee_id: str | None = Field(None, max_length=120)
    scopes: list[str] = Field(default_factory=list)
    purpose: str = Field(..., min_length=1, max_length=240)
    expires_at: datetime | None = None


@router.get("/me")
def list_my_data_connections(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    return {"connections": list_connection_summaries(db, user_id=current_user.id)}


@router.post("/me")
def create_or_update_my_data_connection(
    payload: DataConnectionCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    try:
        connection = upsert_data_connection(
            db,
            user_id=current_user.id,
            provider=payload.provider,
            provider_type=payload.provider_type,
            display_name=payload.display_name,
            scopes=payload.scopes,
            token_status=payload.token_status,
            source_ref=payload.source_ref,
            metadata=payload.metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return serialize_data_connection(db, connection)


@router.post("/{connection_id}/consents")
def create_connection_consent(
    connection_id: int,
    payload: ConsentGrantCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    try:
        grant = create_consent_grant(
            db,
            user_id=current_user.id,
            connection_id=connection_id,
            grantee_type=payload.grantee_type,
            grantee_id=payload.grantee_id,
            scopes=payload.scopes,
            purpose=payload.purpose,
            expires_at=payload.expires_at,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return serialize_consent_grant(grant)


@router.post("/{connection_id}/revoke")
def revoke_my_data_connection(
    connection_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    try:
        connection = revoke_data_connection(db, user_id=current_user.id, connection_id=connection_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return serialize_data_connection(db, connection)
