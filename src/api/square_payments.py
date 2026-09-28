"""Square Payment Webhook & Subscription Management.

Receives payment confirmations from Square and activates user subscriptions.
Also provides an endpoint for the frontend to activate plans after checkout.
"""
from fastapi import APIRouter, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone

from src.db import SessionLocal
from src.models.user import User

router = APIRouter()

# Plan configuration
PLANS = {
    "starter": {"price": 149, "chases": 100, "name": "Starter"},
    "growth":  {"price": 299, "chases": 300, "name": "Growth"},
    "scale":   {"price": 497, "chases": 750, "name": "Scale"},
}


class ActivatePlanRequest(BaseModel):
    """Called by the frontend after Square checkout redirect."""
    email: str
    plan: str
    square_transaction_id: Optional[str] = None


@router.post("/activate")
def activate_plan(data: ActivatePlanRequest):
    """Activate a subscription plan for a user after Square payment.
    
    Called from the Payment Success page. If the user doesn't exist yet,
    they'll register first and then hit this endpoint.
    """
    if data.plan not in PLANS:
        raise HTTPException(status_code=400, detail=f"Invalid plan: {data.plan}")
    
    plan_config = PLANS[data.plan]
    
    db: Session = SessionLocal()
    try:
        user = db.query(User).filter(User.username == data.email).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found. Please register first.")
        
        user.subscription_plan = data.plan
        user.subscription_status = "active"
        user.subscription_started_at = datetime.now(timezone.utc)
        user.square_payment_id = data.square_transaction_id
        user.chases_limit = plan_config["chases"]
        user.chases_used = 0
        
        db.commit()
        
        return {
            "msg": "Subscription activated!",
            "plan": data.plan,
            "plan_name": plan_config["name"],
            "chases_limit": plan_config["chases"],
            "status": "active"
        }
    finally:
        db.close()


@router.post("/webhook")
async def square_webhook(request: Request):
    """Receives webhook events from Square.
    
    Square sends events like 'payment.completed' when a checkout
    link payment is finalized. This confirms the payment server-side.
    
    In production, you should verify the webhook signature using
    your Square webhook signature key.
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    
    event_type = payload.get("type", "")
    
    if event_type == "payment.completed":
        payment_data = payload.get("data", {}).get("object", {}).get("payment", {})
        payment_id = payment_data.get("id", "")
        amount_cents = payment_data.get("amount_money", {}).get("amount", 0)
        buyer_email = payment_data.get("buyer_email_address", "")
        
        # Determine plan from payment amount
        amount_dollars = amount_cents / 100
        plan = None
        for plan_key, config in PLANS.items():
            if config["price"] == amount_dollars:
                plan = plan_key
                break
        
        if not plan:
            # Log but don't fail — could be a different Square payment
            return {"msg": f"Payment received but amount ${amount_dollars} doesn't match any plan"}
        
        plan_config = PLANS[plan]
        
        if buyer_email:
            db: Session = SessionLocal()
            try:
                user = db.query(User).filter(User.username == buyer_email).first()
                if user:
                    user.subscription_plan = plan
                    user.subscription_status = "active"
                    user.subscription_started_at = datetime.now(timezone.utc)
                    user.square_payment_id = payment_id
                    user.chases_limit = plan_config["chases"]
                    user.chases_used = 0
                    db.commit()
                    return {"msg": f"Subscription activated for {buyer_email}: {plan_config['name']}"}
            finally:
                db.close()
        
        return {"msg": "Payment received", "payment_id": payment_id, "plan": plan}
    
    # Acknowledge other event types
    return {"msg": f"Event received: {event_type}"}


@router.get("/plans")
def get_plans():
    """Public endpoint — returns available plans and pricing."""
    return {
        "plans": [
            {
                "id": "starter",
                "name": "Starter",
                "price": 149,
                "chases": 100,
                "per_chase": 1.49,
                "checkout_url": "https://square.link/u/MOsw5n5g"
            },
            {
                "id": "growth",
                "name": "Growth",
                "price": 299,
                "chases": 300,
                "per_chase": 0.99,
                "checkout_url": "https://square.link/u/nYps8IHC",
                "badge": "The best deal"
            },
            {
                "id": "scale",
                "name": "Scale",
                "price": 497,
                "chases": 750,
                "per_chase": 0.66,
                "checkout_url": "https://square.link/u/IqJw5Qom"
            }
        ]
    }