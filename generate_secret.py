#!/usr/bin/env python3
"""Generate a secure 32-character secret for API_KEY_ENCRYPTION_SECRET"""
import secrets
import string

def generate_secret(length=32):
    """Generate a cryptographically secure random string."""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

if __name__ == "__main__":
    secret = generate_secret()
    print(f"Generated secure secret (32 chars):")
    print(secret)
    print(f"\nAdd this to your Railway environment variables:")
    print(f"API_KEY_ENCRYPTION_SECRET={secret}")