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


def test_compose_persists_sqlite_and_scheduler_state_in_backend_data_volume():
    """SQLite state must not be written to the container's ephemeral workdir."""
    root = Path(__file__).resolve().parents[2]
    compose = (root / "docker-compose.yml").read_text()
    database = (root / "backend" / "database.py").read_text()
    scheduler = (root / "backend" / "scheduler.py").read_text()

    assert "DATABASE_URL=${DATABASE_URL:-sqlite:////app/data/app.db}" in compose
    assert "SCHEDULER_DATABASE_URL=${SCHEDULER_DATABASE_URL:-sqlite:////app/data/agent_control_plane.db}" in compose
    assert "backend_data:/app/data" in compose
    assert 'os.getenv("DATABASE_URL", "sqlite:///./app.db")' in database
    assert 'os.getenv("SCHEDULER_DATABASE_URL", "sqlite:///./agent_control_plane.db")' in scheduler


def test_compose_uses_the_mongo_environment_variable_names_read_by_backend():
    root = Path(__file__).resolve().parents[2]
    compose = (root / "docker-compose.yml").read_text()
    mongo_database = (root / "backend" / "database_mongo.py").read_text()

    assert "MONGO_URL=${MONGO_URL:-mongodb://mongo:27017/obsidian}" in compose
    assert "MONGO_DB_NAME=${MONGO_DB_NAME:-obsidian}" in compose
    assert 'os.getenv("MONGO_URL"' in mongo_database
    assert 'os.getenv("MONGO_DB_NAME"' in mongo_database
