# Obsidian AI — AI Infrastructure Migration & Lightweight Architecture
## Scope & Impact Analysis Summary

**Date:** 2026-09-02  
**Status:** Architecture/discovery specification — implementation-ready handoff  
**Source:** Codebase documentation supplied for Obsidian AI, plus current official provider documentation checked for the proposed external services.

---

## 1. Executive Decision

The requested modernization is approved as a **provider migration and infrastructure-lightening exercise**, not a rewrite of the agent platform.

### Target architecture

| Capability | Current | Target |
|---|---|---|
| LLM generation | OpenAI + Anthropic + Google Gemini + local Ollama | **OpenAI + Anthropic + Google Gemini** |
| Speech-to-text | Local `faster-whisper` CPU | **Groq Whisper API** |
| Text-to-speech | Qwen3-TTS → Pocket TTS → Kokoro | **Google Cloud Text-to-Speech** |
| Embeddings | Local embedding path feeding FAISS/Leann | **Google Vertex AI Embeddings** |
| Vector storage/search | Local FAISS / Leann HNSW | **Qdrant Cloud Free Tier initially** |
| Agent/workflow engine | Existing | **Preserve** |
| WhatsApp bridge | Baileys sidecar | **Preserve** |
| Docker sandbox | Docker-based execution | **Preserve** |
| SQLite/Mongo persistence | Dual database architecture | **Preserve unless separately redesigned** |

The central design principle is:

> **Remove heavyweight local AI runtimes, not AI capabilities.**

The existing LLM provider abstraction must remain intact. Ollama is the only LLM provider being removed.

---

## 2. Evidence Base and Scope Boundary

The supplied documentation describes Obsidian AI as a Next.js 16 / React 19 frontend, FastAPI/Python 3.12 backend, dual SQLite/MongoDB persistence, a Node.js Baileys WhatsApp sidecar, Docker sandbox execution, an LLM provider factory, and local RAG infrastructure.

The documentation explicitly identifies:
- `backend/llm/provider_factory.py` as the dynamic provider resolver.
- `backend/llm/ollama_provider.py` as the local Ollama provider.
- `backend/services/whatsapp_service.py` as the WhatsApp message processor.
- `backend/services/tts_service.py` as the existing multi-engine TTS service.
- `backend/rag_service.py` as the FAISS/Leann vector-store manager.
- `knowledge_router.py` as the knowledge-base indexing entry point.

The documentation also states that WhatsApp audio is currently transcribed locally with `faster-whisper`, TTS uses Qwen3/Pocket/Kokoro, and RAG writes FAISS/Leann indexes to local disk.

**Important source limitation:** the supplied artifact is architecture/codebase documentation, not the actual repository source tree. Therefore this document identifies the affected implementation surface and required verification points; it does not claim that every reference has been found in source code.

---

# 3. Current Architecture

```text
                         User Browser
                              |
                         Next.js / SSE
                              |
                              v
                     FastAPI Backend
                              |
        +---------------------+----------------------+
        |                     |                      |
        v                     v                      v
   LLM Factory             RAG Engine          WhatsApp Service
        |                  FAISS/Leann                |
   +----+----+----+                                  v
   |    |    |    |                             Local STT
 OpenAI Claude Gemini Ollama                         |
                                                     v
                                                Local TTS
                                           Qwen/Pocket/Kokoro
                                                     |
                                                     v
                                               wa-bridge
                                                     |
                                                  WhatsApp
```

The current architecture places significant AI compute and model dependencies on the application host.

The target architecture moves those AI-heavy workloads to managed APIs:

```text
                         User Browser
                              |
                         Next.js / SSE
                              |
                              v
                     FastAPI Backend
                              |
       +----------+-----------+-----------+-------------+
       |          |                       |             |
       v          v                       v             v
   LLM Factory   RAG                 WhatsApp       Sandbox
       |          |                     |
 +-----+-----+    |                Groq Whisper
 |     |     |    |                     |
OpenAI Claude Gemini               Agent Runner
                  |                     |
           Vertex Embeddings       Google Cloud TTS
                  |                     |
               Qdrant Cloud <-----------+
```

---

# 4. Migration #1 — Speech-to-Text

## 4.1 Current behavior

The documented WhatsApp flow is:

```text
WhatsApp voice note
      ↓
Baileys / wa-bridge
      ↓
POST /wa/incoming
      ↓
whatsapp_service.py
      ↓
faster-whisper CPU
      ↓
transcribed text
      ↓
agent execution
```

The local `faster-whisper` runtime is therefore a direct source of CPU load, model storage, startup time, and deployment complexity.

## 4.2 Target behavior

```text
WhatsApp voice note
      ↓
wa-bridge
      ↓
/wa/incoming
      ↓
whatsapp_service.py
      ↓
STT provider abstraction
      ↓
Groq Whisper API
      ↓
transcript
      ↓
agent execution
```

Groq currently exposes OpenAI-compatible audio transcription endpoints and documents `whisper-large-v3` and `whisper-large-v3-turbo`. Supported input formats include common formats such as OGG, MP3, M4A, WAV and WebM. The API accepts an optional ISO-639-1 language, and `verbose_json` can provide timestamps. [Groq official documentation]

## 4.3 Required architectural change

Introduce a small STT service boundary rather than calling Groq directly from the WhatsApp router.

Recommended conceptual contract:

```text
SpeechToTextService
    transcribe(audio_bytes, mime_type, language?, prompt?)
        -> TranscriptResult
```

The implementation should own:
- API authentication
- temporary file/stream handling
- MIME/format normalization
- model selection
- language selection
- timeout
- retry policy
- provider errors
- usage logging
- transcript normalization

## 4.4 Affected components

### Backend
- `backend/services/whatsapp_service.py`
- `backend/routers/whatsapp_router.py` if audio processing currently leaks into the router
- `backend/config.py`
- dependency manifest
- environment configuration
- logging/observability
- tests/fixtures

### Removed dependencies
- `faster-whisper`
- Whisper model files/cache
- any local model-download/bootstrap logic
- CPU-specific transcription initialization

### Configuration
Add a dedicated Groq credential reference through the existing encrypted secrets mechanism where appropriate.

Potential configuration concepts:

```text
GROQ_API_KEY / encrypted secret
GROQ_STT_MODEL
GROQ_STT_TIMEOUT_SECONDS
GROQ_STT_LANGUAGE (optional)
```

The exact names should follow the project's existing configuration conventions.

## 4.5 Failure cases

The implementation must define behavior for:
- empty audio
- corrupt audio
- unsupported MIME type
- oversized audio
- API timeout
- rate limiting
- invalid API key
- provider outage
- transcription returning empty text
- unsupported language
- WhatsApp media download failure
- transient network failure

Recommended user/channel behavior:

```text
STT failure
   ↓
do not invoke agent with fabricated/empty input
   ↓
send a concise failure message
   ↓
record trace/error
```

---

# 5. Migration #2 — Text-to-Speech

## 5.1 Current behavior

The current WhatsApp TTS chain is:

```text
Agent response text
      ↓
tts_service.py
      ↓
Qwen3-TTS CUDA
      ↓ fallback
Pocket TTS CPU
      ↓ fallback
Kokoro CPU
      ↓
ffmpeg
      ↓
OGG Opus
      ↓
wa-bridge
```

This is one of the largest contributors to the application's local AI footprint.

## 5.2 Target behavior

```text
Agent response text
      ↓
tts_service.py
      ↓
Google Cloud Text-to-Speech
      ↓
audio bytes
      ↓
format normalization if required
      ↓
OGG/Opus WhatsApp payload
      ↓
wa-bridge
```

Google Cloud TTS accepts text or SSML and returns synthesized audio, with documented encodings including MP3 and LINEAR16. Google documents a REST `text:synthesize` endpoint and client libraries. [Google Cloud official documentation]

## 5.3 Architectural requirement

Keep `tts_service.py` as the stable service boundary, but replace the local engine-selection pipeline with a managed-provider implementation.

The service should expose concepts such as:

```text
synthesize(
    text,
    voice,
    language,
    speaking_rate?,
    pitch?,
    audio_format?
) -> AudioResult
```

The WhatsApp layer should not know which TTS provider is being used.

## 5.4 Remove

- Qwen3-TTS runtime
- GPU-specific TTS initialization
- Pocket TTS
- Kokoro
- model downloads
- local voice-model caches
- local voice-cloning dependencies
- local TTS fallback chain

The existing documentation specifically notes Qwen voice-clone sample support. That capability will **not automatically survive** the migration and must be treated as a deliberate feature decision. The target requirement currently specifies Google Cloud TTS, not voice cloning.

## 5.5 Audio compatibility requirement

WhatsApp delivery currently expects OGG Opus after ffmpeg conversion.

Therefore the migration must preserve:

```text
Google TTS output
        ↓
audio conversion/normalization
        ↓
OGG Opus
        ↓
Baileys
```

Do not remove ffmpeg until actual WhatsApp compatibility has been verified with the selected Google TTS output encoding.

## 5.6 Failure cases

- Google authentication failure
- quota exhaustion
- unavailable voice
- invalid language/voice combination
- text too long
- API timeout
- malformed audio
- ffmpeg conversion failure
- WhatsApp upload failure

TTS failure should degrade to **text response**, rather than causing the whole agent request to fail.

---

# 6. Migration #3 — Embeddings

## 6.1 Current behavior

The documented RAG service:

1. parses a document;
2. chunks it at 1000 characters with 150-character overlap;
3. generates local embeddings;
4. writes vectors to FAISS or Leann HNSW;
5. persists index files under `backend/data/rag_indices/`;
6. embeds user queries and performs top-K retrieval.

## 6.2 Target behavior

```text
Document
   ↓
chunking
   ↓
Vertex AI Embeddings
   ↓
embedding vector
   ↓
Qdrant collection
   ↓
metadata + source reference

Query
   ↓
Vertex AI Embeddings
   ↓
query vector
   ↓
Qdrant similarity search
   ↓
top-K chunks
   ↓
LLM context
```

## 6.3 Important embedding invariant

The same embedding model and dimensionality must be used consistently for:
- indexed document vectors
- query vectors
- re-index operations
- collection configuration

The migration must therefore define a fixed embedding model identifier and persist its identity/version with the knowledge-base indexing configuration.

## 6.4 RAG service redesign

`backend/rag_service.py` should evolve from a local-index manager into a provider-neutral RAG orchestration service.

Conceptual separation:

```text
RAG Service
   |
   +-- Chunker
   |
   +-- Embedding Provider
   |      └── Vertex AI
   |
   +-- Vector Store
          └── Qdrant
```

This prevents future replacement of Vertex or Qdrant from requiring a rewrite of the knowledge-base workflow.

---

# 7. Vector Storage Decision

## Recommendation: Qdrant Cloud Free Tier

Qdrant currently provides a free cloud tier intended for testing and prototypes. Its documented free cluster is a single node with 0.5 vCPU, 1 GB RAM and 4 GB disk, with no credit card required to create a free cluster. Qdrant states that this configuration can support approximately 1 million 768-dimensional vectors, depending on workload and capacity requirements. Free clusters are automatically suspended after one week of inactivity and deleted after four weeks if not reactivated. [Qdrant official documentation]

This makes Qdrant a strong match for the stated requirement:

> **Start for free without running a local vector database/model runtime.**

### Why Qdrant over the alternatives

| Option | Advantages | Concern |
|---|---|---|
| **Qdrant Cloud Free** | Dedicated vector DB, HNSW/vector-native, free starting tier, small operational footprint | Adds one managed service |
| Supabase pgvector | Free Postgres tier; vectors live beside relational data | Adds/introduces Postgres and is less specialized for the existing architecture |
| Pinecone | Mature managed vector platform | Free-tier economics/features should be checked against workload |
| Local FAISS | No external service cost | Directly conflicts with the goal of removing local AI/RAG infrastructure |

Supabase currently documents pgvector support and a free Postgres tier with 500 MB database storage, but this would introduce a Postgres dependency into a system already documented as SQLite/MongoDB. [Supabase official documentation]

### Architectural conclusion

Use:

```text
Qdrant Cloud
    ↓
VectorStore interface
    ↓
RAG service
```

Do **not** expose Qdrant APIs throughout the application.

---

# 8. Existing RAG Data Migration

This is a critical migration item.

Existing FAISS/Leann indexes cannot simply be reused by Qdrant.

A re-index process is required:

```text
Existing Knowledge Base Documents
             ↓
       extract original text
             ↓
        re-chunk documents
             ↓
     Vertex AI embeddings
             ↓
       Qdrant upsert
             ↓
       verify counts/search
             ↓
    mark KB migration complete
```

## Required migration metadata

Each indexed chunk should retain enough information to reconstruct retrieval context, including:

- knowledge-base ID
- document ID
- chunk ID
- source filename/reference
- chunk text or retrievable source pointer
- embedding model
- embedding dimension
- chunk ordering
- optional page/section metadata
- created/updated timestamps

## Backward compatibility

Do not delete local indexes until:

1. all knowledge bases have been re-indexed;
2. vector counts have been validated;
3. representative retrieval tests pass;
4. production traffic is confirmed against Qdrant;
5. rollback criteria are defined.

---

# 9. Migration #4 — Remove Ollama

## Confirmed decision

**Keep the existing multi-provider LLM system and remove only Ollama.**

The target LLM factory is:

```text
LLM Factory
   ├── OpenAI
   ├── Anthropic
   └── Google Gemini
```

The provider abstraction itself must remain.

## 9.1 Direct removal

Documented file:

```text
backend/llm/ollama_provider.py
```

This file becomes removable once all imports/references have been eliminated.

## 9.2 Required reference sweep

Search the entire repository for:

```text
ollama
Ollama
OLLAMA
ollama_provider
localhost:11434
11434
OLLAMA_HOST
OLLAMA_BASE_URL
```

Also search:
- provider enums
- provider validation
- model lists
- provider factory branches
- health checks
- startup checks
- environment templates
- Docker Compose
- Dockerfiles
- CI/CD
- scripts
- seed data
- fixtures
- tests
- frontend provider selectors
- agent creation/edit forms
- analytics/cost tables
- documentation
- README
- deployment instructions

## 9.3 Provider factory

The factory should transition conceptually from:

```text
OpenAI
Anthropic
Google
Ollama
```

to:

```text
OpenAI
Anthropic
Google
```

No consumer should need to change its provider-resolution interface.

## 9.4 Existing persisted configurations

This is a critical edge case.

Agents may already contain:

```text
provider = "ollama"
model = "..."
```

The application must define a deterministic migration behavior.

Recommended behavior:

```text
existing Ollama agent
       ↓
marked "migration required"
       ↓
not silently switched to another model
       ↓
admin/user chooses OpenAI / Anthropic / Gemini
```

Silently changing an agent's model could change behavior unexpectedly.

If a database migration is desired later, it should be a separate explicit migration task.

---

# 10. Frontend Impact

The frontend does not directly call STT, TTS, embeddings, or Ollama.

However, it may expose configuration and provider-selection UI.

## Required audit areas

### Provider UI

Search for:
- Ollama provider labels
- Ollama model selectors
- Ollama connection status
- Ollama-specific forms
- Ollama icons/badges
- local endpoint configuration

Remove only Ollama-specific UI.

Preserve:
- OpenAI
- Anthropic
- Google Gemini
- generic provider abstraction

### Agent configuration

Any provider dropdown must no longer allow:

```text
Ollama
```

### Knowledge UI

The knowledge page should continue to present:
- document upload
- indexing
- retrieval status
- document deletion
- knowledge-base association

The implementation should not expose Qdrant implementation details unless operational diagnostics are intentionally added.

### WhatsApp UI

The WhatsApp channel configuration should preserve:

```text
voice_reply_enabled
```

The user-facing feature should remain "voice replies", not become "Google TTS".

---

# 11. Secrets and Credential Management

The documentation states that LLM provider configuration uses `secret_id` referencing encrypted secrets in `user_secrets`.

The new managed services should follow the same secret-management architecture where practical.

## Credentials

Required external credentials:

```text
Groq
 └── API credential

Google Cloud
 ├── Vertex AI credential
 └── Cloud TTS credential

Qdrant
 └── cluster URL + API key
```

## Security requirements

- Never expose provider API keys to the Next.js browser.
- Keep credentials server-side.
- Prefer the existing encrypted secret vault.
- Do not log credentials.
- Redact authorization headers.
- Separate credentials by environment.
- Rotate credentials without code changes.
- Apply least-privilege Google Cloud IAM.
- Apply least-privilege Qdrant API credentials where supported.

---

# 12. Dependency Footprint Reduction

## Remove

Expected heavyweight local AI dependencies include:

```text
faster-whisper
Qwen3-TTS
Pocket TTS
Kokoro
local embedding model/runtime
FAISS
Leann
Ollama integration
```

The exact Python package names must be confirmed from the actual dependency files before deletion.

## Preserve

```text
FastAPI
SQLAlchemy
Motor
LLM provider SDKs
Docker SDK
APScheduler
Baileys
MCP dependencies
sandbox dependencies
```

The objective is not to minimize package count blindly; it is to eliminate **model runtimes, model weights, local vector indexes, GPU requirements, and heavyweight AI execution**.

---

# 13. Deployment Impact

## Before

The application host may need:

```text
CPU
large model storage
Whisper model
TTS models
embedding model
FAISS/Leann indexes
GPU for Qwen TTS
ffmpeg
Ollama runtime
```

## After

The main host should require only:

```text
Application runtime
database connectivity
Docker sandbox capability
ffmpeg if WhatsApp audio conversion still requires it
network access to:
  - Groq
  - Google Cloud
  - Qdrant Cloud
```

### Expected operational simplification

- no GPU requirement for TTS
- no local Whisper model
- no local TTS model
- no local embedding model
- no Ollama daemon
- no FAISS index lifecycle
- no Leann index lifecycle
- reduced image/model storage
- faster deployment/bootstrap
- less host RAM/CPU pressure

---

# 14. WhatsApp End-to-End Target Flow

## Text message

```text
WhatsApp
  ↓
Baileys
  ↓
wa-bridge
  ↓
/wa/incoming
  ↓
whatsapp_service
  ↓
Agent / LLM Factory
  ↓
OpenAI / Anthropic / Gemini
  ↓
Response
  ↓
wa-bridge
  ↓
WhatsApp
```

## Voice message

```text
WhatsApp voice note
        ↓
     Baileys
        ↓
    wa-bridge
        ↓
 /wa/incoming
        ↓
whatsapp_service
        ↓
   Groq Whisper
        ↓
   transcript
        ↓
   Agent runner
        ↓
 LLM Factory
        ↓
OpenAI / Anthropic / Gemini
        ↓
 response text
        ↓
 Google Cloud TTS
        ↓
 audio bytes
        ↓
 ffmpeg/normalizer
        ↓
   OGG Opus
        ↓
    wa-bridge
        ↓
    WhatsApp
```

---

# 15. RAG End-to-End Target Flow

## Indexing

```text
Upload document
      ↓
knowledge_router
      ↓
document parser
      ↓
chunker
      ↓
Vertex AI Embeddings
      ↓
Qdrant
      ↓
index metadata
```

## Retrieval

```text
User query
   ↓
Vertex AI Embeddings
   ↓
Qdrant similarity search
   ↓
top-K chunks
   ↓
context assembly
   ↓
LLM Factory
   ↓
response
```

---

# 16. Cross-Cutting Reliability Requirements

Managed services introduce network dependencies that local models did not have.

Every provider integration should therefore support:

### Timeouts
No external AI request should be allowed to hang an agent indefinitely.

### Retry policy
Retry only transient failures.

Avoid retrying:
- invalid credentials
- malformed requests
- unsupported models
- invalid input

### Rate limiting
Provider rate limits must be surfaced distinctly from application rate limits.

### Circuit breaking
Repeated provider failures should avoid continuously hammering an unavailable service.

### Observability

Trace:

```text
provider
operation
model
latency
success/failure
error class
request ID if safe
usage metadata where available
```

Never store raw credentials.

### Fallback policy

The architecture should distinguish between:

```text
LLM fallback
STT fallback
TTS fallback
Embedding fallback
Vector-store fallback
```

They are not interchangeable.

For example:

```text
TTS unavailable
→ send text

STT unavailable
→ ask sender to resend as text

Embedding unavailable
→ knowledge search unavailable

Qdrant unavailable
→ RAG unavailable but ordinary chat may continue

LLM unavailable
→ agent request cannot complete unless another configured LLM provider is intentionally selected
```

---

# 17. Cost and Usage Tracking

The current platform has analytics and token-cost tracking.

The migration should extend observability to non-LLM AI services.

Recommended usage dimensions:

```text
LLM
  input tokens
  output tokens
  model
  provider

STT
  audio duration
  model
  provider

TTS
  characters/text units
  voice/model
  provider

Embeddings
  input tokens/text units
  model
  provider

Vector DB
  request count
  storage
  collection size
```

Do not assume all providers have identical billing metrics.

---

# 18. Configuration Model

Recommended conceptual configuration:

```text
AI Providers
├── LLM
│   ├── OpenAI
│   ├── Anthropic
│   └── Google Gemini
│
├── Speech
│   ├── STT: Groq Whisper
│   └── TTS: Google Cloud TTS
│
└── Retrieval
    ├── Embeddings: Vertex AI
    └── Vector Store: Qdrant
```

This is preferable to scattering provider-specific environment variables throughout the codebase.

---

# 19. Database / Persistence Impact

No core application database migration is inherently required merely to change providers.

However, provider metadata may exist in persisted agent, settings, knowledge-base, or integration records.

Audit for:

```text
provider
model
embedding_model
vector_store
tts_engine
stt_engine
```

## Required compatibility check

Any persisted Ollama configuration must be detected.

Any persisted references to:
- FAISS index paths
- Leann indexes
- local embedding model names
- local TTS engines
- local STT engines

must be migrated or invalidated deliberately.

---

# 20. Knowledge Base Migration Strategy

Recommended phased strategy:

### Phase A — Dual-read validation

Continue existing local index while building Qdrant indexes.

```text
Document
 ├── local index
 └── Qdrant
```

Run retrieval comparisons.

### Phase B — Qdrant primary

```text
Document
   ↓
Vertex
   ↓
Qdrant
```

Use Qdrant for production retrieval.

### Phase C — Remove local vector stack

Delete:
- FAISS
- Leann
- local index directory
- index-management code
- associated dependencies

Only after successful migration.

---

# 21. Testing Matrix

## STT

- English voice note
- multilingual voice note
- noisy audio
- short audio
- long audio
- silent audio
- malformed audio
- unsupported format
- provider timeout
- provider rate limit
- invalid credential

## TTS

- short reply
- long reply
- punctuation
- numbers
- Nigerian English usage
- supported/unsupported voice
- supported/unsupported language
- API failure
- audio conversion failure
- WhatsApp playback

## Embeddings

- new KB indexing
- multiple documents
- empty document
- duplicate document
- large document
- query retrieval
- top-K ordering
- metadata filtering
- embedding dimension mismatch
- provider failure

## Qdrant

- collection creation
- upsert
- search
- deletion
- KB isolation
- user isolation
- empty collection
- unavailable cluster
- API key failure
- free-tier suspension behavior

## Ollama removal

- provider list
- agent creation
- agent edit
- existing Ollama agent
- provider validation
- frontend selectors
- backend factory
- deployment startup
- CI tests
- Docker environment

## Regression

- standard chat
- streaming
- tools
- HITL
- workflows
- scheduled workflows
- memory
- optimizer
- eval harness
- MCP
- sandbox
- WhatsApp text
- WhatsApp voice
- authentication

---

# 22. Acceptance Criteria

The migration is complete when all of the following are true.

## Ollama

- [ ] No Ollama provider appears in the UI.
- [ ] Provider factory supports OpenAI, Anthropic and Google only.
- [ ] Ollama runtime/configuration is absent from deployment.
- [ ] Ollama-specific dependencies are removed.
- [ ] Existing Ollama configurations are detected and handled explicitly.
- [ ] No runtime code references Ollama.

## STT

- [ ] WhatsApp voice notes use Groq Whisper.
- [ ] Local Whisper models are no longer downloaded or loaded.
- [ ] Transcription errors are handled gracefully.
- [ ] Audio input normalization remains reliable.

## TTS

- [ ] Voice replies use Google Cloud TTS.
- [ ] Qwen3/Pocket/Kokoro are removed.
- [ ] Voice responses remain compatible with WhatsApp.
- [ ] TTS failure degrades to text response.

## Embeddings

- [ ] Vertex AI is the only production embedding provider.
- [ ] Embedding model/dimension is explicit.
- [ ] Query and document embeddings are compatible.
- [ ] API failures are observable.

## Vector storage

- [ ] Qdrant Cloud is used for vector storage/search.
- [ ] Knowledge-base isolation is enforced.
- [ ] Local FAISS/Leann indexes are no longer required in production.
- [ ] Existing knowledge bases have a re-index path.
- [ ] Qdrant credentials are server-side only.

## Lightweight deployment

- [ ] No GPU is required for the application AI stack.
- [ ] No local AI model weights are required.
- [ ] No Ollama daemon is required.
- [ ] Local vector indexes are removed after migration.
- [ ] Startup is not blocked by model downloads.

---

# 23. Implementation Work Breakdown

## Workstream A — Provider Abstractions

1. Audit `backend/llm/base.py`.
2. Audit `provider_factory.py`.
3. Remove Ollama provider implementation.
4. Remove Ollama provider registration.
5. Preserve OpenAI/Anthropic/Google interfaces.
6. Audit all provider validation.
7. Audit frontend provider lists.

## Workstream B — STT

1. Introduce provider-neutral STT service.
2. Integrate Groq.
3. Move WhatsApp transcription through service.
4. Add configuration/secrets.
5. Add timeout/retry/error mapping.
6. Remove local Whisper runtime.
7. Add integration tests.

## Workstream C — TTS

1. Preserve `tts_service.py` boundary.
2. Implement Google Cloud TTS backend.
3. Define voice/language configuration.
4. Preserve WhatsApp audio contract.
5. Validate OGG/Opus conversion.
6. Remove local TTS engines.
7. Add graceful text fallback.

## Workstream D — RAG

1. Refactor `rag_service.py`.
2. Separate chunking, embedding and vector storage.
3. Integrate Vertex AI embeddings.
4. Integrate Qdrant.
5. Implement collection/tenant/KB isolation.
6. Implement re-indexing.
7. Validate retrieval quality.
8. Remove FAISS/Leann.

## Workstream E — Deployment

1. Remove model download scripts.
2. Remove Ollama service.
3. Remove GPU dependencies.
4. Remove model caches/volumes.
5. Add external-service credentials.
6. Verify production network egress.
7. Reduce container image footprint.

## Workstream F — Observability

1. Add provider operation tracing.
2. Add latency/error metrics.
3. Add usage metrics.
4. Add provider request IDs where appropriate.
5. Add cost/usage reporting.
6. Add alerts for external-service failures.

---

# 24. Files / Areas Expected to Change

| Area | Expected action | Priority |
|---|---|---:|
| `backend/llm/ollama_provider.py` | Remove | P0 |
| `backend/llm/provider_factory.py` | Remove Ollama branch | P0 |
| `backend/llm/base.py` | Preserve abstraction; verify provider contract | P0 |
| `backend/services/whatsapp_service.py` | Route STT through Groq service | P0 |
| `backend/services/tts_service.py` | Replace local engines with Google TTS | P0 |
| `backend/rag_service.py` | Replace local embedding/vector flow | P0 |
| `backend/routers/knowledge_router.py` | Integrate new RAG lifecycle | P0 |
| `backend/config.py` | Add external service configuration | P0 |
| `backend/routers/providers_router.py` | Remove Ollama exposure | P0 |
| Frontend provider configuration | Remove Ollama UI | P0 |
| Dependencies | Remove local AI stacks; add managed API SDKs | P0 |
| Docker/deployment | Remove Ollama/GPU/model assets | P0 |
| Knowledge migration tooling | Re-index into Qdrant | P0 |
| Analytics | Add STT/TTS/embedding usage | P1 |
| Tests | Add provider and regression coverage | P0 |
| Documentation | Update architecture/deployment instructions | P1 |

---

# 25. Non-Goals

This migration does **not** authorize:

- rewriting the agent engine;
- replacing FastAPI;
- replacing Next.js;
- replacing SQLite/MongoDB;
- replacing Baileys;
- removing Docker sandboxing;
- removing MCP;
- removing workflows;
- removing memory;
- removing tools;
- removing HITL;
- removing Claude Skills;
- removing OpenAI;
- removing Anthropic;
- removing Google Gemini;
- redesigning authentication.

The goal is specifically to replace heavyweight local AI infrastructure with managed services.

---

# 26. Risks

### High

**Existing local RAG indexes.**  
They must be re-embedded and migrated.

**Persisted Ollama agents.**  
Existing configurations can become unusable if removal is handled as a simple code deletion.

**WhatsApp audio compatibility.**  
Google TTS output must still arrive at Baileys in a compatible audio format.

**External API availability.**  
The system becomes network-dependent for STT, TTS, embeddings and vector search.

### Medium

**Embedding quality changes.**  
Retrieval quality may differ after changing embedding models.

**Voice quality changes.**  
Google TTS will not be acoustically identical to Qwen/Pocket/Kokoro.

**Cost visibility.**  
The analytics system must account for usage dimensions beyond LLM tokens.

### Low

**Frontend impact.**  
Most UI functionality remains unchanged except provider configuration.

---

# 27. Recommended Rollout

```text
                    ┌──────────────────────┐
                    │ 1. Remove Ollama     │
                    │ from provider layer  │
                    └──────────┬───────────┘
                               ↓
                    ┌──────────────────────┐
                    │ 2. Groq STT          │
                    │ WhatsApp validation  │
                    └──────────┬───────────┘
                               ↓
                    ┌──────────────────────┐
                    │ 3. Google TTS        │
                    │ WhatsApp validation  │
                    └──────────┬───────────┘
                               ↓
                    ┌──────────────────────┐
                    │ 4. Vertex Embeddings │
                    │ + Qdrant indexing    │
                    └──────────┬───────────┘
                               ↓
                    ┌──────────────────────┐
                    │ 5. RAG migration     │
                    │ and retrieval tests  │
                    └──────────┬───────────┘
                               ↓
                    ┌──────────────────────┐
                    │ 6. Remove local AI   │
                    │ dependencies/assets  │
                    └──────────┬───────────┘
                               ↓
                    ┌──────────────────────┐
                    │ 7. Full regression   │
                    │ + deployment test    │
                    └──────────────────────┘
```

---

# 28. Final Target State

```text
                         OBSIDIAN AI
                              |
             +----------------+----------------+
             |                |                |
             v                v                v
         Frontend          FastAPI          wa-bridge
                             |
          +------------------+------------------+
          |                  |                  |
          v                  v                  v
      LLM Factory           RAG             WhatsApp
          |                  |                  |
    +-----+-----+       +----+----+        +----+----+
    |     |     |       |         |        |         |
 OpenAI Claude Gemini Vertex    Qdrant    Groq      Google
                     Embeddings Cloud    Whisper     TTS
          |
       Agents
          |
   +------+------+------+
   |      |      |      |
 Tools  MCP   Sandbox  Workflows
```

The resulting platform keeps the existing orchestration capabilities while removing the principal local AI workloads.

---

# 29. Handoff Summary

### Approved changes

1. **STT → Groq Whisper API**
2. **TTS → Google Cloud TTS**
3. **Embeddings → Google Vertex AI Embeddings**
4. **Vector store → Qdrant Cloud Free Tier initially**
5. **Remove Ollama only**
6. **Preserve OpenAI + Anthropic + Google Gemini**
7. **Preserve the LLM provider abstraction**
8. **Preserve agent/workflow/MCP/sandbox/WhatsApp functionality**
9. **Remove heavyweight local AI model runtimes**
10. **Re-index existing knowledge bases into the new vector store**

### Architecture principle

> **Managed AI services at the edges; lightweight orchestration at the core.**

### Critical implementation caveat

This analysis is based on the supplied codebase documentation. Before source modification, perform a repository-wide reference/dependency sweep and verify every file, import, environment variable, Docker service, persisted configuration, and UI reference identified above against the actual repository.

---

## 30. External References

- Groq Speech-to-Text documentation: https://console.groq.com/docs/speech-to-text
- Google Cloud Text-to-Speech documentation: https://docs.cloud.google.com/text-to-speech/docs
- Qdrant Cloud pricing/free tier: https://qdrant.tech/pricing/
- Qdrant Cloud cluster documentation: https://qdrant.tech/documentation/cloud/create-cluster/
- Supabase pgvector documentation: https://supabase.com/docs/guides/database/extensions/pgvector
