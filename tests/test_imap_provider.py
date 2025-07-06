def test_get_message_handles_no_search_results(mock_imap_conn):
    """
    Verify that get_message returns None when the IMAP search finds no messages.
    """
    # Arrange
    # Configure the mock to return an empty list of message numbers
    mock_imap_conn.search.return_value = ('OK', [b''])
    mock_imap_conn.list.return_value = ('OK', [b'(\\HasNoChildren) "/" "INBOX"'])

    # Act
    from mail_to_sqlite.providers.imap import IMAPProvider
    provider = IMAPProvider()
    provider.authenticate(data_dir='/fake/dir')
    message = provider.get_message(message_id="<non-existent-id@example.com>")

    # Assert
    assert message is None
    # Ensure fetch was not called since no message was found
    mock_imap_conn.fetch.assert_not_called()

def test_parse_message_preserves_malformed_message_id():
    """
    Verify that a malformed Message-ID (e.g., just '<' or '>') is preserved
    and not replaced by a UUID.
    """
    from mail_to_sqlite.providers.imap import IMAPProvider
    provider = IMAPProvider()

    # Case 1: Message-ID is just ">"
    raw_email_malformed_1 = b"""From: sender@example.com
To: receiver@example.com
Subject: Malformed ID 1
Message-ID: >

Body.
"""
    message_1 = provider._parse_imap_message(raw_email_malformed_1, labels={'INBOX': 'INBOX'})
    assert message_1.id == '>'

    # Case 2: Message-ID is just "<"
    raw_email_malformed_2 = b"""From: sender@example.com
To: receiver@example.com
Subject: Malformed ID 2
Message-ID: <

Body.
"""
    message_2 = provider._parse_imap_message(raw_email_malformed_2, labels={'INBOX': 'INBOX'})
    assert message_2.id == '<'

    # Case 3: Message-ID has only one bracket
    raw_email_malformed_3 = b"""From: sender@example.com
To: receiver@example.com
Subject: Malformed ID 3
Message-ID: <unclosed.id@example.com

Body.
"""
    message_3 = provider._parse_imap_message(raw_email_malformed_3, labels={'INBOX': 'INBOX'})
    assert message_3.id == '<unclosed.id@example.com'
import pytest
from unittest.mock import MagicMock
import re

# A minimal, valid raw email message in bytes.
# We use a simple Message-ID for easy testing.
RAW_EMAIL_BYTES = b"""From: sender@example.com
To: receiver@example.com
Subject: Test Email
Message-ID: <test-id-123@example.com>

This is the body of the test email.
"""

# We need to mock the auth module to prevent it from trying to read files.
@pytest.fixture(autouse=True)
def mock_auth(mocker):
    """Auto-mock the auth module to avoid filesystem access."""
    mocker.patch('mail_to_sqlite.auth.get_imap_credentials', return_value={
        'server': 'mock.imap.com',
        'username': 'user',
        'password': 'password',
        'insecure': False
    })

@pytest.fixture
def mock_imap_conn(mocker):
    """Provides a MagicMock for the imaplib.IMAP4_SSL connection."""
    mock_conn = MagicMock()
    # Patch the imaplib.IMAP4_SSL class to return our mock connection instance.
    mocker.patch('imaplib.IMAP4_SSL', return_value=mock_conn)
    return mock_conn

def test_get_message_is_read_if_seen_flag_is_present(mock_imap_conn):
    """
    Verify msg.is_read is True when \\Seen flag is in the IMAP response.
    """
    # 1. Arrange: Configure the mock connection for this specific test case.
    
    # The 'fetch' command should return a response containing the \\Seen flag.
    # The format mimics the complex tuple structure of imaplib.
    mock_fetch_response = [
        # The first part of the tuple contains metadata like flags.
        # The {198} is a placeholder for the message size.
        (b'1 (FLAGS (\\Seen \\Recent) RFC822 {198})', RAW_EMAIL_BYTES)
    ]
    mock_imap_conn.fetch.return_value = ('OK', mock_fetch_response)
    
    # The 'search' command should return a single message number.
    mock_imap_conn.search.return_value = ('OK', [b'1'])
    # The 'list' command is used to get folders
    mock_imap_conn.list.return_value = ('OK', [b'(\\HasNoChildren) "/" "INBOX"'])

    # 2. Act: Instantiate the provider and call the method.
    from mail_to_sqlite.providers.imap import IMAPProvider
    provider = IMAPProvider()
    provider.authenticate(data_dir='/fake/dir') # Auth is mocked, dir doesn't matter
    
    # This call will now use our mocked connection and its pre-configured responses.
    message = provider.get_message(message_id="<test-id-123@example.com>")

    # 3. Assert: Check that the logic correctly set is_read.
    assert message.is_read is True
    
    # Also good to check that the correct fetch command was made.
    mock_imap_conn.fetch.assert_called_with(b'1', '(FLAGS RFC822)')


def test_get_message_is_not_read_if_seen_flag_is_absent(mock_imap_conn):
    """
    Verify msg.is_read is False when \\Seen flag is not in the IMAP response.
    """
    # 1. Arrange: Configure the mock, but this time without the \\Seen flag.
    mock_fetch_response = [
        (b'1 (FLAGS (\\Recent) RFC822 {198})', RAW_EMAIL_BYTES)
    ]
    mock_imap_conn.fetch.return_value = ('OK', mock_fetch_response)
    mock_imap_conn.search.return_value = ('OK', [b'1'])
    mock_imap_conn.list.return_value = ('OK', [b'(\\HasNoChildren) "/" "INBOX"'])

    # 2. Act
    from mail_to_sqlite.providers.imap import IMAPProvider
    provider = IMAPProvider()
    provider.authenticate(data_dir='/fake/dir')
    message = provider.get_message(message_id="<test-id-123@example.com>")

    # 3. Assert
    assert message.is_read is False
    mock_imap_conn.fetch.assert_called_with(b'1', '(FLAGS RFC822)')


# A raw email message that is explicitly missing the Message-ID header.
RAW_EMAIL_NO_MSG_ID = b"""From: sender@example.com
To: receiver@example.com
Subject: Another Test Email

This email has no message ID.
"""

def test_parse_message_uses_existing_message_id():
    """
    Verify that _parse_imap_message uses the Message-ID from the header if present.
    """
    from mail_to_sqlite.providers.imap import IMAPProvider
    import email

    # We can test the private parsing method directly by passing in the raw bytes.
    provider = IMAPProvider()
    
    message = provider._parse_imap_message(RAW_EMAIL_BYTES, labels={'INBOX': 'INBOX'})
    
    # The ID should be the one from the header, without the angle brackets.
    # The provider's parsing logic should strip them.
    assert message.id == 'test-id-123@example.com'


def test_parse_message_generates_uuid_if_message_id_is_missing(mocker):
    """
    Verify _parse_imap_message generates a UUID if the Message-ID header is missing.
    """
    from mail_to_sqlite.providers.imap import IMAPProvider
    import email

    # Mock uuid.uuid4 to return a predictable value
    mock_uuid = mocker.patch('uuid.uuid4')
    mock_uuid.return_value = 'a-fake-but-valid-uuid'
    
    provider = IMAPProvider()
    
    message = provider._parse_imap_message(RAW_EMAIL_NO_MSG_ID, labels={'INBOX': 'INBOX'})
    
    # Assert that our mocked UUID was used as the message ID.
    assert message.id == 'a-fake-but-valid-uuid'
    mock_uuid.assert_called_once()


UNICODE_EMAIL = b"""From: =?utf-8?B?Sm9zw6kgR29uesOhbGV6?= <jose.gonzalez@example.com>
To: receiver@example.com
Subject: =?utf-8?B?csOpc3Vtw6k=?=
Message-ID: <unicode-test-456@example.com>

This is the body.
"""

def test_unicode_header_decoding():
    """
    Verify that RFC 2047 encoded headers are correctly decoded.
    """
    from mail_to_sqlite.providers.imap import IMAPProvider
    provider = IMAPProvider()
    
    message = provider._parse_imap_message(UNICODE_EMAIL, labels={'INBOX': 'INBOX'})
    
    assert message.sender['name'] == 'José González'
    assert message.subject == 'résumé'
