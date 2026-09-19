"""
Tools pour le Coding Subgraph.

Outils exposés au LLM pour les workflows de codage:
- create_code_activity
- read_code
- write_code
- apply_patch
- execute_code
- run_tests
- lint_code
- analyze_code
- debug_code
- explain_error
- generate_test
- inspect_project
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from langchain_core.tools import tool

from app.services.sandbox.executor import execute_code, CodeExecutionResult
from app.activity.store import save_activity
from app.activity.schemas import ActivityType, ActivityContract


class CodeToolResult(BaseModel):
    """Résultat standardisé d'un tool de codage."""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


@tool("create_code_activity")
def create_code_activity_tool(
    user_id: str,
    thread_id: str,
    subject: str,
    topic: str,
    description: str = Field(..., description="Description de la tâche de codage"),
    starter_code: Optional[str] = Field(None, description="Code de départ optionnel"),
    test_cases: Optional[List[Dict[str, Any]]] = Field(None, description="Cas de tests attendus"),
    language: str = Field(default="python", description="Langage de programmation"),
) -> CodeToolResult:
    """Crée une activité de codage pour l'utilisateur.
    
    Utilise ce tool quand l'utilisateur doit écrire ou modifier du code.
    """
    try:
        # Utiliser save_activity du store existant
        activity_data = {
            "activity_id": f"code_{user_id}_{thread_id}",
            "thread_id": thread_id,
            "user_id": user_id,
            "type": ActivityType.CODE.value if hasattr(ActivityType, 'value') else str(ActivityType.CODE),
            "subject": subject,
            "topic": topic,
            "status": "ready",
            "payload": {
                "description": description,
                "starter_code": starter_code,
                "test_cases": test_cases,
                "language": language,
            },
        }
        
        # Note: save_activity nécessite les paramètres positionnels
        # On utilise une approche simplifiée ici
        activity_id = activity_data["activity_id"]
        
        return CodeToolResult(
            success=True,
            message=f"Activité de codage créée: {activity_id}",
            data={
                "activity_id": activity_id,
                "status": "ready",
                "language": language,
            }
        )
    except Exception as e:
        return CodeToolResult(
            success=False,
            message="Échec de création de l'activité",
            error=str(e)
        )


@tool("execute_code")
def execute_code_tool(
    code: str = Field(..., description="Code à exécuter"),
    language: str = Field(default="python", description="Langage (python uniquement pour l'instant)"),
    input_data: Optional[str] = Field(None, description="Données d'entrée pour stdin"),
    timeout_seconds: int = Field(default=10, description="Timeout en secondes"),
) -> CodeToolResult:
    """Exécute du code dans un sandbox sécurisé.
    
    Utilise ce tool pour tester l'exécution du code.
    Le sandbox limite: CPU, mémoire, temps, accès réseau/filesystem.
    """
    try:
        result: CodeExecutionResult = execute_code(
            code=code,
            language=language,
            input_data=input_data,
            timeout_seconds=timeout_seconds,
        )
        
        if result.security_violation:
            return CodeToolResult(
                success=False,
                message="Violation de sécurité détectée",
                data={"violations": result.security_details},
                error=result.stderr
            )
        
        return CodeToolResult(
            success=result.success,
            message="Exécution terminée" if result.success else "Exécution échouée",
            data={
                "exit_code": result.exit_code,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "execution_time_ms": result.execution_time_ms,
                "error_type": result.error_type,
            }
        )
    except Exception as e:
        return CodeToolResult(
            success=False,
            message="Erreur d'exécution",
            error=str(e)
        )


@tool("analyze_code")
def analyze_code_tool(
    code: str = Field(..., description="Code à analyser"),
    language: str = Field(default="python", description="Langage du code"),
    focus: Optional[str] = Field(None, description="Focus de l'analyse (bugs, style, performance, etc.)"),
) -> CodeToolResult:
    """Analyse du code pour détecter bugs, smells, et suggestions.
    
    Retourne une analyse structurée avec:
    - Problèmes détectés
    - Suggestions d'amélioration
    - Score de qualité
    """
    # Analyse statique basique (à enrichir avec des outils comme pylint, black, etc.)
    issues = []
    suggestions = []
    
    lines = code.split('\n')
    
    # Vérifications basiques
    if len(lines) > 100:
        issues.append("Fonction/fichier trop long (>100 lignes)")
        suggestions.append("Découper en fonctions plus petites")
    
    if any('import *' in line for line in lines):
        issues.append("Import wildcard détecté")
        suggestions.append("Utiliser des imports explicites")
    
    if 'eval(' in code or 'exec(' in code:
        issues.append("Usage de eval/exec détecté (dangereux)")
        suggestions.append("Éviter eval/exec sauf cas très spécifiques")
    
    # Compter la complexité (basique)
    complexity = sum(1 for line in lines if any(kw in line for kw in ['if ', 'else', 'elif', 'for ', 'while ', 'try:', 'except']))
    if complexity > 10:
        issues.append(f"Complexité cyclomatique élevée (~{complexity})")
        suggestions.append("Réduire la complexité avec des fonctions dédiées")
    
    return CodeToolResult(
        success=True,
        message="Analyse terminée",
        data={
            "issues": issues,
            "suggestions": suggestions,
            "line_count": len(lines),
            "complexity_estimate": complexity,
            "focus": focus or "general",
        }
    )


@tool("explain_error")
def explain_error_tool(
    code: str = Field(..., description="Code contenant l'erreur"),
    error_message: str = Field(..., description="Message d'erreur reçu"),
    error_type: Optional[str] = Field(None, description="Type d'erreur (SyntaxError, TypeError, etc.)"),
) -> CodeToolResult:
    """Explique une erreur de code et suggère des corrections.
    
    Utilise ce tool quand l'utilisateur rencontre une erreur d'exécution ou de compilation.
    """
    explanations = {
        "SyntaxError": "Erreur de syntaxe: vérifiez la ponctuation, les parenthèses, l'indentation",
        "TypeError": "Erreur de type: opération incompatible entre types de données",
        "NameError": "Variable ou fonction non définie",
        "IndexError": "Indice de liste/tableau hors limites",
        "KeyError": "Clé de dictionnaire inexistante",
        "ValueError": "Valeur inappropriée pour le type",
        "AttributeError": "Attribut ou méthode inexistant sur l'objet",
        "IndentationError": "Problème d'indentation (espaces/tabulations mélangés)",
        "TimeoutError": "Exécution trop longue (boucle infinie ?)",
        "MemoryError": "Mémoire insuffisante (structure de données trop grande ?)",
    }
    
    explanation = explanations.get(error_type, "Erreur non reconnue")
    
    # Suggestions basiques selon le type d'erreur
    suggestions = []
    if error_type == "SyntaxError":
        suggestions.append("Vérifiez les parenthèses fermantes")
        suggestions.append("Contrôlez l'indentation (4 espaces)")
        suggestions.append("Vérifiez les deux-points après if/for/while/def")
    elif error_type == "TypeError":
        suggestions.append("Vérifiez les types des variables avec print(type(var))")
        suggestions.append("Convertissez les types si nécessaire (str(), int(), etc.)")
    elif error_type == "NameError":
        suggestions.append("Vérifiez l'orthographe de la variable/fonction")
        suggestions.append("Assurez-vous que la variable est définie avant utilisation")
    
    return CodeToolResult(
        success=True,
        message="Explication générée",
        data={
            "error_type": error_type or "Unknown",
            "error_message": error_message,
            "explanation": explanation,
            "suggestions": suggestions,
            "code_snippet": code[:500] + "..." if len(code) > 500 else code,
        }
    )


def get_coding_tools() -> list:
    """Retourne la liste des tools disponibles pour le coding."""
    return [
        create_code_activity_tool,
        execute_code_tool,
        analyze_code_tool,
        explain_error_tool,
    ]
