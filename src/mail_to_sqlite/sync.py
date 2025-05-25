from peewee import IntegrityError

from . import db
from .providers.base import EmailProvider
from .providers.gmail import GmailProvider
from .providers.imap import IMAPProvider


def get_provider(provider_type: str, data_dir: str) -> EmailProvider:
    """
    Get an instance of the appropriate email provider.

    Args:
        provider_type (str): The type of provider ('gmail' or 'imap')
        data_dir (str): Path to data directory

    Returns:
        EmailProvider: An initialized provider instance
    """
    if provider_type == "gmail":
        provider = GmailProvider()
    elif provider_type == "imap":
        provider = IMAPProvider()
    else:
        raise ValueError(f"Unsupported provider type: {provider_type}")

    provider.authenticate(data_dir)
    return provider


def process_attachments(provider, provider_type: str, msg):
    """
    Process attachments for a message.

    Args:
        provider: The email provider instance
        provider_type (str): 'gmail' or 'imap'
        msg (Message): The message containing attachments
    """
    for idx, attachment in enumerate(msg.attachments):


        try:
            if db.attachment_exists(msg.id, attachment["filename"]):
                print(
                    f"  Attachment already exists: {attachment['filename']}"
                )
                continue

            # Gmail: fetch content separately
            if (
                provider_type == "gmail"
                and attachment.get("attachment_id")
            ):
                content = provider.get_attachment_content(
                    msg.id, attachment["attachment_id"]
                )
                if content:
                    attachment["content"] = content
                    db.save_attachment(attachment)
                    print(
                        f"  Downloaded attachment {idx+1}/" +
                        f"{len(msg.attachments)}: {attachment['filename']} "
                        f"({attachment['size']/1024:.1f} KB)"
                    )
            
            # IMAP: already have content
            elif provider_type == "imap" and attachment.get("content"):
                db.save_attachment(attachment)
                print(
                    f"  Saved attachment {idx+1}/" +
                    f"{len(msg.attachments)}: {attachment['filename']} "
                    f"({attachment['size']/1024:.1f} KB)"
                )

        except Exception as e:
            print(
                f"  Error processing attachment "
                f"{attachment.get('filename', 'unknown')}: {e}"
            )


def all_messages(
    provider_type: str, data_dir: str, full_sync=False, clobber=[],
    download_attachments=False
) -> int:
    """
    Fetches messages from the email provider.

    Args:
        provider_type (str): The type of provider ('gmail' or 'imap')
        data_dir (str): Path to data directory
        full_sync (bool): Whether to do a full sync or not.
        clobber (List[str]): Fields to update on conflict
        download_attachments (bool): Whether to download attachments

    Returns:
        int: The number of messages fetched.
    """
    provider = get_provider(provider_type, data_dir)

    # Build query based on DB state if not full sync
    query = None
    if not full_sync:
        last = db.last_indexed()
        first = db.first_indexed()
        if last or first:
            query = provider.build_query(after=last, before=first)

    page_token = None
    run = True
    total_messages = 0

    while run:
        results = provider.list_messages(query=query, page_token=page_token)

        messages = results.get("messages", [])

        total_messages += len(messages)
        for i, m in enumerate(
            messages, start=total_messages - len(messages) + 1
        ):
            try:
                msg = provider.get_message(m["id"])
                db.create_message(msg, clobber)
                print(
                    f"Synced message {msg.id} from {msg.timestamp} (Count: {i})"
                )

                if download_attachments and msg.attachments:
                    process_attachments(provider, provider_type, msg)

            except IntegrityError as e:
                print(
                    f"Could not process message {m['id']}: {str(e)}"
                )
            except Exception as e:
                print(f"Could not get message {m['id']}: {str(e)}")

        if (
            "nextPageToken" in results
            and results["nextPageToken"] is not None
        ):
            page_token = results["nextPageToken"]
        else:
            run = False

    return total_messages


def single_message(
    provider_type: str, data_dir: str, message_id: str, clobber=[],
    download_attachments=False
) -> None:
    """
    Syncs a single message using the provided credentials and message ID.

    Args:
        provider_type (str): The type of provider ('gmail' or 'imap')
        data_dir (str): Path to data directory
        message_id: The ID of the message to fetch.
        clobber (List[str]): Fields to update on conflict
        download_attachments (bool): Whether to download attachments

    Returns:
        None
    """
    provider = get_provider(provider_type, data_dir)

    try:
        msg = provider.get_message(message_id)
        db.create_message(msg, clobber)
        print(f"Synced message {message_id} from {msg.timestamp}")

        if download_attachments and msg.attachments:
            process_attachments(provider, provider_type, msg)

    except IntegrityError as e:
        print(f"Could not process message {message_id}: {str(e)}")
    except Exception as e:
        print(f"Could not get message {message_id}: {str(e)}")

