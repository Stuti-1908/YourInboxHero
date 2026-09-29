"""Tests for Stripe checkout session creation and webhook handling.

The core security property under test: a subscription can ONLY be activated
via a signature-verified webhook event, never via a direct/forged request.
"""
import json
import uuid
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.app import app
from src.db import SessionLocal
from src.models.user import User
from src.auth import get_password_hash

client = TestClient(app)


def _make_user(username=None):
    username = username or f"{uuid.uuid4().hex[:8]}@example.com"
    session = SessionLocal()
    try:
        user = User(username=username, hashed_password=get_password_hash("pw"), company_name="Test Co")
        session.add(user)
        session.commit()
        session.refresh(user)
        return user.username
    finally:
        session.close()


def test_create_checkout_session_requires_configured_price(monkeypatch):
    """If STRIPE_SECRET_KEY / price IDs aren't configured, fail clearly (503), not silently."""
    from src.api import stripe_payments
    monkeypatch.setattr(stripe_payments.settings, "stripe_secret_key", None)

    resp = client.post("/api/payments/create-checkout-session", json={"plan": "growth", "email": "a@b.com"})
    assert resp.status_code == 503


def test_create_checkout_session_rejects_invalid_plan():
    resp = client.post("/api/payments/create-checkout-session", json={"plan": "not-a-plan", "email": "a@b.com"})
    assert resp.status_code == 400


def test_create_checkout_session_success(monkeypatch):
    from src.api import stripe_payments
    monkeypatch.setattr(stripe_payments.settings, "stripe_secret_key", "sk_test_fake")
    monkeypatch.setattr(stripe_payments.settings, "stripe_price_growth", "price_fake123")

    mock_session = MagicMock()
    mock_session.url = "https://checkout.stripe.com/fake-session"

    with patch("src.api.stripe_payments.stripe.checkout.Session.create", return_value=mock_session) as mock_create:
        resp = client.post("/api/payments/create-checkout-session", json={"plan": "growth", "email": "a@b.com"})

    assert resp.status_code == 200
    assert resp.json()["checkout_url"] == "https://checkout.stripe.com/fake-session"
    mock_create.assert_called_once()
    assert mock_create.call_args.kwargs["mode"] == "subscription"


def test_webhook_rejects_missing_secret_config(monkeypatch):
    from src.api import stripe_payments
    monkeypatch.setattr(stripe_payments.settings, "stripe_webhook_secret", None)

    resp = client.post("/api/payments/webhook", content=b"{}", headers={"stripe-signature": "fake"})
    assert resp.status_code == 503


def test_webhook_rejects_invalid_signature(monkeypatch):
    from src.api import stripe_payments
    monkeypatch.setattr(stripe_payments.settings, "stripe_webhook_secret", "whsec_fake")

    resp = client.post("/api/payments/webhook", content=b'{"type": "checkout.session.completed"}', headers={"stripe-signature": "bad-sig"})
    assert resp.status_code == 401


def test_webhook_activates_subscription_on_verified_event(monkeypatch):
    """This is the critical security test: activation only happens through
    a signature-verified event — construct_event standing in for Stripe's
    real signature check."""
    from src.api import stripe_payments
    monkeypatch.setattr(stripe_payments.settings, "stripe_webhook_secret", "whsec_fake")

    username = _make_user()

    fake_event = {
        "id": "evt_test123",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "customer": "cus_fake123",
                "subscription": "sub_fake123",
                "customer_email": username,
                "metadata": {"plan": "growth", "email": username},
            }
        },
    }

    with patch("src.api.stripe_payments.stripe.Webhook.construct_event", return_value=fake_event):
        resp = client.post("/api/payments/webhook", content=b"{}", headers={"stripe-signature": "valid-per-mock"})

    assert resp.status_code == 200

    session = SessionLocal()
    try:
        user = session.query(User).filter(User.username == username).first()
        assert user.subscription_plan == "growth"
        assert user.subscription_status == "active"
        assert user.stripe_customer_id == "cus_fake123"
        assert user.stripe_subscription_id == "sub_fake123"
        assert user.chases_limit == 300
    finally:
        session.close()


def test_activate_endpoint_no_longer_exists():
    """The old unauthenticated /activate endpoint (Square era) must not exist —
    it was a security hole allowing anyone to grant themselves a paid plan."""
    resp = client.post("/api/payments/activate", json={"email": "a@b.com", "plan": "growth"})
    assert resp.status_code in (404, 405)


def test_webhook_marks_subscription_past_due_on_payment_failure(monkeypatch):
    from src.api import stripe_payments
    monkeypatch.setattr(stripe_payments.settings, "stripe_webhook_secret", "whsec_fake")

    username = _make_user()
    session = SessionLocal()
    try:
        user = session.query(User).filter(User.username == username).first()
        user.stripe_customer_id = "cus_fake456"
        user.subscription_status = "active"
        session.commit()
    finally:
        session.close()

    fake_event = {
        "id": "evt_fail1",
        "type": "invoice.payment_failed",
        "data": {"object": {"customer": "cus_fake456"}},
    }

    with patch("src.api.stripe_payments.stripe.Webhook.construct_event", return_value=fake_event):
        resp = client.post("/api/payments/webhook", content=b"{}", headers={"stripe-signature": "valid-per-mock"})

    assert resp.status_code == 200
    session = SessionLocal()
    try:
        user = session.query(User).filter(User.username == username).first()
        assert user.subscription_status == "past_due"
    finally:
        session.close()


def test_webhook_reactivates_subscription_on_payment_success_after_past_due(monkeypatch):
    """A subscription that lapsed to past_due must flip back to active once
    a retried/renewed payment succeeds -- this was a real gap: nothing
    previously listened for invoice.payment_succeeded at all."""
    from src.api import stripe_payments
    monkeypatch.setattr(stripe_payments.settings, "stripe_webhook_secret", "whsec_fake")

    username = _make_user()
    session = SessionLocal()
    try:
        user = session.query(User).filter(User.username == username).first()
        user.stripe_customer_id = "cus_fake789"
        user.subscription_status = "past_due"
        session.commit()
    finally:
        session.close()

    fake_event = {
        "id": "evt_success1",
        "type": "invoice.payment_succeeded",
        "data": {"object": {"customer": "cus_fake789"}},
    }

    with patch("src.api.stripe_payments.stripe.Webhook.construct_event", return_value=fake_event):
        resp = client.post("/api/payments/webhook", content=b"{}", headers={"stripe-signature": "valid-per-mock"})

    assert resp.status_code == 200
    session = SessionLocal()
    try:
        user = session.query(User).filter(User.username == username).first()
        assert user.subscription_status == "active"
    finally:
        session.close()
