import argparse
import os
import sys

from . import auth
from . import db
from . import sync


def prepare_data_dir(data_dir: str) -> None:
    """
    Get the project name from command line arguments and create a directory for it if it doesn't exist.

    Raises:
        ValueError: If project name is not provided.

    Returns:
        None
    """

    if not os.path.exists(data_dir):
        os.makedirs(data_dir)


def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Sync all messages
    parser_sync = subparsers.add_parser("sync", help="Sync all messages")
    parser_sync.add_argument(
        "--data-dir", help="The path where the data should be stored", required=True
    )
    parser_sync.add_argument(
        "--provider",
        help="Email provider to use (gmail or imap)",
        default="gmail",
        choices=["gmail", "imap"],
    )
    parser_sync.add_argument(
        "--full-sync",
        help="Force a full sync of all messages",
        action="store_true",
    )
    parser_sync.add_argument(
        "--clobber",
        help=(
            "attributes to clobber. Options: "
            "thread_id, sender, recipients, subject, body, size, timestamp, "
            "is_outgoing, is_read, labels"
        ),
        nargs="*",
    )
    parser_sync.add_argument(
        "--download-attachments",
        help="Download and store email attachments",
        action="store_true",
    )

    # Sync a single message
    parser_sync_message = subparsers.add_parser(
        "sync-message", help="Sync a single message"
    )
    parser_sync_message.add_argument(
        "--data-dir", help="The path where the data should be stored", required=True
    )
    parser_sync_message.add_argument(
        "--provider",
        help="Email provider to use (gmail or imap)",
        default="gmail",
        choices=["gmail", "imap"],
    )
    parser_sync_message.add_argument(
        "--message-id",
        help="The ID of a single message to sync",
        required=True,
    )
    parser_sync_message.add_argument(
        "--clobber",
        help=(
            "attributes to clobber. Options: "
            "thread_id, sender, recipients, subject, body, size, timestamp, "
            "is_outgoing, is_read, labels"
        ),
        nargs="*",
    )
    parser_sync_message.add_argument(
        "--download-attachments",
        help="Download and store email attachments",
        action="store_true",
    )

    # Rebuild threads
    parser_rebuild_threads = subparsers.add_parser(
        "rebuild-threads", help="Rebuild message threads"
    )
    parser_rebuild_threads.add_argument(
        "--data-dir", help="The path where the data should be stored", required=True
    )

    args = parser.parse_args()

    prepare_data_dir(args.data_dir)
    db_conn = db.init(args.data_dir)

    try:
        if args.command == "sync":
            sync.all_messages(
                args.provider,
                args.data_dir,
                full_sync=args.full_sync,
                clobber=args.clobber or [],
                download_attachments=args.download_attachments,
            )
            db.rebuild_threads()
        elif args.command == "sync-message":
            sync.single_message(
                args.provider,
                args.data_dir,
                args.message_id,
                clobber=args.clobber or [],
                download_attachments=args.download_attachments,
            )
        elif args.command == "rebuild-threads":
            db.rebuild_threads()
    except KeyboardInterrupt:
        print("\nExiting gracefully...")
        sys.exit(0)
    finally:
        db_conn.close()
