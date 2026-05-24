from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional


def to_naive_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """
    Normalize a datetime to naive UTC.

    - Already naive → returned as-is (assumed UTC by convention).
    - Timezone-aware → converted to UTC, then tzinfo stripped.
    - None → None.

    All internal timestamps in ProfitPilot are naive UTC.  Use this at system
    boundaries (Pydantic schemas, external API responses) so downstream code
    never has to handle mixed-aware comparisons.
    """
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt
