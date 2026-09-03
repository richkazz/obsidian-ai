import secrets
import bcrypt

def generate_api_key() -> tuple[str, str, str]:
    secret = secrets.token_urlsafe(32)
    prefix = f"oba_{secrets.token_hex(6)}"
    return prefix, secret, f"{prefix}.{secret}"

def hash_api_key(secret: str) -> str:
    return bcrypt.hashpw(secret.encode(), bcrypt.gensalt()).decode()

def verify_api_key(secret: str, digest: str) -> bool:
    return bcrypt.checkpw(secret.encode(), digest.encode())
