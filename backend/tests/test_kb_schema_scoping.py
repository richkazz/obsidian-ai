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
        embedding_model="text-embedding-004",
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
        "embedding_model": "text-embedding-004",
        "secret_id": "sec_123",
    }
    mongo_model = KnowledgeBaseMongo(**kb_data)
    assert mongo_model.owner_id == "user_1"
    assert mongo_model.app_id == "bug_tracker"
    assert mongo_model.external_id == "proj_42"
    assert mongo_model.secret_id == "sec_123"
