from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa

# Generate a private key
private_key = rsa.generate_private_key(
    public_exponent=65537,
    key_size=2048,
    backend=default_backend()
)

# Generate a certificate signing request (CSR)
csr = x509.CertificateSigningRequestBuilder().subject_name(x509.Name([
    x509.NameAttribute(x509.NameOID.COMMON_NAME, u"example.com"),
]))\
    .add_extension(
        x509.SubjectAlternativeName([x509.DNSName(u"localhost")]),
        critical=False,
    # Sign the CSR with the private key
).sign(private_key, hashes.SHA256(), default_backend())

# Generate a self-signed certificate
cert = x509.CertificateBuilder().subject_name(csr.subject)\
    .issuer_name(csr.subject)\
    .public_key(csr.public_key())\
    .serial_number(x509.random_serial_number())\
    .not_valid_before(datetime.datetime.utcnow())\
    .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=365))\
    .sign(private_key, hashes.SHA256(), default_backend())

# Write the private key to a file
with open("key.pem", "wb") as f:
    f.write(private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    ))

# Write the certificate to a file
with open("cert.pem", "wb") as f:
    f.write(cert.public_bytes(serialization.Encoding.PEM))