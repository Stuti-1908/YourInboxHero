import os
import tempfile
db_file = tempfile.mktemp()
os.environ["DATABASE_URL"] = f"sqlite:///{db_file}"
os.environ["SENDGRID_API_KEY"] = "SG.test"

from fastapi.testclient import TestClient
from src.app import app
from src.db import engine
from src.models.base import Base
# Import all models to ensure they are registered with Base.metadata
from src.models import debtor, invoice, reminder  # noqa: F401

# Create tables
Base.metadata.create_all(bind=engine)

client = TestClient(app)

def test_manual_reminder_404():
    # Use a valid UUID format that does not exist in the DB
    fake_id = "00000000-0000-0000-0000-000000000000"
    resp = client.post('/reminder/manual', json={'invoice_id': fake_id})
    print(f"Response status: {resp.status_code}")
    print(f"Response body: {resp.text}")
    assert resp.status_code == 404