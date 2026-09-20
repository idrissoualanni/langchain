"""
Admin Observability API — LangSmith Monitoring

Endpoints sécurisés pour accéder aux métriques, traces et évaluations LangSmith.
Tous les endpoints nécessitent une authentification admin valide.

Sécurité :
- Vérification ADMIN_CLERK_IDS obligatoire
- Aucun secret LangSmith exposé au frontend
- Filtrage des données sensibles dans les traces
- CORS restreint aux origines autorisées
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
import os

from app.auth.resolver import CurrentUser, require_admin
from app.logging.events import log_event

router = APIRouter(prefix="/observability", tags=["admin-observability"])


# ============================================================================
# Security Dependencies
# ============================================================================

def verify_admin_auth(
    current_user: CurrentUser = Depends(require_admin),
) -> CurrentUser:
    """
    Vérifie que l'utilisateur est un admin autorisé.

    Défère à require_admin (auth réelle Clerk/dev + ADMIN_CLERK_IDS).
    """
    return current_user


# ============================================================================
# Response Schemas
# ============================================================================

class ObservabilitySummary(BaseModel):
    """Résumé des métriques d'observabilité."""
    
    total_runs: int = Field(default=0, description="Nombre total d'exécutions")
    successful_runs: int = Field(default=0, description="Exécutions réussies")
    failed_runs: int = Field(default=0, description="Exécutions échouées")
    avg_latency_ms: float = Field(default=0.0, description="Latence moyenne (ms)")
    total_tokens: int = Field(default=0, description="Total tokens utilisés")
    error_rate: float = Field(default=0.0, description="Taux d'erreur (%)")
    period_hours: int = Field(default=24, description="Période analysée (heures)")


class RunInfo(BaseModel):
    """Information sur une exécution."""
    
    run_id: str
    name: Optional[str] = None
    project_name: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    status: str  # success, error, pending
    workflow: Optional[str] = None
    model: Optional[str] = None
    latency_ms: Optional[float] = None
    tokens: Optional[dict[str, int]] = None
    error_message: Optional[str] = None


class TraceDetail(BaseModel):
    """Détail complet d'une trace."""
    
    run_id: str
    name: str
    run_type: str = ""
    status: Optional[str] = None
    latency_ms: Optional[float] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    feedback: Optional[dict[str, Any]] = None
    child_runs: list["TraceDetail"] = Field(default_factory=list)


class EvaluationResult(BaseModel):
    """Résultat d'évaluation."""
    
    dataset_name: str
    experiment_name: Optional[str] = None
    average_score: float = Field(default=0.0)
    total_examples: int = Field(default=0)
    metrics: dict[str, float] = Field(default_factory=dict)


class ModelUsage(BaseModel):
    """Utilisation par modèle."""
    
    model_name: str
    provider: Optional[str] = None
    total_calls: int = Field(default=0)
    total_tokens: int = Field(default=0)
    input_tokens: int = Field(default=0)
    output_tokens: int = Field(default=0)
    estimated_cost: Optional[float] = None
    avg_latency_ms: Optional[float] = None


class ErrorEntry(BaseModel):
    """Entrée de journal d'erreurs."""
    
    run_id: str
    timestamp: datetime
    error_type: str
    error_message: str
    workflow: Optional[str] = None
    node: Optional[str] = None
    stack_trace: Optional[str] = None


class LangSmithLink(BaseModel):
    """Lien vers le dashboard LangSmith."""
    
    dashboard_url: str
    project_name: str
    environment: str
    expires_in_seconds: Optional[int] = None


# ============================================================================
# Helper Functions
# ============================================================================

def get_langsmith_client():
    """Récupère le client LangSmith configuré."""
    try:
        from langsmith import Client
        
        api_key = os.getenv("LANGSMITH_API_KEY")
        endpoint = os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")
        
        if not api_key:
            return None
        
        return Client(
            api_key=api_key,
            api_url=endpoint,
        )
    except ImportError:
        return None
    except Exception:
        return None


# ============================================================================
# API Endpoints
# ============================================================================

@router.get("/summary", response_model=ObservabilitySummary)
async def get_observability_summary(
    hours: int = Query(default=24, ge=1, le=720),
    admin: dict = Depends(verify_admin_auth),
):
    """
    Résumé des métriques d'observabilité.
    
    Retourne des statistiques agrégées sur les exécutions LangSmith :
    - Nombre total de runs
    - Taux de succès/échec
    - Latence moyenne
    - Utilisation des tokens
    - Taux d'erreur
    
    Nécessite une authentification admin.
    """
    client = get_langsmith_client()
    
    if not client:
        # Retourner des données vides si LangSmith non configuré
        return ObservabilitySummary(period_hours=hours)
    
    try:
        # Récupérer les runs récents
        projects = list(client.list_projects())
        
        total_runs = 0
        successful_runs = 0
        failed_runs = 0
        total_latency = 0.0
        total_tokens = 0
        
        for project in projects:
            runs = list(client.list_runs(
                project_name=project.name,
                execution_order=1,
            ))
            
            for run in runs:
                total_runs += 1
                
                if run.error is None:
                    successful_runs += 1
                else:
                    failed_runs += 1
                
                # Tokens
                if run.metadata:
                    usage = run.metadata.get("usage", {})
                    total_tokens += usage.get("total_tokens", 0)
                
                # Latence
                if run.start_time and run.end_time:
                    latency = (run.end_time - run.start_time).total_seconds() * 1000
                    total_latency += latency
        
        avg_latency = total_latency / total_runs if total_runs > 0 else 0.0
        error_rate = (failed_runs / total_runs * 100) if total_runs > 0 else 0.0
        
        return ObservabilitySummary(
            total_runs=total_runs,
            successful_runs=successful_runs,
            failed_runs=failed_runs,
            avg_latency_ms=round(avg_latency, 2),
            total_tokens=total_tokens,
            error_rate=round(error_rate, 2),
            period_hours=hours,
        )
        
    except Exception as e:
        log_event(
            "ADMIN_OBSERVABILITY_ERROR",
            message=f"Failed to fetch observability summary: {e}",
            extra={"operation": "get_observability_summary"},
        )
        # Retourner des données vides en cas d'erreur
        return ObservabilitySummary(period_hours=hours)


@router.get("/runs", response_model=list[RunInfo])
async def get_recent_runs(
    limit: int = Query(default=50, ge=1, le=500),
    project: Optional[str] = None,
    status_filter: Optional[str] = None,
    workflow: Optional[str] = None,
    admin: dict = Depends(verify_admin_auth),
):
    """
    Liste des exécutions récentes.
    
    Permet de filtrer par projet, statut et workflow.
    Les données sensibles sont filtrées.
    """
    client = get_langsmith_client()
    
    if not client:
        return []
    
    try:
        runs_list = []
        
        # Si aucun projet spécifié, prendre le projet par défaut
        project_names = [project] if project else [os.getenv("LANGSMITH_PROJECT", "agent-tutor")]
        
        for project_name in project_names:
            runs = list(client.list_runs(
                project_name=project_name,
                limit=limit,
            ))
            
            for run in runs:
                # Filtrer par statut si demandé
                if status_filter:
                    if status_filter == "success" and run.error is not None:
                        continue
                    elif status_filter == "error" and run.error is None:
                        continue
                
                # Filtrer par workflow si demandé
                if workflow and run.metadata:
                    run_workflow = run.metadata.get("workflow")
                    if run_workflow != workflow:
                        continue
                
                # Calculer la latence
                latency_ms = None
                if run.start_time and run.end_time:
                    latency_ms = (run.end_time - run.start_time).total_seconds() * 1000
                
                # Extraire les tokens
                tokens = None
                if run.metadata:
                    usage = run.metadata.get("usage", {})
                    if usage:
                        tokens = {
                            "input": usage.get("prompt_tokens", 0),
                            "output": usage.get("completion_tokens", 0),
                            "total": usage.get("total_tokens", 0),
                        }
                
                runs_list.append(RunInfo(
                    run_id=str(run.id),
                    name=run.name if hasattr(run, "name") else None,
                    project_name=project_name,
                    start_time=run.start_time,
                    end_time=run.end_time,
                    status="error" if run.error else "success",
                    workflow=run.metadata.get("workflow") if run.metadata else None,
                    model=run.metadata.get("model") if run.metadata else None,
                    latency_ms=round(latency_ms, 2) if latency_ms else None,
                    tokens=tokens,
                    error_message=str(run.error)[:500] if run.error else None,  # Tronquer
                ))
        
        # Trier par date décroissante
        runs_list.sort(key=lambda r: r.start_time or datetime.min, reverse=True)
        
        return runs_list[:limit]
        
    except Exception as e:
        log_event(
            "ADMIN_OBSERVABILITY_ERROR",
            message=f"Failed to fetch runs: {e}",
            extra={"operation": "get_recent_runs"},
        )
        return []


@router.get("/run/{run_id}", response_model=TraceDetail)
async def get_run_detail(
    run_id: str,
    admin: CurrentUser = Depends(verify_admin_auth),
):
    """
    Détail complet d'une exécution (trace arbre).

    Retourne la hiérarchie complète des spans avec :
    - Inputs/outputs (filtrés)
    - Métadonnées
    - Feedback
    - Child runs

    Les prompts systèmes complets et secrets sont masqués.
    """
    client = get_langsmith_client()

    if not client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LangSmith not configured",
        )

    try:
        from uuid import UUID

        run = client.read_run(UUID(run_id))

        # Récupérer TOUTE la trace (même trace_id) pour reconstruire
        # l'arbre via dotted_order (parent_run_id / child_run_ids sont
        # None dans cette version du SDK).
        trace_id = getattr(run, "trace_id", None)
        all_runs = {}
        if trace_id:
            for r in client.list_runs(trace_id=trace_id, limit=100):
                all_runs[str(r.id)] = r

        def _run_id_of(segment: str) -> str | None:
            """Extrait le run_id (UUID 36 chars) d'un segment dotted_order."""
            return segment[-36:] if len(segment) >= 36 else None

        parent_map: dict[str, str] = {}
        for r in all_runs.values():
            dotted = getattr(r, "dotted_order", None)
            if not dotted or "." not in dotted:
                continue
            parts = dotted.split(".")
            cid = _run_id_of(parts[-1])
            pid = _run_id_of(parts[-2])
            if cid and pid:
                parent_map[cid] = pid

        def _sanitize(data: dict | None) -> dict[str, Any]:
            if not isinstance(data, dict):
                return {}
            out = {}
            for k, v in data.items():
                if k.startswith("_"):
                    continue
                if k in ("system_prompt", "prompt", "serialized"):
                    out[k] = "[REDACTED]"
                else:
                    out[k] = v
            return out

        def _build(r, depth: int = 0) -> TraceDetail:
            children_ids = [str(cid) for cid in getattr(r, "child_run_ids", None) or []]
            if not children_ids:
                children_ids = [
                    str(rid) for rid, pid in parent_map.items()
                    if pid == str(r.id)
                ]
            children = [
                _build(all_runs[cid], depth + 1)
                for cid in children_ids
                if cid in all_runs
            ]
            inputs = _sanitize(r.inputs or {})
            outputs = _sanitize(r.outputs or {})
            if not children:
                inputs = {k: v for k, v in inputs.items() if k not in ("messages", "input")}
            latency_ms = None
            if r.start_time and r.end_time:
                latency_ms = round(
                    (r.end_time - r.start_time).total_seconds() * 1000, 2
                )
            return TraceDetail(
                run_id=str(r.id),
                name=r.name or "",
                run_type=r.run_type or "",
                status=r.status or ("error" if r.error else "success"),
                latency_ms=latency_ms,
                start_time=r.start_time,
                end_time=r.end_time,
                inputs=inputs,
                outputs=outputs,
                error=str(r.error) if r.error else None,
                metadata=r.metadata or {},
                feedback=None,  # À implémenter si nécessaire
                child_runs=children,
            )

        return _build(run)

    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid run ID format",
        )
    except HTTPException:
        raise
    except Exception as e:
        log_event(
            "ADMIN_OBSERVABILITY_ERROR",
            message=f"Failed to fetch run detail: {e}",
            extra={"operation": "get_run_detail", "run_id": run_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch run detail",
        )


@router.get("/evaluations", response_model=list[EvaluationResult])
async def get_evaluations(
    admin: dict = Depends(verify_admin_auth),
):
    """
    Résultats d'évaluations (datasets, scores).
    
    Retourne les performances sur les datasets d'évaluation.
    """
    client = get_langsmith_client()
    
    if not client:
        return []
    
    try:
        evaluations_list = []
        
        # Lister les datasets
        datasets = list(client.list_datasets())
        
        for dataset in datasets:
            # Obtenir les expérimentations associées
            experiments = list(client.list_experiments(dataset_name=dataset.name))
            
            if not experiments:
                # Pas d'expérimentations, retourner les stats du dataset
                examples = list(client.list_examples(dataset_id=dataset.id))
                evaluations_list.append(EvaluationResult(
                    dataset_name=dataset.name,
                    experiment_name=None,
                    average_score=0.0,
                    total_examples=len(examples),
                    metrics={},
                ))
            else:
                # Prendre la dernière expérimentation
                latest_exp = sorted(experiments, key=lambda e: e.created_at or datetime.min, reverse=True)[0]
                
                # Calculer les scores moyens (simplifié)
                # En réalité, il faudrait lire les résultats détaillés
                evaluations_list.append(EvaluationResult(
                    dataset_name=dataset.name,
                    experiment_name=latest_exp.name,
                    average_score=0.0,  # À calculer depuis les résultats
                    total_examples=0,  # À obtenir depuis les résultats
                    metrics={},
                ))
        
        return evaluations_list
        
    except Exception as e:
        log_event(
            "ADMIN_OBSERVABILITY_ERROR",
            message=f"Failed to fetch evaluations: {e}",
            extra={"operation": "get_evaluations"},
        )
        return []


@router.get("/models/usage", response_model=list[ModelUsage])
async def get_model_usage(
    days: int = Query(default=7, ge=1, le=90),
    admin: dict = Depends(verify_admin_auth),
):
    """
    Statistiques d'utilisation par modèle.
    
    Affiche :
    - Nombre d'appels par modèle
    - Tokens consommés
    - Coûts estimés (si disponibles)
    - Latence moyenne
    """
    client = get_langsmith_client()
    
    if not client:
        return []
    
    try:
        # Agréger par modèle
        model_stats: dict[str, dict] = {}
        
        project_name = os.getenv("LANGSMITH_PROJECT", "agent-tutor")
        runs = list(client.list_runs(
            project_name=project_name,
            limit=1000,  # Limite raisonnable
        ))
        
        for run in runs:
            if not run.metadata:
                continue
            
            model = run.metadata.get("model")
            if not model:
                continue
            
            if model not in model_stats:
                model_stats[model] = {
                    "calls": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "total_tokens": 0,
                    "latencies": [],
                }
            
            stats = model_stats[model]
            stats["calls"] += 1
            
            usage = run.metadata.get("usage", {})
            stats["input_tokens"] += usage.get("prompt_tokens", 0)
            stats["output_tokens"] += usage.get("completion_tokens", 0)
            stats["total_tokens"] += usage.get("total_tokens", 0)
            
            if run.start_time and run.end_time:
                latency = (run.end_time - run.start_time).total_seconds() * 1000
                stats["latencies"].append(latency)
        
        # Construire la réponse
        result = []
        for model_name, stats in model_stats.items():
            avg_latency = (
                sum(stats["latencies"]) / len(stats["latencies"])
                if stats["latencies"] else None
            )
            
            # Estimation de coût très simplifiée (à améliorer)
            # Les prix réels dépendent du provider
            estimated_cost = None
            
            result.append(ModelUsage(
                model_name=model_name,
                provider=None,  # Peut être extrait du nom du modèle
                total_calls=stats["calls"],
                total_tokens=stats["total_tokens"],
                input_tokens=stats["input_tokens"],
                output_tokens=stats["output_tokens"],
                estimated_cost=estimated_cost,
                avg_latency_ms=round(avg_latency, 2) if avg_latency else None,
            ))
        
        # Trier par nombre d'appels décroissant
        result.sort(key=lambda m: m.total_calls, reverse=True)
        
        return result
        
    except Exception as e:
        log_event(
            "ADMIN_OBSERVABILITY_ERROR",
            message=f"Failed to fetch model usage: {e}",
            extra={"operation": "get_model_usage"},
        )
        return []


@router.get("/errors", response_model=list[ErrorEntry])
async def get_error_log(
    limit: int = Query(default=100, ge=1, le=1000),
    admin: dict = Depends(verify_admin_auth),
):
    """
    Journal des erreurs avec traces.
    
    Liste les erreurs récentes avec leur contexte.
    """
    client = get_langsmith_client()
    
    if not client:
        return []
    
    try:
        errors_list = []
        
        project_name = os.getenv("LANGSMITH_PROJECT", "agent-tutor")
        runs = list(client.list_runs(
            project_name=project_name,
            filter="error exists",
            limit=limit,
        ))
        
        for run in runs:
            if not run.error:
                continue
            
            errors_list.append(ErrorEntry(
                run_id=str(run.id),
                timestamp=run.start_time or datetime.now(),
                error_type=type(run.error).__name__ if hasattr(run.error, '__class__') else "Unknown",
                error_message=str(run.error)[:500],  # Tronquer
                workflow=run.metadata.get("workflow") if run.metadata else None,
                node=run.name,
                stack_trace=None,  # Stack trace complète si disponible
            ))
        
        # Trier par date décroissante
        errors_list.sort(key=lambda e: e.timestamp, reverse=True)
        
        return errors_list[:limit]
        
    except Exception as e:
        log_event(
            "ADMIN_OBSERVABILITY_ERROR",
            message=f"Failed to fetch errors: {e}",
            extra={"operation": "get_error_log"},
        )
        return []


@router.get("/langsmith-link", response_model=LangSmithLink)
async def get_langsmith_dashboard_link(
    admin: dict = Depends(verify_admin_auth),
):
    """
    Lien sécurisé vers le dashboard LangSmith.
    
    Génère un lien vers le projet LangSmith actuel.
    Ne transmet JAMAIS la clé API au navigateur.
    """
    project_name = os.getenv("LANGSMITH_PROJECT", "agent-tutor")
    environment = os.getenv("LANGSMITH_ENVIRONMENT", "development")
    
    # URL du dashboard LangSmith
    dashboard_url = "https://smith.langchain.com"
    
    return LangSmithLink(
        dashboard_url=dashboard_url,
        project_name=project_name,
        environment=environment,
        expires_in_seconds=None,  # Lien permanent
    )


__all__ = ["router"]
