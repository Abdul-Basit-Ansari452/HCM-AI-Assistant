"""Password hashing and JWT helpers.

New passwords use bcrypt. Legacy PBKDF2 hashes from the earlier scaffold are
still accepted so existing seeded users can log in.

Never log passwords, hashes, or token contents.
"""

import base64
import binascii
import hashlib
import hmac
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.config import settings

_LEGACY_ALGORITHM = "pbkdf2_sha256"
_LEGACY_ITERATIONS = 600_000
_BCRYPT_MAX_BYTES = 72


def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt."""
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > _BCRYPT_MAX_BYTES:
        raise ValueError("Password must be at most 72 bytes")
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")


def _verify_legacy_password(password: str, password_hash: str) -> bool:
    """Verify a PBKDF2 hash created by the pre-auth scaffold."""
    try:
        algorithm, iterations_text, salt, encoded = password_hash.split("$", 3)
        if algorithm != _LEGACY_ALGORITHM:
            return False
        iterations = int(iterations_text)
        expected = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        return False

    actual = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("ascii"),
        iterations,
    )
    return hmac.compare_digest(actual, expected)


def verify_password(password: str, password_hash: str) -> bool:
    """Return True when the password matches the stored hash."""
    if password_hash.startswith(f"{_LEGACY_ALGORITHM}$"):
        return _verify_legacy_password(password, password_hash)

    password_bytes = password.encode("utf-8")
    if len(password_bytes) > _BCRYPT_MAX_BYTES:
        return False

    try:
        return bcrypt.checkpw(password_bytes, password_hash.encode("utf-8"))
    except (TypeError, ValueError):
        return False


def create_access_token(
    user_id: int,
    role: str,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a signed JWT carrying the user id and role."""
    if not settings.jwt_secret:
        raise RuntimeError("JWT_SECRET is not configured")

    now = datetime.now(UTC)
    expires = now + (
        expires_delta
        or timedelta(minutes=settings.access_token_expire_minutes)
    )
    payload: dict[str, object] = {
        "sub": str(user_id),
        "role": role,
        "iat": now,
        "exp": expires,
    }
    return jwt.encode(
        payload,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> dict[str, object] | None:
    """Decode and validate a JWT, returning None when it is invalid."""
    if not settings.jwt_secret:
        return None

    try:
        return jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.PyJWTError:
        return None
