import os

# use as a second param "sqlite" or "mongo"
DATABASE_TYPE = os.getenv("DATABASE_TYPE", "sqlite")

# Speech-to-Text Config (Groq Whisper API)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_STT_MODEL = os.getenv("GROQ_STT_MODEL", "whisper-large-v3-turbo")
GROQ_STT_TIMEOUT_SECONDS = int(os.getenv("GROQ_STT_TIMEOUT_SECONDS", "30"))
GROQ_STT_LANGUAGE = os.getenv("GROQ_STT_LANGUAGE", None)

# Text-to-Speech Config (Google Cloud Text-to-Speech)
GOOGLE_TTS_API_KEY = os.getenv("GOOGLE_TTS_API_KEY", "")
GOOGLE_TTS_LANGUAGE_CODE = os.getenv("GOOGLE_TTS_LANGUAGE_CODE", "en-US")
GOOGLE_TTS_VOICE_NAME = os.getenv("GOOGLE_TTS_VOICE_NAME", "en-US-Journey-F")

# Vector Store / RAG Config (Google Vertex Embeddings + Qdrant Cloud)
QDRANT_URL = os.getenv("QDRANT_URL", "")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")
QDRANT_COLLECTION_NAME = os.getenv("QDRANT_COLLECTION_NAME", "obsidian_rag")
GOOGLE_EMBEDDING_MODEL = os.getenv("GOOGLE_EMBEDDING_MODEL", "text-embedding-004")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
