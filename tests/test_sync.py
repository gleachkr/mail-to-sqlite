from datetime import datetime
from unittest.mock import MagicMock
import pytest
from mail_to_sqlite import sync

@pytest.fixture
def mock_provider(mocker):
    """Fixture to create a mock email provider."""
    provider = MagicMock()
    # Mock the get_provider function to return our mock provider
    mocker.patch('mail_to_sqlite.sync.get_provider', return_value=provider)
    return provider

@pytest.fixture
def mock_db(mocker):
    """Fixture to mock database functions."""
    mocker.patch('mail_to_sqlite.db.init')
    mocker.patch('mail_to_sqlite.db.create_message')
    mocker.patch('mail_to_sqlite.db.last_indexed', return_value=None)
    mocker.patch('mail_to_sqlite.db.first_indexed', return_value=None)

def test_sync_all_pagination(mock_provider, mock_db):
    """
    Verify that sync_all correctly handles pagination.
    """
    # Arrange
    mock_provider.list_messages.side_effect = [
        {"messages": [{"id": "msg1"}, {"id": "msg2"}], "nextPageToken": "page2"},
        {"messages": [{"id": "msg3"}], "nextPageToken": None},
    ]
    # We need to mock get_message for each message ID
    mock_provider.get_message.side_effect = [
        MagicMock(id="msg1"), MagicMock(id="msg2"), MagicMock(id="msg3")
    ]

    # Act
    sync.all_messages(data_dir="/fake/dir", provider_type="gmail", clobber=None, full_sync=True)

    # Assert
    assert mock_provider.list_messages.call_count == 2
    # First call with no page token
    mock_provider.list_messages.assert_any_call(query=None, page_token=None)
    # Second call with the token from the first response
    mock_provider.list_messages.assert_any_call(query=None, page_token="page2")

def test_incremental_sync_query_building(mock_provider, mock_db, mocker):
    """
    Verify that incremental syncs build the correct query using timestamps.
    """
    # Arrange
    last_indexed_time = datetime(2024, 1, 1, 12, 0, 0)
    first_indexed_time = datetime(2024, 1, 1, 0, 0, 0)
    
    # Mock the database to return specific timestamps
    mocker.patch('mail_to_sqlite.db.last_indexed', return_value=last_indexed_time)
    mocker.patch('mail_to_sqlite.db.first_indexed', return_value=first_indexed_time)
    
    # Set up the provider to return no messages to keep the test simple
    mock_provider.list_messages.return_value = {"messages": [], "nextPageToken": None}
    expected_query = "after:1704109200 before:1704067200" # Timestamps for the above dates
    mock_provider.build_query.return_value = expected_query
    
    # Act: Run a standard sync (not a full sync)
    sync.all_messages(data_dir="/fake/dir", provider_type="gmail", clobber=None, full_sync=False)

    # Assert
    mock_provider.build_query.assert_called_once_with(
        after=last_indexed_time, before=first_indexed_time
    )
    mock_provider.list_messages.assert_called_once_with(
        query=expected_query, page_token=None
    )
