"""Repository du contrôle d'accès knowledge (façade de ``resolver``)."""
from __future__ import annotations

from typing import Literal

from app.services.knowledge import resolver as _resolver_service


def register_knowledge_base(
    info: _resolver_service.KnowledgeBaseInfo,
) -> None:
    """Enregistre une base de connaissance dans le registre."""
    _resolver_service.register_knowledge_base(info)


def get_knowledge_base(
    kb_id: str,
) -> _resolver_service.KnowledgeBaseInfo | None:
    """Retourne les informations d'une base de connaissance."""
    return _resolver_service.get_knowledge_base(kb_id)


def list_knowledge_bases() -> list[_resolver_service.KnowledgeBaseInfo]:
    """Liste toutes les bases de connaissance enregistrées."""
    return _resolver_service.list_knowledge_bases()


def add_access_rule(rule: _resolver_service.KnowledgeAccessRule) -> None:
    """Ajoute une règle d'accès pour une base de connaissance."""
    _resolver_service.add_access_rule(rule)


def remove_access_rule(rule: _resolver_service.KnowledgeAccessRule) -> bool:
    """Supprime une règle d'accès (False si elle n'existe pas)."""
    return _resolver_service.remove_access_rule(rule)


def check_access(
    knowledge_base_id: str,
    user_id: str,
    group_ids: list[str] | None = None,
    is_admin: bool = False,
) -> _resolver_service.AccessResult:
    """Vérifie si un utilisateur peut accéder à une base donnée."""
    return _resolver_service.check_access(
        knowledge_base_id, user_id, group_ids, is_admin
    )


def get_accessible_knowledge_bases(
    user_id: str,
    group_ids: list[str] | None = None,
    is_admin: bool = False,
) -> list[str]:
    """Liste les bases de connaissance accessibles à un utilisateur."""
    return _resolver_service.get_accessible_knowledge_bases(
        user_id, group_ids, is_admin
    )


def grant_access(
    knowledge_base_id: str,
    scope: Literal["public", "group", "user"],
    target_id: str = "",
) -> bool:
    """Accorde un accès à une base de connaissance."""
    return _resolver_service.grant_access(
        knowledge_base_id, scope, target_id
    )


def revoke_access(
    knowledge_base_id: str,
    scope: Literal["public", "group", "user"],
    target_id: str = "",
) -> bool:
    """Révoque un accès à une base de connaissance."""
    return _resolver_service.revoke_access(
        knowledge_base_id, scope, target_id
    )


def clear_all_rules() -> None:
    """Supprime toutes les règles d'accès (contexte de test)."""
    _resolver_service.clear_all_rules()


def clear_rules_for_kb(kb_id: str) -> int:
    """Supprime les règles d'une seule base (nombre supprimé)."""
    return _resolver_service.clear_rules_for_kb(kb_id)


def list_rules_for_kb(
    kb_id: str,
) -> list[_resolver_service.KnowledgeAccessRule]:
    """Liste les règles d'accès d'une seule base de connaissance."""
    return _resolver_service.list_rules_for_kb(kb_id)


def unregister_knowledge_base(kb_id: str) -> bool:
    """Retire une base du registre (False si elle n'existe pas)."""
    return _resolver_service.unregister_knowledge_base(kb_id)


def clear_all_knowledge_bases() -> None:
    """Supprime toutes les bases enregistrées (contexte de test)."""
    _resolver_service.clear_all_knowledge_bases()


__all__ = [
    "register_knowledge_base",
    "get_knowledge_base",
    "list_knowledge_bases",
    "add_access_rule",
    "remove_access_rule",
    "check_access",
    "get_accessible_knowledge_bases",
    "grant_access",
    "revoke_access",
    "clear_all_rules",
    "clear_rules_for_kb",
    "list_rules_for_kb",
    "unregister_knowledge_base",
    "clear_all_knowledge_bases",
]
