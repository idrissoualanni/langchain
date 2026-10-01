"""
Cloudflare Workers Python Entry Point
Agent Control Center - Adapted for Cloudflare Workers AI

This worker wraps the FastAPI application for deployment on Cloudflare Workers.
Uses the `workers` Python package for Cloudflare Workers Python support.
"""

from workers import WorkerEntrypoint, Response, Request as WorkersRequest
import asyncio
import sys
import os

# Add backend to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

# Import the FastAPI app
from app.main import app as fastapi_app

# Import ASGI adapter for Cloudflare Workers
try:
    from asgiref.wsgi import WsgiToAsgi
    from asgiref.sync import async_to_sync
except ImportError:
    # Fallback if asgiref not available
    WsgiToAsgi = None


class AgentControlCenterWorker(WorkerEntrypoint):
    """Cloudflare Worker entry point for Agent Control Center."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._asgi_app = None
    
    def _get_asgi_app(self):
        """Get or create the ASGI app wrapper."""
        if self._asgi_app is None:
            # FastAPI is already ASGI, but we need to ensure it works with Workers
            # The workers package provides an ASGI adapter
            self._asgi_app = fastapi_app
        return self._asgi_app
    
    async def fetch(self, request: WorkersRequest) -> Response:
        """Handle incoming HTTP requests."""
        # Convert Cloudflare Workers Request to ASGI scope
        asgi_app = self._get_asgi_app()
        
        # Build ASGI scope from Workers request
        url = request.url
        method = request.method
        headers = dict(request.headers)
        
        # Read body
        body = b""
        if method in ("POST", "PUT", "PATCH", "DELETE"):
            try:
                body = await request.bytes()
            except Exception:
                body = b""
        
        # Create ASGI scope
        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": method,
            "path": url.path,
            "query_string": url.query.encode() if url.query else b"",
            "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
            "client": ("127.0.0.1", 8080),
            "server": ("0.0.0.0", 8080),
        }
        
        # Create receive and send functions for ASGI
        receive_called = False
        
        async def receive():
            nonlocal receive_called
            if not receive_called:
                receive_called = True
                return {
                    "type": "http.request",
                    "body": body,
                    "more_body": False,
                }
            return {"type": "http.disconnect"}
        
        response_data = {"status": 500, "headers": [], "body": b""}
        response_started = False
        
        async def send(message):
            nonlocal response_started, response_data
            if message["type"] == "http.response.start":
                response_data["status"] = message["status"]
                response_data["headers"] = message.get("headers", [])
                response_started = True
            elif message["type"] == "http.response.body":
                response_data["body"] += message.get("body", b"")
        
        # Call the ASGI app
        try:
            await asgi_app(scope, receive, send)
        except Exception as e:
            return Response(
                f"Internal Server Error: {str(e)}",
                status=500,
                headers={"Content-Type": "text/plain"}
            )
        
        # Build Cloudflare Workers Response
        response_headers = {}
        for k, v in response_data["headers"]:
            response_headers[k.decode()] = v.decode()
        
        return Response(
            response_data["body"],
            status=response_data["status"],
            headers=response_headers
        )


# Export the worker class
export = AgentControlCenterWorker