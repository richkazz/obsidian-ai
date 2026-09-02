"""Regression tests for unauthenticated health checks and WA sidecar wiring."""

import asyncio
import inspect
from pathlib import Path

from fastapi import Request

from routers.user_router import health_check


def test_health_check_is_public_and_returns_liveness_status():
    """Health checks must work for Docker, nginx, and external monitors."""
    request = Request({"type": "http", "method": "GET", "path": "/health", "headers": []})
    assert asyncio.run(health_check(request=request)) == {"status": "ok"}
    assert "Depends" not in inspect.getsource(health_check)


def test_compose_sets_the_sidecar_variable_consumed_by_backend():
    """Prevent a return to the WA_BRIDGE_URL/WA_SIDECAR_URL naming mismatch."""
    root = Path(__file__).resolve().parents[2]
    compose = (root / "docker-compose.yml").read_text()
    router = (root / "backend" / "routers" / "whatsapp_router.py").read_text()
    service = (root / "backend" / "services" / "whatsapp_service.py").read_text()

    assert "WA_SIDECAR_URL=http://wa-bridge:3200" in compose
    assert "WA_BRIDGE_URL=" not in compose
    assert 'os.environ.get("WA_SIDECAR_URL"' in router
    assert 'os.environ.get("WA_SIDECAR_URL"' in service
