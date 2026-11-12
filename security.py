import os
from cryptography.fernet import Fernet

# generate this key ONCE chrome (reminder)
# key = Fernet.generate_key()
# print(key.decode())

def get_cipher():
    key = os.environ.get("ENCRYPTION_KEY").encode()
    return Fernet(key)

def encrypt_token(token: str) -> str:
    cipher = get_cipher()
    return cipher.encrypt(token.encode()).decode()

def decrypt_token(encrypted_token: str) -> str:
    cipher = get_cipher()
    return cipher.decrypt(encrypted_token.encode()).decode()
