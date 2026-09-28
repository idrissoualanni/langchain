# Knowledge Access Control — ACL pour bases de connaissance (§11-§18).
#
# Contrôle d'accès aux knowledge bases avant retrieval.
# Répond à : "Cette knowledge base est-elle accessible à cet utilisateur
# dans ce contexte ?"
#
# Scopes :
#   - public : accessible à tous
#   - group  : accessible aux membres d'un groupe
#   - user   : accessible à un utilisateur spécifique
#   - admin  : réservé aux administrateurs
#
# PERSISTANCE : les KB et règles vivent dans NEON ( knowledge_bases /
# knowledge_access_rules ) — les dict en mémoire étaient perdus à chaque
# redémarrage. Convention : une KB dont l'id = subject_id restreint le
# corpus de cette matière ( appliqué par knowledge_retriever via
# user_id — sans KB enregistrée, le corpus reste ouvert ).
#
# Isolation garantie :
#   - User A ≠ User B
#   - Group A ≠ Group B
#   - Revoked access = no access
from __future__ import annotations

import json
import time
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text

from app.infrastructure.database.persistence import _postgres_url
from app.logging.events import log_event


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
    """Résultat de vérification d'accès."""

    allowed: bool
    knowledge_base_id: str
    user_id: str
    reason: str = ""
    scope: str = "unknown"
    matched_rule: KnowledgeAccessRule | None = None


def _engine():
    return create_engine(_postgres_url(), pool_pre_ping=True)


def _kb_row_to_info(row) -> KnowledgeBaseInfo:
    return KnowledgeBaseInfo(
        id=row[0],
        name=row[1],
        description=row[2] or "",
        subject_id=row[3] or "",
        scope=row[4] or "private",
        owner_user_id=row[5] or "",
        group_ids=json.loads(row[6] or "[]"),
        enabled=bool(row[7]),
        metadata=json.loads(row[8] or "{}"),
    )


def _rules_for(kb_id: str) -> list[KnowledgeAccessRule]:
    """Règles ( actives ET désactivées ) d'une KB, depuis Neon."""
    with _engine().connect() as conn:
        rows = conn.execute(
            text(
                "SELECT knowledge_base_id, scope, target_id, enabled "
                "FROM knowledge_access_rules WHERE knowledge_base_id = :k"
            ),
            {"k": kb_id},
        ).fetchall()
    return [
        KnowledgeAccessRule(
            knowledge_base_id=r[0], scope=r[1], target_id=r[2], enabled=bool(r[3])
        )
        for r in rows
    ]


def register_knowledge_base(info: KnowledgeBaseInfo) -> None:
    """Enregistre ( ou met à jour ) une knowledge base — Neon."""
    with _engine().begin() as conn:
        conn.execute(
            text(
                "INSERT INTO knowledge_bases "
                "(id, name, description, subject_id, scope, owner_user_id, "
                " group_ids, enabled, metadata, created_at) "
                "VALUES (:i, :n, :d, :s, :sc, :o, :g, :e, :m, :c) "
                "ON CONFLICT (id) DO UPDATE SET "
                "name=EXCLUDED.name, description=EXCLUDED.description, "
                "subject_id=EXCLUDED.subject_id, scope=EXCLUDED.scope, "
                "owner_user_id=EXCLUDED.owner_user_id, "
                "group_ids=EXCLUDED.group_ids, enabled=EXCLUDED.enabled, "
                "metadata=EXCLUDED.metadata"
            ),
            {
                "i": info.id,
                "n": info.name,
                "d": info.description,
                "s": info.subject_id,
                "sc": info.scope,
                "o": info.owner_user_id,
                "g": json.dumps(info.group_ids),
                "e": info.enabled,
                "m": json.dumps(info.metadata),
                "c": time.strftime("%Y-%m-%dT%H:%M:%S"),
            },
        )


def get_knowledge_base(kb_id: str) -> KnowledgeBaseInfo | None:
    with _engine().connect() as conn:
        row = conn.execute(
            text(
                "SELECT id, name, description, subject_id, scope, "
                "owner_user_id, group_ids, enabled, metadata "
                "FROM knowledge_bases WHERE id = :i"
            ),
            {"i": kb_id},
        ).first()
    return _kb_row_to_info(row) if row else None


def list_knowledge_bases() -> list[KnowledgeBaseInfo]:
    with _engine().connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, name, description, subject_id, scope, "
                "owner_user_id, group_ids, enabled, metadata "
                "FROM knowledge_bases ORDER BY id"
            )
        ).fetchall()
    return [_kb_row_to_info(r) for r in rows]


def add_access_rule(rule: KnowledgeAccessRule) -> None:
    """Ajoute une règle d'accès — Neon ( idempotent par triple unique )."""
    with _engine().begin() as conn:
        conn.execute(
            text(
                "INSERT INTO knowledge_access_rules "
                "(knowledge_base_id, scope, target_id, enabled) "
                "VALUES (:k, :s, :t, :e) "
                "ON CONFLICT (knowledge_base_id, scope, target_id) "
                "DO UPDATE SET enabled = EXCLUDED.enabled"
            ),
            {
                "k": rule.knowledge_base_id,
                "s": rule.scope,
                "t": rule.target_id,
                "e": rule.enabled,
            },
        )


def remove_access_rule(rule: KnowledgeAccessRule) -> bool:
    with _engine().begin() as conn:
        n = conn.execute(
            text(
                "DELETE FROM knowledge_access_rules "
                "WHERE knowledge_base_id = :k AND scope = :s "
                "AND target_id = :t"
            ),
            {
                "k": rule.knowledge_base_id,
                "s": rule.scope,
                "t": rule.target_id,
            },
        ).rowcount
    return bool(n)


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

    rules = _rules_for(knowledge_base_id)

    # 2. Règles user-specific
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
    """Knowledge bases accessibles à un utilisateur ( filtrage retrieval )."""
    accessible = []
    for kb in list_knowledge_bases():
        result = check_access(kb.id, user_id, group_ids, is_admin)
        if result.allowed:
            accessible.append(kb.id)
    return accessible


def grant_access(
    knowledge_base_id: str,
    scope: Literal["public", "group", "user"],
    target_id: str = "",
) -> bool:
    """Accorde l'accès à une knowledge base (§14)."""
    add_access_rule(
        KnowledgeAccessRule(
            knowledge_base_id=knowledge_base_id,
            scope=scope,
            target_id=target_id,
            enabled=True,
        )
    )
    return True


def revoke_access(
    knowledge_base_id: str,
    scope: Literal["public", "group", "user"],
    target_id: str = "",
) -> bool:
    """Révoque l'accès à une knowledge base (§14)."""
    return remove_access_rule(
        KnowledgeAccessRule(
            knowledge_base_id=knowledge_base_id,
            scope=scope,
            target_id=target_id,
            enabled=True,
        )
    )


def clear_all_rules() -> None:
    """Supprime toutes les règles (pour tests/reset)."""
    with _engine().begin() as conn:
        conn.execute(text("DELETE FROM knowledge_access_rules"))


def clear_rules_for_kb(kb_id: str) -> int:
    """Supprime uniquement les règles d'UNE knowledge base.

    Retourne le nombre de règles supprimées. Contrairement à
    clear_all_rules(), les autres KB ne sont pas affectées (§26 :
    isolation des données entre ressources).
    """
    with _engine().begin() as conn:
        n = conn.execute(
            text("DELETE FROM knowledge_access_rules WHERE knowledge_base_id = :k"),
            {"k": kb_id},
        ).rowcount
    return int(n or 0)


def list_rules_for_kb(kb_id: str) -> list[KnowledgeAccessRule]:
    """Liste les règles d'accès d'UNE knowledge base."""
    return _rules_for(kb_id)


def unregister_knowledge_base(kb_id: str) -> bool:
    """Retire une KB du registry. Retourne True si elle existait."""
    with _engine().begin() as conn:
        n = conn.execute(
            text("DELETE FROM knowledge_bases WHERE id = :i"),
            {"i": kb_id},
        ).rowcount
    return bool(n)


def clear_all_knowledge_bases() -> None:
    """Supprime toutes les KB enregistrées (pour tests/reset)."""
    with _engine().begin() as conn:
        conn.execute(text("DELETE FROM knowledge_bases"))


def is_corpus_restricted(subject_id: str) -> bool:
    """Le corpus d'une matière est-il restreint par une KB enregistrée ?

    Convention : une KB d'id = subject_id ( ex. 'python' ) restreint le
    corpus de cette matière. Aucune KB → corpus ouvert ( rétro-compat ).
    """
    return get_knowledge_base(subject_id) is not None


def ensure_acl_tables() -> None:
    """Crée les tables ACL si absentes ( usage direct hors init_schema )."""
    from app.infrastructure.database.schema import init_schema

    init_schema()


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
    "clear_rules_for_kb",
    "list_rules_for_kb",
    "unregister_knowledge_base",
    "clear_all_knowledge_bases",
    "is_corpus_restricted",
    "ensure_acl_tables",
]
