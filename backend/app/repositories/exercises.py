from __future__ import annotations
from sqlalchemy import text
from app.infrastructure.database.connections import get_conn

def search_exercises(subject_id: str, topic_slug: str, limit: int = 5) -> list[dict]:
    """Recherche des exercices validés et efficaces dans la bibliothèque."""
    conn = get_conn()
    rows = conn.execute(
        text("""
            SELECT id, content, success_rate, difficulty 
            FROM exercise_library 
            WHERE subject_id = :sid 
              AND topic_slug = :topic 
              AND is_validated = TRUE 
            ORDER BY success_rate DESC 
            LIMIT :limit
        """),
        {"sid": subject_id, "topic": topic_slug, "limit": limit}
    ).fetchall()
    
    return [
        {
            "id": r[0],
            "content": r[1],
            "success_rate": r[2],
            "difficulty": r[3]
        }
        for r in rows
    ]

def save_exercise(subject_id: str, topic_slug: str, difficulty: str, content: str) -> str:
    """Enregistre un nouvel exercice dans la bibliothèque."""
    conn = get_conn()
    res = conn.execute(
        text("""
            INSERT INTO exercise_library (subject_id, topic_slug, difficulty, content)
            VALUES (:sid, :topic, :diff, :cont)
            RETURNING id
        """),
        {"sid": subject_id, "topic": topic_slug, "diff": difficulty, "cont": content}
    ).fetchone()
    return res[0] if res else ""

def update_exercise_stats(exercise_id: str, success: bool) -> None:
    """Met à jour le taux de réussite d'un exercice."""
    conn = get_conn()
    # On utilise une moyenne mobile simple ou incrémentale
    # Ici, on simplifie pour l'exemple, mais on pourrait stocker total_attempts
    conn.execute(
        text("""
            UPDATE exercise_library 
            SET success_rate = (success_rate * 0.9) + (CASE WHEN :success THEN 0.1 ELSE 0 END),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :id
        """),
        {"success": success, "id": exercise_id}
    )

def validate_exercise(exercise_id: str) -> None:
    """Marque un exercice comme validé."""
    conn = get_conn()
    conn.execute(
        text("UPDATE exercise_library SET is_validated = TRUE WHERE id = :id"),
        {"id": exercise_id}
    )
