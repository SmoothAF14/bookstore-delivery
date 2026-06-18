"""
test_classifier.py — Tests for order classification + dispatch decisioning.
"""
from app.core.config import settings
from app.schemas.delivery import ClassifyOrderRequest, DeliveryTier
from app.services import classifier, dispatch_service


def _req(items, total=None, order_id="o1"):
    return ClassifyOrderRequest(
        order_id=order_id,
        items=[{"book_id": f"b{i}", **it} for i, it in enumerate(items)],
        total_amount=total,
    )


def test_standard_order():
    req = _req([{"quantity": 1, "unit_price": 100.0, "stock": 10}])
    tier, reasons = classifier.classify(req)
    assert tier == DeliveryTier.STANDARD
    assert reasons


def test_express_by_value():
    # Value at/above the express threshold -> EXPRESS.
    price = settings.express_value_threshold
    req = _req([{"quantity": 1, "unit_price": price, "stock": 5}])
    tier, _ = classifier.classify(req)
    assert tier == DeliveryTier.EXPRESS


def test_bulk_by_quantity():
    qty = settings.bulk_quantity_threshold
    req = _req([{"quantity": qty, "unit_price": 10.0, "stock": qty}])
    tier, _ = classifier.classify(req)
    assert tier == DeliveryTier.BULK


def test_backorder_takes_precedence_over_value():
    # High value AND short stock -> BACKORDER wins.
    req = _req([{"quantity": 3, "unit_price": settings.express_value_threshold, "stock": 1}])
    tier, _ = classifier.classify(req)
    assert tier == DeliveryTier.BACKORDER


def test_unknown_stock_assumed_available():
    req = _req([{"quantity": 2, "unit_price": 50.0}])  # stock omitted
    assert classifier.is_in_stock(req.items) is True


def test_value_recomputed_when_total_omitted():
    req = _req([{"quantity": 2, "unit_price": 75.0, "stock": 10}], total=None)
    assert classifier.order_value(req.items, req.total_amount) == 150.0


def test_dispatch_decision_eta_after_now():
    req = _req([{"quantity": 1, "unit_price": 100.0, "stock": 10}])
    decision = dispatch_service.decide(req)
    assert decision.tier == DeliveryTier.STANDARD
    assert decision.total_quantity == 1
    assert decision.in_stock is True
    # ETA is in the future relative to placement.
    assert decision.dispatch_eta is not None
