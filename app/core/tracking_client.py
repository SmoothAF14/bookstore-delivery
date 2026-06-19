"""
tracking_client.py — httpx client for the tracking service.

Pulls tracking state (and its checkpoints) from bookstore-tracking so the
delivery-status timeline can be enriched with live shipment movement.

Tracking is the source of truth for the movement stages (dispatched →
in_transit → out_for_delivery → delivered); the delivery bot owns the earlier
classification/dispatch stages. Pulls are best-effort: if tracking is
unreachable or hasn't started for an order yet, callers get None and fall back
to the classification-only timeline.
"""
import logging

import httpx

from app.core.config import settings
from app.schemas.delivery import TrackingState

logger = logging.getLogger(__name__)


def get_tracking_state(order_id: str, access_token: str | None = None) -> TrackingState | None:
    """Fetch GET {TRACKING_SERVICE_URL}/tracking/{order_id}.

    Returns a parsed TrackingState, or None if tracking isn't available for the
    order (404) or the service can't be reached.
    """
    headers = {}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    url = f"{settings.tracking_service_url}/tracking/{order_id}"
    try:
        with httpx.Client(timeout=5.0, headers=headers) as client:
            resp = client.get(url)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return TrackingState.model_validate(resp.json())
    except httpx.HTTPError as exc:
        logger.info("Tracking pull skipped for %s: %s", order_id, exc)
        return None
