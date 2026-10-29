"""Ed25519 signatures, so a version of the settings counts only when its approver signed it.

a5s only ever reads public keys. A private key stays with its owner, who signs
with `a5s sign`.
"""

from __future__ import annotations

import base64
import binascii

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

# Signatures over settings are never valid for anything else.
_DOMAIN = b"a5s settings v1\n"


def keypair() -> tuple[str, str]:
    """A new private and public key, base64-encoded."""
    key = Ed25519PrivateKey.generate()
    private = key.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()
    )
    public = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return base64.b64encode(private).decode(), base64.b64encode(public).decode()


def sign(private_key: str, data: bytes) -> str:
    key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(private_key))
    return base64.b64encode(key.sign(_DOMAIN + data)).decode()


def verify(public_key: str, data: bytes, signature: str) -> bool:
    try:
        key = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key))
        key.verify(base64.b64decode(signature), _DOMAIN + data)
    except (InvalidSignature, ValueError, binascii.Error):
        return False
    return True
