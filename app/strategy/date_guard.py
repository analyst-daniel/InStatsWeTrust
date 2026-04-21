from __future__ import annotations

import re
from datetime import datetime, timezone

from app.normalize.models import NormalizedMarket


DATE_RE = re.compile(r"20\d{2}-\d{2}-\d{2}")


def market_date_is_current_or_unknown(market: NormalizedMarket, *, today: str | None = None) -> bool:
    today = today or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    text = " ".join([market.event_slug, market.market_slug, market.event_title, market.question, market.start_time, market.end_date])
    dates = DATE_RE.findall(text)
    if not dates:
        return True
    return max(dates) >= today
