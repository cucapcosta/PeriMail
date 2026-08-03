from unittest.mock import MagicMock
from peribot.mail.db import Account
from peribot.mail.services import gmail_service_for_account


def test_gmail_service_for_account_decrypts_and_builds(mocker):
    account = Account(id=1, email="a@b.com", account_type="personal",
                      encrypted_tokens="enc", registered_at="2026-01-01")
    mocker.patch("peribot.mail.services.decrypt", return_value='{"token":"t"}')
    mocker.patch("peribot.mail.services.get_credentials", return_value="CREDS")
    build = mocker.patch("peribot.mail.services.get_gmail_service", return_value="SERVICE")
    result = gmail_service_for_account(account, b"key")
    assert result == "SERVICE"
    build.assert_called_once_with("CREDS")
