import datetime


def calculate_phase(now: datetime.datetime | None = None) -> float:
    now = now or datetime.datetime.now(tz=datetime.timezone.utc)

    # https://en.wikipedia.org/wiki/Lunar_phase#Calculating_phase
    total_seconds = (now - datetime.datetime(1999, 8, 11).replace(tzinfo=now.tzinfo)).total_seconds()

    total_days = total_seconds / (60 * 60 * 24)

    PHASE_LENGTH = 29.530588853

    phase = (total_days % PHASE_LENGTH) / PHASE_LENGTH

    return phase


def phase_emoji(now: datetime.datetime | None = None):
    return chr(0x1F311 + round(calculate_phase(now=now) * 8))
