from mail_to_sqlite.message import Message

def test_parse_addresses_simple():
    """Test parsing a simple, well-behaved address string."""
    msg = Message()
    address_string = "sender@example.com, Another Person <another@example.com>"
    expected = [
        {"name": "", "email": "sender@example.com"},
        {"name": "Another Person", "email": "another@example.com"}
    ]
    # The current implementation might pass this, which is fine.
    # We are building up to the failing case.
    assert msg.parse_addresses(address_string) == expected

def test_parse_addresses_handles_commas_in_names():
    """
    Test that parse_addresses correctly handles addresses where the
    display name contains a comma, e.g., "Doe, John <doe@example.com>".
    This test should fail with the current implementation.
    """
    msg = Message()
    # This is the string that will break the simple .split(',') logic
    address_string = '"Doe, John" <john.doe@example.com>, "Smith, Jane" <jane.smith@example.com>'
    expected = [
        {"name": "Doe, John", "email": "john.doe@example.com"},
        {"name": "Smith, Jane", "email": "jane.smith@example.com"}
    ]
    
    # This assertion will fail because split(',') will create three parts:
    # '"Doe', ' John" <john.doe@example.com>', ' "Smith...'
    assert msg.parse_addresses(address_string) == expected
