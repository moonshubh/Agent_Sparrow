"""
Secure encryption utilities for API key management.
Uses AES-256 encryption with user-specific keys for maximum security.
"""

import os
import base64
import hashlib
from typing import Optional, Union
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from app.core.settings import get_settings

settings = get_settings()

class APIKeyEncryption:
    """
    Handles encryption and decryption of API keys with user-specific keys.
    Each user has their own encryption key derived from their user ID.
    """
    
    def __init__(self):
        # Master secret from environment - should be 32 bytes for AES-256
        self.master_secret = self._get_master_secret()
    
    def _get_master_secret(self) -> bytes:
        """Get or generate master secret for encryption."""
        secret = os.getenv('API_KEY_ENCRYPTION_SECRET')
        if not secret:
            # In development, use a default (NOT for production)
            secret = "MB_SPARROW_DEV_SECRET_CHANGE_IN_PRODUCTION"
        
        # Ensure we have a 32-byte key
        return hashlib.sha256(secret.encode()).digest()
    
    def _derive_user_key(self, user_id: str) -> bytes:
        """Derive a unique encryption key for each user."""
        # Combine user ID with master secret for user-specific key
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=f"mb_sparrow_user_{user_id}".encode(),
            iterations=100000,
        )
        return base64.urlsafe_b64encode(kdf.derive(self.master_secret))
    
    def encrypt_api_key(self, user_id: str, api_key: str) -> str:
        """
        Encrypt an API key for a specific user.
        Returns base64-encoded encrypted data.
        """
        if not api_key or not api_key.strip():
            raise ValueError("API key cannot be empty")
        
        user_key = self._derive_user_key(user_id)
        fernet = Fernet(user_key)
        encrypted = fernet.encrypt(api_key.encode())
        return base64.urlsafe_b64encode(encrypted).decode()
    
    def decrypt_api_key(self, user_id: str, encrypted_key: str) -> str:
        """
        Decrypt an API key for a specific user.
        Returns the original API key string.
        """
        if not encrypted_key or not encrypted_key.strip():
            raise ValueError("Encrypted key cannot be empty")
        
        try:
            user_key = self._derive_user_key(user_id)
            fernet = Fernet(user_key)
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_key.encode())
            decrypted = fernet.decrypt(encrypted_bytes)
            return decrypted.decode()
        except Exception as e:
            raise ValueError(f"Failed to decrypt API key: {str(e)}")
    
    def is_valid_api_key_format(self, api_key_type: str, api_key: str) -> bool:
        """
        Validate API key format based on provider requirements.
        """
        if not api_key or not api_key.strip():
            return False
        
        # Remove whitespace
        api_key = api_key.strip()
        
        if api_key_type == "gemini":
            # Gemini keys typically start with "AIza" and are 39 characters
            return api_key.startswith("AIza") and len(api_key) == 39
        elif api_key_type == "tavily":
            # Tavily keys are typically 32-40 characters, alphanumeric
            return len(api_key) >= 32 and len(api_key) <= 40 and api_key.isalnum()
        elif api_key_type == "firecrawl":
            # Firecrawl keys typically start with "fc-" and are longer
            return api_key.startswith("fc-") and len(api_key) >= 20
        else:
            return False
    
    def mask_api_key(self, api_key: str) -> str:
        """
        Mask API key for display purposes (show only last 4 characters).
        """
        if not api_key or len(api_key) < 4:
            return "****"
        return "*" * (len(api_key) - 4) + api_key[-4:]

# Global instance
encryption_service = APIKeyEncryption()