"""
backend_client.py — httpx client for the Django backend.

Reads an order (items + delivery) and maps it into a ClassifyOrderRequest so
the bot can classify a real order by id. All calls forward the caller's JWT
(the delivery service shares the backend's SECRET_KEY, so the token is valid).

The Django backend wraps responses in the envelope:
    {"status": {...}, "data": <payload>}
"""
import logging
from datetime import datetime

import httpx

from app.core.config import settings
from app.schemas.delivery import ClassifyOrderRequest, OrderItemIn

logger = logging.getLogger(__name__)


def _parse_dt(value) -> datetime | None:
    """Parse an ISO 8601 datetime string (e.g. order.created_at) safely."""
    if not value:
        return None
    try:
        # Django/DRF emits ISO 8601, sometimes with a trailing 'Z'.
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _client(access_token: str | None = None) -> httpx.Client:
    headers = {}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    return httpx.Client(base_url=settings.django_api_url, timeout=10.0, headers=headers)


def _unwrap(payload):
    if isinstance(payload, dict) and "data" in payload:
        return payload.get("data")
    return payload


def get_order(order_id: str, access_token: str | None = None) -> dict:
    """Fetch an order (includes its `items` and `delivery` blocks)."""
    with _client(access_token) as client:
        resp = client.get(f"/api/orders/{order_id}/")
        resp.raise_for_status()
        return _unwrap(resp.json()) or {}


def order_to_classify_request(order: dict) -> ClassifyOrderRequest:
    """Map a backend order payload into a ClassifyOrderRequest.

    The order's items carry book, quantity, unit_price. `stock` is included per
    item when the backend provides it (book_stock); otherwise left None and
    treated as available. `created_at` becomes `placed_at` so the dispatch ETA
    is anchored to when the order was placed (stable across refreshes).
    """
    items: list[OrderItemIn] = []
    for it in order.get("items", []) or []:
        items.append(
            OrderItemIn(
                book_id=str(it.get("book") or it.get("book_id") or ""),
                quantity=int(it.get("quantity", 1)),
                unit_price=float(it.get("unit_price", 0) or 0),
                stock=(int(it["book_stock"]) if it.get("book_stock") is not None else None),
            )
        )

    total = order.get("total_amount")
    return ClassifyOrderRequest(
        order_id=str(order.get("id") or ""),
        items=items,
        total_amount=(float(total) if total is not None else None),
        placed_at=_parse_dt(order.get("created_at")),
    )
