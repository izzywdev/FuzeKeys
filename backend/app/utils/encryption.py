from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
import base64
import os
import json
from typing import Optional, Any, Dict
from passlib.context import CryptContext

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class EncryptionManager:
    """Manager for handling encryption and decryption of sensitive data."""
    
    def __init__(self, master_key: str, salt: Optional[bytes] = None):
        """
        Initialize encryption manager with master key.
        
        Args:
            master_key: The master key for encryption
            salt: Salt for key derivation (if None, uses default from env)
        """
        self.master_key = master_key
        self.salt = salt or os.getenv("MASTER_KEY_SALT", "default_salt").encode()
        self._fernet = self._create_fernet_key()
    
    def _create_fernet_key(self) -> Fernet:
        """Create Fernet encryption key from master key and salt."""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=self.salt,
            iterations=100000,
            backend=default_backend()
        )
        key = base64.urlsafe_b64encode(kdf.derive(self.master_key.encode()))
        return Fernet(key)
    
    def encrypt(self, data: Any) -> str:
        """
        Encrypt data and return base64 encoded string.
        
        Args:
            data: Data to encrypt (will be JSON serialized if not string)
            
        Returns:
            Base64 encoded encrypted string
        """
        if data is None:
            return ""
        
        # Convert to string if not already
        if isinstance(data, str):
            plain_text = data
        else:
            plain_text = json.dumps(data)
        
        # Encrypt and encode
        encrypted_bytes = self._fernet.encrypt(plain_text.encode())
        return base64.urlsafe_b64encode(encrypted_bytes).decode()
    
    def decrypt(self, encrypted_data: str) -> Optional[str]:
        """
        Decrypt base64 encoded encrypted string.
        
        Args:
            encrypted_data: Base64 encoded encrypted string
            
        Returns:
            Decrypted string or None if decryption fails
        """
        if not encrypted_data:
            return None
        
        try:
            # Decode and decrypt
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_data.encode())
            decrypted_bytes = self._fernet.decrypt(encrypted_bytes)
            return decrypted_bytes.decode()
        except Exception:
            return None
    
    def decrypt_json(self, encrypted_data: str) -> Optional[Dict]:
        """
        Decrypt and parse JSON data.
        
        Args:
            encrypted_data: Base64 encoded encrypted JSON string
            
        Returns:
            Parsed JSON object or None if decryption/parsing fails
        """
        decrypted_str = self.decrypt(encrypted_data)
        if decrypted_str is None:
            return None
        
        try:
            return json.loads(decrypted_str)
        except json.JSONDecodeError:
            return None


def _hash_secret(secret: str) -> str:
    """Hash a FuzeKeys-domain secret (the vault master key) using bcrypt.

    PRIVATE on purpose. There used to be public `hash_password` /
    `verify_password` helpers here and they were used to authenticate users
    locally. User authentication now belongs to the FuzeFront Security API —
    FuzeKeys stores no user password at all — so exposing a general-purpose
    password hasher would only invite that mistake back in. The one remaining
    caller is the vault master-key verifier below, which is domain state, not a
    login credential.
    """
    return pwd_context.hash(secret)


def _verify_secret(plain_secret: str, stored_hash: str) -> bool:
    """Verify a FuzeKeys-domain secret against its stored hash. PRIVATE."""
    return pwd_context.verify(plain_secret, stored_hash)


def generate_master_key_hash(master_key: str, salt: Optional[str] = None) -> str:
    """Generate a hash of the vault master key for storage."""
    if salt is None:
        salt = os.getenv("MASTER_KEY_SALT", "default_salt")

    return _hash_secret(master_key + salt)


def verify_master_key(master_key: str, stored_hash: str, salt: Optional[str] = None) -> bool:
    """Verify a vault master key against its stored hash. Fail-closed."""
    if salt is None:
        salt = os.getenv("MASTER_KEY_SALT", "default_salt")
    if not stored_hash:
        return False

    return _verify_secret(master_key + salt, stored_hash)


def create_encryption_manager(master_key: str) -> EncryptionManager:
    """Create an encryption manager instance."""
    return EncryptionManager(master_key)


# Global encryption manager (will be set after user authentication)
_global_encryption_manager: Optional[EncryptionManager] = None


def set_global_encryption_manager(master_key: str):
    """Set the global encryption manager for the current user session."""
    global _global_encryption_manager
    _global_encryption_manager = EncryptionManager(master_key)


def get_global_encryption_manager() -> Optional[EncryptionManager]:
    """Get the global encryption manager."""
    return _global_encryption_manager


def encrypt_field(data: Any) -> str:
    """Encrypt a field using the global encryption manager."""
    if _global_encryption_manager is None:
        raise ValueError("Encryption manager not initialized")
    return _global_encryption_manager.encrypt(data)


def decrypt_field(encrypted_data: str) -> Optional[str]:
    """Decrypt a field using the global encryption manager."""
    if _global_encryption_manager is None:
        raise ValueError("Encryption manager not initialized")
    return _global_encryption_manager.decrypt(encrypted_data)


def decrypt_json_field(encrypted_data: str) -> Optional[Dict]:
    """Decrypt a JSON field using the global encryption manager."""
    if _global_encryption_manager is None:
        raise ValueError("Encryption manager not initialized")
    return _global_encryption_manager.decrypt_json(encrypted_data) 