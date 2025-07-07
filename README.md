# Mail to SQLite

This is a loosely-coded just-for-fun script to download emails from a variety 
of providers and store them in a SQLite database for further analysis. It's 
useful if you want to run SQL queries against your email (and who doesn't!) 
It's also useful for hooking up an LLM with email, with a minimum of fuss. Try 
combining it with [lectic](https://github.com/gleachkr/lectic), which has 
built-in SQLite support.

## Installation

1. With nix: `nix profile install github:gleachkr/mail-to-sqlite`. 
   After installation, the command `mail_to_sqlite` will be available.

2. With pip: if you want to do this, just post an issue and I'll make 
   it possible.

## Authentication Setup

### For Gmail

You'll need OAuth credentials from Google for a *Desktop App*:

1. Visit the [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the Gmail API for your project
4. Create OAuth credentials for a Desktop application
5. Download the credentials JSON file, and keep it in your `--data-dir` 
   (see below)

For detailed instructions, follow Google's [Python Quickstart 
Guide](https://developers.google.com/gmail/api/quickstart/python#set_up_your_environment).

### For IMAP Providers

For IMAP servers, you'll need:
- Server address and port
- Your username/email
- Your password or an app-specific password

Put them in a JSON file called imap_credentials.json, and keep that in 
the `--data-dir` that you pass to the program.

## Usage

### Basic Command Structure

```
mail_to_sqlite {sync,sync-message,rebuild-threads} [OPTIONS]
```

### Syncing All Messages

```
mail_to_sqlite sync --data-dir PATH/TO/DATA --provider [gmail|imap]
```

This creates and updates a SQLite database at `PATH/TO/DATA/messages.db`. On 
the first sync it will pull down everything. Subsequent syncs are incremental 
(IMAP only lets you specify a time range with day-level granularity though, so 
you might still pull down some already downloaded emails). After a successful 
sync, the message threads are automatically rebuilt.

### Syncing a Single Message

```
mail_to_sqlite sync-message --data-dir PATH/TO/DATA --message-id MESSAGE_ID
```

### Rebuilding Message Threads

If a sync is interrupted, or if you need to manually rebuild the email
thread relationships, you can use the `rebuild-threads` command:

```
mail_to_sqlite rebuild-threads --data-dir PATH/TO/DATA
```

This command will update the `in_reply_to_id` column for all messages,
linking them to their parent messages where possible.

### Command-line Parameters

```
usage: mail_to_sqlite [-h] {sync,sync-message,rebuild-threads} ...

options:
  -h, --help                Show this help message and exit
  --data-dir DATA_DIR       Directory where data should be stored
  --full-sync               Force a full sync of all messages
  --message-id MESSAGE_ID   The ID of the message to sync
  --clobber [ATTR ...]      Attributes to overwrite on existing messages. 
                            Options: thread_id, sender, recipients, subject, 
                            body, size, timestamp, is_outgoing, is_read, labels
  --provider {gmail,imap}   Email provider to use (default: gmail)
  --download-attachments    Download and store email attachments
```

## Database Schema

The database consists of three tables: `messages`, `message_references`, and 
`attachments`.

### The `messages` table

This is the core table, storing all email metadata.

```sql
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
    "rfc822_message_id" TEXT UNIQUE,
    "in_reply_to" TEXT,
    "in_reply_to_id" TEXT,
    FOREIGN KEY ("in_reply_to_id") REFERENCES "messages"("message_id") ON DELETE SET NULL
);
```

### Finding Replies

This query helps you find all direct replies to a specific email. This is
useful for tracing a conversation from a starting point, especially when a
`thread_id` is not available.

```sql
SELECT
    reply.subject,
    reply.sender->>'$.email' as sender,
    reply.timestamp
FROM
    messages AS original
JOIN
    messages AS reply ON original.message_id = reply.in_reply_to_id
WHERE
    original.message_id = '<message-id-of-the-original-email>';
```

### Reconstructing a Thread

If your email provider (like Gmail) supports it, you can list all messages
that belong to a single conversation using `thread_id`.

```sql
SELECT
    subject,
    sender->>'$.email' as sender,
    timestamp
FROM messages
WHERE thread_id = (
    SELECT thread_id FROM messages WHERE message_id = '<any-message-id-in-the-thread>'
)
ORDER BY timestamp ASC;
```

### Finding Attachments by Type

This query lets you find all attachments of a specific file type, such as
PDFs. This is great for locating documents you've been sent.

```sql
SELECT
    a.filename,
    a.size,
    m.subject,
    m.sender->>'$.email' as sender
FROM attachments a
JOIN messages m ON a.message_id = m.message_id
WHERE a.content_type = 'application/pdf'
ORDER BY a.size DESC;
```

### Attachment Size by Sender

Discover which senders are sending you the most data in attachments.

```sql
SELECT
    m.sender->>'$.email' AS sender_email,
    SUM(a.size) * 1.0 / (1024 * 1024) AS total_mb
FROM attachments a
JOIN messages m ON a.message_id = m.message_id
GROUP BY sender_email
ORDER BY total_mb DESC
LIMIT 20;
```

### The `message_references` table

This table tracks the reply chain of emails, helping to reconstruct discussion 
threads.

```sql
CREATE TABLE "message_references" (
    "message_id" TEXT NOT NULL,
    "refers_to_id" TEXT NOT NULL,
    FOREIGN KEY ("message_id") REFERENCES "messages"("message_id") ON DELETE CASCADE,
    PRIMARY KEY ("message_id", "refers_to_id")
);
```

### The `attachments` table

This table stores information about email attachments.

```sql
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
```


## Example Queries

### Most Frequent Senders

```sql
SELECT sender->>'$.email', COUNT(*) AS count
FROM messages
GROUP BY sender->>'$.email'
ORDER BY count DESC
LIMIT 20;
```

### Unread Emails by Sender

```sql
SELECT sender->>'$.email', COUNT(*) AS count
FROM messages
WHERE is_read = 0
GROUP BY sender->>'$.email'
ORDER BY count DESC;
```

### Email Volume by Time Period

```sql
-- For yearly statistics
SELECT strftime('%Y', timestamp) AS year, COUNT(*) AS count
FROM messages
GROUP BY year
ORDER BY year DESC;
```

### Storage Usage by Sender (MB)

```sql
SELECT sender->>'$.email', sum(size)/1024/1024 AS size_mb
FROM messages
GROUP BY sender->>'$.email'
ORDER BY size_mb DESC
LIMIT 20;
```

### Potential Newsletters

```sql
SELECT sender->>'$.email', COUNT(*) AS count
FROM messages
WHERE body LIKE '%unsubscribe%' 
GROUP BY sender->>'$.email'
ORDER BY count DESC;
```

### Self-Emails

```sql
SELECT count(*)
FROM messages
WHERE json_extract(sender, '$.email') IN (
  SELECT json_extract(value, '$.email')
  FROM json_each(messages.recipients->'$.to')
);
```

## Advanced Usage

### Targeted Sync with Specific Fields

If you want to update only specific attributes of existing messages:

```
mail_to_sqlite sync --data-dir PATH/TO/DATA --clobber labels is_read
```

### Periodic Syncing

For regular updates, consider setting up a cron job:

```
# Update email database every hour
0 * * * * mail_to_sqlite sync --data-dir ~/mail-data
```
## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for 
details. Thanks to @marcboeker for [the original 
gmail-to-sqlite](https://github.com/marcboeker/gmail-to-sqlite).
