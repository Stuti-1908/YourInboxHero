"""Tests for the Growth+ plan gate on PUT /email-template — custom reminder
templates are a paid-tier feature, not available on Starter."""
import pytest
from fastapi.testclient import TestClient
from src.app import app
from src.auth import get_current_user
from src.models.user import User

client = TestClient(app)
app.state.limiter.enabled = False


@pytest.fixture(autouse=True)
def restore_overrides():
    # Popping just get_current_user after a per-test override would leave
    # conftest.py's global override gone entirely for every test that runs
    # after this one in the same process -- save/restore the whole dict.
    old_overrides = app.dependency_overrides.copy()
    yield
    app.dependency_overrides = old_overrides


def _override_user(plan):
    def _fn():
        return User(
            id="test-id", username="testuser", company_name="Test Corp",
            subscription_status="active", subscription_plan=plan,
            chases_limit=750, chases_used=0,
        )
    return _fn


def test_save_template_blocked_on_starter():
    app.dependency_overrides[get_current_user] = _override_user("starter")
    resp = client.put("/email-template", json={
        "template_type": "overdue", "subject": "Pay up", "body": "You owe us money.",
    })
    assert resp.status_code == 403


def test_save_template_allowed_on_growth():
    app.dependency_overrides[get_current_user] = _override_user("growth")
    resp = client.put("/email-template", json={
        "template_type": "overdue", "subject": "Pay up", "body": "You owe us money.",
    })
    assert resp.status_code == 200


def test_save_template_allowed_on_scale():
    app.dependency_overrides[get_current_user] = _override_user("scale")
    resp = client.put("/email-template", json={
        "template_type": "overdue", "subject": "Pay up", "body": "You owe us money.",
    })
    assert resp.status_code == 200


def test_sms_template_does_not_overwrite_email_template():
    """Regression: SMS and email templates used to share the key
    "overdue", so saving one silently replaced the other."""
    app.dependency_overrides[get_current_user] = _override_user("scale")
    r1 = client.put("/email-template", json={
        "template_type": "overdue", "subject": "Email subj", "body": "EMAIL BODY MARKER",
    })
    r2 = client.put("/email-template", json={
        "template_type": "sms_overdue", "subject": "", "body": "SMS BODY MARKER",
    })
    assert r1.status_code == 200 and r2.status_code == 200
    by_type = {t["template_type"]: t for t in client.get("/email-template").json()}
    assert by_type["overdue"]["body"] == "EMAIL BODY MARKER"
    assert by_type["sms_overdue"]["body"] == "SMS BODY MARKER"


def test_unknown_template_type_rejected():
    app.dependency_overrides[get_current_user] = _override_user("scale")
    resp = client.put("/email-template", json={
        "template_type": "whatever", "subject": "x", "body": "y",
    })
    assert resp.status_code == 422


def test_sms_template_length_limit():
    app.dependency_overrides[get_current_user] = _override_user("scale")
    resp = client.put("/email-template", json={
        "template_type": "sms_overdue", "subject": "", "body": "x" * 321,
    })
    assert resp.status_code == 422


def test_email_template_requires_subject():
    app.dependency_overrides[get_current_user] = _override_user("scale")
    resp = client.put("/email-template", json={
        "template_type": "due", "subject": "  ", "body": "body",
    })
    assert resp.status_code == 422


def test_list_templates_still_allowed_on_starter():
    """Viewing (GET) is never gated -- only saving/editing is."""
    app.dependency_overrides[get_current_user] = _override_user("starter")
    resp = client.get("/email-template")
    assert resp.status_code == 200
