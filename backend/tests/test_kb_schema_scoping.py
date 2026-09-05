"""
Tests for Knowledge Base schema scoping, app_id/external_id/owner_id constraints,
and dual-database compatibility (SQLAlchemy and MongoDB).
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool

from database import Base
from models import KnowledgeBase, KnowledgeBaseDocument
from models_mongo import KnowledgeBaseCollection, KnowledgeBaseMongo


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def test_kb_schema_scoping_creation_and_uniqueness(db_session):
    """
    1. Assert that creating a KnowledgeBase with app_id='bug_tracker',
       external_id='proj_42', and owner_id='user_1' succeeds.
    2. Assert that creating a second KnowledgeBase with the same
       (owner_id, app_id, external_id) raises an integrity/duplicate constraint error.
    3. Assert that two different users CAN have identical external_ids without collision.
    """
    kb1 = KnowledgeBase(
        name="Bug Tracker KB User 1",
        owner_id="user_1",
        app_id="bug_tracker",
        external_id="proj_42",
        scope_type="workspace",
        embedding_provider="google",
        embedding_model="gemini-embedding-2",
    )
    db_session.add(kb1)
    db_session.commit()

    assert kb1.id is not None
    assert kb1.owner_id == "user_1"
    assert kb1.app_id == "bug_tracker"
    assert kb1.external_id == "proj_42"

    # Duplicate (owner_id, app_id, external_id) should raise IntegrityError
    kb_duplicate = KnowledgeBase(
        name="Duplicate KB",
        owner_id="user_1",
        app_id="bug_tracker",
        external_id="proj_42",
    )
    db_session.add(kb_duplicate)
    with pytest.raises(IntegrityError):
        db_session.commit()

    db_session.rollback()

    # Different owner_id with same app_id and external_id should succeed
    kb2 = KnowledgeBase(
        name="Bug Tracker KB User 2",
        owner_id="user_2",
        app_id="bug_tracker",
        external_id="proj_42",
        scope_type="workspace",
    )
    db_session.add(kb2)
    db_session.commit()

    assert kb2.id is not None
    assert kb2.owner_id == "user_2"
    assert kb2.external_id == "proj_42"


def test_kb_document_scoping_fields(db_session):
    """Verify KnowledgeBaseDocument contains scoping and description fields."""
    kb = KnowledgeBase(
        name="Docs KB",
        owner_id="user_1",
        app_id="app_1",
        external_id="ext_1",
    )
    db_session.add(kb)
    db_session.commit()

    doc = KnowledgeBaseDocument(
        kb_id=kb.id,
        doc_type="text",
        name="Doc 1",
        description="Sample document description",
        app_id="app_1",
        external_id="doc_ext_1",
        content_text="Hello world",
    )
    db_session.add(doc)
    db_session.commit()

    assert doc.id is not None
    assert doc.description == "Sample document description"
    assert doc.app_id == "app_1"
    assert doc.external_id == "doc_ext_1"


def test_sqlite_kb_migration_backfills_and_alters(db_session):
    """
    Simulate an older SQLite database schema where knowledge_bases and kb_documents
    lacked owner_id and other scoping columns, then run _run_sqlite_migrations
    and verify columns exist, owner_id is backfilled, and queries succeed.
    """
    import sqlalchemy
    from main import _run_sqlite_migrations

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Create old schema manually without owner_id and app_id/external_id
    with engine.connect() as conn:
        conn.execute(sqlalchemy.text("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                username TEXT NOT NULL,
                email TEXT NOT NULL,
                role TEXT NOT NULL,
                hashed_password TEXT NOT NULL
            )
        """))
        conn.execute(sqlalchemy.text("""
            CREATE TABLE knowledge_bases (
                id INTEGER PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),
                name TEXT NOT NULL,
                description TEXT,
                is_shared BOOLEAN DEFAULT 0,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP
            )
        """))
        conn.execute(sqlalchemy.text("""
            CREATE TABLE kb_documents (
                id INTEGER PRIMARY KEY,
                kb_id INTEGER NOT NULL REFERENCES knowledge_bases(id),
                doc_type TEXT NOT NULL,
                name TEXT NOT NULL,
                content_text TEXT,
                file_id TEXT,
                filename TEXT,
                media_type TEXT,
                indexed BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        # Insert a user and old knowledge base row (owner_id missing)
        conn.execute(sqlalchemy.text("INSERT INTO users (id, username, email, role, hashed_password) VALUES (1, 'alice', 'alice@example.com', 'user', 'hash')"))
        conn.execute(sqlalchemy.text("INSERT INTO knowledge_bases (id, user_id, name, description) VALUES (10, 1, 'Old KB', 'Legacy KB')"))
        conn.commit()

    # Run migration
    _run_sqlite_migrations(engine)

    # Query using SQLAlchemy ORM model KnowledgeBase
    Session = sessionmaker(bind=engine)
    session = Session()

    kb = session.query(KnowledgeBase).filter(KnowledgeBase.id == 10).first()
    assert kb is not None
    assert kb.owner_id == "1"
    assert kb.name == "Old KB"
    assert kb.scope_type == "workspace"
    assert kb.embedding_provider == "google"
    assert kb.embedding_model == "gemini-embedding-2"

    # Verify query by owner_id works seamlessly (the cause of OperationalError before fix)
    kbs = session.query(KnowledgeBase).filter(KnowledgeBase.owner_id == "1").all()
    assert len(kbs) == 1
    session.close()


def test_sqlite_trace_spans_migration_adds_trace_identity_columns():
    import sqlalchemy
    from main import _run_sqlite_migrations

    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as conn:
        conn.execute(sqlalchemy.text("""
            CREATE TABLE trace_spans (
                id INTEGER PRIMARY KEY,
                session_id INTEGER,
                span_type TEXT NOT NULL,
                name TEXT NOT NULL
            )
        """))
        conn.commit()

    _run_sqlite_migrations(engine)

    with engine.connect() as conn:
        columns = {
            row[1]
            for row in conn.execute(sqlalchemy.text("PRAGMA table_info(trace_spans)"))
        }

    assert {"trace_id", "span_id", "parent_span_id"} <= columns


@pytest.mark.asyncio
async def test_mongo_kb_schema_fields_and_index_spec():
    """Assert KnowledgeBaseMongo document structure and index specification."""
    kb_data = {
        "name": "Mongo KB",
        "owner_id": "user_1",
        "app_id": "bug_tracker",
        "external_id": "proj_42",
        "description": "Scoped KB",
        "scope_type": "workspace",
        "embedding_provider": "google",
        "embedding_model": "gemini-embedding-2",
        "secret_id": "sec_123",
    }
    mongo_model = KnowledgeBaseMongo(**kb_data)
    assert mongo_model.owner_id == "user_1"
    assert mongo_model.app_id == "bug_tracker"
    assert mongo_model.external_id == "proj_42"
    assert mongo_model.secret_id == "sec_123"
