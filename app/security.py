"""Password hashing helpers.

JWT issuance is added with the auth feature. Never log passwords, hashes, or
token contents.
"""

import base64
import binascii
import hashlib
import hmac
import secrets

_ALGORITHM = "pbkdf2_sha256"
_ITERATIONS = 600_000


def hash_password(password: str) -> str:
    """Hash a plaintext password with a fresh random salt."""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("ascii"),
        _ITERATIONS,
    )
    encoded = base64.b64encode(digest).decode("ascii")
    return f"{_ALGORITHM}${_ITERATIONS}${salt}${encoded}"


def verify_password(password: str, password_hash: str) -> bool:
    """Return True when the password matches the stored hash."""
    try:
        algorithm, iterations_text, salt, encoded = password_hash.split("$", 3)
        if algorithm != _ALGORITHM:
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
