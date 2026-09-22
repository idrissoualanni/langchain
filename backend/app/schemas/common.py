# Helpers partagés des schemas — SANS logique métier.
#
# Ces deux helpers étaient dupliqués dans app/api/schemas.py
# (_valid_uuid) et app/learning/schemas.py (_now) : source unique ici.
import uuid
from datetime import datetime, timezone


def valid_uuid(value: str, field_name: str) -> str:
    """Valide qu'une chaîne est un UUID (validateur Pydantic)."""
    try:
        uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        raise ValueError(f"{field_name} doit être un UUID valide")
    return value


def utc_now() -> str:
    """Horodatage ISO 8601 UTC (convention projet)."""
    return datetime.now(timezone.utc).isoformat()


__all__ = ["utc_now", "valid_uuid"]
