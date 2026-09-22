# SHIM de compatibilité (refactor — phase migration).
from app.infrastructure.mcp.servers.filesystem_server import (
    create_file,
    read_file,
    write_file,
)

__all__ = ["create_file", "read_file", "write_file"]
