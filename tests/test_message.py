from mail_to_sqlite.message import ParsedMessage


def test_decode_body_multipart_alternative():
    message = ParsedMessage()
    part = {
        "mimeType": "multipart/alternative",
        "body": {},
        "parts": [
            {
                "mimeType": "text/plain",
                "body": {"data": "VGhpcyBpcyB0aGUgcGxhaW4gdGV4dCBib2R5Lg=="}  # "This is the plain text body."
            },
            {
                "mimeType": "text/html",
                "body": {"data": "PGh0bWw+PGJvZHk+VGhpcyBpcyB0aGUgPGI+SFRNTDwvYj4gYm9keS48L2JvZHk+PC9odG1sPg=="}  # "<html><body>This is the <b>HTML</b> body.</body></html>"
            }
        ]
    }
    decoded_body = message.decode_body(part)
    assert decoded_body == "This is the plain text body."


def test_decode_body_html_only():
    message = ParsedMessage()
    part = {
        "mimeType": "multipart/alternative",
        "body": {},
        "parts": [
            {
                "mimeType": "text/html",
                "body": {"data": "PGgxPkhlbGxvPC9oMT48cD5UaGlzIGlzIEhUTUwuPC9wPg=="}  # "<h1>Hello</h1><p>This is HTML.</p>"
            }
        ]
    }
    decoded_body = message.decode_body(part)
    assert decoded_body == "Hello\nThis is HTML."


def test_decode_body_nested_multipart():
    message = ParsedMessage()
    part = {
        "mimeType": "multipart/mixed",
        "body": {},
        "parts": [
            {
                "mimeType": "multipart/alternative",
                "body": {},
                "parts": [
                    {
                        "mimeType": "text/plain",
                        "body": {"data": "VGhpcyBpcyBhIG5lc3RlZCBtZXNzYWdlLg=="}  # "This is a nested message."
                    }
                ]
            }
        ]
    }
    decoded_body = message.decode_body(part)
    assert decoded_body == "This is a nested message."


def test_decode_body_plain_text_only():
    message = ParsedMessage()
    part = {
        "mimeType": "text/plain",
        "body": {"data": "VGhpcyBpcyBwbGFpbiB0ZXh0Lg=="}  # "This is plain text."
    }
    decoded_body = message.decode_body(part)
    assert decoded_body == "This is plain text."


def test_decode_body_no_body():
    message = ParsedMessage()
    part = {
        "mimeType": "text/plain",
        "body": {}
    }
    decoded_body = message.decode_body(part)
    assert decoded_body == ""
