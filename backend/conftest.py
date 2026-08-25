"""
Test configuration. Sets the minimal env vars the app's module-level config
(config.py, encryption.py, auth.py) needs just to import cleanly, since
importing routers.chat_router pulls in the whole app wiring.

No live DB or network access is used by the test suite — see
tests/test_team_delegation.py and friends for what's actually exercised
(pure logic: teammate resolution, retry wrappers, prompt formatting).
"""
import os

os.environ.setdefault("DATABASE_TYPE", "mongo")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("MONGO_DB_NAME", "aios_test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-not-for-production")
os.environ.setdefault("ENCRYPTION_KEY", "dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleTE=")
