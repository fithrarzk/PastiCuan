"""Optional Ed25519 integrity for immutable research artifacts."""

from __future__ import annotations

import base64
import os


def sign_checksum(checksum: str) -> tuple[str | None, str | None]:
    encoded = os.getenv("SNAPSHOT_ED25519_PRIVATE_KEY")
    if not encoded:
        return None, None
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(encoded))
    signature = base64.b64encode(key.sign(checksum.encode("ascii"))).decode("ascii")
    return signature, os.getenv("SNAPSHOT_SIGNING_KEY_ID", "primary")


def verify_checksum(checksum: str, signature: str | None) -> bool:
    encoded = os.getenv("SNAPSHOT_ED25519_PUBLIC_KEY")
    if not encoded:
        return True
    if not signature:
        return False
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        key = Ed25519PublicKey.from_public_bytes(base64.b64decode(encoded))
        key.verify(base64.b64decode(signature), checksum.encode("ascii"))
        return True
    except Exception:
        return False
