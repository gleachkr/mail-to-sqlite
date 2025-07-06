


def test_sigint_graceful_exit(mocker, tmp_path):
    """
    Verify that the program handles SIGINT (Ctrl+C) gracefully
    by closing the database connection before exiting.
    """
    # 1. ARRANGE
    # Mock the sync function to raise a KeyboardInterrupt
    mocker.patch(
        "mail_to_sqlite.main.sync.all_messages",
        side_effect=KeyboardInterrupt
    )

    # Spy on the database connection's close method
    mock_db_conn = MagicMock()
    mocker.patch("mail_to_sqlite.main.db.init", return_value=mock_db_conn)

    data_dir = str(tmp_path)
    mocker.patch.object(
        sys, "argv", ["mail_to_sqlite", "--data-dir", data_dir]
    )

    # 2. ACT & ASSERT
    # Expect a SystemExit because of the KeyboardInterrupt handling
    with pytest.raises(SystemExit) as e:
        main()

    # Assert that the exit code is 0
    assert e.value.code == 0

    # 3. ASSERT
    # Verify that the database connection was closed
    mock_db_conn.close.assert_called_once()

def test_incremental_sync_uses_timestamps(mocker, tmp_path, mock_message_one, mock_message_two):
    """
    Verify that an incremental sync correctly uses the timestamps from the DB
    to build a query for the provider.
    """
    # 1. ARRANGE: Mock the provider and the db timestamp functions
    mock_provider = MagicMock()
    mock_provider.list_messages.return_value = {"messages": []} # No messages returned
    mocker.patch("mail_to_sqlite.sync.get_provider", return_value=mock_provider)

    # Mock the database functions to simulate a DB with existing messages
    last_indexed_time = datetime(2024, 1, 15, 0, 0, 0)
    first_indexed_time = datetime(2024, 1, 1, 0, 0, 0)
    mocker.patch("mail_to_sqlite.db.last_indexed", return_value=last_indexed_time)
    mocker.patch("mail_to_sqlite.db.first_indexed", return_value=first_indexed_time)
    
    # The query that we expect the provider to build with the above timestamps
    expected_query = ["after:1705294800", "before:1704085200"]
    mock_provider.build_query.return_value = expected_query

    # 2. ACT: Run a standard sync (not a full sync)
    data_dir = str(tmp_path)
    mocker.patch.object(sys, "argv", ["mail_to_sqlite", "--data-dir", data_dir])
    main()

    # 3. ASSERT: Verify that the provider's methods were called as expected
    mock_provider.build_query.assert_called_once_with(
        after=last_indexed_time, before=first_indexed_time
    )
    mock_provider.list_messages.assert_called_once_with(
        query=expected_query, page_token=None
    )

def test_sync_with_clobber_end_to_end(mocker, tmp_path, mock_message_one):
    """
    Test that the --clobber flag correctly updates specific fields
    on a duplicate message.
    """
    # 1. ARRANGE: Initial sync to populate the database
    mock_provider = MagicMock()
    mock_provider.get_message.return_value = mock_message_one
    mocker.patch(
        "mail_to_sqlite.sync.get_provider", return_value=mock_provider
    )
    
    data_dir = str(tmp_path)
    db_path = tmp_path / "messages.db"
    
    # First run (no clobber, just sync the message)
    mocker.patch.object(
        sys,
        "argv",
        [
            "mail_to_sqlite",
            "--data-dir",
            data_dir,
            "--message-id",
            mock_message_one.id,
        ],
    )
    main()

    # 2. ACT: Create a modified message and sync with --clobber
    
    # Modify the mock message object that the provider will return
    mock_message_one.is_read = True
    mock_message_one.labels = ["INBOX", "PROCESSED"]
    mock_message_one.subject = "This Subject Should NOT Be Updated"
    mock_provider.get_message.return_value = mock_message_one

    # Second run, this time with the --clobber flag
    mocker.patch.object(
        sys,
        "argv",
        [
            "mail_to_sqlite",
            "--data-dir",
            data_dir,
            "--message-id",
            mock_message_one.id,
            "--clobber",
            "is_read",
            "labels",
        ],
    )
    main()

    # 3. ASSERT: Check the database to see what was updated
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # Makes accessing columns by name easy
    cursor = conn.cursor()
    cursor.execute("SELECT message_id, subject, is_read, labels FROM messages")
    result = cursor.fetchone()
    conn.close()

    assert result is not None
    assert result["is_read"] == 1  # is_read should be updated to True (1)
    assert json.loads(result["labels"]) == ["INBOX", "PROCESSED"]
    # The original subject should be preserved
    assert result["subject"] == "Test Subject"
from datetime import datetime
from datetime import datetime

import json
import sqlite3
import sys
from unittest.mock import MagicMock
from mail_to_sqlite.main import main
import pytest


def test_sync_all_messages_end_to_end(mocker, tmp_path, mock_message_one):
    """
    Test the main 'sync' command from end-to-end by mocking the provider.
    This verifies argument parsing, database initialization, and the sync loop.
    """
    # 1. Arrange: Create a mock provider that returns a single message
    mock_provider = MagicMock()
    mock_provider.list_messages.return_value = {
        "messages": [{"id": mock_message_one.id}],
        "nextPageToken": None
    }
    mock_provider.get_message.return_value = mock_message_one

    # Mock the function that returns the provider
    mocker.patch(
        "mail_to_sqlite.sync.get_provider", return_value=mock_provider
    )

    # 2. Act: Run the main function with command-line arguments
    data_dir = str(tmp_path)
    db_path = tmp_path / "messages.db"
    
    # We patch sys.argv to simulate command-line execution
    mocker.patch.object(
        sys, "argv", ["mail_to_sqlite", "--data-dir", data_dir]
    )
    main()

    # 3. Assert: Verify the database was created and contains the correct data
    assert db_path.exists()
    
    # Query the database to ensure the message was saved correctly
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT message_id, subject, is_read FROM messages")
    result = cursor.fetchone()
    conn.close()

    assert result is not None
    assert result[0] == mock_message_one.id
    assert result[1] == mock_message_one.subject
    assert result[2] == 0  # is_read should be False (0 in SQLite)


def test_sync_single_message_end_to_end(mocker, tmp_path, mock_message_one):
    """
    Test the 'sync-message' command from end-to-end.
    """
    # 1. Arrange
    mock_provider = MagicMock()
    mock_provider.get_message.return_value = mock_message_one
    mocker.patch(
        "mail_to_sqlite.sync.get_provider", return_value=mock_provider
    )

    # 2. Act
    data_dir = str(tmp_path)
    db_path = tmp_path / "messages.db"
    mocker.patch.object(
        sys,
        "argv",
        [
            "mail_to_sqlite",
            "--data-dir",
            data_dir,
            "--message-id",
            mock_message_one.id,
        ],
    )
    main()

    # 3. Assert
    assert db_path.exists()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT message_id, subject FROM messages")
    result = cursor.fetchone()
    conn.close()

    assert result is not None
    assert result[0] == mock_message_one.id
    assert result[1] == mock_message_one.subject


def test_main_exits_with_error_on_invalid_provider(mocker, capsys, tmp_path):
    """
    Verify that the main function exits and prints an error message
    when an invalid provider is given, without showing a traceback.
    """
    # Arrange: Mock argv with an invalid provider
    data_dir = str(tmp_path)
    mocker.patch.object(
        sys, "argv", ["mail_to_sqlite", "--data-dir", data_dir, "--provider", "bogus"]
    )

    # Act & Assert: The program should exit with a SystemExit exception
    with pytest.raises(SystemExit) as e:
        main()

    # Assert that the exit code is non-zero (argparse uses 2 for bad args)
    assert e.value.code != 0

    # Assert that a helpful error message was printed to stderr
    captured = capsys.readouterr()
    assert "invalid choice: 'bogus'" in captured.err
    assert "usage: mail_to_sqlite" in captured.err
    assert "Traceback" not in captured.err
