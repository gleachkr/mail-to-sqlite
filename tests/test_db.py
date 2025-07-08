import pytest
from peewee import IntegrityError
from mail_to_sqlite import db
from datetime import datetime


# A sample message object that we can use to create a message record.
# The data doesn't have to be perfect, just enough to satisfy the model.
SAMPLE_MESSAGE_DATA = {
    'id': 'test-message-123',
    'rfc822_message_id': 'rfc822-test-message-123',
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

SAMPLE_MESSAGE_DATA_2 = {
    'id': 'message-2',
    'rfc822_message_id': 'rfc822-message-2',
    'thread_id': 'thread-a',
    'sender': {'name': 'Sender 2', 'email': 'sender2@example.com'},
    'recipients': {'to': [{'name': 'Recipient 2', 'email': 'recipient2@example.com'}]},
    'labels': ['INBOX'],
    'subject': 'Test Subject 2',
    'body': 'This is the body of the second message.',
    'size': 2048,
    'timestamp': datetime(2023, 10, 27, 11, 0, 0),
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
    in_memory_db.create_tables([db.Message, db.Attachment, db.MessageReference])

    # Yield control to the test function.
    yield in_memory_db

    # Teardown: close the connection after the test has run.
    in_memory_db.close()


def test_save_attachment_updates_on_duplicate(memory_db):
    """
    Verifies that calling save_attachment twice for the same attachment
    with different content results in a new, de-duplicated attachment.
    """
    # 1. Arrange: Create a parent message and save the attachment once.
    db.create_message(type('Message', (), SAMPLE_MESSAGE_DATA))
    db.save_attachment(SAMPLE_ATTACHMENT_DATA)

    # 2. Act: Create new data for the same attachment and save it again.
    updated_attachment_data = SAMPLE_ATTACHMENT_DATA.copy()
    updated_attachment_data['content'] = b'New updated content!'
    updated_attachment_data['size'] = len(updated_attachment_data['content'])

    db.save_attachment(updated_attachment_data)

    # 3. Assert: Retrieve the records and check that there are two.
    saved_attachments = db.Attachment.select().where(
        db.Attachment.message_id == 'test-message-123'
    ).order_by(db.Attachment.id)

    assert saved_attachments.count() == 2
    assert saved_attachments[0].content == SAMPLE_ATTACHMENT_DATA['content']
    assert saved_attachments[1].content == updated_attachment_data['content']
    assert saved_attachments[1].filename == 'test_attachment(1).txt'


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


def test_create_message_saves_thread_info(memory_db):
    """
    Verify `create_message` saves threading info to the correct places.
    - The raw `in_reply_to` header goes into the `in_reply_to` text column.
    - All references (`in_reply_to` + `references` headers) go into the
      `message_references` table.
    - The `in_reply_to_id` foreign key column remains NULL.
    """
    # 1. Arrange: A message that is a reply to a parent and references a grandparent.
    message_data = SAMPLE_MESSAGE_DATA.copy()
    message_data['in_reply_to'] = 'parent-id'
    message_data['references'] = ['grandparent-id', 'parent-id']
    message_obj = type('Message', (), message_data)

    # 2. Act: Create the message.
    db.create_message(message_obj)

    # 3. Assert:
    # Check the main messages table for correct state.
    saved_message = db.Message.get(db.Message.message_id == 'test-message-123')
    assert saved_message.in_reply_to == 'parent-id'  # The new text field
    assert saved_message.in_reply_to_id is None      # The foreign key is NULL

    # Check the message_references table for a complete log.
    references = db.MessageReference.select().where(
        db.MessageReference.message == 'test-message-123'
    ).order_by(db.MessageReference.refers_to_id)

    assert references.count() == 2
    assert references[0].refers_to_id == 'grandparent-id'
    assert references[1].refers_to_id == 'parent-id'


def test_rebuild_threads_links_correct_parent(memory_db):
    """
    Verify `rebuild_threads` correctly links a message to its direct parent
    using the `in_reply_to` text field, not just any reference.
    """
    # 1. Arrange: Create a grandparent, parent, and child message.
    grandparent_data = {**SAMPLE_MESSAGE_DATA, 'id': 'grandparent', 'rfc822_message_id': 'grandparent-id'}
    parent_data = {**SAMPLE_MESSAGE_DATA, 'id': 'parent', 'rfc822_message_id': 'parent-id', 'in_reply_to': 'grandparent-id'}
    child_data = {
        **SAMPLE_MESSAGE_DATA,
        'id': 'child',
        'rfc822_message_id': 'child-id',
        'in_reply_to': 'parent-id',
        'references': ['grandparent-id', 'parent-id']
    }

    db.create_message(type('Message', (), grandparent_data))
    db.create_message(type('Message', (), parent_data))
    db.create_message(type('Message', (), child_data))

    # 2. Act: Rebuild the threads.
    db.rebuild_threads()

    # 3. Assert: Check that the foreign keys are now correctly set.
    grandparent = db.Message.get(db.Message.message_id == 'grandparent')
    parent = db.Message.get(db.Message.message_id == 'parent')
    child = db.Message.get(db.Message.message_id == 'child')

    assert child.in_reply_to_id.message_id == 'parent'
    assert parent.in_reply_to_id.message_id == 'grandparent'
    assert grandparent.in_reply_to_id is None


def test_save_attachment_fails_without_parent_message(memory_db):
    """
    Verify that saving an attachment fails with an IntegrityError
    if the parent message does not exist.
    """
    # Act & Assert: Attempt to save an attachment for a message that
    # hasn't been created. This should violate the foreign key constraint.
    with pytest.raises(IntegrityError):
        db.save_attachment(SAMPLE_ATTACHMENT_DATA)


def test_message_can_have_multiple_references(memory_db):
    """
    Verify that a single message can have multiple references, simulating
    a long email thread.
    """
    # 1. Arrange: Create a message that will have references.
    message_data = SAMPLE_MESSAGE_DATA.copy()

    class MockMessage:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    # Add a 'references' attribute to our mock message object.
    message_data['references'] = ['message-ref-A', 'message-ref-B']

    # 2. Act: Create the message in the database.
    # The create_message function should handle saving the references.
    db.create_message(MockMessage(**message_data))

    # 3. Assert: Check that the references were saved correctly.
    message = db.Message.get(db.Message.message_id == 'test-message-123')

    # Check the count of references.
    assert message.references.count() == 2

    # Check the content of the references.
    saved_ref_ids = [ref.refers_to_id for ref in message.references.order_by(db.MessageReference.refers_to_id)]
    assert saved_ref_ids == ['message-ref-A', 'message-ref-B']


def test_create_message_with_no_references(memory_db):
    """
    Verify that creating a message with no 'references' attribute
    succeeds and results in no entries in the MessageReference table.
    """
    # 1. Arrange: Create a message without a 'references' attribute.
    message_data = SAMPLE_MESSAGE_DATA.copy()

    class MockMessage:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
            if 'references' not in self.__dict__:
                self.references = []

    # 2. Act: Create the message.
    db.create_message(MockMessage(**message_data))

    # 3. Assert: Check that the message was created and has no references.
    message = db.Message.get(db.Message.message_id == 'test-message-123')
    assert message is not None
    assert message.references.count() == 0


def test_rebuild_threads_with_whitespace_mismatch(memory_db):
    """
    Verify that `rebuild_threads` correctly links messages even if there is
    a whitespace mismatch in the `rfc822_message_id` and `in_reply_to`
    fields.
    """
    # 1. Arrange: Create two messages, a parent and a child.
    parent_data = SAMPLE_MESSAGE_DATA.copy()
    parent_data['rfc822_message_id'] = 'parent.message.id'

    child_data = SAMPLE_MESSAGE_DATA_2.copy()
    child_data['in_reply_to'] = ' <parent.message.id> '

    class MockMessage:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
            if 'references' not in self.__dict__:
                self.references = []
            if 'in_reply_to' not in self.__dict__:
                self.in_reply_to = None

    db.create_message(MockMessage(**parent_data))
    db.create_message(MockMessage(**child_data))

    # 2. Act: Rebuild the threads.
    db.rebuild_threads()

    # 3. Assert: Check that the child message IS linked to the parent.
    child = db.Message.get(db.Message.message_id == 'message-2')
    assert child.in_reply_to_id is not None
    assert child.in_reply_to_id.message_id == 'test-message-123'


def test_create_message_with_empty_references_list(memory_db):
    """
    Verify that creating a message with an empty 'references' list
    succeeds and results in no entries in the MessageReference table.
    """
    # 1. Arrange: Create a message with an empty 'references' list.
    message_data = SAMPLE_MESSAGE_DATA.copy()
    message_data['references'] = []

    class MockMessage:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    # 2. Act: Create the message.
    db.create_message(MockMessage(**message_data))

    # 3. Assert: Check that the message was created and has no references.
    message = db.Message.get(db.Message.message_id == 'test-message-123')
    assert message is not None
    assert message.references.count() == 0
