# Knowledge Access Control — ACL pour bases de connaissance (§11-§18)
#
# Contrôle d'accès aux knowledge bases avant retrieval.
# Répond à : "Cette knowledge base est-elle accessible à cet utilisateur dans ce contexte ?"
#
# Scopes :
#   - public : accessible à tous
#   - group : accessible aux membres d'un groupe
#   - user : accessible à un utilisateur spécifique
#   - admin : réservé aux administrateurs
#
# Architecture :
#   User → Knowledge Access Resolver → allowed knowledge bases → Retriever
#
# Isolation garantie :
#   - User A ≠ User B
#   - Group A ≠ Group B
#   - Revoked access = no access
from __future__ import annotations

import os
from typing import Literal

from pydantic import BaseModel, Field


class KnowledgeAccessRule(BaseModel):
    """Règle d'accès à une knowledge base."""
    
    knowledge_base_id: str
    scope: Literal["public", "group", "user", "admin"] = "private"
    target_id: str = ""  # user_id ou group_id selon scope
    enabled: bool = True


class KnowledgeBaseInfo(BaseModel):
    """Informations sur une knowledge base."""
    
    id: str
    name: str
    description: str = ""
    subject_id: str = ""
    scope: Literal["public", "group", "user", "admin", "private"] = "private"
    owner_user_id: str = ""
    group_ids: list[str] = Field(default_factory=list)
    enabled: bool = True
    metadata: dict = Field(default_factory=dict)


class AccessResult(BaseModel):
    """Résultat d'une vérification d'accès."""
    
    allowed: bool
    knowledge_base_id: str
    user_id: str
    reason: str = ""
    scope: str = "unknown"
    matched_rule: KnowledgeAccessRule | None = None


# Registry en mémoire des règles d'accès (sera persisté en DB)
_access_rules: dict[str, list[KnowledgeAccessRule]] = {}  # kb_id -> rules
_knowledge_bases: dict[str, KnowledgeBaseInfo] = {}  # kb_id -> info


def register_knowledge_base(info: KnowledgeBaseInfo) -> None:
    """Enregistre une knowledge base dans le registry."""
    _knowledge_bases[info.id] = info


def get_knowledge_base(kb_id: str) -> KnowledgeBaseInfo | None:
    """Récupère les infos d'une knowledge base."""
    return _knowledge_bases.get(kb_id)


def list_knowledge_bases() -> list[KnowledgeBaseInfo]:
    """Liste toutes les knowledge bases enregistrées."""
    return list(_knowledge_bases.values())


def add_access_rule(rule: KnowledgeAccessRule) -> None:
    """Ajoute une règle d'accès pour une knowledge base."""
    if rule.knowledge_base_id not in _access_rules:
        _access_rules[rule.knowledge_base_id] = []
    _access_rules[rule.knowledge_base_id].append(rule)


def remove_access_rule(rule: KnowledgeAccessRule) -> bool:
    """Supprime une règle d'accès."""
    if rule.knowledge_base_id not in _access_rules:
        return False
    
    rules = _access_rules[rule.knowledge_base_id]
    for i, r in enumerate(rules):
        if (r.scope == rule.scope and 
            r.target_id == rule.target_id and
            r.knowledge_base_id == rule.knowledge_base_id):
            rules.pop(i)
            return True
    return False


def check_access(
    knowledge_base_id: str,
    user_id: str,
    group_ids: list[str] | None = None,
    is_admin: bool = False,
) -> AccessResult:
    """Vérifie si un utilisateur a accès à une knowledge base (§12-§15).
    
    Algorithme :
      1. Si admin → accès toujours autorisé
      2. Chercher règles explicites pour cet utilisateur
      3. Chercher règles pour ses groupes
      4. Vérifier si public
      5. Sinon → refusé
    
    Args :
        knowledge_base_id : ID de la knowledge base
        user_id : ID de l'utilisateur
        group_ids : IDs des groupes de l'utilisateur
        is_admin : l'utilisateur est-il admin
    
    Returns :
        AccessResult avec allowed=True/False et reason
    """
    # 1. Admin → toujours accès
    if is_admin:
        return AccessResult(
            allowed=True,
            knowledge_base_id=knowledge_base_id,
            user_id=user_id,
            reason="Admin access",
            scope="admin",
        )
    
    # 2. Règles user-specific
    rules = _access_rules.get(knowledge_base_id, [])
    for rule in rules:
        if not rule.enabled:
            continue
        if rule.scope == "user" and rule.target_id == user_id:
            return AccessResult(
                allowed=True,
                knowledge_base_id=knowledge_base_id,
                user_id=user_id,
                reason=f"User assignment: {user_id}",
                scope="user",
                matched_rule=rule,
            )
    
    # 3. Règles group-specific
    if group_ids:
        for rule in rules:
            if not rule.enabled:
                continue
            if rule.scope == "group" and rule.target_id in group_ids:
                return AccessResult(
                    allowed=True,
                    knowledge_base_id=knowledge_base_id,
                    user_id=user_id,
                    reason=f"Group assignment: {rule.target_id}",
                    scope="group",
                    matched_rule=rule,
                )
    
    # 4. Public
    for rule in rules:
        if not rule.enabled:
            continue
        if rule.scope == "public":
            return AccessResult(
                allowed=True,
                knowledge_base_id=knowledge_base_id,
                user_id=user_id,
                reason="Public access",
                scope="public",
                matched_rule=rule,
            )
    
    # 5. Vérifier si la KB elle-même est publique
    kb_info = get_knowledge_base(knowledge_base_id)
    if kb_info and kb_info.scope == "public":
        return AccessResult(
            allowed=True,
            knowledge_base_id=knowledge_base_id,
            user_id=user_id,
            reason="Knowledge base is public",
            scope="public",
        )
    
    # 6. Refusé
    return AccessResult(
        allowed=False,
        knowledge_base_id=knowledge_base_id,
        user_id=user_id,
        reason="No matching access rule",
        scope="denied",
    )


def get_accessible_knowledge_bases(
    user_id: str,
    group_ids: list[str] | None = None,
    is_admin: bool = False,
) -> list[str]:
    """Retourne la liste des knowledge bases accessibles à un utilisateur.
    
    Usage : filtrer les résultats de retrieval AVANT de chercher.
    
    Args :
        user_id : ID de l'utilisateur
        group_ids : IDs des groupes
        is_admin : l'utilisateur est-il admin
    
    Returns :
        Liste des knowledge_base_id accessibles
    """
    accessible = []
    
    for kb_id in _knowledge_bases.keys():
        result = check_access(kb_id, user_id, group_ids, is_admin)
        if result.allowed:
            accessible.append(kb_id)
    
    return accessible


def grant_access(
    knowledge_base_id: str,
    scope: Literal["public", "group", "user"],
    target_id: str = "",
) -> bool:
    """Accorde l'accès à une knowledge base (§14).
    
    Args :
        knowledge_base_id : ID de la KB
        scope : type d'accès (public, group, user)
        target_id : user_id ou group_id (vide si public)
    
    Returns :
        True si succès
    """
    rule = KnowledgeAccessRule(
        knowledge_base_id=knowledge_base_id,
        scope=scope,
        target_id=target_id,
        enabled=True,
    )
    add_access_rule(rule)
    return True


def revoke_access(
    knowledge_base_id: str,
    scope: Literal["public", "group", "user"],
    target_id: str = "",
) -> bool:
    """Révoque l'accès à une knowledge base (§14).
    
    Args :
        knowledge_base_id : ID de la KB
        scope : type d'accès
        target_id : user_id ou group_id
    
    Returns :
        True si une règle a été supprimée
    """
    rule = KnowledgeAccessRule(
        knowledge_base_id=knowledge_base_id,
        scope=scope,
        target_id=target_id,
        enabled=True,
    )
    return remove_access_rule(rule)


def clear_all_rules() -> None:
    """Supprime toutes les règles (pour tests/reset)."""
    _access_rules.clear()


def clear_all_knowledge_bases() -> None:
    """Supprime toutes les KB enregistrées (pour tests/reset)."""
    _knowledge_bases.clear()


__all__ = [
    "KnowledgeAccessRule",
    "KnowledgeBaseInfo",
    "AccessResult",
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
    "clear_all_knowledge_bases",
]
