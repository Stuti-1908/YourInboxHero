"""Stripe Checkout & Webhook — subscription management.

Replaces the previous Square integration. Unlike Square's static checkout
links, Stripe Checkout Sessions are created server-side per request, and
the ONLY trusted path for activating a subscription is the signature-verified
webhook — there is no unauthenticated "/activate" endpoint. A user calling
an API directly cannot grant themselves a paid plan.
"""
import structlog
from fastapi import APIRouter, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime, timezone

import stripe

from src.config.settings import get_settings
from src.db import SessionLocal
from src.models.user import User
from src.models.pending_subscription import PendingSubscription

logger = structlog.get_logger(__name__)
settings = get_settings()
router = APIRouter()

# Plan configuration. Stripe Price IDs are configured via environment
# variables (see .env.example) since they are created per-Stripe-account.
PLANS = {
    "starter": {"price": 149, "chases": 100, "name": "Starter", "price_id_attr": "stripe_price_starter"},
    "growth":  {"price": 299, "chases": 300, "name": "Growth", "price_id_attr": "stripe_price_growth"},
    "scale":   {"price": 497, "chases": 750, "name": "Scale", "price_id_attr": "stripe_price_scale"},
}


def _get_stripe_client():
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=503, detail="Payments are not configured")
    stripe.api_key = settings.stripe_secret_key
    return stripe


class CreateCheckoutSessionRequest(BaseModel):
    plan: str
    email: str


@router.post("/create-checkout-session")
def create_checkout_session(data: CreateCheckoutSessionRequest):
    """Create a Stripe Checkout Session for the given plan and redirect the
    user there. The user's email is attached as client_reference_id / the
    Checkout customer email so the webhook can match it back to a User row.
    """
    if data.plan not in PLANS:
        raise HTTPException(status_code=400, detail=f"Invalid plan: {data.plan}")

    plan_config = PLANS[data.plan]
    price_id = getattr(settings, plan_config["price_id_attr"])
    if not price_id:
        raise HTTPException(status_code=503, detail=f"Plan '{data.plan}' is not configured (missing Stripe Price ID)")

    client = _get_stripe_client()
    try:
        session = client.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            customer_email=data.email,
            client_reference_id=data.email,
            metadata={"plan": data.plan, "email": data.email},
            success_url=f"{settings.stripe_success_url}?plan={data.plan}&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=settings.stripe_cancel_url,
        )
    except stripe.error.StripeError as e:
        logger.error("stripe_checkout_session_failed", error=str(e))
        raise HTTPException(status_code=502, detail="Could not start checkout")

    return {"checkout_url": session.url}


@router.post("/webhook")
async def stripe_webhook(request: Request):
    """Receives and verifies Stripe webhook events. This is the ONLY place
    a subscription is activated, renewed, or cancelled — never trust a
    client-supplied plan/email pair without this signature check.
    """
    if not settings.stripe_webhook_secret:
        logger.error("stripe_webhook_secret_not_configured")
        raise HTTPException(status_code=503, detail="Webhook not configured")

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, settings.stripe_webhook_secret)
    except (ValueError, stripe.error.SignatureVerificationError) as e:
        logger.warning("stripe_webhook_invalid_signature", error=str(e))
        raise HTTPException(status_code=401, detail="Invalid signature")

    event_type = event["type"]
    db: Session = SessionLocal()
    try:
        if event_type == "checkout.session.completed":
            session = event["data"]["object"]
            plan = session.get("metadata", {}).get("plan")
            email = session.get("metadata", {}).get("email") or session.get("customer_email")

            if not plan or plan not in PLANS or not email:
                logger.warning("stripe_webhook_missing_plan_or_email", event_id=event["id"])
                return {"msg": "Ignored — missing plan or email"}

            plan_config = PLANS[plan]
            user = db.query(User).filter(User.username == email).first()

            if not user:
                # Stripe Checkout collects payment before this app has ever
                # seen the customer — the user may register afterwards. Park
                # the paid plan so registration can pick it up instead of
                # losing the payment.
                pending = db.query(PendingSubscription).filter(PendingSubscription.email == email).first()
                if not pending:
                    pending = PendingSubscription(email=email)
                    db.add(pending)
                pending.plan = plan
                pending.chases_limit = plan_config["chases"]
                pending.stripe_customer_id = session.get("customer")
                pending.stripe_subscription_id = session.get("subscription")
                db.commit()
                logger.info("subscription_pending_registration", email=email, plan=plan)
                return {"msg": f"No user found for {email} yet — plan will activate on registration"}

            user.subscription_plan = plan
            user.subscription_status = "active"
            user.subscription_started_at = datetime.now(timezone.utc)
            user.stripe_customer_id = session.get("customer")
            user.stripe_subscription_id = session.get("subscription")
            user.chases_limit = plan_config["chases"]
            user.chases_used = 0
            db.commit()
            logger.info("subscription_activated", email=email, plan=plan)
            return {"msg": f"Subscription activated for {email}: {plan_config['name']}"}

        elif event_type == "customer.subscription.deleted":
            subscription = event["data"]["object"]
            user = db.query(User).filter(User.stripe_subscription_id == subscription["id"]).first()
            if user:
                user.subscription_status = "cancelled"
                db.commit()
                logger.info("subscription_cancelled", user_id=user.id)
            return {"msg": "Subscription cancelled"}

        elif event_type == "invoice.payment_failed":
            invoice = event["data"]["object"]
            user = db.query(User).filter(User.stripe_customer_id == invoice.get("customer")).first()
            if user:
                user.subscription_status = "past_due"
                db.commit()
                logger.warning("subscription_payment_failed", user_id=user.id)
            return {"msg": "Payment failure recorded"}

        return {"msg": f"Event received: {event_type}"}
    finally:
        db.close()


@router.get("/plans")
def get_plans():
    """Public endpoint — returns available plans and pricing (no checkout URL;
    the frontend calls /create-checkout-session with the chosen plan + email)."""
    return {
        "plans": [
            {"id": "starter", "name": "Starter", "price": 149, "chases": 100, "per_chase": 1.49},
            {"id": "growth", "name": "Growth", "price": 299, "chases": 300, "per_chase": 0.99, "badge": "The best deal"},
            {"id": "scale", "name": "Scale", "price": 497, "chases": 750, "per_chase": 0.66},
        ]
    }
