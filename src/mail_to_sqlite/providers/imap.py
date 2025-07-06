import imaplib
import email
from email.utils import parseaddr, parsedate_to_datetime
from typing import Dict, List, Optional
from datetime import datetime
import re
import uuid

from .base import EmailProvider
from ..message import ParsedMessage

class IMAPProvider(EmailProvider):
    """IMAP implementation of the EmailProvider interface."""
    
    def __init__(self):
        self.conn = None
        self.username = None
        
    def authenticate(self, data_dir: str):
        """Authenticate with IMAP server."""
        from .. import auth
        credentials = auth.get_imap_credentials(data_dir)
        
        self.username = credentials['username']
        if credentials['insecure']:
            self.conn = imaplib.IMAP4(credentials['server'])
        else:
            self.conn = imaplib.IMAP4_SSL(credentials['server'])
        self.conn.login(credentials['username'], credentials['password'])
    
    def get_labels(self) -> Dict[str, str]:
        """Get all folders from IMAP server."""
        labels = {}
        typ, data = self.conn.list()
        if typ == 'OK':
            for folder in data:
                folder_str = folder.decode('utf-8')
                match = re.search(r'"([^"]+)"$|([^ ]+)$', folder_str)
                if match:
                    folder_name = match.group(1) or match.group(2)
                    labels[folder_name] = folder_name
        return labels
    
    def _parse_imap_message(self, raw_msg, labels, flags=()) -> ParsedMessage:
        """Parse an IMAP message into our Message format."""
        msg_obj = ParsedMessage()
        
        # Parse email using the built-in email module
        email_message = email.message_from_bytes(raw_msg)
        
        # Extract headers
        msg_obj.id = email_message.get('Message-ID', '').strip('<>')
        if not msg_obj.id:
            # Create a synthetic ID if none exists
            msg_obj.id = str(uuid.uuid4())
        
        msg_obj.thread_id = None
        
        # Parse From
        from_header = email_message.get('From', '')
        from_name, from_email = parseaddr(from_header)
        msg_obj.sender = {"name": from_name, "email": from_email}
        
        # Parse To, CC, BCC
        msg_obj.recipients = {}
        if 'To' in email_message:
            msg_obj.recipients['to'] = msg_obj.parse_addresses(email_message['To'])
        if 'Cc' in email_message:
            msg_obj.recipients['cc'] = msg_obj.parse_addresses(email_message['Cc'])
        if 'Bcc' in email_message:
            msg_obj.recipients['bcc'] = msg_obj.parse_addresses(email_message['Bcc'])
        
        # Subject
        msg_obj.subject = email_message.get('Subject', '')
        
        # Date
        date_str = email_message.get('Date')
        if date_str:
            try:
                msg_obj.timestamp = parsedate_to_datetime(date_str)
            except:
                msg_obj.timestamp = datetime.now()
        
        # Body
        msg_obj.body = ""
        if email_message.is_multipart():
            for part in email_message.walk():
                if part.get_content_type() == "text/plain":
                    msg_obj.body = part.get_payload(decode=True).decode('utf-8', errors='replace')
                    break
                elif part.get_content_type() == "text/html" and not msg_obj.body:
                    html = part.get_payload(decode=True).decode('utf-8', errors='replace')
                    msg_obj.body = msg_obj.html2text(html)
        else:
            payload = email_message.get_payload(decode=True)
            if payload:
                msg_obj.body = payload.decode('utf-8', errors='replace')
        
        # Size
        msg_obj.size = len(raw_msg)
        
        # Labels - use the current folder name
        msg_obj.labels = list(labels.values())
        
        # Read status and outgoing
        msg_obj.is_read = b'\\Seen' in flags
        msg_obj.is_outgoing = from_email == self.username

        msg_obj.attachments = []
        for part in email_message.walk():
            content_disposition = part.get("Content-Disposition", None)
            if content_disposition and "attachment" in content_disposition.lower():
                filename = part.get_filename()
                if filename:
                    payload = part.get_payload(decode=True)
                    msg_obj.attachments.append({
                        "message_id": msg_obj.id,
                        "filename": filename,
                        "content_type": part.get_content_type(),
                        "size": len(payload) if payload else 0,
                        "attachment_id": None,  # Not used for IMAP
                        "content": payload      # The binary content
                    })
        
        return msg_obj
    
    def get_message(self, message_id: str) -> ParsedMessage:
        """Get a single message by ID from IMAP."""
        # In IMAP we need to search for message_id
        labels = self.get_labels()
        
        for folder_name in labels.keys():
            self.conn.select('"' + folder_name + '"')
            # Search for the message by Message-ID header
            typ, data = self.conn.search(None, f'HEADER Message-ID "{message_id}"')
            if typ == 'OK' and data[0]:
                # Get the first matching message
                msg_nums = data[0].split()
                if msg_nums:
                    typ, msg_data = self.conn.fetch(msg_nums[0], '(FLAGS RFC822)')
                    if typ == 'OK':
                        metadata = msg_data[0][0]
                        raw_msg = msg_data[0][1]

                        flags = ()
                        match = re.search(br'FLAGS \((.*?)\)', metadata)
                        if match:
                            flags = match.group(1).split()
                        
                        return self._parse_imap_message(
                            raw_msg, {folder_name: folder_name}, flags
                        )
        
        raise ValueError(f"Message with ID {message_id} not found")

    def _list_messages_in_folder(self, folder_name: str, query: List[str], 
                               start_idx: int = 1, max_results: int = 500) -> Dict:
        """List messages in a single folder with pagination."""
        self.conn.select('"' + folder_name + '"')
        
        # Build search criteria
        search_criteria = " OR ".join(query)
        search_criteria = "OR " + search_criteria + " NOT ALL"
        typ, data = self.conn.search(None, search_criteria)
        
        result = {"messages": [], "remaining": 0}
        
        if typ == 'OK':
            message_nums = data[0].split()
            total_msgs = len(message_nums)

            # Apply pagination within this folder
            end_idx = min(start_idx + max_results - 1, total_msgs)
            if start_idx <= total_msgs:
                batch = message_nums[start_idx-1:end_idx]
                
                for num in batch:
                    # Just get the headers and UID for listing
                    typ, msg_data = self.conn.fetch(num, '(UID BODY.PEEK[HEADER])')
                    if typ == 'OK':
                        msg_id = None
                        for response_part in msg_data:
                            if isinstance(response_part, tuple):
                                header_text = response_part[1].decode('utf-8')
                                parsed_headers = email.message_from_string(header_text)
                                msg_id = parsed_headers.get('Message-ID', '').strip('<>')
                                if not msg_id: 
                                    print("Warning. A message was missing the Message-ID header")
                        
                        if msg_id:
                            result["messages"].append({"id": msg_id})
            
            # Calculate how many messages remain in this folder
            result["remaining"] = max(0, total_msgs - end_idx)
        
        return result
    
    def list_messages(self, query=None, page_token=None, max_results=500):
        """List messages across all folders with proper pagination."""
        if query is None:
            query = ["ALL"]
        
        # Parse pagination token: "folder_idx:msg_idx"
        folder_idx, msg_idx = 0, 1
        if page_token:
            folder_idx, msg_idx = map(int, page_token.split(':'))
        
        result = {"messages": [], "nextPageToken": None}
        labels = list(self.get_labels().keys())
        remaining_quota = max_results
        
        # Continue from where we left off
        for i in range(folder_idx, len(labels)):
            folder_result = self._list_messages_in_folder(
                labels[i], query, msg_idx, remaining_quota
            )

            result["messages"].extend(folder_result["messages"])
            remaining_quota -= len(folder_result["messages"])
            
            # If this folder has more messages, set next token
            if folder_result["remaining"] > 0:
                next_msg_idx = msg_idx + len(folder_result["messages"])
                result["nextPageToken"] = f"{i}:{next_msg_idx}"
                break
            
            # If we've filled our quota, move to next folder
            if remaining_quota <= 0:
                next_folder = i + 1 if i + 1 < len(labels) else None
                if next_folder is not None:
                    result["nextPageToken"] = f"{next_folder}:1"
                break
                
            # Reset message index for next folder
            msg_idx = 1
        
        return result
    
    # XXX: IMAP search granularity is one-day, so we can't do any better for
    # getting non-indexed email without a lot of complication.
    def build_query(self, after: Optional[datetime] = None, 
                   before: Optional[datetime] = None) -> List[str]:
        """Build an IMAP query based on datetime filters."""
        query = []
        if after:
            # Format date for IMAP: DD-MMM-YYYY
            date_str = after.strftime("%d-%b-%Y")
            query.append(f'SINCE "{date_str}"')
        if before:
            date_str = before.strftime("%d-%b-%Y")
            query.append(f'BEFORE "{date_str}"')
        
        if not query:
            query = ["ALL"]
            
        return query
