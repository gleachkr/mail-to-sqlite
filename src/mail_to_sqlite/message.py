import base64
from email.utils import getaddresses
from bs4 import BeautifulSoup


class Message:
    def __init__(self):
        self.id = None
        self.thread_id = None
        self.sender = {}
        self.recipients = {}
        self.labels = []
        self.subject = None
        self.body = None
        self.size = 0
        self.timestamp = None
        self.is_read = False
        self.is_outgoing = False
        self.attachments = []  # Attachments: list of dicts

    def parse_addresses(self, addresses: str) -> list:
        """
        Parse a string of one or more email addresses.

        Args:
            addresses (str): The list of email addresses to parse.
        Returns:
            list: The parsed email addresses.
        """
        # getaddresses handles multiple addresses and complex names correctly.
        # It returns a list of (realname, email_address) tuples.
        parsed = getaddresses([addresses])
        return [{"name": name, "email": email.lower()} for name, email in parsed if email]

    def decode_body(self, part) -> str:
        """
        Decode the body of a message part.

        Args:
            part (dict): The message part to decode.
        Returns:
            str: The decoded body of the message part.
        """
        if "data" in part["body"]:
            return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8")
        elif "parts" in part:
            for subpart in part["parts"]:
                decoded_body = self.decode_body(subpart)
                if decoded_body:
                    return decoded_body
        return ""

    def html2text(self, html: str) -> str:
        """
        Convert HTML to plain text.

        Args:
            html (str): The HTML to convert.
        Returns:
            str: The converted HTML.
        """
        soup = BeautifulSoup(html, features="html.parser")
        return soup.get_text()
