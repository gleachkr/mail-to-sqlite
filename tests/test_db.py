import pytest
from peewee import IntegrityError
from mail_to_sqlite import db
from datetime import datetime

# A sample message object that we can use to create a message record.
# The data doesn't have to be perfect, just enough to satisfy the model.
SAMPLE_MESSAGE_DATA = {
    'id': 'test-message-123',
    'thread_id': 'thread-abc',
    'sender': {'name': 'Test Sender', 'email': 'sender@example.com'},
    'recipients': {'to': [{'name': 'Test Recipient', 'email': 'recipient@example.com'}]},
    'labels': ['INBOX'],
    'subject': 'Test Subject',
    'body': 'This is a test message body.',
    'size': 1024,
    'timestamp': datetime(2023, 10, 27, 10, 0, 0),
    'is_read': False,
    'is_outgoing': False,
}

# Sample attachment data.
SAMPLE_ATTACHMENT_DATA = {
    'message_id': 'test-message-123',
    'filename': 'test_attachment.txt',
    'content_type': 'text/plain',
    'size': 14,
    'content': b'Test content!!'
}

@pytest.fixture
def memory_db():
    """
    Fixture to set up and tear down a temporary, in-memory SQLite database
    for each test function. It ensures a single, consistent database
    connection is used for the duration of a test.
    """
    # Create a fresh, in-memory SQLite database for the test.
    # Using SqliteExtDatabase is a good practice as it supports more features.
    in_memory_db = db.SqliteExtDatabase(':memory:')
    
    # Configure the global database proxy to use our in-memory database.
    db.database_proxy.initialize(in_memory_db)
    
    # Create the tables. This uses the models' definitions.
    in_memory_db.create_tables([db.Message, db.Attachment])
    
    # Yield control to the test function.
    yield in_memory_db
    
    # Teardown: close the connection after the test has run.
    in_memory_db.close()

def test_save_attachment_updates_on_duplicate(memory_db):
    """
    Verifies that calling save_attachment twice for the same attachment
    updates the existing record rather than raising an error, as per the
    docstring's description.
    """
    # 1. Arrange: Create a parent message and save the attachment once.
    db.create_message(type('Message', (), SAMPLE_MESSAGE_DATA))
    db.save_attachment(SAMPLE_ATTACHMENT_DATA)

    # 2. Act: Create new data for the same attachment and save it again.
    updated_attachment_data = SAMPLE_ATTACHMENT_DATA.copy()
    updated_attachment_data['content'] = b'New updated content!'
    updated_attachment_data['size'] = len(updated_attachment_data['content'])
    
    # This call should now update, not raise an IntegrityError.
    db.save_attachment(updated_attachment_data)

    # 3. Assert: Retrieve the record and check that its content was updated.
    saved_attachment = db.Attachment.get(
        (db.Attachment.message_id == 'test-message-123') &
        (db.Attachment.filename == 'test_attachment.txt')
    )
    
    assert saved_attachment.content == b'New updated content!'
    assert saved_attachment.size == len(b'New updated content!')
