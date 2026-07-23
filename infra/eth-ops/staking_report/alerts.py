from datetime import datetime, timedelta


def should_send(last_sent: datetime | None, now: datetime, cooldown: timedelta = timedelta(minutes=30)) -> bool:
    return last_sent is None or now - last_sent >= cooldown
