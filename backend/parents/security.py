"""Private-field crypto reuses the project's key rotation policy."""

import hashlib

from common.security.identifiers import (
    decrypt_national_id,
    encrypt_national_id,
    national_id_lookup_hash,
)
from school_sms.security import recipient_hash

encrypt_value = encrypt_national_id
decrypt_value = decrypt_national_id
contact_hash = recipient_hash


def mobile_hash(mobile: str) -> str:
    return national_id_lookup_hash(f"parent-mobile:{mobile}")


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
