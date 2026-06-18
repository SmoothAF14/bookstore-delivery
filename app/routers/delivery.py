"""
delivery.py — Delivery router.

Endpoints:
  POST /delivery/classify             Classify an order -> DispatchDecision.
  POST /delivery/{order_id}/timeline  Build the delivery-status timeline.

Classification is synchronous and cheap (pure functions), and is also exposed
as a Celery task for the async/scheduled path (see app/tasks/delivery_tasks.py).
"""
from fastapi import APIRouter

from app.schemas.delivery import (
    ClassifyOrderRequest,
    DeliveryTimelineResponse,
    DispatchDecision,
)
from app.services import dispatch_service, timeline_service

router = APIRouter()


@router.post("/classify", response_model=DispatchDecision)
def classify_order(request: ClassifyOrderRequest) -> DispatchDecision:
    """Classify an order and return its dispatch decision."""
    return dispatch_service.decide(request)


@router.post("/{order_id}/timeline", response_model=DeliveryTimelineResponse)
def order_timeline(order_id: str, request: ClassifyOrderRequest) -> DeliveryTimelineResponse:
    """Build the delivery-status timeline for an order from its current items."""
    # Keep the path order_id authoritative over any body value.
    request.order_id = order_id
    decision = dispatch_service.decide(request)
    return timeline_service.build_initial_timeline(decision)
