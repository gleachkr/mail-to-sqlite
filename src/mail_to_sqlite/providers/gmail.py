import base64
from typing import Dict, List, Optional
from datetime import datetime

from googleapiclient.discovery import build

from email.header import decode_header
from email.utils import parseaddr, parsedate_to_datetime
from .base import EmailProvider
from ..message import ParsedMessage
from .. import auth

class GmailProvider(EmailProvider):
    """Gmail implementation of the EmailProvider interface."""
    
    def __init__(self):
        self.service = None
        self.credentials = None
    
    def authenticate(self, data_dir: str):
        """Authenticate with Gmail."""
        self.credentials = auth.get_gmail_credentials(data_dir)
        self.service = build("gmail", "v1", credentials=self.credentials)
    
    def get_labels(self) -> Dict[str, str]:
        """Get all labels from Gmail."""
        labels = {}
        for label in self.service.users().labels().list(userId="me").execute()["labels"]:
            labels[label["id"]] = label["name"]
        return labels
    
    def get_message(self, message_id: str) -> ParsedMessage:
        """Get a single message by ID."""
        labels = self.get_labels()
        raw_msg = self.service.users().messages().get(
            userId="me", id=message_id).execute()
        return self._parse_gmail_message(raw_msg, labels)

    def _parse_gmail_message(self, raw: dict, labels: dict) -> ParsedMessage:
        """
        Parse a Gmail raw API message dict to a Message class instance.
        """
        return self._parse_gmail_message_data(raw, labels)

    def _decode_header(self, header_value):
        decoded_parts = decode_header(header_value)
        parts = []
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                parts.append(part.decode(encoding or 'utf-8'))
            else:
                parts.append(part)
        return ''.join(parts)

    def _parse_gmail_message_data(self, msg: dict, labels: dict) -> ParsedMessage:
        m = ParsedMessage()
        m.id = msg["id"]
        m.thread_id = msg["threadId"]
        m.size = msg["sizeEstimate"]

        for header in msg["payload"]["headers"]:
            name = header["name"].lower()
            value = header["value"]
            if name == "from":
                name, email = parseaddr(value)
                decoded_name = self._decode_header(name)
                m.sender = {"name": decoded_name, "email": email}
            elif name == "to":
                m.recipients["to"] = m.parse_addresses(value)
            elif name == "cc":
                m.recipients["cc"] = m.parse_addresses(value)
            elif name == "bcc":
                m.recipients["bcc"] = m.parse_addresses(value)
            elif name == "subject":
                m.subject = self._decode_header(value)
            elif name == "date":
                m.timestamp = parsedate_to_datetime(value)

        # Labels
        if "labelIds" in msg:
            for l in msg["labelIds"]:
                m.labels.append(labels[l])
            m.is_read = "UNREAD" not in msg["labelIds"]
            m.is_outgoing = "SENT" in msg["labelIds"]

        # Extract body
        m.body = m.decode_body(msg["payload"])

        # Extract attachments
        m.attachments = []
        if "payload" in msg:
            self._extract_gmail_attachments(msg["payload"], m)
        return m

    def _extract_gmail_attachments(self, part, m: ParsedMessage):
        """
        Recursively extract attachment metadata from Gmail message parts.
        """
        if "parts" in part:
            for subpart in part["parts"]:
                self._extract_gmail_attachments(subpart, m)
        if "filename" in part and part.get("filename"):
            attachment = {
                "message_id": m.id,
                "filename": part.get("filename", ""),
                "content_type": part.get("mimeType", "application/octet-stream"),
                "size": 0,
                "attachment_id": None,
                "content": None
            }
            if "body" in part and "attachmentId" in part["body"]:
                attachment["attachment_id"] = part["body"]["attachmentId"]
                attachment["size"] = part["body"].get("size", 0)
            m.attachments.append(attachment)

    
    def list_messages(self, 
                     query: Optional[List[str]] = None, 
                     page_token: Optional[str] = None,
                     max_results: int = 500) -> Dict:
        """List messages, optionally filtered by query."""
        if query is None:
            query = []
            
        results = (
            self.service.users()
            .messages()
            .list(
                userId="me",
                maxResults=max_results,
                pageToken=page_token,
                q=" | ".join(query),
            )
            .execute()
        )
        return results
    
    def build_query(self, after: Optional[datetime] = None, 
                   before: Optional[datetime] = None) -> List[str]:
        """Build a Gmail query based on datetime filters."""
        query = []
        if after:
            query.append(f"after:{int(after.timestamp())}")
        if before:
            query.append(f"before:{int(before.timestamp())}")
        return query

    
    def get_attachment_content(self, message_id: str, attachment_id: str) -> bytes:
        """
        Fetch the raw byte content of an attachment from Gmail.

        Args:
            message_id (str): The Gmail message ID.
            attachment_id (str): The Gmail attachment ID.

        Returns:
            bytes: The decoded attachment content, or None if not found.
        """
        try:
            response = (
                self.service.users()
                    .messages()
                    .attachments()
                    .get(userId="me", messageId=message_id, id=attachment_id)
                    .execute()
            )
            data = response.get("data")
            if data:
                return base64.urlsafe_b64decode(data)
        except Exception as e:
            print(f"Failed to fetch attachment {attachment_id}: {e}")
            return None
