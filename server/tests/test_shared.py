"""Tests for server/shared.py."""

from server.shared import _sanitize


class TestSanitize:
    """Test SQL injection sanitization."""

    def test_basic_string(self):
        assert _sanitize("hello") == "hello"

    def test_with_single_quote(self):
        assert _sanitize("it's") == "it''s"

    def test_multiple_quotes(self):
        assert _sanitize("'a' 'b'") == "''a'' ''b''"

    def test_empty_string(self):
        assert _sanitize("") == ""

    def test_no_quotes(self):
        assert _sanitize("simple") == "simple"

    def test_unicode(self):
        assert _sanitize("héllo") == "héllo"

    def test_sql_injection_attempt(self):
        assert _sanitize("'; DROP TABLE tasks; --") == "''; DROP TABLE tasks; --"
