import pytest
from datetime import datetime

# Using a class allows for dot-notation access (e.g., msg.id),
# which is cleaner than dictionary access (e.g., msg['id']).
class MockParsedMessage:
    def __init__(self, **kwargs):
        self.id = "test-id-123"
        self.thread_id = "thread-abc"
        self.sender = {'name': 'Test Sender', 'email': 'sender@example.com'}
        self.recipients = {
            'to': [{'name': 'Test Recipient', 'email': 'recipient@example.com'}]
        }
        self.labels = ["INBOX", "UNREAD"]
        self.subject = "Test Subject"
        self.body = "This is the body of the test email."
        self.size = 1024
        self.timestamp = datetime(2023, 10, 27, 10, 0, 0)
        self.is_read = False
        self.is_outgoing = False
        self.attachments = []
        self.__dict__.update(kwargs)

@pytest.fixture
def mock_message_one():
    """A default, reusable mock message object for testing."""
    return MockParsedMessage()

@pytest.fixture
def mock_message_two():
    """A second, different mock message for testing multiple messages."""
    return MockParsedMessage(
        id="test-id-456",
        thread_id="thread-def",
        subject="Another Subject",
        timestamp=datetime(2023, 10, 28, 12, 0, 0)
    )
