# Video Compliance Analyzer

An end-to-end prototype pipeline that audits YouTube videos for brand and regulatory compliance. It supports a fast Azure AI Speech route and a detailed Azure Video Indexer route, retrieves relevant compliance rules with RAG, and produces a structured report with Azure OpenAI.

---

## How It Works

```
YouTube URL
  │
  ├── Fast mode: yt-dlp → ffmpeg → Azure AI Speech
  │
  └── Full mode: yt-dlp → Azure Video Indexer → transcript + OCR
                │
                ▼
         Azure AI Search RAG → Azure OpenAI audit
                │
                ▼
         Compliance report, risk score, and findings
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Orchestration | LangGraph (StateGraph) |
| LLM | Azure OpenAI (GPT) |
| Embeddings | Azure OpenAI (text-embedding-3-small) |
| Knowledge Base | Azure AI Search (vector store) |
| Fast Transcription | Azure AI Speech |
| Detailed Video Analysis | Azure Video Indexer |
| Video Download | yt-dlp |
| API Server | FastAPI |
| Observability | Azure Monitor / OpenTelemetry |
| Tracing | LangSmith |
| Package Manager | uv |

---

## Project Structure

```
video-compliance-analyzer/
├── backend/
│   ├── data/                        # Compliance PDFs for the knowledge base
│   │   ├── 1001a-influencer-guide-508_1.pdf
│   │   └── youtube-ad-specs.pdf
│   ├── scripts/
│   │   └── index_documents.py       # One-time script to populate Azure AI Search
│   └── src/
│       ├── api/
│       │   ├── server.py            # FastAPI server with /audit and /health endpoints
│       │   └── telemetry.py         # Azure Monitor OpenTelemetry setup
│       ├── graph/
│       │   ├── workflow.py          # Full Video Indexer graph
│       │   ├── workflow_fast.py     # Fast Azure Speech graph
│       │   ├── nodes.py             # Full-mode nodes
│       │   ├── nodes_fast.py        # Fast-mode nodes
│       │   └── state.py             # VideoAuditState TypedDict schema
│       └── services/
│           ├── video_indexer.py     # YouTube download and Video Indexer API
│           ├── azure_speech_transcriber.py # ffmpeg and Azure Speech
│           └── video_cache.py       # Mode-specific local result cache
├── main.py                          # CLI runner for local testing
├── pyproject.toml                   # Dependencies (managed with uv)
├── .env.example                     # Environment variable template
└── .gitignore
```

---

## Prerequisites

- Python 3.14+
- [uv](https://docs.astral.sh/uv/getting-started/installation/) package manager
- Azure CLI installed and logged in (`az login`)
- `ffmpeg` installed and available on `PATH` when using fast Azure Speech mode
- The following Azure services provisioned:
  - Azure OpenAI (chat + embedding deployments)
  - Azure AI Search
  - Azure AI Speech resource for fast mode
  - Azure Video Indexer
  - Azure Monitor / Application Insights (optional, for telemetry)

---

## Setup

**1. Clone the repo**

```bash
git clone https://github.com/YOUR_USERNAME/video-compliance-analyzer.git
cd video-compliance-analyzer
```

**2. Install dependencies**

```bash
uv sync
```

**3. Configure environment variables**

```bash
cp .env.example .env
```

Fill in all values in `.env`. See the [Environment Variables](#environment-variables) section below.

On Windows, install ffmpeg with `winget install Gyan.FFmpeg` and restart the terminal so the `ffmpeg` command is available.

**4. Populate the knowledge base (run once)**

This indexes the compliance PDFs in `backend/data/` into Azure AI Search:

```bash
uv run python -m backend.scripts.index_documents
```

The number of indexed chunks depends on the PDFs in `backend/data/`.

---

## Running

### Performance Mode Toggle

The pipeline supports two modes:

| Mode | Transcription | Time (First Run) | Time (Cached) | OCR | Advanced Features |
|---|---|---|---|---|---|
| **Fast** (Azure Speech) | Azure AI Speech | **20–60s** | ~15s | ❌ No | ❌ No |
| **Full** (Azure VI) | Azure Video Indexer | 5–10 min | ~15s | ✅ Yes | ✅ Speaker diarization, topics, brands |

Set in `.env`:
```env
USE_FAST_TRANSCRIPTION=true   # Fast mode (20-60s)
USE_FAST_TRANSCRIPTION=false  # Full mode (5-10min, default)
```

Use fast mode for lower-latency transcript-based audits. Use full mode when OCR and advanced video insights are required.

---

### CLI (local test)

Runs a single audit against the hardcoded YouTube URL in `main.py`. The selected route follows `USE_FAST_TRANSCRIPTION`:

```bash
uv run python main.py
```

### API Server

```bash
uv run uvicorn backend.src.api.server:app --reload --port 8000
```

**Endpoints:**

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Check service status and missing env vars |
| `POST` | `/audit` | Submit a YouTube URL for audit (returns job_id immediately) |
| `GET` | `/audit/{job_id}` | Poll for audit status and result |
| `DELETE` | `/audit/{job_id}` | Delete a completed job |

**Example audit flow:**

```bash
# 1. Submit audit (returns immediately)
curl -X POST http://localhost:8000/audit \
  -H "Content-Type: application/json" \
  -d '{"video_url": "https://youtu.be/YOUR_VIDEO_ID"}' \
  | jq .

# Response:
# {
#   "job_id": "abc123-...",
#   "status": "pending",
#   "message": "Audit job submitted. Use GET /audit/{job_id} to check status."
# }

# 2. Poll for status (repeat until status is "completed" or "failed")
curl http://localhost:8000/audit/abc123-... | jq .

# While processing:
# {
#   "job_id": "abc123-...",
#   "status": "processing",
#   "video_url": "https://youtu.be/...",
#   "created_at": "2026-07-28T10:00:00",
#   "completed_at": null,
#   "result": null
# }

# When complete:
# {
#   "job_id": "abc123-...",
#   "status": "completed",
#   "video_url": "https://youtu.be/...",
#   "created_at": "2026-07-28T10:00:00",
#   "completed_at": "2026-07-28T10:08:15",
#   "result": {
#     "status": "FAIL",
#     "risk_score": 76,
#     "compliance_results": [...],
#     ...
#   }
# }
```

---

## Environment Variables

Copy `.env.example` to `.env` and fill in:

```env
# Azure OpenAI
AZURE_OPENAI_ENDPOINT=https://<your-resource>.services.ai.azure.com/
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_API_VERSION=2025-04-01-preview
AZURE_OPENAI_CHAT_DEPLOYMENT=           # e.g. gpt-4o
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-small

# Azure AI Speech (required for fast mode)
AZURE_SPEECH_ENDPOINT=https://<region>.stt.speech.microsoft.com
AZURE_SPEECH_KEY=
AZURE_SPEECH_REGION=
AZURE_SPEECH_LANGUAGE=en-US

# Azure AI Search
AZURE_SEARCH_ENDPOINT=https://<your-search-service>.search.windows.net
AZURE_SEARCH_API_KEY=
AZURE_SEARCH_INDEX_NAME=brand-compliance-rules

# Azure Video Indexer
AZURE_VI_NAME=
AZURE_VI_LOCATION=                      # e.g. eastus
AZURE_VI_ACCOUNT_ID=
AZURE_SUBSCRIPTION_ID=
AZURE_RESOURCE_GROUP=

# Azure Monitor (optional)
APPLICATION_INSIGHTS_CONNECTION_STRING=

# LangSmith tracing (optional)
LANGCHAIN_TRACING_V2=true
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
LANGCHAIN_API_KEY=
LANGCHAIN_PROJECT=video-compliance-analyzer
```

---

## Adding More Compliance Documents

Drop additional PDFs into `backend/data/` and re-run the indexing script:

```bash
uv run python -m backend.scripts.index_documents
```

The new content will be chunked and added to the existing Azure AI Search index.

---

## Observability

When `APPLICATION_INSIGHTS_CONNECTION_STRING` is set, the API server initializes Azure Monitor OpenTelemetry. LangSmith tracing is optional and is enabled when its environment variables are configured.

---

## Performance & Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for:
- Async job queue architecture (202 Accepted pattern)
- Video processing cache (instant results for repeat audits)
- Docker / Azure Container Apps / AKS deployment guides
- Production checklist and monitoring setup
- Cost estimates and scaling strategies

## Prototype Scope

This is a working demonstration pipeline, not a production-ready service. The current API uses an in-memory job store, has limited test coverage, and requires production hardening such as authentication, rate limiting, durable job storage, managed identity, secret management, and long-video Speech handling.
