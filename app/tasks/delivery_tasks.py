"""
delivery_tasks.py — Celery tasks for asynchronous delivery processing.

Wraps the synchronous classification/dispatch logic so it can be scheduled and
executed off the request path. Results are returned as plain dicts (JSON-safe)
because the free-tier setup keeps the Celery result backend off.
"""
from app.celery_app import celery
from app.schemas.delivery import ClassifyOrderRequest
from app.services import dispatch_service, timeline_service


@celery.task(name="delivery.classify_order")
def classify_order(payload: dict) -> dict:
    """Classify an order. `payload` matches ClassifyOrderRequest."""
    request = ClassifyOrderRequest.model_validate(payload)
    decision = dispatch_service.decide(request)
    return decision.model_dump(mode="json")


@celery.task(name="delivery.build_timeline")
def build_timeline(payload: dict) -> dict:
    """Classify an order and build its initial delivery-status timeline."""
    request = ClassifyOrderRequest.model_validate(payload)
    decision = dispatch_service.decide(request)
    timeline = timeline_service.build_initial_timeline(decision)
    return timeline.model_dump(mode="json")


# TODO: schedule_dispatch(order_id) — persist the decision and push the
#       dispatch status to the Django backend at the computed ETA.
# TODO: autodiscover: register these in celery_app via autodiscover_tasks.
