from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class YearProgress:
    year: int
    elapsed_seconds: float
    total_seconds: float
    percent_complete: float


def calculate_year_progress(now: datetime | None = None) -> YearProgress:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    start_of_year = datetime(now.year, 1, 1, tzinfo=now.tzinfo)
    start_of_next_year = datetime(now.year + 1, 1, 1, tzinfo=now.tzinfo)

    elapsed_seconds = (now - start_of_year).total_seconds()
    total_seconds = (start_of_next_year - start_of_year).total_seconds()
    percent_complete = (elapsed_seconds / total_seconds) * 100

    return YearProgress(
        year=now.year,
        elapsed_seconds=elapsed_seconds,
        total_seconds=total_seconds,
        percent_complete=percent_complete,
    )


def progress_bar(percent: float, *, length: int = 20) -> str:
    clamped = max(0.0, min(percent, 100.0))
    filled = round((clamped / 100) * length)
    return "█" * filled + "░" * (length - filled)
