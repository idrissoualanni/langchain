from __future__ import annotations
from typing import Annotated
from langchain_core.tools import tool
from langchain.tools import InjectedState
from langgraph.types import Command
from langchain_core.messages import ToolMessage

from app.repositories import exercises

@tool
def search_exercise_library(
    subject: str,
    topic: str,
) -> Command:
    """Recherche des exercices existants, validés et efficaces dans la 
    bibliothèque pédagogique pour un sujet donné.
    
    Utilise-le AVANT de générer un nouvel exercice avec create_exercise 
    pour éviter les répétitions et privilégier les contenus ayant un 
    taux de réussite élevé.
    
    Args:
        subject: id de la matière (ex: "python").
        topic: le topic recherché (ex: "boucles").
    """
    exos = exercises.search_exercises(subject, topic)
    
    if not exos:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=f"Aucun exercice validé trouvé dans la bibliothèque pour {subject}/{topic}. "
                                 f"Tu peux en générer un nouveau avec create_exercise.",
                        tool_call_id="", # tool_call_id handled by harness
                    )
                ]
            }
        )
    
    content = (
        f"EXERCICES TROUVÉS DANS LA BIBLIOTHÈQUE — {subject}/{topic}\n\n"
        f"Voici les exercices les plus efficaces :\n"
        + "\n\n".join([
            f"Exo ID {e['id']} (Diff: {e['difficulty']}, Succès: {e['success_rate']*100:.0f}%):\n{e['content']}"
            for e in exos
        ])
        + "\n\nCOMPORTEMENT : Choisis l'un de ces exercices pour l'étudiant. "
        + "L'exercice est déjà structuré, utilise-le tel quel. "
        + "N'oublie pas de mettre le thread en 'waiting_for_answer' "
        + "comme pour create_exercise."
    )
    
    return Command(
        update={
            "messages": [
                ToolMessage(content=content, tool_call_id="")
            ]
        }
    )
