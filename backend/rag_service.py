"""
Managed RAG Service — Google Vertex/Gemini Embeddings + Qdrant Vector Database.
Replaces local FAISS / LEANN and SentenceTransformer models.
"""
import io
import os
import logging
import httpx
from typing import Optional, List, Dict, Any
import uuid

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from config import (
    QDRANT_URL,
    QDRANT_API_KEY,
    QDRANT_COLLECTION_NAME,
    GOOGLE_EMBEDDING_MODEL,
    GOOGLE_API_KEY,
)

logger = logging.getLogger(__name__)

# Google Gemini / Vertex Embeddings Endpoint (REST)
GOOGLE_EMBEDDING_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GOOGLE_EMBEDDING_MODEL}:embedContent"

# Global client cache
_qdrant_client: Optional[QdrantClient] = None


def get_qdrant_client() -> QdrantClient:
    global _qdrant_client
    if _qdrant_client is None:
        url = QDRANT_URL or os.getenv("QDRANT_URL")
        key = QDRANT_API_KEY or os.getenv("QDRANT_API_KEY") or None
        if not url:
            logger.info("QDRANT_URL not set; using in-memory Qdrant client")
            _qdrant_client = QdrantClient(location=":memory:")
        else:
            _qdrant_client = QdrantClient(url=url, api_key=key)
    return _qdrant_client


def _ensure_collection_exists(vector_size: int = 768):
    client = get_qdrant_client()
    collection_name = QDRANT_COLLECTION_NAME
    try:
        collections = [c.name for c in client.get_collections().collections]
        if collection_name not in collections:
            logger.info("Creating Qdrant collection: %s (size=%d)", collection_name, vector_size)
            client.create_collection(
                collection_name=collection_name,
                vectors_config=qmodels.VectorParams(
                    size=vector_size,
                    distance=qmodels.Distance.COSINE,
                ),
            )
    except Exception as e:
        logger.warning("Error checking/creating Qdrant collection %s: %s", collection_name, e)


async def get_google_embedding(text: str) -> List[float]:
    """Generate embedding vector for text using Google Gemini/Vertex API."""
    api_key = GOOGLE_API_KEY or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY is not configured for embeddings")

    url = f"{GOOGLE_EMBEDDING_API_URL}?key={api_key}"
    payload = {
        "model": f"models/{GOOGLE_EMBEDDING_MODEL}",
        "content": {
            "parts": [{"text": text}]
        }
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(url, json=payload)

    if response.status_code != 200:
        raise RuntimeError(f"Google Embedding API error ({response.status_code}): {response.text}")

    data = response.json()
    embedding_values = data.get("embedding", {}).get("values")
    if not embedding_values:
        raise RuntimeError("Google Embedding API returned empty vector")

    return embedding_values


def _run_coroutine_sync(coro):
    """Safely execute a coroutine from both sync and async contexts."""
    import asyncio
    import concurrent.futures
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(lambda: asyncio.run(coro))
            return future.result()
    else:
        return asyncio.run(coro)


class RAGService:

    @staticmethod
    def has_index(session_id: str) -> bool:
        client = get_qdrant_client()
        try:
            results = client.scroll(
                collection_name=QDRANT_COLLECTION_NAME,
                scroll_filter=qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(
                            key="session_id",
                            match=qmodels.MatchValue(value=session_id),
                        )
                    ]
                ),
                limit=1,
            )
            return len(results[0]) > 0
        except Exception:
            return False

    @staticmethod
    async def index_document_async(session_id: str, text: str, metadata: dict):
        """Chunk text, generate Google embeddings, and upsert to Qdrant."""
        chunks = RAGService._chunk_text(text, chunk_size=500, overlap=50)
        if not chunks:
            return

        sample_vec = await get_google_embedding(chunks[0])
        _ensure_collection_exists(len(sample_vec))

        client = get_qdrant_client()
        points = []

        vectors = [sample_vec]
        for c in chunks[1:]:
            vec = await get_google_embedding(c)
            vectors.append(vec)

        for i, (chunk, vec) in enumerate(zip(chunks, vectors)):
            point_id = str(uuid.uuid4())
            payload = {
                **metadata,
                "session_id": session_id,
                "text": chunk,
                "chunk_index": i,
                "type": "session_doc",
            }
            points.append(qmodels.PointStruct(
                id=point_id,
                vector=vec,
                payload=payload,
            ))

        client.upsert(
            collection_name=QDRANT_COLLECTION_NAME,
            points=points,
        )

    @staticmethod
    def index_document(session_id: str, text: str, metadata: dict):
        """Synchronous wrapper for index_document_async."""
        _run_coroutine_sync(RAGService.index_document_async(session_id, text, metadata))

    @staticmethod
    async def search_async(session_id: str, query: str, top_k: int = 5) -> List[dict]:
        """Search vectors in Qdrant for a given session."""
        try:
            query_vector = await get_google_embedding(query)
            client = get_qdrant_client()

            search_result = client.search(
                collection_name=QDRANT_COLLECTION_NAME,
                query_vector=query_vector,
                query_filter=qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(
                            key="session_id",
                            match=qmodels.MatchValue(value=session_id),
                        )
                    ]
                ),
                limit=top_k,
            )

            results = []
            for hit in search_result:
                payload = hit.payload or {}
                results.append({
                    "text": payload.get("text", ""),
                    "score": float(hit.score),
                    "metadata": payload,
                })
            return results
        except Exception as e:
            logger.warning("RAG search failed for session %s: %s", session_id, e)
            return []

    @staticmethod
    def search(session_id: str, query: str, top_k: int = 5) -> List[dict]:
        """Synchronous wrapper for search_async."""
        return _run_coroutine_sync(RAGService.search_async(session_id, query, top_k))

    # -- Knowledge Base RAG ---------------------------------------------------

    @staticmethod
    def has_kb_index(kb_id: str) -> bool:
        client = get_qdrant_client()
        try:
            results = client.scroll(
                collection_name=QDRANT_COLLECTION_NAME,
                scroll_filter=qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(
                            key="kb_id",
                            match=qmodels.MatchValue(value=kb_id),
                        )
                    ]
                ),
                limit=1,
            )
            return len(results[0]) > 0
        except Exception:
            return False

    @staticmethod
    async def index_kb_document_async(kb_id: str, text: str, metadata: dict):
        chunks = RAGService._chunk_text(text, chunk_size=500, overlap=50)
        if not chunks:
            return

        sample_vec = await get_google_embedding(chunks[0])
        _ensure_collection_exists(len(sample_vec))

        client = get_qdrant_client()
        points = []

        vectors = [sample_vec]
        for c in chunks[1:]:
            vec = await get_google_embedding(c)
            vectors.append(vec)

        for i, (chunk, vec) in enumerate(zip(chunks, vectors)):
            point_id = str(uuid.uuid4())
            payload = {
                **metadata,
                "kb_id": kb_id,
                "text": chunk,
                "chunk_index": i,
                "type": "kb_doc",
            }
            points.append(qmodels.PointStruct(
                id=point_id,
                vector=vec,
                payload=payload,
            ))

        client.upsert(
            collection_name=QDRANT_COLLECTION_NAME,
            points=points,
        )

    @staticmethod
    def index_kb_document(kb_id: str, text: str, metadata: dict):
        """Synchronous wrapper for index_kb_document_async."""
        _run_coroutine_sync(RAGService.index_kb_document_async(kb_id, text, metadata))

    @staticmethod
    async def search_kb_async(kb_id: str, query: str, top_k: int = 5) -> List[dict]:
        try:
            query_vector = await get_google_embedding(query)
            client = get_qdrant_client()

            search_result = client.search(
                collection_name=QDRANT_COLLECTION_NAME,
                query_vector=query_vector,
                query_filter=qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(
                            key="kb_id",
                            match=qmodels.MatchValue(value=kb_id),
                        )
                    ]
                ),
                limit=top_k,
            )

            results = []
            for hit in search_result:
                payload = hit.payload or {}
                results.append({
                    "text": payload.get("text", ""),
                    "score": float(hit.score),
                    "metadata": payload,
                })
            return results
        except Exception as e:
            logger.warning("KB RAG search failed for kb %s: %s", kb_id, e)
            return []

    @staticmethod
    def search_kb(kb_id: str, query: str, top_k: int = 5) -> List[dict]:
        """Synchronous wrapper for search_kb_async."""
        return _run_coroutine_sync(RAGService.search_kb_async(kb_id, query, top_k))

    @staticmethod
    def delete_kb_index(kb_id: str):
        """Delete all points associated with a knowledge base."""
        client = get_qdrant_client()
        try:
            client.delete(
                collection_name=QDRANT_COLLECTION_NAME,
                points_selector=qmodels.FilterSelector(
                    filter=qmodels.Filter(
                        must=[
                            qmodels.FieldCondition(
                                key="kb_id",
                                match=qmodels.MatchValue(value=kb_id),
                            )
                        ]
                    )
                )
            )
        except Exception as e:
            logger.warning("Failed to delete Qdrant points for kb %s: %s", kb_id, e)

    # -- Extract text helpers -------------------------------------------------

    @staticmethod
    def extract_text(file_bytes: bytes, filename: str, media_type: str) -> str:
        lower = filename.lower()

        if media_type == "text/plain" or lower.endswith(".txt"):
            return file_bytes.decode("utf-8", errors="replace")

        if media_type == "text/markdown" or lower.endswith(".md"):
            return file_bytes.decode("utf-8", errors="replace")

        if media_type == "application/pdf" or lower.endswith(".pdf"):
            try:
                import pdfplumber
                with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                    return "\n".join(page.extract_text() or "" for page in pdf.pages)
            except ImportError:
                from pypdf import PdfReader
                reader = PdfReader(io.BytesIO(file_bytes))
                return "\n".join(page.extract_text() or "" for page in reader.pages)

        if lower.endswith(".docx"):
            try:
                import docx
                doc = docx.Document(io.BytesIO(file_bytes))
                return "\n".join(para.text for para in doc.paragraphs)
            except ImportError:
                logger.warning("python-docx not installed, cannot extract DOCX text")
                return ""

        return ""

    @staticmethod
    def _chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
        if not text.strip():
            return []
        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunks.append(text[start:end])
            start = end - overlap
        return chunks
