"""
classifier.py — Order classification.

Classifies an order into a DeliveryTier from its quantity, total value, and
stock availability. Pure functions — no I/O — so they're trivially testable and
safe to call from either the API path or a Celery task.

Precedence (first match wins):
  1. BACKORDER  — any line item wants more than the known stock on hand.
  2. BULK       — total quantity >= bulk_quantity_threshold.
  3. EXPRESS    — total value >= express_value_threshold.
  4. STANDARD   — everything else.
"""
from app.core.config import settings
from app.schemas.delivery import ClassifyOrderRequest, DeliveryTier, OrderItemIn


def total_quantity(items: list[OrderItemIn]) -> int:
    return sum(item.quantity for item in items)


def order_value(items: list[OrderItemIn], total_amount: float | None) -> float:
    """Trust an explicit total only if given; otherwise recompute from items."""
    if total_amount is not None:
        return total_amount
    return sum(item.quantity * item.unit_price for item in items)


def is_in_stock(items: list[OrderItemIn]) -> bool:
    """False if any line item requests more than its known stock.

    Items with unknown stock (None) are assumed available — the backend is the
    source of truth and may not always send stock.
    """
    for item in items:
        if item.stock is not None and item.quantity > item.stock:
            return False
    return True


def classify(request: ClassifyOrderRequest) -> tuple[DeliveryTier, list[str]]:
    """Return the delivery tier plus human-readable reasons for the decision."""
    qty = total_quantity(request.items)
    value = order_value(request.items, request.total_amount)
    reasons: list[str] = []

    if not is_in_stock(request.items):
        reasons.append("One or more items exceed available stock; holding for restock.")
        return DeliveryTier.BACKORDER, reasons

    if qty >= settings.bulk_quantity_threshold:
        reasons.append(
            f"Total quantity {qty} >= bulk threshold {settings.bulk_quantity_threshold}."
        )
        return DeliveryTier.BULK, reasons

    if value >= settings.express_value_threshold:
        reasons.append(
            f"Order value {value:.2f} >= express threshold {settings.express_value_threshold:.2f}."
        )
        return DeliveryTier.EXPRESS, reasons

    reasons.append("Standard order: within normal quantity and value bounds.")
    return DeliveryTier.STANDARD, reasons
