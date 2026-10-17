import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row


load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)


def get_connection():
    """Return a connection to use with a transaction context manager."""
    password = os.environ.get("PGPASSWORD")
    if not password:
        raise RuntimeError("Set PGPASSWORD in your environment or project .env file")
    return psycopg.connect(
        host=os.environ.get("PGHOST", "127.0.0.1"),
        port=os.environ.get("PGPORT", "5432"),
        dbname=os.environ.get("PGDATABASE", "task_manager"),
        user=os.environ.get("PGUSER", "k8_app"),
        password=password,
        connect_timeout=5,
        row_factory=dict_row,
    )
