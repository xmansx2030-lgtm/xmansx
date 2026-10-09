"""Generate ignored local-only keys/TLS; never export a production credential.

Run via the isolated tests container and mount artifacts/parent-staging at
/materials. Existing files are refused so encrypted synthetic data is not made
unreadable by accidental key rotation.
"""

import argparse
import os
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    expected = {
        "PARENT_VERIFICATION_LOCAL_ONLY": "1",
        "POSTGRES_DB": "parent_verification",
        "POSTGRES_USER": "parent_verify_owner",
        "POSTGRES_HOST": "postgres",
    }
    if any(os.environ.get(key) != value for key, value in expected.items()):
        raise RuntimeError("Refusing to generate materials outside isolated synthetic verification")
    output = Path(args.output).resolve()
    if output != Path("/materials"):
        raise RuntimeError("The materials destination must be the explicitly mounted /materials")
    output.mkdir(parents=True, exist_ok=True)
    targets = [output / name for name in (".env", "localhost.key", "localhost.crt")]
    if any(path.exists() for path in targets):
        raise RuntimeError("Existing staging keys must be retained; choose a fresh isolated stack")
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost synthetic staging")])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=30))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    values = {
        "DJANGO_SECRET_KEY": secrets.token_urlsafe(48),
        "FIELD_ENCRYPTION_KEYS": Fernet.generate_key().decode("ascii"),
        "NATIONAL_ID_HMAC_KEY": secrets.token_urlsafe(48),
    }
    targets[0].write_text(
        "".join(f"{key}={value}\n" for key, value in values.items()), encoding="utf-8"
    )
    targets[1].write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    targets[2].write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    for path in targets:
        path.chmod(0o600)
    print("Generated isolated localhost materials; values were not printed")


if __name__ == "__main__":
    main()
