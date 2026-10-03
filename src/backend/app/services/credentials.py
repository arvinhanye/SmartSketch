"""AES-256-GCM sealing of user-supplied model API keys (ADR-080).

The associated data is the owner's ``user_id``: a ciphertext copied into another user's row
fails authentication. Nothing here logs; no repr or error carries key material.
"""

from __future__ import annotations

import base64
import binascii
import os
from collections.abc import Callable

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import Settings
from app.repositories.model_configs import SealedKey

__all__ = ["CredentialCipher", "CredentialError", "CredentialUnavailable", "ModelConfigRequired", "SealedKey",
           "decode_root_key"]

KEY_BYTES = 32
NONCE_BYTES = 12


class CredentialError(Exception):
    """The root key is missing, or a sealed key cannot be authenticated."""


class ModelConfigRequired(Exception):
    """``LLM_MODE=personal`` and the current user has no saved model configuration."""


class CredentialUnavailable(Exception):
    """A task's key snapshot cannot be used; ``reason`` is a contract ``details.reason`` value."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def decode_root_key(raw: str) -> bytes:
    """Decode URL-safe base64 (padding optional) to exactly 32 bytes; ``ValueError`` otherwise."""
    text = raw.strip()
    try:
        key = base64.b64decode(text + "=" * (-len(text) % 4), altchars=b"-_", validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("root key is not URL-safe base64") from None
    if len(key) != KEY_BYTES:
        raise ValueError("root key must be 32 bytes")
    return key


class CredentialCipher:
    def __init__(self, root_key: bytes, *, random: Callable[[int], bytes] = os.urandom) -> None:
        if not isinstance(root_key, bytes) or len(root_key) != KEY_BYTES:
            raise CredentialError("root key must be 32 bytes")
        self._aead = AESGCM(root_key)
        self._random = random

    def __repr__(self) -> str:
        return "CredentialCipher()"

    @classmethod
    def from_settings(cls, settings: Settings) -> CredentialCipher:
        raw = settings.MODEL_CREDENTIAL_KEY.get_secret_value()
        if not raw.strip():
            raise CredentialError("MODEL_CREDENTIAL_KEY is not configured")
        try:
            return cls(decode_root_key(raw))
        except ValueError:
            raise CredentialError("MODEL_CREDENTIAL_KEY is invalid") from None

    def seal(self, user_id: str, api_key: str) -> SealedKey:
        nonce = self._random(NONCE_BYTES)
        return SealedKey(self._aead.encrypt(nonce, api_key.encode("utf-8"), user_id.encode("utf-8")), nonce)

    def open(self, user_id: str, sealed: SealedKey) -> str:
        try:
            return self._aead.decrypt(sealed.nonce, sealed.ciphertext, user_id.encode("utf-8")).decode("utf-8")
        except (InvalidTag, ValueError):
            raise CredentialError("sealed key cannot be opened") from None
