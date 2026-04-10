"""
Generate a self-signed TLS certificate for development use.

Usage (run from the project root):
    python certs/gen_certs.py

Outputs:
    certs/server.key  — private key (keep secret)
    certs/server.crt  — self-signed certificate

For production, replace these with certificates issued by a trusted CA.
"""

import ipaddress
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

CERT_DIR = Path(__file__).parent
KEY_FILE = CERT_DIR / "server.key"
CERT_FILE = CERT_DIR / "server.crt"

# Generate RSA private key
key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

KEY_FILE.write_bytes(
    key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
)

# Build self-signed certificate
subject = issuer = x509.Name([
    x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
    x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Cisco Debug Database Dev"),
])

cert = (
    x509.CertificateBuilder()
    .subject_name(subject)
    .issuer_name(issuer)
    .public_key(key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(datetime.now(timezone.utc))
    .not_valid_after(datetime.now(timezone.utc) + timedelta(days=365))
    .add_extension(
        x509.SubjectAlternativeName([
            x509.DNSName("localhost"),
            x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
        ]),
        critical=False,
    )
    .sign(key, hashes.SHA256())
)

CERT_FILE.write_bytes(cert.public_bytes(serialization.Encoding.PEM))

print(f"Generated: {KEY_FILE}")
print(f"Generated: {CERT_FILE}")
print()
print("Start the API server (port 8443):")
print("  uvicorn main:app --ssl-keyfile certs/server.key --ssl-certfile certs/server.crt --port 8443")
print()
print("Start the web client (port 8000):")
print("  uvicorn client.main:app --ssl-keyfile certs/server.key --ssl-certfile certs/server.crt --port 8000")
