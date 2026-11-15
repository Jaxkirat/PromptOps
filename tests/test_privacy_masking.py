"""Unit tests for the PII/secret masking engine — every category plus negatives."""

from __future__ import annotations

import pytest

from codeforge.privacy.masker import MASK, mask_sensitive_data
from codeforge.privacy.patterns import luhn_valid


class TestApiKeys:
    @pytest.mark.parametrize(
        "text",
        [
            "my key is sk-abcdef1234567890abcdef",
            "GROQ key gsk_QnnAbCdEf1234567890XyZ",
            "github ghp_abcdefghij1234567890ABCDEFGHIJ",
            "aws AKIAIOSFODNN7EXAMPLE",
            "google AIzaSyA-1234567890abcdefghijklmnopqrstuvw",
            "slack xoxb-123456789012-abcdefghijkl",
            "api_key = 'supersecretvalue12345'",
        ],
    )
    def test_api_keys_masked(self, text: str) -> None:
        result = mask_sensitive_data(text)
        assert MASK in result.sanitized_text
        assert "api_key" in result.redaction_categories
        assert result.redaction_count >= 1

    def test_key_value_not_retained(self) -> None:
        result = mask_sensitive_data("key sk-verysecretkey123456")
        assert "sk-verysecretkey123456" not in result.sanitized_text


class TestEmails:
    def test_simple_email(self) -> None:
        result = mask_sensitive_data("contact me at alice@example.com please")
        assert result.sanitized_text == f"contact me at {MASK} please"
        assert result.redaction_categories == ["email"]

    def test_email_with_plus_and_dots(self) -> None:
        result = mask_sensitive_data("send to first.last+tag@sub.domain.co.in")
        assert MASK in result.sanitized_text
        assert "first.last" not in result.sanitized_text


class TestPhones:
    @pytest.mark.parametrize(
        "text",
        [
            "call +91 9876543210 now",
            "call 9876543210 now",
            "call +91-98765-43210 now",
            "call +919876543210 now",
            "US office +1-202-555-0143 line",
            "UK office +44 20 7946 0958 line",
        ],
    )
    def test_phones_masked(self, text: str) -> None:
        result = mask_sensitive_data(text)
        assert MASK in result.sanitized_text
        assert "phone" in result.redaction_categories


class TestAadhaar:
    @pytest.mark.parametrize(
        "text",
        [
            "aadhaar 234567890123 here",
            "aadhaar 2345 6789 0123 here",
            "aadhaar 2345-6789-0123 here",
        ],
    )
    def test_aadhaar_masked(self, text: str) -> None:
        result = mask_sensitive_data(text)
        assert MASK in result.sanitized_text
        assert "aadhaar" in result.redaction_categories


class TestCards:
    def test_luhn(self) -> None:
        assert luhn_valid("4111111111111111") is True
        assert luhn_valid("4111111111111112") is False

    @pytest.mark.parametrize(
        "text",
        [
            "visa 4111111111111111 ok",
            "visa 4111 1111 1111 1111 ok",
            "visa 4111-1111-1111-1111 ok",
            "amex 378282246310005 ok",
        ],
    )
    def test_valid_cards_masked(self, text: str) -> None:
        result = mask_sensitive_data(text)
        assert MASK in result.sanitized_text
        assert "card" in result.redaction_categories

    def test_luhn_invalid_16_digits_not_card(self) -> None:
        # Fails Luhn => not masked as a card.
        result = mask_sensitive_data("number 1234 5678 9012 3456 here")
        assert "card" not in result.redaction_categories


class TestNegativesAndEdgeCases:
    @pytest.mark.parametrize(
        "text",
        [
            "I have 100 apples and 42 oranges",
            "the year 2024 was great",
            "order id 1234567",
            "1234567890 is my ticket number",  # 10 digits but not starting 6-9
            "pi is 3.14159265358979",
        ],
    )
    def test_benign_numbers_untouched(self, text: str) -> None:
        result = mask_sensitive_data(text)
        assert result.sanitized_text == text
        assert result.redaction_count == 0

    def test_empty_input(self) -> None:
        result = mask_sensitive_data("")
        assert result.sanitized_text == ""
        assert result.redaction_count == 0

    def test_already_masked_input_unchanged(self) -> None:
        text = f"my key is {MASK} and email {MASK}"
        result = mask_sensitive_data(text)
        assert result.sanitized_text == text
        assert result.redaction_count == 0

    def test_multiple_values_and_categories(self) -> None:
        text = (
            "mail bob@test.org, phone +91 9876543210, key sk-secret1234567890, "
            "aadhaar 2345 6789 0123, card 4111 1111 1111 1111"
        )
        result = mask_sensitive_data(text)
        assert result.redaction_count == 5
        assert result.redaction_categories == ["aadhaar", "api_key", "card", "email", "phone"]
        for raw in ("bob@test.org", "9876543210", "sk-secret", "2345 6789", "4111"):
            assert raw not in result.sanitized_text

    def test_overlapping_card_and_aadhaar_handled_once(self) -> None:
        # 16-digit valid card must be masked as ONE card, not card + aadhaar/phone.
        result = mask_sensitive_data("card: 4111111111111111")
        assert result.redaction_count == 1
        assert result.redaction_categories == ["card"]

    def test_result_contains_no_original_values(self) -> None:
        result = mask_sensitive_data("secret sk-topsecret99999999")
        dumped = result.model_dump_json()
        assert "sk-topsecret99999999" not in dumped
