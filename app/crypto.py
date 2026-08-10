"""Encryption for stored settings.

The only secret in the environment is SECRET_KEY. Everything sensitive that
lives in the database (SMTP passwords, GitHub tokens, VAPID keys, TOTP seeds)
is encrypted with a key derived from it, so a stolen database file on its own
gives up nothing.
"""
import base64
import hashlib
import os

from cryptography.fernet import Fernet


def _fernet() -> Fernet:
    secret = os.environ.get("SECRET_KEY", "")
    if not secret:
        raise RuntimeError("SECRET_KEY is not set — refusing to store secrets unencrypted.")
    digest = hashlib.sha256(("chkt-settings:" + secret).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(plaintext: str) -> bytes:
    return _fernet().encrypt(plaintext.encode())


def decrypt(ciphertext: bytes) -> str:
    return _fernet().decrypt(ciphertext).decode()
