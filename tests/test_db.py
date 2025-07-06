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
    in_memory_db = db.SqliteExtDatabase(':memory:', pragmas={'foreign_keys': 1})
    
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

def test_create_message_with_clobber(memory_db):
    """
    Verify that create_message with --clobber updates only specified fields.
    """
    # 1. Arrange: Create an initial message record.
    initial_data = SAMPLE_MESSAGE_DATA.copy()
    db.create_message(type('Message', (), initial_data))

    # 2. Act: Create a new message object with the same ID but different data
    #    and specify which fields to "clobber" (overwrite).
    updated_data = initial_data.copy()
    updated_data['is_read'] = True
    updated_data['labels'] = ['INBOX', 'PROCESSED']
    updated_data['subject'] = 'This Subject Should NOT Be Updated'

    # The 'clobber' parameter should instruct the function to only update
    # 'is_read' and 'labels' from the new object.
    db.create_message(type('Message', (), updated_data), clobber=['is_read', 'labels'])

    # 3. Assert: Retrieve the message and check the fields.
    saved_message = db.Message.get(db.Message.message_id == 'test-message-123')

    # These fields should have been updated.
    assert saved_message.is_read is True
    assert saved_message.labels == ['INBOX', 'PROCESSED']

    # This field should NOT have been updated because it wasn't in clobber.
    assert saved_message.subject == 'Test Subject'

    # The timestamp should also remain unchanged.
    assert saved_message.timestamp == datetime(2023, 10, 27, 10, 0, 0)

def test_create_message_updates_last_indexed_on_duplicate_no_clobber(memory_db):
    """
    Verify that creating a duplicate message without clobbering only
    updates the 'last_indexed' field.
    """
    # 1. Arrange: Create the initial message.
    initial_data = SAMPLE_MESSAGE_DATA.copy()
    initial_message = type('Message', (), initial_data)
    db.create_message(initial_message)
    first_saved_message = db.Message.get(db.Message.message_id == initial_data['id'])
    original_last_indexed = first_saved_message.last_indexed

    # 2. Act: Create a new message object with the same ID but different data.
    # We do *not* provide a clobber list.
    updated_data = initial_data.copy()
    updated_data['subject'] = "This Subject Should NOT Be Updated"
    updated_message = type('Message', (), updated_data)
    db.create_message(updated_message)

    # 3. Assert: Retrieve the message and check its fields.
    final_saved_message = db.Message.get(db.Message.message_id == initial_data['id'])

    # The subject should NOT have changed.
    assert final_saved_message.subject == initial_data['subject']

    # The last_indexed timestamp SHOULD have changed.
    assert final_saved_message.last_indexed > original_last_indexed

def test_save_attachment_fails_without_parent_message(memory_db):
    """
    Verify that saving an attachment fails with an IntegrityError
    if the parent message does not exist.
    """
    # Act & Assert: Attempt to save an attachment for a message that
    # hasn't been created. This should violate the foreign key constraint.
    with pytest.raises(IntegrityError):
        db.save_attachment(SAMPLE_ATTACHMENT_DATA)
