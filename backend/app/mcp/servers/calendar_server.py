# SHIM de compatibilité (refactor — phase migration).
from app.infrastructure.mcp.servers.calendar_server import (
    check_availability,
    create_event,
    list_events,
)

__all__ = ["check_availability", "create_event", "list_events"]
