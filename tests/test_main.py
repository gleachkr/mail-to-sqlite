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
        sys, "argv", ["mail_to_sqlite", "sync", "--data-dir", data_dir]
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
            "sync-message",
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
        sys, "argv", ["mail_to_sqlite", "sync", "--data-dir", data_dir, "--provider", "bogus"]
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
