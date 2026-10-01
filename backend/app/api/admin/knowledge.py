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
# Sécurité : réservé aux admins (vérification ADMIN_EXTERNAL_IDS)
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from pydantic import BaseModel, Field
from typing import Literal

from app.auth.resolver import CurrentUser, require_admin
from app.core.rate_limit import limiter
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


# ==================================================================
# CONTENU du corpus — Neon knowledge_sections ( vectorisé à l'écriture )
#
# Le corpus de cours vit DANS Neon ( mission : aucune base de
# connaissance codée en dur dans le projet ). Ces routes permettent
# d'AJOUTER / lister / supprimer des sections depuis l'admin : chaque
# section est embeddée par le provider actif ( embeddings.yaml ) au
# moment de l'écriture — la recherche sémantique la voit immédiatement.
# ==================================================================

from pydantic import ConfigDict  # noqa: E402

from app.services.knowledge import store as knowledge_store  # noqa: E402


class SectionUpsertRequest(BaseModel):
    """Création/remplacement d'une section de cours."""

    model_config = ConfigDict(extra="forbid")

    subject_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)
    source_label: str | None = Field(default=None, max_length=200)


class SectionUpsertResponse(BaseModel):
    id: int
    subject_id: str
    topic_slug: str
    title: str
    embedded: bool


class SectionListResponse(BaseModel):
    sections: list[dict]
    total: int


@router.get("/content", response_model=SectionListResponse)
def admin_list_sections(
    subject_id: str | None = None,
    current_user: CurrentUser = Depends(require_admin),
) -> SectionListResponse:
    """Inventaire des sections du corpus ( sans les vecteurs )."""
    sections = knowledge_store.list_sections(subject_id)
    return SectionListResponse(sections=sections, total=len(sections))


@router.post(
    "/content",
    response_model=SectionUpsertResponse,
    status_code=status.HTTP_201_CREATED,
)
def admin_upsert_section(
    data: SectionUpsertRequest,
    current_user: CurrentUser = Depends(require_admin),
) -> SectionUpsertResponse:
    """Ajoute ( ou remplace ) une section — vectorisée à l'écriture.

    Erreurs explicites : titre invalide, contenu vide, provider
    d'embedding KO ( on n'insère jamais de section sans vecteur ).
    """
    try:
        result = knowledge_store.upsert_section(
            subject_id=data.subject_id,
            title=data.title,
            content=data.content,
            source_label=data.source_label,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"Vectorisation impossible ( provider d'embedding ou "
                f"base injoignable ) : {exc}"
            ),
        )
    return SectionUpsertResponse(**result)


@router.delete("/content/{section_id}")
def admin_delete_section(
    section_id: int,
    current_user: CurrentUser = Depends(require_admin),
) -> dict:
    """Supprime une section du corpus par id."""
    if not knowledge_store.delete_section(section_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Section {section_id} introuvable",
        )
    return {"success": True, "deleted": section_id}


# ==================================================================
# UPLOAD DE FICHIERS — parsing Markdown/texte → sections vectorisées
# ==================================================================

from fastapi import File, UploadFile
import re
import unicodedata
import hashlib
import time


def _strip_accents(value: str) -> str:
    """Retire les accents — identique au découpage d'indexation."""
    return "".join(
        c
        for c in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(c)
    )


def _split_sections(content: str) -> list[tuple[str, str, str]]:
    """[(topic_slug, title_brut, contenu)] — découpe sur « ## Titre »."""
    sections: list[tuple[str, str, str]] = []
    current_topic = "_intro"
    current_title = "(introduction)"
    current_lines: list[str] = []
    for line in content.splitlines():
        m = re.match(r"^##\s+(.+)$", line)
        if m:
            if current_lines:
                sections.append(
                    (current_topic, current_title, "\n".join(current_lines).strip())
                )
            current_title = m.group(1).strip()
            current_topic = _strip_accents(current_title.lower())
            current_lines = []
        else:
            current_lines.append(line)
    if current_lines:
        sections.append(
            (current_topic, current_title, "\n".join(current_lines).strip())
        )
    return [(t, ti, c) for t, ti, c in sections if c]


def _subject_for_path(path: str, definitions: dict[str, str]) -> str:
    """Résout le subject_id depuis le chemin du fichier.

    Stratégie : mapping YAML knowledge.sources → subject_id ;
    repli : premier segment du chemin ( ex: "informatique/python" → "informatique" ).
    """
    path_no_ext = path.removesuffix(".md")
    if path_no_ext in definitions:
        return definitions[path_no_ext]
    # Repli : premier segment du chemin
    return path_no_ext.split("/")[0] if path_no_ext else "general"


# Cache des définitions YAML ( rechargé à chaque upload si nécessaire )
async def _load_definitions_map() -> dict[str, str]:
    from app.services.knowledge.store import load_subject_definitions
    mapping: dict[str, str] = {}
    definitions = load_subject_definitions()
    for sid, yaml_text in definitions.items():
        try:
            import yaml
            data = yaml.safe_load(yaml_text) or {}
        except Exception:
            continue
        for src in (data.get("knowledge") or {}).get("sources", []):
            mapping[str(src)] = sid
    return mapping


class FileUploadRequest(BaseModel):
    """Métadonnées optionnelles pour l'upload ( le fichier vient dans multipart )."""
    subject_id: str | None = None
    source_label: str | None = None


class FileUploadResponse(BaseModel):
    file_path: str
    subject_id: str
    sections_created: int
    sections: list[dict]


@router.post(
    "/upload",
    response_model=FileUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("10/minute")
async def admin_upload_knowledge_file(
    request: Request,
    # `response` requis par le décorateur slowapi ( injection headers ),
    # cf. commentaire dans api/chat.py.
    response: Response,
    file: UploadFile = File(...),
    subject_id: str | None = None,
    source_label: str | None = None,
    current_user: CurrentUser = Depends(require_admin),
) -> FileUploadResponse:
    """Upload un fichier ( .md / .txt ) → parsing sections + vectorisation.

    - Le fichier est stocké dans le bucket `knowledge_files` ( Neon )
    - Chaque section « ## Titre » devient une entrée dans `knowledge_sections`
      avec embedding ( recherche sémantique immédiate )
    - Si subject_id n'est pas fourni, il est déduit du chemin / définitions YAML
    """
    # --- Validation type de fichier ---
    allowed_ct = {"text/markdown", "text/plain", "text/x-markdown"}
    filename = file.filename or "upload.md"
    if file.content_type not in allowed_ct and not filename.endswith((".md", ".txt")):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Type de fichier non supporté ( .md ou .txt uniquement )",
        )

    # --- Lecture contenu ---
    content_bytes = await file.read()
    try:
        content = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Fichier non-UTF-8",
        )

    if not content.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Fichier vide",
        )

    # --- Stockage dans le bucket knowledge_files ---
    sha = hashlib.sha256(content_bytes).hexdigest()
    file_path = filename
    from app.services.knowledge.store import put_file
    put_file(file_path, subject_id or "auto", content)

    # --- Résolution subject_id ---
    resolved_subject = subject_id
    if not resolved_subject:
        definitions_map = await _load_definitions_map()
        resolved_subject = _subject_for_path(file_path, definitions_map)

    # --- Parsing en sections + upsert ( vectorisation ) ---
    created_sections = []
    for topic_slug, title, section_content in _split_sections(content):
        if not section_content.strip():
            continue
        try:
            result = knowledge_store.upsert_section(
                subject_id=resolved_subject,
                title=title,
                content=section_content,
                source_label=source_label or f"upload/{file_path}",
            )
            created_sections.append({
                "id": result["id"],
                "topic_slug": result["topic_slug"],
                "title": result["title"],
            })
        except Exception as exc:
            # On log mais on continue pour les autres sections
            log_event(
                "KNOWLEDGE_UPLOAD_SECTION_FAILED",
                level="WARNING",
                message=f"Section upload failed: {topic_slug} ({exc})",
                extra={"file": file_path, "topic": topic_slug},
            )

    return FileUploadResponse(
        file_path=file_path,
        subject_id=resolved_subject,
        sections_created=len(created_sections),
        sections=created_sections,
    )


# ==================================================================
# LISTE / PREVIEW des fichiers du bucket knowledge_files
# ==================================================================

from app.services.knowledge.store import list_files, get_file  # noqa: E402


class FilePreviewResponse(BaseModel):
    path: str
    subject_id: str
    sha256: str
    created_at: str
    content_preview: str
    size_bytes: int


@router.get("/files", response_model=list[FilePreviewResponse])
def admin_list_knowledge_files(
    subject_id: str | None = None,
    current_user: CurrentUser = Depends(require_admin),
) -> list[FilePreviewResponse]:
    """Liste les fichiers sources du bucket ( sans le contenu complet )."""
    files = list_files(subject_id)
    return [
        FilePreviewResponse(
            path=f["path"],
            subject_id=f["subject_id"],
            sha256=f["sha256"],
            created_at=f["created_at"],
            content_preview="",
            size_bytes=0,
        )
        for f in files
    ]


@router.get("/files/{file_path:path}", response_model=FilePreviewResponse)
def admin_get_knowledge_file(
    file_path: str,
    current_user: CurrentUser = Depends(require_admin),
) -> FilePreviewResponse:
    """Récupère un fichier avec son contenu ( pour preview )."""
    content = get_file(file_path)
    if content is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Fichier {file_path} introuvable",
        )
    return FilePreviewResponse(
        path=file_path,
        subject_id="",
        sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        created_at="",
        content_preview=content[:2000],
        size_bytes=len(content.encode("utf-8")),
    )


__all__ = ["router"]
