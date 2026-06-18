"""
timeline_service.py — Delivery-status timeline management.

Builds the per-order delivery-status timeline shown on the orders page. The
early stages (placed → classified → awaiting dispatch → projected dispatch) are
owned here; the later movement stages (in transit → out for delivery →
delivered) are filled in from the tracking bot's checkpoints once it takes over.

State is currently derived on demand from the dispatch decision. Persisting the
timeline (e.g. in Redis/DB) and merging live tracking checkpoints are the next
steps — see the TODOs.
"""
from datetime import datetime, timezone

from app.schemas.delivery import (
    DeliveryTimelineResponse,
    DispatchDecision,
    TimelineEvent,
    TimelineStage,
)

# Human-readable labels for each stage.
_STAGE_LABELS: dict[TimelineStage, str] = {
    TimelineStage.PLACED: "Order placed",
    TimelineStage.CLASSIFIED: "Order classified",
    TimelineStage.AWAITING_DISPATCH: "Awaiting dispatch",
    TimelineStage.DISPATCHED: "Dispatched from store",
    TimelineStage.IN_TRANSIT: "In transit",
    TimelineStage.OUT_FOR_DELIVERY: "Out for delivery",
    TimelineStage.DELIVERED: "Delivered",
}


def build_initial_timeline(
    decision: DispatchDecision,
    placed_at: datetime | None = None,
) -> DeliveryTimelineResponse:
    """Build the timeline right after classification.

    Completed stages: PLACED, CLASSIFIED. Then a projected AWAITING_DISPATCH and
    a projected DISPATCHED at the computed ETA. Movement stages are added later
    by the tracking bot, so they are not included yet.
    """
    now = placed_at or datetime.now(timezone.utc)

    events: list[TimelineEvent] = [
        TimelineEvent(
            stage=TimelineStage.PLACED,
            label=_STAGE_LABELS[TimelineStage.PLACED],
            at=now,
            completed=True,
        ),
        TimelineEvent(
            stage=TimelineStage.CLASSIFIED,
            label=_STAGE_LABELS[TimelineStage.CLASSIFIED],
            at=now,
            note=f"Tier: {decision.tier.value}",
            completed=True,
        ),
        TimelineEvent(
            stage=TimelineStage.AWAITING_DISPATCH,
            label=_STAGE_LABELS[TimelineStage.AWAITING_DISPATCH],
            at=now,
            note=(
                "Awaiting restock before dispatch."
                if not decision.in_stock
                else "Queued for dispatch."
            ),
            completed=True,
        ),
        # Projected — not yet reached.
        TimelineEvent(
            stage=TimelineStage.DISPATCHED,
            label=_STAGE_LABELS[TimelineStage.DISPATCHED],
            at=decision.dispatch_eta,
            note="Projected dispatch time.",
            completed=False,
        ),
    ]

    return DeliveryTimelineResponse(
        order_id=decision.order_id,
        tier=decision.tier,
        events=events,
    )


# TODO: persist_timeline(order_id, timeline) — store in Redis/DB so reads don't
#       require re-classification.
# TODO: merge_tracking_checkpoints(order_id, checkpoints) — fold the tracking
#       bot's IN_TRANSIT / OUT_FOR_DELIVERY / DELIVERED checkpoints into the
#       stored timeline (see app/core/tracking_client.py).
