import logging
from datetime import datetime

from peewee import *
from playhouse.sqlite_ext import *

database_proxy = Proxy()

class Message(Model):
    """
    Represents an email message.

    Attributes:
        message_id (TextField): The unique identifier of the message.
        thread_id (TextField): The unique identifier of the thread.
        sender (JSONField): The sender of the message.
        recipients (JSONField): The recipients of the message.
        labels (JSONField): The labels of the message.
        subject (TextField): The subject of the message.
        body (TextField): The last messages sent or received without all
            other replies to the thread.
        size (IntegerField): The size of the message.
        timestamp (DateTimeField): The timestamp of the message.
        is_read (BooleanField): Indicates whether the message has been read.
        is_outgoing (BooleanField): Indicates whether the message was sent by
            the user.
        last_indexed (DateTimeField): The timestamp when the message was last
            indexed.

    Meta:
        database (Database): The database connection to use.
        db_table (str): The name of the database table for storing messages.
    """
    message_id = TextField(unique=True)
    thread_id = TextField(null=True)
    sender = JSONField()
    recipients = JSONField()
    labels = JSONField()
    subject = TextField(null=True)
    body = TextField(null=True)
    size = IntegerField()
    timestamp = DateTimeField()
    is_read = BooleanField()
    is_outgoing = BooleanField()
    last_indexed = DateTimeField()

    class Meta:
        database = database_proxy
        table_name = "messages"

class Attachment(Model):
    """
    Represents an email attachment.
    message_id (TextField): The associated Message.message_id
    filename (TextField): The attachment's filename
    content_type (TextField): MIME type
    size (IntegerField): Size in bytes
    content (BlobField): The binary data
    last_indexed (DateTimeField): Capture timestamp
    """
    message_id = ForeignKeyField(
        Message, field='message_id', backref='attachments',
        on_delete='CASCADE', column_name='message_id'
    )
    filename = TextField()
    content_type = TextField()
    size = IntegerField()
    content = BlobField()
    last_indexed = DateTimeField()
    class Meta:
        database = database_proxy
        table_name = "attachments"
        indexes = ((("message_id", "filename"), True),)

def init(data_dir: str, enable_logging=False) -> SqliteDatabase:
    """
    Initialize the database for the given data_dir. The database is stored 
    in <data_dir>/messages.db. Fails if either table exists already.

    Args:
        data_dir (str): The path where to store the data.
        enable_logging (bool, optional): Whether to enable logging. Defaults to False.

    Returns:
        SqliteDatabase: The initialized database object.
    """
    import os
    db_path = f"{data_dir}/messages.db"
    db_exists = os.path.exists(db_path)
    db = SqliteDatabase(db_path, pragmas={'foreign_keys': 1})
    database_proxy.initialize(db)

    if not db_exists:
        db.execute_sql("""
        CREATE TABLE messages (
            id INTEGER NOT NULL PRIMARY KEY,
            message_id TEXT NOT NULL UNIQUE,
            thread_id TEXT,
            sender JSON NOT NULL,
            recipients JSON NOT NULL,
            labels JSON NOT NULL,
            subject TEXT,
            body TEXT,
            size INTEGER NOT NULL,
            timestamp DATETIME NOT NULL,
            is_read INTEGER NOT NULL,
            is_outgoing INTEGER NOT NULL,
            last_indexed DATETIME NOT NULL
        )
        """)
        db.execute_sql("""
        CREATE TABLE attachments (
            id INTEGER NOT NULL PRIMARY KEY,
            message_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            content_type TEXT NOT NULL,
            size INTEGER NOT NULL,
            content BLOB NOT NULL,
            last_indexed DATETIME NOT NULL,
            FOREIGN KEY (message_id) REFERENCES messages(message_id) ON DELETE CASCADE
        )
        """)
        db.execute_sql("""
        CREATE UNIQUE INDEX idx_attachment_message_filename ON attachments(message_id, filename)
        """)
    # we could in principle check here for the schema in the DB being correct.

    if enable_logging:
        logger = logging.getLogger("peewee")
        logger.setLevel(logging.DEBUG)
        logger.addHandler(logging.StreamHandler())

    return db


def create_message(msg: Message, clobber=[]):
    """
    Saves a message to the database.

    Args:
        msg (Message): The message to save.
        clobber (list): Fields to update on conflict
    """
    last_indexed = datetime.now()
    Message.insert(
        message_id=msg.id,
        thread_id=msg.thread_id,
        sender=msg.sender,
        recipients=msg.recipients,
        labels=msg.labels,
        subject=msg.subject,
        body=msg.body,
        size=msg.size,
        timestamp=msg.timestamp,
        is_read=msg.is_read,
        is_outgoing=msg.is_outgoing,
        last_indexed=last_indexed,
    ).on_conflict(
        conflict_target=[Message.message_id],
        # weirdly, "preserve" means almost the opposite of what you'd expect.
        # It preserves the value from the *INSERTED* row, not the original row.
        # So our "clobber" is the same as playhouse "preserve".
        preserve=[] +
        ([Message.thread_id] if "thread_id" in clobber else []) + 
        ([Message.sender] if "sender" in clobber else []) + 
        ([Message.recipients] if "recipients" in clobber else []) + 
        ([Message.subject] if "subject" in clobber else []) +
        ([Message.body] if "body" in clobber else []) +
        ([Message.size] if "size" in clobber else []) +
        ([Message.timestamp] if "timestamp" in clobber else []) +
        ([Message.is_outgoing] if "is_outgoing" in clobber else []) +
        ([Message.is_read] if "is_read" in clobber else []) +
        ([Message.labels] if "labels" in clobber else []) ,
        update={
            Message.last_indexed: last_indexed,
        },
    ).execute()


def last_indexed() -> datetime:
    """
    Returns the timestamp of the last indexed message.

    Returns:
        datetime: The timestamp of the last indexed message.
    """

    msg = Message.select().order_by(Message.timestamp.desc()).first()
    if msg:
        return datetime.fromisoformat(msg.timestamp)
    else:
        return None


def first_indexed() -> datetime:
    """
    Returns the timestamp of the first indexed message.

    Returns:
        datetime: The timestamp of the first indexed message.
    """

    msg = Message.select().order_by(Message.timestamp.asc()).first()
    if msg:
        return datetime.fromisoformat(msg.timestamp)
    else:
        return None

def attachment_exists(message_id: str, filename: str) -> bool:
    """
    Checks if an attachment exists in the database for the given message_id
    and filename.

    Args:
        message_id (str): The ID of the message
        filename (str): The attachment filename

    Returns:
        bool: True if the attachment exists, False otherwise
    """
    return Attachment.select().where(
        (Attachment.message_id == message_id) &
        (Attachment.filename == filename)
    ).exists()

def save_attachment(
    attachment,
    last_indexed=None,
):
    """
    Saves an attachment into the database. If a row with the same
    message_id and filename exists, updates its content and metadata.

    Args:
        an attachment (dict): Dict of attachment  .
        last_indexed (datetime, optional): The time of saving. Defaults to now.
    """
    if last_indexed is None:
        from datetime import datetime
        last_indexed = datetime.now()
    Attachment.insert(
        message_id=attachment["message_id"],
        filename=attachment["filename"],
        content_type=attachment["content_type"],
        content=attachment["content"],
        size=attachment["size"],
        last_indexed=last_indexed
    ).on_conflict(
        conflict_target=[Attachment.message_id, Attachment.filename],
        preserve=[
            Attachment.content_type,
            Attachment.content,
            Attachment.size,
            Attachment.last_indexed
        ]
    ).execute()
