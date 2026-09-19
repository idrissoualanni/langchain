# Admin API Module

from app.api.admin.models import router as models_router
from app.api.admin.knowledge import router as knowledge_router
from app.api.admin.observability import router as observability_router
from app.api.admin.dashboard import router as dashboard_router

__all__ = ["models_router", "knowledge_router", "observability_router", "dashboard_router"]
