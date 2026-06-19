"""
dispatch_service.py — Dispatch-time decisioning.

Turns a classified order into a concrete DispatchDecision: which tier, the
computed quantities/value, stock status, and the dispatch ETA derived from the
tier's SLA (hours from order placement).

The delivery bot is the platform's 3rd AI feature: after the deterministic
classifier runs, an optional LLM review layer (same LLM_API_KEY as the
assistant + tracking bots) may adjust the tier with a short rationale. The
rules are always the fallback, so the bot works with or without an LLM key.
"""
import json
import logging
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.schemas.delivery import (
    ClassifyOrderRequest,
    DeliveryTier,
    DispatchDecision,
)
from app.services import classifier

logger = logging.getLogger(__name__)

# Hours-from-placement SLA per tier.
_TIER_SLA_HOURS: dict[DeliveryTier, int] = {
    DeliveryTier.EXPRESS: settings.dispatch_hours_express,
    DeliveryTier.STANDARD: settings.dispatch_hours_standard,
    DeliveryTier.BULK: settings.dispatch_hours_bulk,
    DeliveryTier.BACKORDER: settings.dispatch_hours_backorder,
}

_LLM_SYSTEM_PROMPT = (
    "You are a delivery-operations classifier for an online bookstore. You are "
    "given an order's computed metrics and a rule-based delivery tier. Tiers: "
    "express (fast handling), standard (default), bulk (large quantity), "
    "backorder (insufficient stock; dispatch held). You may CONFIRM the "
    "rule-based tier or override it ONLY when clearly justified, but you must "
    "NEVER move an order out of 'backorder' if stock is insufficient. Respond "
    'with ONLY a JSON object: {"tier": "<tier>", "reason": "<short reason>"}.'
)


def dispatch_eta(tier: DeliveryTier, placed_at: datetime | None = None) -> datetime:
    """Compute the dispatch ETA for a tier, relative to placement (default now)."""
    base = placed_at or datetime.now(timezone.utc)
    return base + timedelta(hours=_TIER_SLA_HOURS[tier])


def _llm_review_tier(
    request: ClassifyOrderRequest,
    rule_tier: DeliveryTier,
    qty: int,
    value: float,
    in_stock: bool,
) -> tuple[DeliveryTier, str | None]:
    """Ask the LLM to confirm/adjust the tier. Falls back to the rule tier.

    Never raises — any failure (no key, SDK missing, bad output) returns the
    rule-based tier so classification always succeeds.
    """
    if not settings.llm_enabled:
        return rule_tier, None

    try:
        from app.core.llm import get_llm_client
        client = get_llm_client()
    except Exception as exc:  # noqa: BLE001 — no key/SDK -> rules only
        logger.info("Delivery classifier using rules only (no LLM): %s", exc)
        return rule_tier, None

    user = (
        f"Order metrics:\n"
        f"- total quantity: {qty}\n"
        f"- order value: {value:.2f}\n"
        f"- all items in stock: {in_stock}\n"
        f"- rule-based tier: {rule_tier.value}\n"
        f"Confirm or adjust the tier."
    )

    try:
        resp = client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": _LLM_SYSTEM_PROMPT},
                {"role": "user", "content": user},
            ],
            max_tokens=settings.llm_max_tokens,
        )
        content = (resp.choices[0].message.content or "").strip()
        start, end = content.find("{"), content.rfind("}")
        data = json.loads(content[start:end + 1]) if start != -1 else {}
        chosen = data.get("tier")
        reason = data.get("reason")
        valid = {t.value for t in DeliveryTier}
        if chosen in valid:
            tier = DeliveryTier(chosen)
            # Safety rail: never override a genuine backorder into dispatch.
            if not in_stock:
                return DeliveryTier.BACKORDER, "Stock insufficient — held regardless of LLM."
            if tier != rule_tier:
                return tier, (reason or f"LLM adjusted {rule_tier.value} -> {tier.value}.")
            return rule_tier, reason
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM tier review failed, using rules: %s", exc)

    return rule_tier, None


def decide(request: ClassifyOrderRequest, placed_at: datetime | None = None) -> DispatchDecision:
    """Classify the order and produce a full dispatch decision.

    The dispatch ETA is anchored to when the order was PLACED — preferring an
    explicit `placed_at` arg, then the request's `placed_at` (order.created_at),
    and only falling back to "now" when neither is available. This keeps the ETA
    stable across refreshes instead of sliding forward with the current time.
    """
    anchor = placed_at or request.placed_at
    tier, reasons = classifier.classify(request)
    qty = classifier.total_quantity(request.items)
    value = classifier.order_value(request.items, request.total_amount)
    in_stock = classifier.is_in_stock(request.items)

    # LLM review layer (3rd AI feature) — may adjust the tier.
    llm_tier, llm_reason = _llm_review_tier(request, tier, qty, value, in_stock)
    if llm_tier != tier:
        reasons.append(f"LLM review: {tier.value} -> {llm_tier.value}.")
        tier = llm_tier
    if llm_reason:
        reasons.append(f"LLM: {llm_reason}")

    eta = dispatch_eta(tier, anchor)
    reasons.append(f"Dispatch SLA: {_TIER_SLA_HOURS[tier]}h from placement.")

    return DispatchDecision(
        order_id=request.order_id,
        tier=tier,
        total_quantity=qty,
        total_amount=value,
        in_stock=in_stock,
        dispatch_eta=eta,
        reasons=reasons,
    )
