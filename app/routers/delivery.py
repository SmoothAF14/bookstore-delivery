"""
delivery.py — Delivery router.

Endpoints:
  POST /delivery/classify             Classify an order -> DispatchDecision.
  POST /delivery/{order_id}/timeline  Build the delivery-status timeline,
                                      enriched with live tracking checkpoints.
  POST /delivery/{order_id}/checkpoint  Receive a single pushed checkpoint from
                                      the tracking bot (best-effort sync).

Classification is synchronous and cheap (pure functions), and is also exposed
as a Celery task for the async/scheduled path (see app/tasks/delivery_tasks.py).
"""
import logging

from fastapi import APIRouter, Depends, HTTPException

from app.core import tracking_client
from app.core import backend_client
from app.core.auth import AuthenticatedUser, require_user
from app.schemas.delivery import (
    ClassifyOrderRequest,
    DeliveryTimelineResponse,
    DispatchDecision,
    TrackingCheckpoint,
)
from app.services import dispatch_service, timeline_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/classify", response_model=DispatchDecision)
def classify_order(
    request: ClassifyOrderRequest,
    user: AuthenticatedUser = Depends(require_user),
) -> DispatchDecision:
    """Classify an order from a supplied payload and return its dispatch decision."""
    return dispatch_service.decide(request)


@router.get("/{order_id}/classify", response_model=DispatchDecision)
def classify_by_order_id(
    order_id: str,
    user: AuthenticatedUser = Depends(require_user),
) -> DispatchDecision:
    """Fetch a real order from the Django backend by id and classify it."""
    try:
        order = backend_client.get_order(order_id, user.access_token)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Could not read order: {exc}") from exc
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")
    request = backend_client.order_to_classify_request(order)
    request.order_id = order_id
    return dispatch_service.decide(request)


@router.post("/{order_id}/timeline", response_model=DeliveryTimelineResponse)
def order_timeline(
    order_id: str,
    request: ClassifyOrderRequest,
    user: AuthenticatedUser = Depends(require_user),
) -> DeliveryTimelineResponse:
    """Build the delivery-status timeline for an order from a supplied payload.

    Starts from the classification/dispatch lead-in stages, then pulls the
    tracking bot's checkpoints (best-effort) and merges them so the movement
    stages reflect live shipment progress.
    """
    # Keep the path order_id authoritative over any body value.
    request.order_id = order_id
    return _build_timeline(order_id, request, user.access_token)


@router.get("/{order_id}/timeline", response_model=DeliveryTimelineResponse)
def order_timeline_by_id(
    order_id: str,
    user: AuthenticatedUser = Depends(require_user),
) -> DeliveryTimelineResponse:
    """Build the delivery-status timeline by fetching the real order from the
    backend (no request body needed). This is what the orders page calls."""
    try:
        order = backend_client.get_order(order_id, user.access_token)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Could not read order: {exc}") from exc
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")
    request = backend_client.order_to_classify_request(order)
    request.order_id = order_id
    return _build_timeline(order_id, request, user.access_token)


def _build_timeline(order_id, request, access_token) -> DeliveryTimelineResponse:
    """Shared timeline builder: classify, then merge live tracking checkpoints."""
    decision = dispatch_service.decide(request)
    # Anchor the lead-in stage timestamps to when the order was placed, so they
    # don't drift on refresh either.
    timeline = timeline_service.build_initial_timeline(decision, placed_at=request.placed_at)

    state = tracking_client.get_tracking_state(order_id, access_token)
    if state and state.checkpoints:
        timeline = timeline_service.merge_tracking_checkpoints(timeline, state.checkpoints)

    return timeline


@router.post("/{order_id}/checkpoint", response_model=DeliveryTimelineResponse)
def receive_checkpoint(
    order_id: str,
    checkpoint: TrackingCheckpoint,
    user: AuthenticatedUser = Depends(require_user),
) -> DeliveryTimelineResponse:
    """Receive a single checkpoint pushed by the tracking bot.

    This is the push counterpart to the pull in /timeline. The tracking bot's
    delivery_client.notify_checkpoint POSTs here as the shipment advances. We
    pull the full tracking state and re-merge so the returned timeline is
    consistent (the single pushed checkpoint is a wake-up signal, not the whole
    truth — tracking remains authoritative).

    NOTE: without the order's items we can't re-run classification here, so the
    returned timeline contains only the movement stages from tracking. The
    orders page should call /timeline (which includes classification) for the
    full picture; this endpoint exists so a push can trigger a refresh.
    """
    logger.info("Checkpoint pushed for order %s: %s", order_id, checkpoint.status)

    state = tracking_client.get_tracking_state(order_id, user.access_token)
    checkpoints = state.checkpoints if state and state.checkpoints else [checkpoint]

    # Empty base timeline (no classification context on the push path).
    base = DeliveryTimelineResponse(order_id=order_id, tier=None, events=[])
    return timeline_service.merge_tracking_checkpoints(base, checkpoints)
