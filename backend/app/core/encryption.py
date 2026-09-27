"""Module de chiffrement Fernet AES pour les données LiveKit.

Chiffre les transcripts et métadonnées avant stockage en base Neon.
Utilise Fernet (AES-128-CBC avec HMAC) via la bibliothèque cryptography.
"""

from __future__ import annotations

import base64
import os
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.config import ENCRYPTION_KEY

# =============================================================================
# INITIALISATION
# =============================================================================

_fernet: Fernet | None = None
_KEY_CACHE: bytes | None = None


def _get_fernet() -> Fernet:
    """Singleton Fernet — initialisé paresseusement."""
    global _fernet, _KEY_CACHE
    if _fernet is None:
        key = _derive_key(ENCRYPTION_KEY or os.urandom(32))
        _fernet = Fernet(key)
        _KEY_CACHE = key
    return _fernet


def _derive_key(password: str | bytes) -> bytes:
    """Dérive une clé Fernet depuis un mot de passe ou une clé brute.

    Si la clé est déjà une clé Fernet valide (44 caractères base64url),
    elle est utilisée directement. Sinon, elle est derivée via PBKDF2.
    """
    if isinstance(password, bytes):
        password_str = password.decode("utf-8", errors="ignore")
    else:
        password_str = password

    # Si c'est déjà une clé Fernet valide, la retourner directement
    try:
        if len(password_str) == 44 and all(
            c in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
            for c in password_str
        ):
            return password_str.encode("utf-8")
    except (ValueError, TypeError):
        pass

    # Dériver une clé depuis le mot de passe via PBKDF2
    salt = b"livekit_encryption_salt_v1"  # Salt fixe pour reproductibilité
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(password_str.encode("utf-8")))
    return key


# =============================================================================
# API PUBLIQUE
# =============================================================================


def encrypt(data: str | bytes) -> bytes:
    """Chiffre une chaîne ou des bytes.

    Args:
        data: Données à chiffrer (str ou bytes)

    Returns:
        Bytes chiffrés (format Fernet)
    """
    if isinstance(data, str):
        data = data.encode("utf-8")

    fernet = _get_fernet()
    return fernet.encrypt(data)


def decrypt(encrypted_data: bytes) -> bytes:
    """Déchiffre des données chiffrées Fernet.

    Args:
        encrypted_data: Bytes chiffrés

    Returns:
        Bytes déchiffrés

    Raises:
        InvalidToken: Si la clé est incorrecte ou les données corrompues
    """
    fernet = _get_fernet()
    return fernet.decrypt(encrypted_data)


def encrypt_str(data: str | bytes) -> str:
    """Chiffre et retourne une chaîne base64.

    Args:
        data: Données à chiffrer

    Returns:
        Chaîne base64 des données chiffrées
    """
    return encrypt(data).decode("utf-8")


def decrypt_str(encrypted_str: str) -> str:
    """Déchiffre une chaîne base64 et retourne du texte.

    Args:
        encrypted_str: Chaîne base64 chiffrée

    Returns:
        Texte déchiffré
    """
    return decrypt(encrypted_str.encode("utf-8")).decode("utf-8")


def encrypt_json(obj: dict[str, Any]) -> bytes:
    """Sérialise et chiffre un objet JSON.

    Args:
        obj: Objet dict à chiffrer

    Returns:
        Bytes chiffrés
    """
    import json

    json_str = json.dumps(obj, ensure_ascii=False)
    return encrypt(json_str)


def decrypt_json(encrypted_data: bytes) -> dict[str, Any]:
    """Déchiffre et désérialise un objet JSON.

    Args:
        encrypted_data: Bytes chiffrés

    Returns:
        Objet dict désérialisé
    """
    import json

    decrypted = decrypt(encrypted_data)
    return json.loads(decrypted.decode("utf-8"))


# =============================================================================
# VALIDATION
# =============================================================================


def is_encryption_configured() -> bool:
    """True si la clé de chiffrement est configurée."""
    return bool(ENCRYPTION_KEY)


def test_encryption() -> bool:
    """Teste que le chiffrement fonctionne.

    Returns:
        True si le test réussit
    """
    test_data = "Test de chiffrement LiveKit!"
    try:
        encrypted = encrypt(test_data)
        decrypted = decrypt(encrypted)
        return decrypted.decode("utf-8") == test_data
    except (InvalidToken, Exception):
        return False