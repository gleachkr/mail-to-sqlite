import logging
from datetime import datetime
import sqlite3

from peewee import *
from playhouse.sqlite_ext import *

# Deal with a DeprecationWarning from peewee regarding datetime handling
# See: https://docs.python.org/3/library/sqlite3.html#adapter-and-converter-recipes
def adapt_datetime_iso(val):
    """Adapt datetime.datetime to timezone-naive ISO 8601 format."""
    return val.isoformat()

def convert_datetime_iso(s):
    """Convert ISO 8601 string to datetime.datetime object."""
    return datetime.fromisoformat(s.decode())

sqlite3.register_adapter(datetime, adapt_datetime_iso)
sqlite3.register_converter("datetime", convert_datetime_iso)

class SchemaError(Exception):
    pass

database_proxy = Proxy()

class Message(Model):
    message_id = TextField(unique=True)
    in_reply_to = ForeignKeyField(
        'self',
        field='message_id',
        backref='replies',
        null=True,
        on_delete='SET NULL',
        column_name='in_reply_to_id'
    )
    thread_id = TextField(null=True)
    sender = JSONField()
    recipients = JSONField()
    labels = JSONField()
    subject = TextField(null=True)
    body = TextField(null=True)
    size = IntegerField()
    timestamp = DateTimeField(formats=['%Y-%m-%dT%H:%M:%S'])
    is_read = BooleanField()
    is_outgoing = BooleanField()
    last_indexed = DateTimeField()

    class Meta:
        database = database_proxy
        table_name = "messages"


class MessageReference(Model):
    message = ForeignKeyField(
        Message,
        field='message_id',
        backref='references',
        on_delete='CASCADE',
        column_name='message_id'
    )
    refers_to_id = TextField()

    class Meta:
        database = database_proxy
        table_name = "message_references"
        primary_key = CompositeKey('message', 'refers_to_id')


class Attachment(Model):
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


def get_expected_schema():
    """
    Returns a dictionary defining the expected database schema.
    This is used to validate the schema of an existing database.
    """
    return {
        "messages": [
            "id", "message_id", "thread_id", "sender", "recipients",
            "labels", "subject", "body", "size", "timestamp", "is_read",
            "is_outgoing", "last_indexed", "in_reply_to_id"
        ],
        "message_references": ["message_id", "refers_to_id"],
        "attachments": [
            "id", "message_id", "filename", "content_type", "size",
            "content", "last_indexed"
        ]
    }


def validate_schema(db):
    """
    Validates the database schema against the expected schema.
    Raises SchemaError if the schema is out of date.
    """
    expected_schema = get_expected_schema()
    
    for table, columns in expected_schema.items():
        try:
            actual_columns_rows = db.execute_sql(f"PRAGMA table_info({table});").fetchall()
            actual_columns = [row[1] for row in actual_columns_rows]
            
            if not set(columns).issubset(set(actual_columns)):
                raise SchemaError(
                    "Database schema is out of date. "
                    f"Table '{table}' is missing columns. "
                    "Please move the existing database file and run the command again to create a new one."
                )
        except OperationalError:
            raise SchemaError(
                "Database schema is out of date. "
                f"Table '{table}' is missing. "
                "Please move the existing database file and run the command again to create a new one."
            )

def init(data_dir: str, enable_logging=False) -> SqliteDatabase:
    """
    Initializes the database.
    """
    import os
    db_path = f"{data_dir}/messages.db"
    db_exists = os.path.exists(db_path)
    db = SqliteDatabase(db_path, pragmas={'foreign_keys': 1})
    database_proxy.initialize(db)

    if db_exists:
        validate_schema(db)
    else: # Database does not exist, so create it from scratch
        create_tables(db)

    if enable_logging:
        logger = logging.getLogger("peewee")
        logger.setLevel(logging.DEBUG)
        logger.addHandler(logging.StreamHandler())

    return db


def create_tables(db):
    """
    Creates all necessary tables in the database.
    We use raw SQL for table creation for self-documentation purposes.
    """
    # The 'messages' table is the core of the database.
    db.execute_sql("""
    CREATE TABLE "messages" (
        "id" INTEGER NOT NULL PRIMARY KEY,
        "message_id" TEXT NOT NULL UNIQUE,
        "thread_id" TEXT,
        "sender" JSON NOT NULL,
        "recipients" JSON NOT NULL,
        "labels" JSON NOT NULL,
        "subject" TEXT,
        "body" TEXT,
        "size" INTEGER NOT NULL,
        "timestamp" DATETIME NOT NULL,
        "is_read" INTEGER NOT NULL,
        "is_outgoing" INTEGER NOT NULL,
        "last_indexed" DATETIME NOT NULL,
        "in_reply_to_id" TEXT,
        FOREIGN KEY ("in_reply_to_id") REFERENCES "messages"("message_id") ON DELETE SET NULL
    );
    """)

    # This table maps the 'References' header to messages, tracking thread history.
    db.execute_sql("""
    CREATE TABLE "message_references" (
        "message_id" TEXT NOT NULL,
        "refers_to_id" TEXT NOT NULL,
        FOREIGN KEY ("message_id") REFERENCES "messages"("message_id") ON DELETE CASCADE,
        PRIMARY KEY ("message_id", "refers_to_id")
    );
    """)

    # This table stores information about email attachments.
    db.execute_sql("""
    CREATE TABLE "attachments" (
        "id" INTEGER NOT NULL PRIMARY KEY,
        "message_id" TEXT NOT NULL,
        "filename" TEXT NOT NULL,
        "content_type" TEXT NOT NULL,
        "size" INTEGER NOT NULL,
        "content" BLOB NOT NULL,
        "last_indexed" DATETIME NOT NULL,
        FOREIGN KEY ("message_id") REFERENCES "messages"("message_id") ON DELETE CASCADE
    );
    """)
    db.execute_sql("""
    CREATE UNIQUE INDEX "idx_attachment_message_filename" ON "attachments"("message_id", "filename");
    """)


def create_message(msg, clobber=None):
    if clobber is None:
        clobber = []

    last_indexed = datetime.now()

    message_data = {
        "message_id": msg.id,
        "thread_id": msg.thread_id,
        "sender": msg.sender,
        "recipients": msg.recipients,
        "labels": msg.labels,
        "subject": msg.subject,
        "body": msg.body,
        "size": msg.size,
        "timestamp": msg.timestamp,
        "is_read": msg.is_read,
        "is_outgoing": msg.is_outgoing,
        "last_indexed": last_indexed,
    }

    if hasattr(msg, 'in_reply_to') and msg.in_reply_to:
        message_data['in_reply_to'] = msg.in_reply_to

    update_data = {
        Message.last_indexed: last_indexed,
    }
    for field_name in clobber:
        if hasattr(Message, field_name):
            update_data[getattr(Message, field_name)] = message_data[field_name]

    query = Message.insert(message_data).on_conflict(
        conflict_target=[Message.message_id],
        update=update_data,
    )
    query.execute()

    if hasattr(msg, 'references') and msg.references:
        with database_proxy.atomic():
            for ref_id in msg.references:
                MessageReference.insert(
                    message=msg.id,
                    refers_to_id=ref_id
                ).on_conflict_ignore().execute()


def last_indexed() -> datetime:
    msg = Message.select().order_by(Message.timestamp.desc()).first()
    if msg:
        return datetime.fromisoformat(msg.timestamp)
    else:
        return None


def first_indexed() -> datetime:
    msg = Message.select().order_by(Message.timestamp.asc()).first()
    if msg:
        return datetime.fromisoformat(msg.timestamp)
    else:
        return None

def attachment_exists(message_id: str, filename: str) -> bool:
    return Attachment.select().where(
        (Attachment.message_id == message_id) &
        (Attachment.filename == filename)
    ).exists()

def save_attachment(
    attachment,
    last_indexed=None,
):
    import os
    if last_indexed is None:
        from datetime import datetime
        last_indexed = datetime.now()
    
    base, ext = os.path.splitext(attachment["filename"])
    filename = attachment["filename"]
    counter = 1
    while Attachment.select().where(
        (Attachment.message_id == attachment["message_id"]) &
        (Attachment.filename == filename)
    ).exists():
        filename = f"{base}({counter}){ext}"
        counter += 1

    Attachment.create(
        message_id=attachment["message_id"],
        filename=filename,
        content_type=attachment["content_type"],
        content=attachment["content"],
        size=attachment["size"],
        last_indexed=last_indexed
    )
