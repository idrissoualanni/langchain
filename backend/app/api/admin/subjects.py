# Routes Admin Subjects — configuration des matières ( définitions YAML ).
#
# Les définitions de matières vivent dans Neon ( subject_definitions ) :
# plus aucun YAML préconfiguré dans le dépôt. Ces routes permettent à
# l'admin de les LIRE, les ÉDITER ( YAML validé par SubjectConfig ) et
# les supprimer — le registry se recharge immédiatement.
#
# GET    /api/admin/subjects               → liste ( id, nom, sha, maj )
# GET    /api/admin/subjects/{id}/definition → YAML brut
# PUT    /api/admin/subjects/{id}/definition → remplace le YAML ( validé )
# DELETE /api/admin/subjects/{id}/definition → retire la matière
#
# Sécurité : réservé aux admins ( vérification ADMIN_CLERK_IDS ).
from __future__ import annotations

import hashlib
import time

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth.resolver import CurrentUser, require_admin
from app.logging.events import log_event
from app.services.knowledge import store as knowledge_store

router = APIRouter(prefix="/api/admin/subjects", tags=["admin-subjects"])


class DefinitionPutRequest(BaseModel):
    """Remplacement du YAML d'une matière — validé avant écriture."""

    yaml: str = Field(min_length=1)


def _parse_yaml(yaml_text: str) -> dict:
    """Parse + valide le YAML contre SubjectConfig ( import tardif :
    le registry importe ce module transitivement, éviter un cycle )."""
    import yaml as pyyaml

    from app.schemas.subject import SubjectConfig

    try:
        data = pyyaml.safe_load(yaml_text) or {}
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"YAML invalide : {exc}",
        )
    if not isinstance(data, dict) or not data.get("id"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Le YAML doit contenir au moins un champ 'id'",
        )
    try:
        SubjectConfig.from_dict(data)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Configuration de matière invalide : {exc}",
        )
    return data


@router.get("")
def admin_list_subject_definitions(
    current_user: CurrentUser = Depends(require_admin),
) -> dict:
    """Liste des définitions de matières stockées dans Neon."""
    from app.schemas.subject import SubjectConfig

    raw = knowledge_store.load_subject_definitions()
    subjects = []
    for subject_id, yaml_text in sorted(raw.items()):
        name = subject_id
        try:
            data = __import__("yaml").safe_load(yaml_text) or {}
            name = data.get("name") or subject_id
            SubjectConfig.from_dict(data)
            valid = True
        except Exception:  # noqa: BLE001
            valid = False
        subjects.append(
            {
                "subject_id": subject_id,
                "name": name,
                "valid": valid,
            }
        )
    return {"subjects": subjects, "total": len(subjects)}


@router.get("/{subject_id}/definition")
def admin_get_subject_definition(
    subject_id: str,
    current_user: CurrentUser = Depends(require_admin),
) -> dict:
    """YAML brut d'une matière."""
    raw = knowledge_store.load_subject_definitions()
    if subject_id not in raw:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Matière {subject_id} introuvable",
        )
    return {"subject_id": subject_id, "yaml": raw[subject_id]}


@router.put("/{subject_id}/definition")
def admin_put_subject_definition(
    subject_id: str,
    data: DefinitionPutRequest,
    current_user: CurrentUser = Depends(require_admin),
) -> dict:
    """Crée / remplace la définition YAML ( validée ) d'une matière.

    Le registry est invalidé : la matière est effective immédiatement
    ( au prochain load_registry ) sans redémarrage.
    """
    parsed = _parse_yaml(data.yaml)
    if parsed["id"] != subject_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Le champ 'id' du YAML ({parsed['id']}) doit correspondre "
                f"à l'URL ({subject_id})"
            ),
        )
    written = knowledge_store.upsert_subject_definition(subject_id, data.yaml)

    from app.subjects import registry

    registry.invalidate()
    log_event(
        "ADMIN_SUBJECT_DEFINITION_PUT",
        message=f"Définition matière mise à jour | {subject_id}",
        extra={"operation": "admin_subject_put", "subject": subject_id},
    )
    return {
        "success": True,
        "subject_id": subject_id,
        "written": written,
        "sha256": hashlib.sha256(data.yaml.encode("utf-8")).hexdigest()[:12],
    }


@router.delete("/{subject_id}/definition")
def admin_delete_subject_definition(
    subject_id: str,
    current_user: CurrentUser = Depends(require_admin),
) -> dict:
    """Retire une matière du registry ( les sections knowledge Neon
    restent en place — ré-importable en re-seedant le YAML )."""
    raw = knowledge_store.load_subject_definitions()
    if subject_id not in raw:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Matière {subject_id} introuvable",
        )
    from sqlalchemy import create_engine, text

    from app.infrastructure.database.persistence import _postgres_url

    with create_engine(_postgres_url(), pool_pre_ping=True).begin() as conn:
        conn.execute(
            text("DELETE FROM subject_definitions WHERE subject_id = :s"),
            {"s": subject_id},
        )

    from app.subjects import registry

    registry.invalidate()
    log_event(
        "ADMIN_SUBJECT_DEFINITION_DELETED",
        message=f"Définition matière supprimée | {subject_id}",
        extra={"operation": "admin_subject_delete", "subject": subject_id},
    )
    return {"success": True, "deleted": subject_id}


__all__ = ["router"]
