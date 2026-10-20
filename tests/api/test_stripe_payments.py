"""Tests for Stripe checkout session creation and webhook handling.

The core security property under test: a subscription can ONLY be activated
via a signature-verified webhook event, never via a direct/forged request.
"""
import uuid
from unittest.mock import patch, MagicMock

import stripe
from fastapi.testclient import TestClient

from src.app import app
from src.db import SessionLocal
from src.models.user import User
from src.auth import get_password_hash

client = TestClient(app)


class StripeObjectLike(dict):
    """Mimics the real Stripe SDK v16+ typed resource object's dict-access
    behavior for tests: supports obj["key"] (including nested access, since
    __getitem__ wraps any nested dict recursively) but raises AttributeError
    on .get(), exactly like the real stripe.Session/.Subscription/.Invoice.

    A plain dict here was the actual root cause of the 500 bug this guards
    against: .get() silently worked in every test (dicts support it) while
    the real SDK object raised AttributeError in production, so the bug
    shipped with full test coverage passing. Any new fake webhook "object"
    payload must use this instead of a bare dict.
    """
    def __getitem__(self, key):
        value = dict.__getitem__(self, key)
        if isinstance(value, dict) and not isinstance(value, StripeObjectLike):
            return StripeObjectLike(value)
        return value

    def get(self, *args, **kwargs):
        raise AttributeError("'get' is a dict method, but a Session is not a dict. Use .to_dict() to convert it.")


def test_stripe_object_like_fixture_matches_real_sdk_v16_behavior():
    """Regression guard for the test fixture itself: if StripeObjectLike
    ever stops raising on .get(), every test above silently loses its
    ability to catch this exact bug class again (plain dict .get() working
    in tests while the real stripe.Session/.Subscription/.Invoice raises
    AttributeError in production is what let the original bug ship)."""
    obj = StripeObjectLike({"customer": "cus_x", "metadata": {"plan": "growth"}})
    assert obj["customer"] == "cus_x"
    assert obj["metadata"]["plan"] == "growth"
    try:
        obj.get("customer")
        assert False, "StripeObjectLike.get() should have raised AttributeError"
    except AttributeError:
        pass


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


def test_billing_portal_requires_existing_customer():
    """A user who has never completed checkout (no stripe_customer_id) has
    nothing to manage -- must get a clear 400, not a Stripe API error."""
    resp = client.post("/api/payments/portal")
    assert resp.status_code == 400
    assert "billing account" in resp.json()["detail"].lower()


def test_billing_portal_creates_session_for_existing_customer(monkeypatch):
    """The only path to cancel/update payment method/view invoices -- must
    create a real Stripe Billing Portal session scoped to this user's own
    stripe_customer_id and return its hosted URL."""
    from src.api import stripe_payments
    from src.auth import get_current_user
    monkeypatch.setattr(stripe_payments.settings, "stripe_secret_key", "sk_test_fake")

    session = SessionLocal()
    try:
        db_user = User(
            username=f"portaltest_{uuid.uuid4().hex[:8]}@example.com",
            hashed_password=get_password_hash("pw"), company_name="Portal Test Co",
            subscription_status="active", subscription_plan="growth",
            stripe_customer_id="cus_portal_fake123",
        )
        session.add(db_user)
        session.commit()
        user_id = db_user.id
        username = db_user.username
    finally:
        session.close()

    mock_portal_session = MagicMock()
    mock_portal_session.url = "https://billing.stripe.com/p/session/fake123"

    old_override = app.dependency_overrides.get(get_current_user)
    try:
        app.dependency_overrides[get_current_user] = lambda: User(
            id=user_id, username=username, subscription_status="active",
            subscription_plan="growth", stripe_customer_id="cus_portal_fake123",
        )
        with patch("src.api.stripe_payments.stripe.billing_portal.Session.create", return_value=mock_portal_session) as mock_create:
            resp = client.post("/api/payments/portal")
    finally:
        if old_override:
            app.dependency_overrides[get_current_user] = old_override
        else:
            app.dependency_overrides.pop(get_current_user, None)

    assert resp.status_code == 200
    assert resp.json()["portal_url"] == "https://billing.stripe.com/p/session/fake123"
    mock_create.assert_called_once()
    assert mock_create.call_args.kwargs["customer"] == "cus_portal_fake123"


def test_billing_portal_requires_authentication():
    from src.auth import get_current_user
    old_override = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides.pop(get_current_user, None)
    try:
        resp = client.post("/api/payments/portal")
        assert resp.status_code == 401
    finally:
        if old_override:
            app.dependency_overrides[get_current_user] = old_override


def test_billing_portal_handles_stripe_error_gracefully(monkeypatch):
    """A Stripe-side failure (bad API key, customer deleted on Stripe's side,
    etc.) must surface as a clean 502, never an unhandled 500."""
    from src.api import stripe_payments
    from src.auth import get_current_user
    monkeypatch.setattr(stripe_payments.settings, "stripe_secret_key", "sk_test_fake")

    session = SessionLocal()
    try:
        db_user = User(
            username=f"portalerr_{uuid.uuid4().hex[:8]}@example.com",
            hashed_password=get_password_hash("pw"), company_name="Portal Err Co",
            subscription_status="active", stripe_customer_id="cus_err_fake",
        )
        session.add(db_user)
        session.commit()
        user_id = db_user.id
        username = db_user.username
    finally:
        session.close()

    old_override = app.dependency_overrides.get(get_current_user)
    try:
        app.dependency_overrides[get_current_user] = lambda: User(
            id=user_id, username=username, subscription_status="active",
            stripe_customer_id="cus_err_fake",
        )
        with patch(
            "src.api.stripe_payments.stripe.billing_portal.Session.create",
            side_effect=stripe.error.StripeError("boom"),
        ):
            resp = client.post("/api/payments/portal")
    finally:
        if old_override:
            app.dependency_overrides[get_current_user] = old_override
        else:
            app.dependency_overrides.pop(get_current_user, None)

    assert resp.status_code == 502


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
            "object": StripeObjectLike({
                "customer": "cus_fake123",
                "subscription": "sub_fake123",
                "customer_email": username,
                "payment_status": "paid",
                "metadata": {"plan": "growth", "email": username},
            })
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
        "data": {"object": StripeObjectLike({"customer": "cus_fake456"})},
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
        "data": {"object": StripeObjectLike({"customer": "cus_fake789"})},
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


def test_webhook_resets_usage_on_genuine_renewal(monkeypatch):
    """billing_reason=subscription_cycle identifies a real monthly renewal
    -- chases_used and both warning flags must reset so the customer isn't
    permanently capped after their first billing cycle."""
    from src.api import stripe_payments
    monkeypatch.setattr(stripe_payments.settings, "stripe_webhook_secret", "whsec_fake")

    username = _make_user()
    session = SessionLocal()
    try:
        user = session.query(User).filter(User.username == username).first()
        user.stripe_customer_id = "cus_renewal1"
        user.subscription_status = "active"
        user.chases_limit = 300
        user.chases_used = 300
        user.usage_warning_80_sent = True
        user.usage_limit_reached_sent = True
        session.commit()
    finally:
        session.close()

    fake_event = {
        "id": "evt_renewal1",
        "type": "invoice.payment_succeeded",
        "data": {"object": StripeObjectLike({"customer": "cus_renewal1", "billing_reason": "subscription_cycle"})},
    }

    with patch("src.api.stripe_payments.stripe.Webhook.construct_event", return_value=fake_event):
        resp = client.post("/api/payments/webhook", content=b"{}", headers={"stripe-signature": "valid-per-mock"})

    assert resp.status_code == 200
    session = SessionLocal()
    try:
        user = session.query(User).filter(User.username == username).first()
        assert user.chases_used == 0
        assert user.usage_warning_80_sent is False
        assert user.usage_limit_reached_sent is False
    finally:
        session.close()


def test_webhook_does_not_reset_usage_on_first_payment():
    """billing_reason=subscription_create (the very first payment) must
    NOT reset usage -- checkout.session.completed already set it to 0, and
    resetting again here could wipe out chases sent in the gap between the
    two webhook events for a brand-new customer."""
    from src.api import stripe_payments
    stripe_payments.settings.stripe_webhook_secret = "whsec_fake"

    username = _make_user()
    session = SessionLocal()
    try:
        user = session.query(User).filter(User.username == username).first()
        user.stripe_customer_id = "cus_firstpay1"
        user.subscription_status = "active"
        user.chases_limit = 300
        user.chases_used = 5  # a chase already sent in the gap between events
        session.commit()
    finally:
        session.close()

    fake_event = {
        "id": "evt_firstpay1",
        "type": "invoice.payment_succeeded",
        "data": {"object": StripeObjectLike({"customer": "cus_firstpay1", "billing_reason": "subscription_create"})},
    }

    with patch("src.api.stripe_payments.stripe.Webhook.construct_event", return_value=fake_event):
        resp = client.post("/api/payments/webhook", content=b"{}", headers={"stripe-signature": "valid-per-mock"})

    assert resp.status_code == 200
    session = SessionLocal()
    try:
        user = session.query(User).filter(User.username == username).first()
        assert user.chases_used == 5  # unchanged, not wiped back to 0
    finally:
        session.close()


def test_create_checkout_session_rejects_existing_active_subscriber(monkeypatch):
    """A second checkout for an already-active subscriber would double-bill
    them and leave the app tracking only one of the two subscriptions."""
    from src.api import stripe_payments
    monkeypatch.setattr(stripe_payments.settings, "stripe_secret_key", "sk_test_fake")
    monkeypatch.setattr(stripe_payments.settings, "stripe_price_growth", "price_fake123")

    username = _make_user()
    session = SessionLocal()
    try:
        user = session.query(User).filter(User.username == username).first()
        user.subscription_status = "active"
        session.commit()
    finally:
        session.close()

    resp = client.post("/api/payments/create-checkout-session", json={"plan": "growth", "email": username})
    assert resp.status_code == 409


def test_create_checkout_session_allows_inactive_subscriber(monkeypatch):
    """A cancelled/past_due user (or brand new email) must still be able to
    start checkout -- only an already-active subscription blocks it."""
    from src.api import stripe_payments
    monkeypatch.setattr(stripe_payments.settings, "stripe_secret_key", "sk_test_fake")
    monkeypatch.setattr(stripe_payments.settings, "stripe_price_growth", "price_fake123")

    username = _make_user()
    session = SessionLocal()
    try:
        user = session.query(User).filter(User.username == username).first()
        user.subscription_status = "cancelled"
        session.commit()
    finally:
        session.close()

    mock_session = MagicMock()
    mock_session.url = "https://checkout.stripe.com/fake-session"
    with patch("src.api.stripe_payments.stripe.checkout.Session.create", return_value=mock_session):
        resp = client.post("/api/payments/create-checkout-session", json={"plan": "growth", "email": username})
    assert resp.status_code == 200


def test_webhook_deduplicates_replayed_event(monkeypatch):
    """The same event ID delivered twice (Stripe retry, or a manual replay
    from the dashboard) must only apply its side effects once."""
    from src.api import stripe_payments
    monkeypatch.setattr(stripe_payments.settings, "stripe_webhook_secret", "whsec_fake")

    username = _make_user()
    session = SessionLocal()
    try:
        user = session.query(User).filter(User.username == username).first()
        user.stripe_customer_id = "cus_dedup1"
        user.subscription_status = "active"
        user.chases_limit = 300
        user.chases_used = 50
        session.commit()
    finally:
        session.close()

    fake_event = {
        "id": "evt_dedup_test1",
        "type": "invoice.payment_succeeded",
        "data": {"object": StripeObjectLike({"customer": "cus_dedup1", "billing_reason": "subscription_cycle"})},
    }

    with patch("src.api.stripe_payments.stripe.Webhook.construct_event", return_value=fake_event):
        resp1 = client.post("/api/payments/webhook", content=b"{}", headers={"stripe-signature": "valid-per-mock"})
    assert resp1.status_code == 200

    session = SessionLocal()
    try:
        user = session.query(User).filter(User.username == username).first()
        assert user.chases_used == 0  # reset by the first (genuine) delivery
        user.chases_used = 77  # simulate chases sent since the renewal reset
        session.commit()
    finally:
        session.close()

    # Replay the identical event.
    with patch("src.api.stripe_payments.stripe.Webhook.construct_event", return_value=fake_event):
        resp2 = client.post("/api/payments/webhook", content=b"{}", headers={"stripe-signature": "valid-per-mock"})
    assert resp2.status_code == 200
    assert resp2.json()["msg"] == "Event already processed"

    session = SessionLocal()
    try:
        user = session.query(User).filter(User.username == username).first()
        # Must NOT have been reset a second time by the replay.
        assert user.chases_used == 77
    finally:
        session.close()


def test_webhook_subscription_updated_changes_plan(monkeypatch):
    """A plan change made directly in Stripe (or via the billing portal)
    must sync the new plan and chase limit without touching chases_used."""
    from src.api import stripe_payments
    monkeypatch.setattr(stripe_payments.settings, "stripe_webhook_secret", "whsec_fake")
    monkeypatch.setattr(stripe_payments.settings, "stripe_price_scale", "price_scale_fake")

    username = _make_user()
    session = SessionLocal()
    try:
        user = session.query(User).filter(User.username == username).first()
        user.stripe_subscription_id = "sub_upgrade1"
        user.subscription_plan = "growth"
        user.subscription_status = "active"
        user.chases_limit = 300
        user.chases_used = 120
        session.commit()
    finally:
        session.close()

    fake_event = {
        "id": "evt_subupdate1",
        "type": "customer.subscription.updated",
        "data": {"object": StripeObjectLike({
            "id": "sub_upgrade1",
            "items": {"data": [{"price": {"id": "price_scale_fake"}}]},
        })},
    }

    with patch("src.api.stripe_payments.stripe.Webhook.construct_event", return_value=fake_event):
        resp = client.post("/api/payments/webhook", content=b"{}", headers={"stripe-signature": "valid-per-mock"})
    assert resp.status_code == 200

    session = SessionLocal()
    try:
        user = session.query(User).filter(User.username == username).first()
        assert user.subscription_plan == "scale"
        assert user.chases_limit == 750
        assert user.chases_used == 120  # untouched by a mid-cycle tier change
    finally:
        session.close()


def test_webhook_subscription_updated_ignores_unrecognized_price(monkeypatch):
    """An unrecognized price ID (e.g. a one-off add-on, not a plan tier)
    must not crash or silently corrupt the user's plan."""
    from src.api import stripe_payments
    monkeypatch.setattr(stripe_payments.settings, "stripe_webhook_secret", "whsec_fake")

    username = _make_user()
    session = SessionLocal()
    try:
        user = session.query(User).filter(User.username == username).first()
        user.stripe_subscription_id = "sub_unknown1"
        user.subscription_plan = "growth"
        session.commit()
    finally:
        session.close()

    fake_event = {
        "id": "evt_subupdate_unknown1",
        "type": "customer.subscription.updated",
        "data": {"object": StripeObjectLike({
            "id": "sub_unknown1",
            "items": {"data": [{"price": {"id": "price_totally_unrecognized"}}]},
        })},
    }

    with patch("src.api.stripe_payments.stripe.Webhook.construct_event", return_value=fake_event):
        resp = client.post("/api/payments/webhook", content=b"{}", headers={"stripe-signature": "valid-per-mock"})
    assert resp.status_code == 200

    session = SessionLocal()
    try:
        user = session.query(User).filter(User.username == username).first()
        assert user.subscription_plan == "growth"  # unchanged
    finally:
        session.close()


def _checkout_event(event_id, event_type, username, payment_status):
    return {
        "id": event_id,
        "type": event_type,
        "data": {
            "object": StripeObjectLike({
                "customer": f"cus_{event_id}",
                "subscription": f"sub_{event_id}",
                "customer_email": username,
                "payment_status": payment_status,
                "metadata": {"plan": "scale", "email": username},
            })
        },
    }


def _post_event(fake_event):
    with patch("src.api.stripe_payments.stripe.Webhook.construct_event", return_value=fake_event):
        return client.post("/api/payments/webhook", content=b"{}", headers={"stripe-signature": "valid-per-mock"})


def _status_of(username):
    session = SessionLocal()
    try:
        u = session.query(User).filter(User.username == username).first()
        return u.subscription_status, u.subscription_plan
    finally:
        session.close()


def test_webhook_does_not_activate_unpaid_checkout(monkeypatch):
    """A delayed-payment checkout completes with payment_status=unpaid
    before any money moves; activating then would give the plan away free
    if the debit later fails."""
    from src.api import stripe_payments
    monkeypatch.setattr(stripe_payments.settings, "stripe_webhook_secret", "whsec_fake")
    username = _make_user()

    resp = _post_event(_checkout_event("evt_unpaid1", "checkout.session.completed", username, "unpaid"))
    assert resp.status_code == 200
    assert "unpaid" in resp.json()["msg"]
    status, plan = _status_of(username)
    assert status != "active"
    assert plan != "scale"


def test_webhook_activates_on_async_payment_succeeded(monkeypatch):
    from src.api import stripe_payments
    monkeypatch.setattr(stripe_payments.settings, "stripe_webhook_secret", "whsec_fake")
    username = _make_user()

    _post_event(_checkout_event("evt_async1", "checkout.session.completed", username, "unpaid"))
    assert _status_of(username)[0] != "active"

    resp = _post_event(_checkout_event("evt_async2", "checkout.session.async_payment_succeeded", username, "paid"))
    assert resp.status_code == 200
    assert _status_of(username) == ("active", "scale")


def test_webhook_activates_free_trial_checkout(monkeypatch):
    from src.api import stripe_payments
    monkeypatch.setattr(stripe_payments.settings, "stripe_webhook_secret", "whsec_fake")
    username = _make_user()

    _post_event(_checkout_event("evt_trial1", "checkout.session.completed", username, "no_payment_required"))
    assert _status_of(username) == ("active", "scale")
