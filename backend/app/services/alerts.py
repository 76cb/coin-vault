"""Spot price alerts: a level per metal, checked each time prices are fetched. An alert fires once, stays on
screen until dismissed, and can be re-armed."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SpotAlert, utcnow


def crossed(direction: str, level: Decimal, price: Decimal) -> bool:
    return price >= level if direction == "above" else price <= level


def check(db: Session, currency: str, prices: dict[str, Decimal], now: dt.datetime | None = None) -> list[SpotAlert]:
    """Fire every waiting alert in this currency whose level today's price has reached. Returns the ones fired."""
    fired = []
    for a in db.scalars(select(SpotAlert).where(SpotAlert.currency == currency, SpotAlert.triggered_at.is_(None))):
        price = prices.get(a.metal)
        if price is not None and crossed(a.direction, a.price, price):
            a.triggered_at, a.triggered_price = now or utcnow(), price
            fired.append(a)
    if fired:
        db.commit()
    return fired
