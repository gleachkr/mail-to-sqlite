import pytest
import json
from unittest.mock import patch, mock_open
from mail_to_sqlite import auth
from google.oauth2.credentials import Credentials

@pytest.fixture
def mock_data_dir(tmp_path):
    """Creates a temporary data directory for testing."""
    return tmp_path

def test_get_imap_credentials_malformed_json(mock_data_dir):
    """
    Verify that a helpful error is raised for a malformed
    imap_credentials.json file.
    """
    # Arrange: Create a malformed JSON file
    credential_path = mock_data_dir / auth.IMAP_CREDENTIALS
    credential_path.write_text("this is not valid json")

    # Act & Assert
    with pytest.raises(ValueError) as e:
        auth.get_imap_credentials(str(mock_data_dir))
    
    assert "is not a valid JSON file" in str(e.value)

def test_get_imap_credentials_missing_keys(mock_data_dir):
    """
    Verify that a helpful error is raised if the imap_credentials.json
    file is missing required keys.
    """
    # Arrange: Create a JSON file that is missing the 'password' key
    credentials = {"server": "imap.example.com", "username": "user"}
    credential_path = mock_data_dir / auth.IMAP_CREDENTIALS
    credential_path.write_text(json.dumps(credentials))

    # Act & Assert
    with pytest.raises(ValueError) as e:
        auth.get_imap_credentials(str(mock_data_dir))

    assert "is missing the following required keys" in str(e.value)
    assert "password" in str(e.value)

@patch('mail_to_sqlite.auth.InstalledAppFlow.from_client_secrets_file')
def test_get_gmail_credentials_malformed_json(mock_from_client_secrets_file, mock_data_dir):
    """
    Verify a helpful error is raised for a malformed credentials.json.
    """
    # Arrange: Simulate a malformed JSON file by having from_client_secrets_file
    # raise an exception.
    mock_from_client_secrets_file.side_effect = ValueError("Invalid JSON")
    
    # Create a dummy credentials file to pass the initial existence check
    (mock_data_dir / auth.OAUTH2_CREDENTIALS).touch()

    # Act & Assert
    with pytest.raises(ValueError) as e:
        auth.get_gmail_credentials(str(mock_data_dir))
    
    assert "is not a valid OAuth2 credentials file" in str(e.value)

@patch('mail_to_sqlite.auth.Credentials.from_authorized_user_file')
@patch('mail_to_sqlite.auth.InstalledAppFlow.from_client_secrets_file')
def test_get_gmail_credentials_invalid_token(
    mock_from_client_secrets_file, mock_from_user_file, mock_data_dir
):
    """
    Verify that a corrupt token.json file is handled gracefully.
    """
    # Arrange
    (mock_data_dir / auth.OAUTH2_CREDENTIALS).touch() # Dummy credentials
    (mock_data_dir / "token.json").touch() # Dummy token
    
    mock_from_user_file.side_effect = ValueError("Corrupt token")
    
    # Mock the flow to avoid user interaction
    mock_flow = mock_from_client_secrets_file.return_value
    mock_flow.run_local_server.return_value = Credentials(token="fake_token")

    # Act & Assert
    try:
        auth.get_gmail_credentials(str(mock_data_dir))
    except ValueError as e:
        pytest.fail(f"Unexpected ValueError was raised: {e}")
    
    # Assert that the flow was re-run
    mock_flow.run_local_server.assert_called_once()
