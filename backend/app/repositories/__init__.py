"""Couche d'accès aux données (Repository).

Distinction architecturale :
- Repository = accès aux données (où et comment les données sont
  stockées : requêtes SQL, store LangGraph, registre en mémoire).
  AUCUNE logique métier ici : chaque fonction délègue au module
  sous-jacent (``app.infrastructure.database.*`` ou ``app.services.*``).
- Service = logique métier (validation, règles, orchestration,
  calculs, déduplication, scoring).

Les repositories exposent des façades fines aux signatures
explicites afin que les couches supérieures (API, graphe) ne
dépendent plus directement des détails de stockage.
"""
from __future__ import annotations

from app.repositories import (
    activity,
    documents,
    knowledge,
    learning,
    memory,
    threads,
    users,
)

__all__ = [
    "activity",
    "documents",
    "knowledge",
    "learning",
    "memory",
    "threads",
    "users",
]
