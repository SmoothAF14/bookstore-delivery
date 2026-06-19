"""
delivery.py — Request/response schemas for the delivery service.

These mirror the shape of the Django backend's order data (apps/orders): an
order has a total_amount and a list of items (each with quantity / unit_price),
which the classifier reduces into a delivery tier and dispatch decision.
"""
from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class DeliveryTier(str, Enum):
    """Delivery tier an order is classified into."""
    EXPRESS = "express"      # high-value or flagged for fast handling
    STANDARD = "standard"    # default
    BULK = "bulk"            # large-quantity orders
    BACKORDER = "backorder"  # insufficient stock; dispatch held


class OrderItemIn(BaseModel):
    """A single line item, matching the backend's OrderItem."""
    book_id: str
    quantity: int = Field(ge=1)
    unit_price: float = Field(ge=0)
    # Available stock for this book, if known. None means "unknown / assume ok".
    stock: int | None = Field(default=None, ge=0)


class ClassifyOrderRequest(BaseModel):
    """Input to classify an order."""
    order_id: str
    items: list[OrderItemIn] = Field(min_length=1)
    # Optional; recomputed from items when omitted so the bot can't be fed a
    # mismatched total.
    total_amount: float | None = Field(default=None, ge=0)
    # When the order was placed (order.created_at). The dispatch ETA is anchored
    # to this, NOT to the current time — so the ETA stays fixed across refreshes.
    # Falls back to "now" only when the caller can't supply it.
    placed_at: datetime | None = None


class DispatchDecision(BaseModel):
    """The classifier + dispatch output for an order."""
    order_id: str
    tier: DeliveryTier
    total_quantity: int
    total_amount: float
    in_stock: bool
    dispatch_eta: datetime
    reasons: list[str]


class TimelineStage(str, Enum):
    """Ordered delivery-status timeline stages shown on the orders page."""
    PLACED = "placed"
    CLASSIFIED = "classified"
    AWAITING_DISPATCH = "awaiting_dispatch"
    DISPATCHED = "dispatched"
    IN_TRANSIT = "in_transit"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"


class TimelineEvent(BaseModel):
    """A single point on the delivery-status timeline."""
    stage: TimelineStage
    label: str
    at: datetime
    note: str | None = None
    # True for stages reached so far; False for projected/future stages.
    completed: bool = True


class DeliveryTimelineResponse(BaseModel):
    """The full delivery-status timeline for an order."""
    order_id: str
    tier: DeliveryTier | None = None
    events: list[TimelineEvent]


# ---------------------------------------------------------------------------
# Shared contract with bookstore-tracking.
#
# These mirror the tracking bot's TrackingCheckpoint / TrackingStateResponse
# (app/schemas/tracking.py in bookstore-tracking). The delivery bot pulls these
# from GET {TRACKING_SERVICE_URL}/tracking/{order_id} and also accepts a single
# pushed checkpoint on POST /delivery/{order_id}/checkpoint.
# ---------------------------------------------------------------------------

# Tracking statuses emitted by the tracking bot.
TrackingStatus = Literal[
    "pending",
    "dispatched",
    "in_transit",
    "out_for_delivery",
    "delivered",
]

# Map each tracking status onto our delivery-timeline stage.
TRACKING_STATUS_TO_STAGE: dict[str, "TimelineStage"] = {
    "pending": TimelineStage.AWAITING_DISPATCH,
    "dispatched": TimelineStage.DISPATCHED,
    "in_transit": TimelineStage.IN_TRANSIT,
    "out_for_delivery": TimelineStage.OUT_FOR_DELIVERY,
    "delivered": TimelineStage.DELIVERED,
}


class GeoPoint(BaseModel):
    """A mock lat/lng point on the route (from the tracking bot)."""
    lat: float
    lng: float
    label: str | None = None


class TrackingCheckpoint(BaseModel):
    """A single checkpoint from the tracking bot. Extra fields are ignored so
    minor additions on the tracking side don't break the delivery bot."""
    model_config = {"extra": "ignore"}

    status: TrackingStatus
    label: str
    description: str | None = None
    location: str | None = None
    point: GeoPoint | None = None
    timestamp: datetime
    is_current: bool = False


class TrackingState(BaseModel):
    """The tracking bot's GET /tracking/{order_id} response (subset we need)."""
    model_config = {"extra": "ignore"}

    order_id: str
    status: TrackingStatus
    order_status: str | None = None
    origin: str | None = None
    destination: str | None = None
    eta: datetime | None = None
    checkpoints: list[TrackingCheckpoint] = Field(default_factory=list)
