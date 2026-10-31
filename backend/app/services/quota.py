"""QuotaManager: counts requests to quota-limited providers per period, persists the count,
stops at a configurable cap, and reconciles with the provider's own usage figures.

Periods:
  calendar_month  resets on the 1st (UTC), e.g. Metals.Dev.
  billing_cycle   resets on the account's billing anchor, e.g. SoldComps. Until the provider has
                  reported its period once, a calendar month is assumed.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import QuotaPeriod, utcnow
from app.providers.base import UsageInfo


def _aware(v: dt.datetime | None) -> dt.datetime | None:
    if v is not None and v.tzinfo is None:
        return v.replace(tzinfo=dt.UTC)
    return v


def calendar_month(now: dt.datetime) -> tuple[dt.datetime, dt.datetime]:
    start = now.astimezone(dt.UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1)
    return start, end


class QuotaManager:
    def __init__(self, db: Session, provider_key: str, cap: int | None, period_kind: str):
        self.db = db
        self.provider_key = provider_key
        self.cap = cap
        self.period_kind = period_kind

    def period(self, now: dt.datetime | None = None) -> QuotaPeriod:
        now = (now or utcnow()).astimezone(dt.UTC)
        rows = self.db.scalars(
            select(QuotaPeriod)
            .where(QuotaPeriod.provider_key == self.provider_key)
            .order_by(QuotaPeriod.period_start.desc())
            .limit(3)
        ).all()
        for row in rows:
            if _aware(row.period_start) <= now < _aware(row.period_end):
                return row
        if self.period_kind == "billing_cycle" and rows:
            # Roll the last known billing period forward by whole months.
            start, end = _aware(rows[0].period_start), _aware(rows[0].period_end)
            while end <= now:
                start, end = end, _add_month(end)
        else:
            start, end = calendar_month(now)
        row = QuotaPeriod(provider_key=self.provider_key, period_start=start, period_end=end, used=0)
        self.db.add(row)
        self.db.flush()
        return row

    def used(self, now: dt.datetime | None = None) -> int:
        return self.period(now).used

    def remaining(self, now: dt.datetime | None = None) -> int | None:
        p = self.period(now)
        options = []
        if self.cap is not None:
            options.append(self.cap - p.used)
        if p.provider_limit is not None:
            options.append(p.provider_limit - p.used)
        return max(0, min(options)) if options else None

    def can_spend(self, cost: int = 1, now: dt.datetime | None = None) -> bool:
        rem = self.remaining(now)
        return rem is None or rem >= cost

    def record(self, cost: int, now: dt.datetime | None = None) -> None:
        if cost <= 0:
            return
        p = self.period(now)
        self.db.execute(update(QuotaPeriod).where(QuotaPeriod.id == p.id).values(used=QuotaPeriod.used + cost))
        self.db.flush()
        self.db.refresh(p)

    def sync(self, info: UsageInfo, now: dt.datetime | None = None) -> QuotaPeriod:
        """Adopt the provider's own numbers. The provider's count wins over ours."""
        now = (now or utcnow()).astimezone(dt.UTC)
        if info.period_start and info.period_end:
            start, end = _aware(info.period_start), _aware(info.period_end)
            # Drop periods we only assumed (never synced) that overlap the real one.
            for other in self.db.scalars(select(QuotaPeriod).where(QuotaPeriod.provider_key == self.provider_key)):
                o_start, o_end = _aware(other.period_start), _aware(other.period_end)
                if o_start != start and other.synced_at is None and o_start < end and start < o_end:
                    self.db.delete(other)
            self.db.flush()
            row = self.db.scalar(
                select(QuotaPeriod).where(QuotaPeriod.provider_key == self.provider_key, QuotaPeriod.period_start == start)
            )
            if row is None:
                row = QuotaPeriod(provider_key=self.provider_key, period_start=start, period_end=end, used=0)
                self.db.add(row)
            row.period_end = end
        else:
            row = self.period(now)
        row.provider_used = info.used
        row.provider_limit = info.limit
        row.used = info.used
        row.synced_at = now
        self.db.flush()
        return row


def _add_month(d: dt.datetime) -> dt.datetime:
    month = d.month + 1
    year = d.year + (month > 12)
    month = 1 if month > 12 else month
    for day in (d.day, 30, 29, 28):
        try:
            return d.replace(year=year, month=month, day=day)
        except ValueError:
            continue
    raise AssertionError("unreachable")
