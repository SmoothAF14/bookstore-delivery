"""
test_timeline.py — Tests for the delivery-status timeline and the merge of
tracking-bot checkpoints into it.
"""
from datetime import datetime, timezone

from app.schemas.delivery import (
    ClassifyOrderRequest,
    TimelineStage,
    TrackingCheckpoint,
)
from app.services import dispatch_service, timeline_service


def _decision():
    req = ClassifyOrderRequest(
        order_id="o1",
        items=[{"book_id": "b1", "quantity": 1, "unit_price": 100.0, "stock": 10}],
    )
    return dispatch_service.decide(req)


def _cp(status, label, **kw):
    return TrackingCheckpoint(
        status=status,
        label=label,
        timestamp=datetime.now(timezone.utc),
        **kw,
    )


def test_initial_timeline_has_lead_in_stages():
    tl = timeline_service.build_initial_timeline(_decision())
    stages = [e.stage for e in tl.events]
    assert TimelineStage.PLACED in stages
    assert TimelineStage.CLASSIFIED in stages
    assert TimelineStage.AWAITING_DISPATCH in stages
    # Dispatch is projected (not completed) before any tracking.
    dispatched = [e for e in tl.events if e.stage == TimelineStage.DISPATCHED]
    assert dispatched and dispatched[0].completed is False


def test_merge_marks_reached_stages_completed():
    tl = timeline_service.build_initial_timeline(_decision())
    checkpoints = [
        _cp("dispatched", "Dispatched from fulfilment centre", location="Mumbai Hub"),
        _cp("in_transit", "In transit", location="Pune"),
        _cp("out_for_delivery", "Out for delivery"),
    ]
    merged = timeline_service.merge_tracking_checkpoints(tl, checkpoints)
    by_stage = {e.stage: e for e in merged.events}

    assert by_stage[TimelineStage.DISPATCHED].completed is True
    assert by_stage[TimelineStage.IN_TRANSIT].completed is True
    assert by_stage[TimelineStage.OUT_FOR_DELIVERY].completed is True
    # Delivered not reached yet -> absent.
    assert TimelineStage.DELIVERED not in by_stage


def test_merge_is_ordered_canonically():
    tl = timeline_service.build_initial_timeline(_decision())
    # Feed checkpoints out of order; result must still be canonical.
    checkpoints = [
        _cp("out_for_delivery", "Out for delivery"),
        _cp("dispatched", "Dispatched"),
        _cp("delivered", "Delivered"),
        _cp("in_transit", "In transit"),
    ]
    merged = timeline_service.merge_tracking_checkpoints(tl, checkpoints)
    indices = [timeline_service._STAGE_INDEX[e.stage] for e in merged.events]
    assert indices == sorted(indices)
    assert merged.events[-1].stage == TimelineStage.DELIVERED
    assert merged.events[-1].completed is True
