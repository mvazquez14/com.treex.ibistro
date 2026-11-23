from base64 import urlsafe_b64encode
from hashlib import sha256

from cryptography.fernet import Fernet

from app.core.config import settings

ALGORITHM = "HS256"


def _session_fernet() -> Fernet:
    digest = sha256(settings.SESSION_SECRET.encode()).digest()
    return Fernet(urlsafe_b64encode(digest))


def encrypt_session(value: str) -> str:
    return _session_fernet().encrypt(value.encode()).decode()


def decrypt_session(value: str) -> str:
    return _session_fernet().decrypt(value.encode()).decode()
