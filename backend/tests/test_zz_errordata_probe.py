"""Reproduction du prérequis du correctif MCP (§39/§40/§41).

À SUPPRIMER après usage. Vérifie un SEUL fait, sans rien importer de la
chaîne `app.*` (bloquée par `import sqlalchemy`) : la SDK `mcp` exige-t-elle
un `message` sur `ErrorData` ?
"""
import pytest
from mcp.types import ErrorData


def test_errordata_sans_message_est_refuse():
    """Reproduction : `ErrorData(code=-32601)` seul doit échouer."""
    with pytest.raises(Exception) as exc_info:
        ErrorData(code=-32601)
    assert "message" in str(exc_info.value), str(exc_info.value)


def test_errordata_avec_message_est_accepte():
    e = ErrorData(code=-32601, message="Method not found")
    assert e.code == -32601
    assert e.message == "Method not found"
