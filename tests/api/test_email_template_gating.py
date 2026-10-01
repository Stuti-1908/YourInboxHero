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


def test_list_templates_still_allowed_on_starter():
    """Viewing (GET) is never gated -- only saving/editing is."""
    app.dependency_overrides[get_current_user] = _override_user("starter")
    resp = client.get("/email-template")
    assert resp.status_code == 200
