"""Minimal account-age projection for explicitly authorized dietary advice."""
from datetime import date
from sqlalchemy.orm import Session
from app.models.user import User


def read_age(db: Session, user_id: int, reference_date: date) -> dict:
    if type(user_id) is not int or user_id <= 0:
        raise ValueError('A valid authenticated user is required')
    row = db.query(User.birth_date).filter(User.id == user_id).one_or_none()
    if row is None:
        raise ValueError('Authenticated user is unavailable')
    birthday = row.birth_date
    age = None
    if birthday is not None and birthday <= reference_date:
        age = reference_date.year - birthday.year - ((reference_date.month, reference_date.day) < (birthday.month, birthday.day))
    return {'age_years': age, 'as_of': reference_date.isoformat(), 'source': 'account_birth_date'}
