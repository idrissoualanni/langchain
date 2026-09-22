# Routes Admin Knowledge — CRUD pour Knowledge Access Control (§29)
#
# GET    /api/admin/knowledge              → liste toutes les KB
# POST   /api/admin/knowledge              → crée une KB
# PATCH  /api/admin/knowledge/{id}         → met à jour une KB
# DELETE /api/admin/knowledge/{id}         → supprime une KB
#
# GET    /api/admin/knowledge/{id}/access  → liste les accès d'une KB
# POST   /api/admin/knowledge/{id}/access  → accorde un accès
# DELETE /api/admin/knowledge/{id}/access  → révoque un accès
#
# Sécurité : réservé aux admins (vérification ADMIN_CLERK_IDS)
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Literal

from app.auth.resolver import CurrentUser, require_admin
from app.services.knowledge.resolver import (
    KnowledgeBaseInfo,
    KnowledgeAccessRule,
    AccessResult,
    register_knowledge_base,
    get_knowledge_base,
    list_knowledge_bases,
    add_access_rule,
    remove_access_rule,
    check_access,
    grant_access,
    revoke_access,
    clear_all_rules,
    clear_all_knowledge_bases,
    clear_rules_for_kb,
    list_rules_for_kb,
    unregister_knowledge_base,
)


router = APIRouter(prefix="/api/admin/knowledge", tags=["admin-knowledge"])


class KnowledgeBaseCreate(BaseModel):
    """Schéma de création d'une knowledge base."""
    
    id: str
    name: str
    description: str = ""
    subject_id: str = ""
    scope: Literal["public", "group", "user", "admin", "private"] = "private"
    owner_user_id: str = ""
    group_ids: list[str] = Field(default_factory=list)
    enabled: bool = True
    metadata: dict = Field(default_factory=dict)


class KnowledgeBaseUpdate(BaseModel):
    """Schéma de mise à jour partielle d'une knowledge base."""
    
    name: str | None = None
    description: str | None = None
    subject_id: str | None = None
    scope: Literal["public", "group", "user", "admin", "private"] | None = None
    owner_user_id: str | None = None
    group_ids: list[str] | None = None
    enabled: bool | None = None
    metadata: dict | None = None


class AccessGrantRequest(BaseModel):
    """Requête pour accorder un accès."""
    
    scope: Literal["public", "group", "user"]
    target_id: str = ""  # user_id ou group_id (vide si public)


class AccessRevokeRequest(BaseModel):
    """Requête pour révoquer un accès."""
    
    scope: Literal["public", "group", "user"]
    target_id: str = ""


class AccessRuleResponse(BaseModel):
    """Réponse pour une règle d'accès."""
    
    knowledge_base_id: str
    scope: Literal["public", "group", "user", "admin"]
    target_id: str
    enabled: bool


class KnowledgeBaseResponse(BaseModel):
    """Réponse pour une knowledge base."""
    
    id: str
    name: str
    description: str
    subject_id: str
    scope: Literal["public", "group", "user", "admin", "private"]
    owner_user_id: str
    group_ids: list[str]
    enabled: bool
    metadata: dict
    access_rules: list[AccessRuleResponse] = Field(default_factory=list)


class KnowledgeListResponse(BaseModel):
    """Réponse liste des knowledge bases."""
    
    knowledge_bases: list[KnowledgeBaseResponse]


@router.get("", response_model=KnowledgeListResponse)
def admin_list_knowledge(
    current_user: CurrentUser = Depends(require_admin),
) -> KnowledgeListResponse:
    """Liste toutes les knowledge bases (admin only)."""
    kbs = list_knowledge_bases()
    
    response_kbs = []
    for kb in kbs:
        # Récupérer les règles d'accès associées
        rules = _get_rules_for_kb(kb.id)
        response_kbs.append(KnowledgeBaseResponse(
            **kb.model_dump(),
            access_rules=rules,
        ))
    
    return KnowledgeListResponse(knowledge_bases=response_kbs)


@router.post("", response_model=KnowledgeBaseResponse, status_code=status.HTTP_201_CREATED)
def admin_create_knowledge(
    data: KnowledgeBaseCreate,
    current_user: CurrentUser = Depends(require_admin),
) -> KnowledgeBaseResponse:
    """Crée une nouvelle knowledge base (admin only)."""
    existing = get_knowledge_base(data.id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Knowledge base {data.id} already exists",
        )
    
    info = KnowledgeBaseInfo(**data.model_dump())
    register_knowledge_base(info)
    
    # Créer une règle par défaut selon le scope
    if data.scope == "public":
        grant_access(data.id, "public", "")
    elif data.scope == "user" and data.owner_user_id:
        grant_access(data.id, "user", data.owner_user_id)
    elif data.scope == "group" and data.group_ids:
        for group_id in data.group_ids:
            grant_access(data.id, "group", group_id)
    
    rules = _get_rules_for_kb(data.id)
    return KnowledgeBaseResponse(**info.model_dump(), access_rules=rules)


@router.patch("/{kb_id}", response_model=KnowledgeBaseResponse)
def admin_update_knowledge(
    kb_id: str,
    data: KnowledgeBaseUpdate,
    current_user: CurrentUser = Depends(require_admin),
) -> KnowledgeBaseResponse:
    """Met à jour une knowledge base existante (admin only)."""
    kb = get_knowledge_base(kb_id)
    if not kb:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Knowledge base {kb_id} not found",
        )
    
    update_data = data.model_dump(exclude_unset=True)
    updated_info = kb.model_copy(update=update_data)
    register_knowledge_base(updated_info)
    
    rules = _get_rules_for_kb(kb_id)
    return KnowledgeBaseResponse(**updated_info.model_dump(), access_rules=rules)


@router.delete("/{kb_id}")
def admin_delete_knowledge(
    kb_id: str,
    current_user: CurrentUser = Depends(require_admin),
) -> dict:
    """Supprime une knowledge base (admin only).

    Scope STRICTEMENT la KB ciblée : on supprime ses règles d'accès
    et on la retire du registry, sans toucher aux autres KB
    ( clear_all_rules() effaçait TOUT — bug d'isolation §26 ).
    """
    kb = get_knowledge_base(kb_id)
    if not kb:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Knowledge base {kb_id} not found",
        )

    removed_rules = clear_rules_for_kb(kb_id)
    unregister_knowledge_base(kb_id)

    return {"success": True, "deleted": kb_id, "removed_access_rules": removed_rules}


@router.get("/{kb_id}/access")
def admin_get_knowledge_access(
    kb_id: str,
    current_user: CurrentUser = Depends(require_admin),
) -> list[AccessRuleResponse]:
    """Liste les règles d'accès d'une knowledge base (admin only)."""
    kb = get_knowledge_base(kb_id)
    if not kb:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Knowledge base {kb_id} not found",
        )
    
    return _get_rules_for_kb(kb_id)


@router.post("/{kb_id}/access", response_model=AccessRuleResponse)
def admin_grant_knowledge_access(
    kb_id: str,
    data: AccessGrantRequest,
    current_user: CurrentUser = Depends(require_admin),
) -> AccessRuleResponse:
    """Accorde un accès à une knowledge base (admin only)."""
    kb = get_knowledge_base(kb_id)
    if not kb:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Knowledge base {kb_id} not found",
        )
    
    grant_access(kb_id, data.scope, data.target_id)
    
    rule = KnowledgeAccessRule(
        knowledge_base_id=kb_id,
        scope=data.scope,
        target_id=data.target_id,
        enabled=True,
    )
    return AccessRuleResponse(**rule.model_dump())


@router.delete("/{kb_id}/access")
def admin_revoke_knowledge_access(
    kb_id: str,
    data: AccessRevokeRequest,
    current_user: CurrentUser = Depends(require_admin),
) -> dict:
    """Révoque un accès d'une knowledge base (admin only)."""
    kb = get_knowledge_base(kb_id)
    if not kb:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Knowledge base {kb_id} not found",
        )
    
    success = revoke_access(kb_id, data.scope, data.target_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Access rule not found for {kb_id}",
        )
    
    return {"success": True, "revoked": {"scope": data.scope, "target_id": data.target_id}}


def _get_rules_for_kb(kb_id: str) -> list[AccessRuleResponse]:
    """Helper pour récupérer les règles d'accès d'une KB."""
    return [
        AccessRuleResponse(**rule.model_dump())
        for rule in list_rules_for_kb(kb_id)
    ]


__all__ = ["router"]
