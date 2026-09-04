"""
Tests for dynamic runtime embedding keys, resilient index loading,
concurrent async locking per KB ID, and invalid secret exception handling.
"""

import os
import shutil
import asyncio
import pytest
from unittest.mock import patch, AsyncMock
from fastapi import HTTPException

import rag_service
from rag_service import (
    RAGService,
    get_embedding_client,
    load_or_create_index,
    _kb_index_locks,
)


@pytest.mark.asyncio
async def test_dynamic_embedding_credentials_per_call(monkeypatch):
    """
    Assert that index_kb_document() / query_kb() accept dynamic embedding credentials
    (embedding_provider, api_key, model) per execution call without reading global env vars.
    """
    # Ensure global env vars are unset
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    mock_embed = AsyncMock(return_value=[0.1] * 768)

    with patch("rag_service.get_embedding_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.embed = mock_embed
        mock_get_client.return_value = mock_client

        # Call index_kb_document with custom runtime credentials
        await rag_service.index_kb_document_async(
            kb_id="kb_dynamic_1",
            text="Test content for dynamic embeddings",
            metadata={"filename": "test.txt"},
            embedding_provider="openai",
            api_key="sk-runtime-dynamic-key-123",
            model="text-embedding-3-small",
        )

        mock_get_client.assert_called_with(
            provider="openai",
            api_key="sk-runtime-dynamic-key-123",
            model="text-embedding-3-small",
        )
        assert mock_embed.called

        # Call query_kb with different runtime credentials
        results = await rag_service.query_kb_async(
            kb_id="kb_dynamic_1",
            query="Test query",
            top_k=3,
            embedding_provider="google",
            api_key="AIzaRuntimeGoogleKey456",
            model="text-embedding-004",
        )

        mock_get_client.assert_called_with(
            provider="google",
            api_key="AIzaRuntimeGoogleKey456",
            model="text-embedding-004",
        )
        assert isinstance(results, list)

        # Synchronous wrapper calls
        rag_service.index_kb_document(
            kb_id="kb_dynamic_sync",
            text="Sync test content",
            embedding_provider="openai",
            api_key="sk-sync-key",
        )
        sync_results = rag_service.query_kb(
            kb_id="kb_dynamic_sync",
            query="Sync test query",
            embedding_provider="openai",
            api_key="sk-sync-key",
        )
        assert isinstance(sync_results, list)


@pytest.mark.asyncio
async def test_load_or_create_index_non_existent_directory(tmp_path):
    """
    Assert that initializing a vector store index for a non-existent index directory
    automatically initializes an empty index without throwing unhandled exceptions.
    """
    target_dir = str(tmp_path / "vector_indices" / "kb_new_999")
    assert not os.path.exists(target_dir)

    index = load_or_create_index(kb_id="kb_new_999", base_dir=str(tmp_path / "vector_indices"))

    assert os.path.exists(target_dir)
    assert index is not None


@pytest.mark.asyncio
async def test_concurrent_async_write_serialization_per_kb():
    """
    Assert that vector store operations under concurrent async calls on the same KB ID
    serialize correctly via _kb_index_locks without index corruption.
    """
    kb_id = "kb_concurrent_123"
    execution_order = []

    async def mock_indexing_task(task_id: int):
        lock = rag_service.get_kb_lock(kb_id)
        async with lock:
            execution_order.append(f"start_{task_id}")
            await asyncio.sleep(0.05)
            execution_order.append(f"end_{task_id}")

    # Launch 3 concurrent indexing tasks for the same KB ID
    await asyncio.gather(
        mock_indexing_task(1),
        mock_indexing_task(2),
        mock_indexing_task(3),
    )

    # Verify that each task completed before the next started
    assert len(execution_order) == 6
    for i in range(0, 6, 2):
        start_tag = execution_order[i]
        end_tag = execution_order[i + 1]
        task_num = start_tag.split("_")[1]
        assert end_tag == f"end_{task_num}"


@pytest.mark.asyncio
async def test_missing_or_invalid_secret_raises_http_exception(monkeypatch):
    """
    Assert that missing or invalid embedding provider credentials raise a structured
    HTTPException(400, "Embedding provider credentials invalid or missing").
    """
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    with pytest.raises(HTTPException) as exc_info:
        await rag_service.index_kb_document_async(
            kb_id="kb_no_key",
            text="Some text",
            metadata={},
            embedding_provider="google",
            api_key=None,
        )

    assert exc_info.value.status_code == 400
    assert "Embedding provider credentials invalid or missing" in exc_info.value.detail
