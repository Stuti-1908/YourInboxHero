"""Root conftest — sets up a single SQLite test database for all tests.

This file is loaded by pytest before any test module, ensuring the
DATABASE_URL and SENDGRID_API_KEY env vars are set consistently, and
tables are created exactly once.
"""
import os
import tempfile

# Must be set BEFORE any src import so src/db.py reads the right URL
_db_file = tempfile.mktemp(suffix=".db")
os.environ["DATABASE_URL"] = f"sqlite:///{_db_file}"
os.environ["SENDGRID_API_KEY"] = "SG.test"

# Now import and create tables (this import triggers src/db.py to create the engine)
from src.db import engine  # noqa: E402
from src.models.base import Base  # noqa: E402
from src.models import debtor, invoice, reminder  # noqa: F401,E402

Base.metadata.create_all(bind=engine)
