from __future__ import annotations

import hashlib
import secrets

from cryptography.fernet import Fernet, InvalidToken


class EncryptionConfigurationError(ValueError):
    pass


class TokenDecryptionError(ValueError):
    pass


class TokenCipher:
    """Encrypt OAuth material at rest with an operator-managed Fernet key."""

    def __init__(self, key: str) -> None:
        try:
            self._fernet = Fernet(key.encode("ascii"))
        except (ValueError, TypeError) as exc:
            raise EncryptionConfigurationError(
                "DATA_ENCRYPTION_KEY must be a Fernet key"
            ) from exc

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode()).decode("ascii")

    def decrypt(self, value: str) -> str:
        try:
            return self._fernet.decrypt(value.encode("ascii")).decode()
        except (InvalidToken, ValueError) as exc:
            raise TokenDecryptionError("Encrypted OAuth value cannot be decrypted") from exc


def new_oauth_state() -> str:
    return secrets.token_urlsafe(32)


def new_code_verifier() -> str:
    # token_urlsafe(64) produces an RFC 7636 verifier within the 43–128 range.
    return secrets.token_urlsafe(64)


def hash_oauth_state(state: str) -> str:
    return hashlib.sha256(state.encode()).hexdigest()
