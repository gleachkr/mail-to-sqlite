
import pytest
from peewee import IntegrityError
from mail_to_sqlite import db
from datetime import datetime

# A sample message object that we can use to create a message record.
# The data doesn't have to be perfect, just enough to satisfy the model.
SAMPLE_MESSAGE_DATA_1 = {
    'id': 'message-1',
    'thread_id': 'thread-a',
    'sender': {'name': 'Sender 1', 'email': 'sender1@example.com'},
    'recipients': {'to': [{'name': 'Recipient 1', 'email': 'recipient1@example.com'}]},
    'labels': ['INBOX'],
    'subject': 'Test Subject 1',
    'body': 'This is the body of the first message.',
    'size': 1024,
    'timestamp': datetime(2023, 10, 27, 10, 0, 0),
    'is_read': False,
    'is_outgoing': False,
}

SAMPLE_MESSAGE_DATA_2 = {
    'id': 'message-2',
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


@pytest.fixture
def memory_db_with_threading():
    """
    Set up an in-memory SQLite database with the new threading schema.
    """
    in_memory_db = db.SqliteExtDatabase(':memory:', pragmas={'foreign_keys': 1})
    db.database_proxy.initialize(in_memory_db)
    
    # Create the tables including the new MessageReference table
    in_memory_db.create_tables([db.Message, db.Attachment, db.MessageReference])
    
    yield in_memory_db
    
    in_memory_db.close()

def test_message_can_reply_to_another(memory_db_with_threading):
    """
    Verify that we can establish a direct reply-to relationship
    between two messages.
    """
    # 1. Arrange: Create two messages
    message1_data = SAMPLE_MESSAGE_DATA_1.copy()
    message2_data = SAMPLE_MESSAGE_DATA_2.copy()

    # The `create_message` function expects an object with attributes,
    # not a dictionary. We can use a simple custom class for this.
    class MockMessage:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    db.create_message(MockMessage(**message1_data))
    db.create_message(MockMessage(**message2_data))

    # 2. Act: Update the second message to be a reply to the first
    message2 = db.Message.get(db.Message.message_id == 'message-2')
    message2.in_reply_to = 'message-1'
    message2.save()

    # 3. Assert: Check the relationship
    message1 = db.Message.get(db.Message.message_id == 'message-1')
    message2 = db.Message.get(db.Message.message_id == 'message-2')

    assert message2.in_reply_to == message1
    assert message1.replies.count() == 1
    assert message1.replies.get() == message2


def test_message_can_have_multiple_references(memory_db_with_threading):
    """
    Verify that a single message can have multiple references, simulating
    a long email thread.
    """
    # 1. Arrange: Create a message that will have references.
    message_data = SAMPLE_MESSAGE_DATA_1.copy()

    class MockMessage:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    # Add a 'references' attribute to our mock message object.
    message_data['references'] = ['message-ref-A', 'message-ref-B']

    # 2. Act: Create the message in the database.
    # The create_message function should handle saving the references.
    db.create_message(MockMessage(**message_data))

    # 3. Assert: Check that the references were saved correctly.
    message = db.Message.get(db.Message.message_id == 'message-1')

    # Check the count of references.
    assert message.references.count() == 2

    # Check the content of the references.
    saved_ref_ids = [ref.refers_to_id for ref in message.references.order_by(db.MessageReference.refers_to_id)]
    assert saved_ref_ids == ['message-ref-A', 'message-ref-B']


def test_create_message_with_no_references(memory_db_with_threading):
    """
    Verify that creating a message with no 'references' attribute
    succeeds and results in no entries in the MessageReference table.
    """
    # 1. Arrange: Create a message without a 'references' attribute.
    message_data = SAMPLE_MESSAGE_DATA_1.copy()

    class MockMessage:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
            if 'references' not in self.__dict__:
                self.references = []

    # 2. Act: Create the message.
    db.create_message(MockMessage(**message_data))

    # 3. Assert: Check that the message was created and has no references.
    message = db.Message.get(db.Message.message_id == 'message-1')
    assert message is not None
    assert message.references.count() == 0


def test_create_message_with_empty_references_list(memory_db_with_threading):
    """
    Verify that creating a message with an empty 'references' list
    succeeds and results in no entries in the MessageReference table.
    """
    # 1. Arrange: Create a message with an empty 'references' list.
    message_data = SAMPLE_MESSAGE_DATA_1.copy()
    message_data['references'] = []

    class MockMessage:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    # 2. Act: Create the message.
    db.create_message(MockMessage(**message_data))

    # 3. Assert: Check that the message was created and has no references.
    message = db.Message.get(db.Message.message_id == 'message-1')
    assert message is not None
    assert message.references.count() == 0
