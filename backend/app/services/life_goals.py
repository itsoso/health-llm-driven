"""Project saved planning fields only; never read Health facts or create a plan."""
from datetime import timedelta
from app.schemas.life_goals import CurrentQuarter, CurrentWeek, LifeGoalsContext
from app.services.life_navigation import get_workspace
from app.utils import timezone as user_time


def get_context(db, user_id):
    now = user_time.get_user_now(db, user_id)
    today = now.date()
    quarter_key = f'{today.year}-Q{(today.month - 1) // 3 + 1}'
    week_start = today - timedelta(days=today.weekday())
    workspace = get_workspace(db, user_id)
    data = workspace.data
    saved_quarter = data.quarters.get(quarter_key)
    quarter = CurrentQuarter(key=quarter_key, **(
        {key: getattr(saved_quarter, key) for key in ('strategy', 'decomposition', 'plan')}
        if saved_quarter else {}))
    saved_week = data.weeks.get(week_start.isoformat())
    tracks = saved_week.tracks if saved_week else []
    present = {
        'life': bool(data.strategy.vision.strip()),
        'annual': bool(data.strategy.annual_goal.strip()),
        'quarterly': any(getattr(quarter, key).strip() for key in ('strategy', 'decomposition', 'plan')),
        'monthly': False,  # The persisted LifeNav schema has no monthly goal field.
        'weekly': any(track.title.strip() or track.criterion.strip() for track in tracks),
    }
    return LifeGoalsContext(owner_id=user_id, local_date=today, timezone=str(now.tzinfo),
        revision=workspace.revision, updated_at=workspace.updated_at, strategy=data.strategy,
        quarter=quarter, week=CurrentWeek(start=week_start, tracks=tracks),
        missing_horizons=[key for key, available in present.items() if not available])
