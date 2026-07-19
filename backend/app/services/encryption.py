import os
from pathlib import Path
from cryptography.fernet import Fernet

# Save key inside backend root
KEY_FILE = Path(__file__).resolve().parent.parent.parent / "secret.key"

def load_or_create_key() -> bytes:
    if not KEY_FILE.exists():
        key = Fernet.generate_key()
        with open(KEY_FILE, "wb") as f:
            f.write(key)
    else:
        with open(KEY_FILE, "rb") as f:
            key = f.read()
    return key

# Initialize Fernet cipher
cipher = Fernet(load_or_create_key())

def encrypt_password(password: str) -> str:
    """Encrypts a plaintext password to an encrypted token string."""
    if not password:
        return ""
    encrypted_bytes = cipher.encrypt(password.encode("utf-8"))
    return encrypted_bytes.decode("utf-8")

def decrypt_password(encrypted_token: str) -> str:
    """Decrypts an encrypted token string back to plaintext password."""
    if not encrypted_token:
        return ""
    decrypted_bytes = cipher.decrypt(encrypted_token.encode("utf-8"))
    return decrypted_bytes.decode("utf-8")
