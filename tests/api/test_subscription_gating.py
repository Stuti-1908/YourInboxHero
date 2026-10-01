"""Tests for require_active_subscription — write actions must be blocked for
a lapsed (past_due/cancelled/inactive) subscription, while reads stay open."""
import uuid
import pytest
from fastapi.testclient import TestClient
from src.app import app
from src.auth import get_current_user
from src.models.user import User

client = TestClient(app)
app.state.limiter.enabled = False


@pytest.fixture(autouse=True)
def clear_overrides():
    old_overrides = app.dependency_overrides.copy()
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides = old_overrides


def _override_user(subscription_status):
    def _fn():
        return User(
            id="test-id",
            username="testuser",
            company_name="Test Corp",
            subscription_status=subscription_status,
            subscription_plan="growth",
            chases_limit=300,
        )
    return _fn


def test_write_action_blocked_for_inactive_subscription():
    app.dependency_overrides[get_current_user] = _override_user("inactive")

    resp = client.post("/debtor", json={
        "name": "Some Client", "email": f"{uuid.uuid4().hex[:8]}@example.com", "debtor_type": "business",
    })

    assert resp.status_code == 402


def test_write_action_blocked_for_past_due_subscription():
    app.dependency_overrides[get_current_user] = _override_user("past_due")

    resp = client.post("/debtor", json={
        "name": "Some Client", "email": f"{uuid.uuid4().hex[:8]}@example.com", "debtor_type": "business",
    })

    assert resp.status_code == 402


def test_write_action_blocked_for_cancelled_subscription():
    app.dependency_overrides[get_current_user] = _override_user("cancelled")

    resp = client.post("/debtor", json={
        "name": "Some Client", "email": f"{uuid.uuid4().hex[:8]}@example.com", "debtor_type": "business",
    })

    assert resp.status_code == 402


def test_write_action_allowed_for_active_subscription():
    app.dependency_overrides[get_current_user] = _override_user("active")

    resp = client.post("/debtor", json={
        "name": "Some Client", "email": f"{uuid.uuid4().hex[:8]}@example.com", "debtor_type": "business",
    })

    assert resp.status_code == 200


def test_read_action_allowed_despite_lapsed_subscription():
    """A lapsed customer must still be able to view their own existing data —
    only mutating actions are blocked, per product decision."""
    app.dependency_overrides[get_current_user] = _override_user("past_due")

    resp = client.get("/debtor")

    assert resp.status_code == 200
