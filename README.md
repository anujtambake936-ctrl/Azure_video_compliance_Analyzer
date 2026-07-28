# Video Compliance Analyzer

An agentic AI pipeline that audits YouTube videos for brand and regulatory compliance. It downloads a video, extracts its transcript and on-screen text using Azure Video Indexer, retrieves relevant compliance rules from a knowledge base using RAG, and produces a structured compliance report via an LLM.

---

## How It Works

```
YouTube URL
    │
    ▼
┌─────────────────────────┐
│  Node 1: Video Indexer  │  yt-dlp download → Azure Video Indexer
│                         │  → transcript + OCR text extraction
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│  Node 2: Auditor        │  RAG retrieval from Azure AI Search
│                         │  → GPT compliance audit
│                         │  → structured JSON report
└─────────────────────────┘
             │
             ▼
  Compliance Report (PASS / FAIL)
  Risk Score · Violations · Summary
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Orchestration | LangGraph (StateGraph) |
| LLM | Azure OpenAI (GPT) |
| Embeddings | Azure OpenAI (text-embedding-3-small) |
| Knowledge Base | Azure AI Search (vector store) |
| Video Processing | Azure Video Indexer |
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
│       │   ├── workflow.py          # LangGraph DAG definition
│       │   ├── nodes.py             # Node 1 (indexer) + Node 2 (auditor) logic
│       │   └── state.py             # VideoAuditState TypedDict schema
│       └── services/
│           └── video_indexer.py     # Azure Video Indexer service wrapper
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
- The following Azure services provisioned:
  - Azure OpenAI (chat + embedding deployments)
  - Azure AI Search
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

**4. Populate the knowledge base (run once)**

This indexes the compliance PDFs in `backend/data/` into Azure AI Search:

```bash
uv run python -m backend.scripts.index_documents
```

You should see:
```
INFO - Indexing complete! Knowledge base is ready.
INFO - Total chunks indexed: 37
```

---

## Running

### CLI (local test)

Runs a single audit against the hardcoded YouTube URL in `main.py`:

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
| `POST` | `/audit` | Submit a YouTube URL for compliance audit |

**Example audit request:**

```bash
curl -X POST http://localhost:8000/audit \
  -H "Content-Type: application/json" \
  -d '{"video_url": "https://youtu.be/YOUR_VIDEO_ID"}'
```

**Example response:**

```json
{
  "session_id": "14037395-...",
  "video_id": "vid_14037395",
  "status": "FAIL",
  "risk_score": 76,
  "video_summary": "A presenter introduces John Cena as the new face of Neutrogena...",
  "compliance_results": [
    {
      "severity": "CRITICAL",
      "category": "Endorsement Disclosure",
      "description": "Celebrity endorsement present but no paid partnership disclosure found."
    }
  ],
  "retrieved_rules": ["...rule chunk 1...", "...rule chunk 2..."],
  "final_report": "The video contains a clear celebrity product endorsement...",
  "errors": []
}
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

When `APPLICATION_INSIGHTS_CONNECTION_STRING` is set, the API server automatically sends telemetry to Azure Monitor via OpenTelemetry — including HTTP request traces, latency metrics, and error logs. LangSmith tracing captures the full LangGraph execution trace when `LANGCHAIN_API_KEY` is set.
