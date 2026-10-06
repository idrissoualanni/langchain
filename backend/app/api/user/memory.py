from fastapi import APIRouter, Depends, HTTPException
from fastapi import Body
from typing import Any, Dict
from app.auth.resolver import CurrentUser, get_current_user
from app.services.memory.cognitive_store import cognitive_store

router = APIRouter(prefix="/api/user/memory", tags=["user-memory"])

@router.get("/learning-map")
async def get_learning_map(current: CurrentUser = Depends(get_current_user)):
    """
    Retrieves the user's current mastery graph of concepts and their dependencies.
    """
    try:
        graph = cognitive_store.get_user_learning_graph(current.user_id)
        return graph
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving learning map: {str(e)}")

@router.post("/learning-map/update")
async def update_mastery(
    payload: Dict[str, Any] = Body(...),
    current: CurrentUser = Depends(get_current_user)
):
    """
    Updates the mastery level of a specific concept.
    Payload: {"concept_slug": "string", "level": float (0.0 to 1.0)}
    """
    concept_slug = payload.get("concept_slug")
    level = payload.get("level")

    if not concept_slug or level is None:
        raise HTTPException(status_code=400, detail="Missing concept_slug or level")

    if not (0.0 <= level <= 1.0):
        raise HTTPException(status_code=400, detail="Level must be between 0.0 and 1.0")

    try:
        cognitive_store.update_concept_mastery(current.user_id, concept_slug, level)
        return {"status": "success", "message": f"Updated {concept_slug} to {level}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating mastery: {str(e)}")
