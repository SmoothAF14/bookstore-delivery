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
    TRACKING_STATUS_TO_STAGE,
    DeliveryTimelineResponse,
    DispatchDecision,
    TimelineEvent,
    TimelineStage,
    TrackingCheckpoint,
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


# Ordinal position of each stage, used to decide which stage is "current".
_STAGE_SEQUENCE: list[TimelineStage] = [
    TimelineStage.PLACED,
    TimelineStage.CLASSIFIED,
    TimelineStage.AWAITING_DISPATCH,
    TimelineStage.DISPATCHED,
    TimelineStage.IN_TRANSIT,
    TimelineStage.OUT_FOR_DELIVERY,
    TimelineStage.DELIVERED,
]
_STAGE_INDEX: dict[TimelineStage, int] = {s: i for i, s in enumerate(_STAGE_SEQUENCE)}


def merge_tracking_checkpoints(
    timeline: DeliveryTimelineResponse,
    checkpoints: list[TrackingCheckpoint],
) -> DeliveryTimelineResponse:
    """Fold the tracking bot's checkpoints into the delivery-status timeline.

    The tracking bot owns the movement stages (dispatched → in_transit →
    out_for_delivery → delivered). For each checkpoint we map its status to a
    TimelineStage and replace/append the corresponding event as completed. The
    classification lead-in stages (placed/classified/awaiting_dispatch) from the
    initial timeline are preserved.

    The result is re-sorted into canonical stage order, and every stage at or
    before the furthest-reached tracking stage is marked completed (with the
    last one flagged current via the note left intact).
    """
    # Index existing events by stage so tracking can upgrade projected ones.
    events_by_stage: dict[TimelineStage, TimelineEvent] = {e.stage: e for e in timeline.events}

    furthest_idx = -1
    for cp in checkpoints:
        stage = TRACKING_STATUS_TO_STAGE.get(cp.status)
        if stage is None:
            continue
        events_by_stage[stage] = TimelineEvent(
            stage=stage,
            label=cp.label,
            at=cp.timestamp,
            note=cp.location or cp.description,
            completed=True,
        )
        furthest_idx = max(furthest_idx, _STAGE_INDEX[stage])

    # Anything up to the furthest reached stage is completed; later stays projected.
    merged: list[TimelineEvent] = []
    for stage in _STAGE_SEQUENCE:
        ev = events_by_stage.get(stage)
        if ev is None:
            continue
        if _STAGE_INDEX[stage] <= furthest_idx:
            ev = ev.model_copy(update={"completed": True})
        merged.append(ev)

    return DeliveryTimelineResponse(
        order_id=timeline.order_id,
        tier=timeline.tier,
        events=merged,
    )
