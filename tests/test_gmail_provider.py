from datetime import datetime
from unittest.mock import MagicMock, patch
import pytest
from mail_to_sqlite.providers.gmail import GmailProvider
from googleapiclient.errors import HttpError


@patch('mail_to_sqlite.providers.gmail.build')
def test_get_message_parsing(mock_build):
    # Arrange
    mock_service = MagicMock()
    mock_build.return_value = mock_service

    provider = GmailProvider()
    provider.service = mock_service

    # A sample raw message from the Gmail API
    message_id = "12345"
    raw_message = {
        "id": message_id,
        "threadId": "thread-abc",
        "labelIds": ["INBOX", "UNREAD"],
        "sizeEstimate": 1024,
        "payload": {
            "headers": [
                {"name": "Subject", "value": "Test Subject"},
                {"name": "From", "value": "Sender <sender@example.com>"},
                {"name": "To", "value": "recipient@example.com"},
                {"name": "Date", "value": "Fri, 16 Feb 2024 10:00:00 -0800"}
            ],
            "body": {
                "data": "VGhpcyBpcyBhIHRlc3QgZW1haWwu"  # "This is a test email."
            }
        }
    }

    # Mock the API calls
    mock_service.users().messages().get().execute.return_value = raw_message
    mock_service.users().labels().list().execute.return_value = {
        "labels": [
            {"id": "INBOX", "name": "INBOX"},
            {"id": "UNREAD", "name": "UNREAD"}
        ]
    }

    # Act
    message = provider.get_message(message_id)

    # Assert
    assert message.id == message_id
    assert message.subject == "Test Subject"
    assert message.sender['email'] == "sender@example.com"
    assert message.body.strip() == "This is a test email."
    assert "INBOX" in message.labels
    assert not message.is_read


@patch('mail_to_sqlite.providers.gmail.build')
def test_get_message_with_attachments(mock_build):
    # Arrange
    mock_service = MagicMock()
    mock_build.return_value = mock_service

    provider = GmailProvider()
    provider.service = mock_service

    message_id = "67890"
    raw_message = {
        "id": message_id,
        "threadId": "thread-def",
        "labelIds": ["INBOX"],
        "sizeEstimate": 2048,
        "payload": {
            "headers": [
                {"name": "Subject", "value": "Attachment Test"},
                {"name": "From", "value": "Sender <sender@example.com>"}
            ],
            "parts": [
                {
                    "partId": "0",
                    "mimeType": "text/plain",
                    "body": {"size": 20, "data": "VGhpcyBpcyB0aGUgYm9keS4="}  # "This is the body."
                },
                {
                    "partId": "1",
                    "mimeType": "application/pdf",
                    "filename": "document.pdf",
                    "body": {
                        "attachmentId": "attachment-123",
                        "size": 1000
                    }
                }
            ]
        }
    }

    mock_service.users().messages().get().execute.return_value = raw_message
    mock_service.users().labels().list().execute.return_value = {
        "labels": [
            {"id": "INBOX", "name": "INBOX"}
        ]
    }

    # Act
    message = provider.get_message(message_id)

    # Assert
    assert len(message.attachments) == 1
    attachment = message.attachments[0]
    assert attachment['filename'] == "document.pdf"
    assert attachment['content_type'] == "application/pdf"
    assert attachment['size'] == 1000
    assert attachment['attachment_id'] == "attachment-123"


@patch('mail_to_sqlite.providers.gmail.build')
def test_get_message_html_only(mock_build):
    # Arrange
    mock_service = MagicMock()
    mock_build.return_value = mock_service

    provider = GmailProvider()
    provider.service = mock_service

    message_id = "html-only-123"
    # Base64 encoded: "<h1>Hello</h1><p>This is HTML.</p>"
    html_body_b64 = "PGgxPkhlbGxvPC9oMT48cD5UaGlzIGlzIEhUTUwuPC9wPg=="
    raw_message = {
        "id": message_id,
        "threadId": "thread-html",
        "labelIds": ["INBOX"],
        "sizeEstimate": 1234,
        "payload": {
            "headers": [{"name": "Subject", "value": "HTML Email"}],
            "mimeType": "multipart/alternative",
            "parts": [
                {
                    "partId": "0",
                    "mimeType": "text/html",
                    "body": {"size": 43, "data": html_body_b64}
                }
            ]
        }
    }
    mock_service.users().messages().get().execute.return_value = raw_message
    mock_service.users().labels().list().execute.return_value = {
        "labels": [{"id": "INBOX", "name": "INBOX"}]
    }

    # Act
    message = provider.get_message(message_id)

    # Assert
    assert message.body.strip() == "Hello\nThis is HTML."


@patch('mail_to_sqlite.providers.gmail.build')
def test_get_message_with_missing_headers(mock_build):
    # Arrange
    mock_service = MagicMock()
    mock_build.return_value = mock_service

    provider = GmailProvider()
    provider.service = mock_service

    message_id = "missing-headers-456"
    raw_message = {
        "id": message_id,
        "threadId": "thread-missing",
        "labelIds": ["INBOX"],
        "sizeEstimate": 512,
        "payload": {
            "headers": [
                # Note: No Subject or Date headers
                {"name": "From", "value": "Sender <sender@example.com>"},
                {"name": "To", "value": "recipient@example.com"}
            ],
            "body": {"data": "VGhpcyBib2R5IGhhcyBubyBoZWFkZXJzLg=="}  # "This body has no headers."
        }
    }
    mock_service.users().messages().get().execute.return_value = raw_message
    mock_service.users().labels().list().execute.return_value = {
        "labels": [{"id": "INBOX", "name": "INBOX"}]
    }

    # Act
    message = provider.get_message(message_id)

    # Assert
    assert message.subject is None
    assert message.timestamp is None
    assert message.sender['email'] == "sender@example.com"


@patch('mail_to_sqlite.providers.gmail.build')
def test_unicode_handling(mock_build):
    # Arrange
    mock_service = MagicMock()
    mock_build.return_value = mock_service

    provider = GmailProvider()
    provider.service = mock_service

    message_id = "unicode-789"
    # From: =?utf-8?B?Sm9zw6kgR29uesOhbGV6?= <jose.gonzalez@example.com>
    # Subject: =?utf-8?B?csOpc3Vtw6k=?= (résumé)
    raw_message = {
        "id": message_id,
        "threadId": "thread-unicode",
        "labelIds": ["INBOX"],
        "sizeEstimate": 2048,
        "payload": {
            "headers": [
                {"name": "From", "value": "=?utf-8?B?Sm9zw6kgR29uesOhbGV6?= <jose.gonzalez@example.com>"},
                {"name": "Subject", "value": "=?utf-8?B?csOpc3Vtw6k=?="},
            ],
            "body": {"size": 100, "data": "SGVsbG8gd29ybGQu"}  # "Hello world."
        }
    }
    mock_service.users().messages().get().execute.return_value = raw_message
    mock_service.users().labels().list().execute.return_value = {
        "labels": [{"id": "INBOX", "name": "INBOX"}]
    }

    # Act
    message = provider.get_message(message_id)

    # Assert
    assert message.sender['name'] == "José González"
    assert message.subject == "résumé"
    assert message.body.strip() == "Hello world."


@patch('mail_to_sqlite.providers.gmail.build')
def test_get_message_multipart_no_plain_text(mock_build):
    # Arrange
    mock_service = MagicMock()
    mock_build.return_value = mock_service

    provider = GmailProvider()
    provider.service = mock_service

    message_id = "multipart-no-plain-123"
    html_body_b64 = "PGgxPkhlbGxvPC9oMT48cD5UaGlzIGlzIEhUTUwuPC9wPg=="
    raw_message = {
        "id": message_id,
        "threadId": "thread-html-only",
        "labelIds": ["INBOX"],
        "sizeEstimate": 1234,
        "payload": {
            "headers": [{"name": "Subject", "value": "HTML Only Email"}],
            "mimeType": "multipart/alternative",
            "parts": [
                {
                    "partId": "0",
                    "mimeType": "text/html",
                    "body": {"size": 43, "data": html_body_b64}
                }
            ]
        }
    }
    mock_service.users().messages().get().execute.return_value = raw_message
    mock_service.users().labels().list().execute.return_value = {
        "labels": [{"id": "INBOX", "name": "INBOX"}]
    }

    # Act
    message = provider.get_message(message_id)

    # Assert
    assert message.body.strip() == "Hello\nThis is HTML."


@patch('mail_to_sqlite.providers.gmail.build')
def test_get_message_no_body(mock_build):
    # Arrange
    mock_service = MagicMock()
    mock_build.return_value = mock_service

    provider = GmailProvider()
    provider.service = mock_service

    message_id = "no-body-123"
    raw_message = {
        "id": message_id,
        "threadId": "thread-no-body",
        "labelIds": ["INBOX"],
        "sizeEstimate": 512,
        "payload": {
            "headers": [{"name": "Subject", "value": "No Body Email"}]
            # No body or parts
        }
    }
    mock_service.users().messages().get().execute.return_value = raw_message
    mock_service.users().labels().list().execute.return_value = {
        "labels": [{"id": "INBOX", "name": "INBOX"}]
    }

    # Act
    message = provider.get_message(message_id)

    # Assert
    assert message.body.strip() == ""


@patch('mail_to_sqlite.auth.get_gmail_credentials', side_effect=ValueError("Authentication failed"))
def test_authentication_failure(mock_get_credentials):
    # Arrange
    provider = GmailProvider()

    # Act & Assert
    with pytest.raises(ValueError, match="Authentication failed"):
        provider.authenticate(data_dir="/fake/dir")

    mock_get_credentials.assert_called_once_with("/fake/dir")


@patch('mail_to_sqlite.providers.gmail.build')
def test_get_message_api_error(mock_build):
    # Arrange
    mock_service = MagicMock()
    mock_build.return_value = mock_service

    provider = GmailProvider()
    provider.service = mock_service

    # a mock response object.
    mock_resp = MagicMock()
    mock_resp.status = 404
    mock_resp.reason = "Not Found"

    # Simulate an API error (e.g., 404 Not Found)
    mock_service.users().messages().get.side_effect = HttpError(
        resp=mock_resp,
        content=b'Error content'
    )

    # Act & Assert
    with pytest.raises(ValueError, match="API error fetching message"):
        provider.get_message("non-existent-id")


@patch('mail_to_sqlite.providers.gmail.build')
def test_get_message_with_malformed_date(mock_build):
    # Arrange
    mock_service = MagicMock()
    mock_build.return_value = mock_service

    provider = GmailProvider()
    provider.service = mock_service

    message_id = "malformed-date-789"
    raw_message = {
        "id": message_id,
        "threadId": "thread-malformed-date",
        "labelIds": ["INBOX"],
        "sizeEstimate": 1024,
        "payload": {
            "headers": [
                {"name": "Date", "value": "This is not a valid date"},
                {"name": "Subject", "value": "Malformed Date Test"}
            ]
        }
    }
    mock_service.users().messages().get().execute.return_value = raw_message
    mock_service.users().labels().list().execute.return_value = {
        "labels": [{"id": "INBOX", "name": "INBOX"}]
    }

    # Act
    message = provider.get_message(message_id)

    # Assert
    assert message.timestamp is not None
    assert isinstance(message.timestamp, datetime)
