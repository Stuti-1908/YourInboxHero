"""Tests for the authentication endpoints."""
from fastapi.testclient import TestClient
from src.app import app
from src.db import SessionLocal
from src.models.user import User
from src.auth import get_password_hash
import uuid

import pytest

@pytest.fixture(autouse=True)
def clear_overrides():
    old_overrides = app.dependency_overrides.copy()
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides = old_overrides

def test_login_success():
    session = SessionLocal()
    try:
        # Create a test user
        test_username = f"user_{uuid.uuid4().hex[:6]}"
        test_password = "securepassword"
        
        db_user = User(
            username=test_username,
            hashed_password=get_password_hash(test_password)
        )
        session.add(db_user)
        session.commit()
    finally:
        session.close()

    client = TestClient(app)
    
    # Try to login
    response = client.post(
        "/token",
        data={"username": test_username, "password": test_password}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

def test_login_failure():
    client = TestClient(app)
    response = client.post(
        "/token",
        data={"username": "wrong", "password": "wrong"}
    )
    assert response.status_code == 401
