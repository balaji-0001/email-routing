import base64
import hashlib
import secrets
from functools import lru_cache

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from cryptography.fernet import Fernet, MultiFernet

from app.core.config import get_settings

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


@lru_cache
def _decoy_hash() -> str:
    return hash_password(secrets.token_urlsafe(16))


def burn_password_check(password: str) -> None:
    """Spend the same time as a real check, so an unknown email is not faster than a wrong password."""
    verify_password(_decoy_hash(), password)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Tokens are stored hashed, so a leaked table cannot be used to sign in."""
    return hashlib.sha256(token.encode()).hexdigest()


def _key_from(seed: str) -> Fernet:
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(seed.encode()).digest()))


@lru_cache
def _fernet() -> MultiFernet:
    settings = get_settings()
    derived = _key_from(f"{settings.database_url}:{settings.app_env}:email_secret_key")
    if settings.encryption_key:
        # New secrets use ENCRYPTION_KEY; ones stored before it was set still open.
        return MultiFernet([_key_from(settings.encryption_key), derived])
    return MultiFernet([derived])


def encrypt_secret(secret: str) -> str:
    """Encrypt sensitive credentials at rest."""
    return _fernet().encrypt(secret.encode("utf-8")).decode("utf-8")


def decrypt_secret(encrypted: str) -> str:
    """Decrypt sensitive credentials at rest."""
    return _fernet().decrypt(encrypted.encode("utf-8")).decode("utf-8")
