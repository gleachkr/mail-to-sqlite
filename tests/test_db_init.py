"""
This module tests the database schema validation and migration logic.
"""
import os
import sqlite3
import pytest
from mail_to_sqlite import db

def test_init_raises_error_on_incomplete_schema(tmp_path):
    """
    Tests that init() raises a helpful error if the schema is incomplete.
    """
    db_path = tmp_path / "messages.db"
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    # Create a table with a missing column
    cur.execute("""
    CREATE TABLE "messages" (
        "id" INTEGER NOT NULL PRIMARY KEY,
        "message_id" TEXT NOT NULL UNIQUE
        -- Missing other columns
    );
    """)
    con.commit()
    con.close()

    with pytest.raises(db.SchemaError, match="Database schema is out of date. Table 'messages' is missing columns. Please move the existing database file and run the command again to create a new one."):
        db.init(str(tmp_path))
