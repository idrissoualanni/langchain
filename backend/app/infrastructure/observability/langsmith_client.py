"""
LangSmith Observability Module

Provides LangSmith tracing and monitoring for LangGraph/LangChain workflows.
Integrates with the existing architecture without creating parallel systems.
"""

from langsmith import Client, traceable
from langsmith.run_helpers import get_run_tree_context, get_tracing_context
from typing import Any, Optional


class LangSmithClient:
    """
    LangSmith client wrapper for observability.
    
    Provides tracing, monitoring, and evaluation capabilities
    for LangGraph/LangChain workflows.
    """
    
    def __init__(self):
        # LANGSMITH_* vient de app.config (source unique des défauts) ;
        # la lecture est fraîche à chaque instanciation pour rester
        # testable (patch.dict de os.environ dans les tests).
        from app.config import langsmith_settings

        settings = langsmith_settings()
        self.enabled = settings.enabled
        self.project = settings.project
        self.api_key = settings.api_key
        self.endpoint = settings.endpoint
        self.environment = settings.environment

        if self.enabled and self.api_key:
            self.client = Client(
                api_key=self.api_key,
                api_url=self.endpoint,
            )
        else:
            self.client = None
    
    def is_enabled(self) -> bool:
        """Check if LangSmith is enabled and configured."""
        return self.enabled and self.client is not None
    
    def log_feedback(
        self,
        run_id: str,
        score: Optional[float] = None,
        value: Optional[str] = None,
        comment: Optional[str] = None,
        correction: Optional[dict] = None,
    ) -> bool:
        """Log feedback for a run."""
        if not self.is_enabled():
            return False
        
        try:
            self.client.create_feedback(
                run_id=run_id,
                score=score,
                value=value,
                comment=comment,
                correction=correction,
            )
            return True
        except Exception as e:
            # Non-blocking: logging failure should not crash the app
            print(f"[LangSmith] Failed to log feedback: {e}")
            return False
    
    def share_run(self, run_id: str) -> Optional[str]:
        """Create a public share link for a run."""
        if not self.is_enabled():
            return None
        
        try:
            return self.client.share_run(run_id)
        except Exception as e:
            print(f"[LangSmith] Failed to share run: {e}")
            return None


# Global client instance
langsmith_client = LangSmithClient()


def get_langsmith_client() -> LangSmithClient:
    """Get the global LangSmith client instance."""
    return langsmith_client


def traceable_agent_action(
    name: Optional[str] = None,
    run_type: str = "tool",
    tags: Optional[list[str]] = None,
    metadata: Optional[dict[str, Any]] = None,
):
    """
    Decorator for tracing agent actions (tools, subgraphs, etc.).
    
    Usage:
        @traceable_agent_action(name="coding_subgraph", run_type="chain")
        async def coding_subgraph(state: CodingState) -> CodingResult:
            ...
    """
    def decorator(func):
        if not langsmith_client.is_enabled():
            return func
        
        return traceable(
            run_type=run_type,
            name=name or func.__name__,
            tags=tags,
            metadata={
                "environment": langsmith_client.environment,
                **(metadata or {}),
            },
        )(func)
    
    return decorator


def set_trace_metadata(
    user_id: Optional[str] = None,
    thread_id: Optional[str] = None,
    run_id: Optional[str] = None,
    session_id: Optional[str] = None,
    model: Optional[str] = None,
    model_provider: Optional[str] = None,
    workflow: Optional[str] = None,
    subject: Optional[str] = None,
    topic: Optional[str] = None,
):
    """
    Set metadata for the current trace.
    
    This should be called at the beginning of a request to propagate
    context throughout the trace hierarchy.
    """
    if not langsmith_client.is_enabled():
        return
    
    metadata = {
        "user_id": user_id,
        "thread_id": thread_id,
        "run_id": run_id,
        "session_id": session_id,
        "model": model,
        "model_provider": model_provider,
        "workflow": workflow,
        "subject": subject,
        "topic": topic,
        "environment": langsmith_client.environment,
    }
    
    # Filter out None values
    metadata = {k: v for k, v in metadata.items() if v is not None}
    
    try:
        # Use LangSmith's set_run_metadata if available
        from langsmith.run_helpers import set_run_metadata
        for key, value in metadata.items():
            set_run_metadata(key, value)
    except Exception as e:
        print(f"[LangSmith] Failed to set trace metadata: {e}")


def log_agent_observation(
    action: str,
    success: bool,
    result: dict[str, Any],
    errors: Optional[list[str]] = None,
    duration_ms: Optional[float] = None,
    tokens: Optional[dict[str, int]] = None,
):
    """
    Log an agent observation to LangSmith.
    
    Used for tracking agent decisions, tool executions, and subgraph results.
    """
    if not langsmith_client.is_enabled():
        return
    
    try:
        ctx = get_run_tree_context()
        if ctx:
            # Metadata is automatically captured by LangSmith
            pass
    except Exception as e:
        print(f"[LangSmith] Failed to log observation: {e}")


def create_dataset(
    dataset_name: str,
    description: Optional[str] = None,
) -> Optional[str]:
    """
    Create a LangSmith dataset for evaluation.
    
    Returns the dataset ID if successful.
    """
    if not langsmith_client.is_enabled():
        return None
    
    try:
        dataset = langsmith_client.client.create_dataset(
            dataset_name=dataset_name,
            description=description,
        )
        return str(dataset.id)
    except Exception as e:
        print(f"[LangSmith] Failed to create dataset: {e}")
        return None


def add_example_to_dataset(
    dataset_id: str,
    inputs: dict[str, Any],
    outputs: Optional[dict[str, Any]] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> bool:
    """
    Add an example to a LangSmith dataset.
    
    Used for building evaluation datasets from real interactions.
    """
    if not langsmith_client.is_enabled():
        return False
    
    try:
        langsmith_client.client.create_example(
            inputs=inputs,
            outputs=outputs,
            dataset_id=dataset_id,
            metadata=metadata,
        )
        return True
    except Exception as e:
        print(f"[LangSmith] Failed to add example: {e}")
        return False
