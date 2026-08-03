from peribot.mail.auth import get_credentials, get_gmail_service
from peribot.mail.crypto import decrypt


def gmail_service_for_account(account, encryption_key: bytes):
    """Build a Gmail API service for a stored account by decrypting its tokens."""
    credentials = get_credentials(decrypt(account.encrypted_tokens, encryption_key))
    return get_gmail_service(credentials)
