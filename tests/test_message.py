import unittest
from mail_to_sqlite.message import ParsedMessage

class TestParsedMessage(unittest.TestCase):
    def test_decode_body_multipart_alternative(self):
        message = ParsedMessage()
        part = {
            "mimeType": "multipart/alternative",
            "body": {},
            "parts": [
                {
                    "mimeType": "text/plain",
                    "body": {"data": "VGhpcyBpcyB0aGUgcGxhaW4gdGV4dC Bib2R5Lg=="} # "This is the plain text body."
                },
                {
                    "mimeType": "text/html",
                    "body": {"data": "PGh0bWw+PGJvZHk+VGhpcyBpcyB0aGUgPGI+SFRNTDwvYj4gYm9keS48L2JvZHk+PC9odG1sPg=="} # "<html><body>This is the <b>HTML</b> body.</body></html>"
                }
            ]
        }
        decoded_body = message.decode_body(part)
        self.assertEqual(decoded_body, "This is the plain text body.")

if __name__ == '__main__':
    unittest.main()
