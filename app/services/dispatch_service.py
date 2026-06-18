"""
dispatch_service.py — Dispatch-time decisioning.

Turns a classified order into a concrete DispatchDecision: which tier, the
computed quantities/value, stock status, and the dispatch ETA derived from the
tier's SLA (hours from order placement).
"""
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.schemas.delivery import (
    ClassifyOrderRequest,
    DeliveryTier,
    DispatchDecision,
)
from app.services import classifier

# Hours-from-placement SLA per tier.
_TIER_SLA_HOURS: dict[DeliveryTier, int] = {
    DeliveryTier.EXPRESS: settings.dispatch_hours_express,
    DeliveryTier.STANDARD: settings.dispatch_hours_standard,
    DeliveryTier.BULK: settings.dispatch_hours_bulk,
    DeliveryTier.BACKORDER: settings.dispatch_hours_backorder,
}


def dispatch_eta(tier: DeliveryTier, placed_at: datetime | None = None) -> datetime:
    """Compute the dispatch ETA for a tier, relative to placement (default now)."""
    base = placed_at or datetime.now(timezone.utc)
    return base + timedelta(hours=_TIER_SLA_HOURS[tier])


def decide(request: ClassifyOrderRequest, placed_at: datetime | None = None) -> DispatchDecision:
    """Classify the order and produce a full dispatch decision."""
    tier, reasons = classifier.classify(request)
    qty = classifier.total_quantity(request.items)
    value = classifier.order_value(request.items, request.total_amount)
    in_stock = classifier.is_in_stock(request.items)
    eta = dispatch_eta(tier, placed_at)

    reasons.append(f"Dispatch SLA: {_TIER_SLA_HOURS[tier]}h from placement.")

    return DispatchDecision(
        order_id=request.order_id,
        tier=tier,
        total_quantity=qty,
        total_amount=value,
        in_stock=in_stock,
        dispatch_eta=eta,
        reasons=reasons,
    )
