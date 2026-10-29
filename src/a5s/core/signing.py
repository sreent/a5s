"""Ed25519 signatures, so a version of the settings, or a release, counts only when the
people it needs signed it.

a5s only ever reads public keys. A private key stays with its owner, who signs
with `a5s sign` or `a5s release sign`.
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

# A signature over settings is never valid for a release, nor the other way round.
SETTINGS = b"a5s settings v1\n"
RELEASE = b"a5s release v1\n"


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


def sign(private_key: str, data: bytes, domain: bytes = SETTINGS) -> str:
    key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(private_key))
    return base64.b64encode(key.sign(domain + data)).decode()


def verify(public_key: str, data: bytes, signature: str, domain: bytes = SETTINGS) -> bool:
    try:
        key = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key))
        key.verify(base64.b64decode(signature), domain + data)
    except (InvalidSignature, ValueError, binascii.Error):
        return False
    return True
