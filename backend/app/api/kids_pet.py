"""Kids dog space APIs."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.deps import get_current_user_required
from app.models.user import User
from app.models.kids_pet import KidsPetProfile
from app.schemas.kids_pet import KidsPetAdoptRequest, KidsPetActionRequest, KidsPetResponse, KidsPetState

router = APIRouter(prefix="/kids-pet", tags=["kids-pet"])

HUNGER_DECAY_PER_DAY = 20
HAPPY_DECAY_PER_DAY = 10
XP_PER_LEVEL = 60


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _clamp(value: int, min_v: int, max_v: int) -> int:
    return max(min_v, min(max_v, value))


def _sync_level(pet: KidsPetProfile) -> None:
    pet.level = max(1, pet.xp // XP_PER_LEVEL + 1)


def _apply_daily_decay(pet: KidsPetProfile) -> None:
    now = _now()
    last = pet.last_decay_at or now
    days = int((now - last).total_seconds() // 86400)
    if days <= 0:
        return
    pet.hunger = _clamp(pet.hunger - days * HUNGER_DECAY_PER_DAY, 0, 100)
    if pet.hunger < 50:
        pet.happiness = _clamp(pet.happiness - days * HAPPY_DECAY_PER_DAY, 0, 100)
    pet.last_decay_at = now


def _to_response(user: User, pet: KidsPetProfile | None, message: str | None = None) -> KidsPetResponse:
    if not pet:
        return KidsPetResponse(has_pet=False, kids_points=user.kids_points or 0, message=message)
    return KidsPetResponse(
        has_pet=True,
        kids_points=user.kids_points or 0,
        pet=KidsPetState.model_validate(pet),
        message=message,
    )


@router.get("/me", response_model=KidsPetResponse, summary="获取我的狗狗空间")
async def get_my_pet(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    pet = db.query(KidsPetProfile).filter(KidsPetProfile.user_id == current_user.id).first()
    if pet:
        _apply_daily_decay(pet)
        db.commit()
        db.refresh(pet)
    return _to_response(current_user, pet)


@router.post("/adopt", response_model=KidsPetResponse, summary="领养狗狗")
async def adopt_pet(
    payload: KidsPetAdoptRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    existing = db.query(KidsPetProfile).filter(KidsPetProfile.user_id == current_user.id).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="已领养狗狗，无法重复领养")
    if (current_user.kids_points or 0) < payload.breed_cost:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="积分不足，无法领养该品种")

    now = _now()
    current_user.kids_points = (current_user.kids_points or 0) - payload.breed_cost

    pet = KidsPetProfile(
        user_id=current_user.id,
        breed_id=payload.breed_id,
        breed_name=payload.breed_name,
        breed_image=payload.breed_image,
        breed_cost=payload.breed_cost,
        dog_name=payload.dog_name.strip(),
        hunger=100,
        happiness=100,
        level=1,
        xp=0,
        food_bags=0,
        has_house=False,
        has_garden=False,
        last_decay_at=now,
        last_interaction_at=now,
    )
    db.add(pet)
    db.commit()
    db.refresh(pet)
    db.refresh(current_user)
    return _to_response(current_user, pet, "领养成功")


@router.post("/action", response_model=KidsPetResponse, summary="狗狗互动")
async def pet_action(
    payload: KidsPetActionRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    pet = db.query(KidsPetProfile).filter(KidsPetProfile.user_id == current_user.id).first()
    if not pet:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="尚未领养狗狗")

    _apply_daily_decay(pet)
    points = current_user.kids_points or 0
    now = _now()
    message = "操作成功"

    if payload.action == "buy_food":
        if points < 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="积分不足，无法购买狗粮")
        current_user.kids_points = points - 1
        pet.food_bags += 1
        pet.xp += 1
        message = "购买狗粮成功"
    elif payload.action == "feed":
        if pet.food_bags <= 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="狗粮不足，请先购买")
        pet.food_bags -= 1
        pet.hunger = _clamp(pet.hunger + 50, 0, 100)
        pet.happiness = _clamp(pet.happiness + 10, 0, 100)
        pet.xp += 5
        message = "喂食成功"
    elif payload.action == "feed_full":
        if points < 2:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="积分不足，无法喂饱")
        current_user.kids_points = points - 2
        pet.hunger = 100
        pet.happiness = _clamp(pet.happiness + 25, 0, 100)
        pet.xp += 12
        message = "喂饱成功"
    elif payload.action == "buy_house":
        if pet.has_house:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="已拥有小屋")
        if points < 3:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="积分不足，无法购买小屋")
        current_user.kids_points = points - 3
        pet.has_house = True
        pet.xp += 8
        message = "购买小屋成功"
    elif payload.action == "buy_garden":
        if pet.has_garden:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="已拥有花园")
        if points < 5:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="积分不足，无法购买花园")
        current_user.kids_points = points - 5
        pet.has_garden = True
        pet.xp += 12
        message = "购买花园成功"
    elif payload.action == "return_house":
        if not pet.has_house:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="没有小屋可以退还")
        pet.has_house = False
        current_user.kids_points = points + 3
        message = "退还小屋成功，返还3积分"
    elif payload.action == "return_garden":
        if not pet.has_garden:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="没有花园可以退还")
        pet.has_garden = False
        current_user.kids_points = points + 5
        message = "退还花园成功，返还5积分"
    elif payload.action == "return_dog":
        refund = pet.breed_cost or 0
        db.delete(pet)
        current_user.kids_points = points + refund
        db.commit()
        db.refresh(current_user)
        return _to_response(current_user, None, f"已送走{pet.dog_name}，返还{refund}积分")

    _sync_level(pet)
    pet.last_interaction_at = now
    db.commit()
    db.refresh(pet)
    db.refresh(current_user)
    return _to_response(current_user, pet, message)
