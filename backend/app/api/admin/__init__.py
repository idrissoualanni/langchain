# Admin API Module

from app.api.admin.models import router as models_router
from app.api.admin.knowledge import router as knowledge_router
from app.api.admin.subjects import router as subjects_router
from app.api.admin.monitoring import router as monitoring_router
from app.api.admin.observability import router as observability_router
from app.api.admin.dashboard import router as dashboard_router
from app.api.admin.users import router as users_router
from app.api.admin.mcp import router as mcp_router

__all__ = [
    "models_router",
    "knowledge_router",
    "subjects_router",
    "monitoring_router",
    "observability_router",
    "dashboard_router",
    "users_router",
    "mcp_router",
]
