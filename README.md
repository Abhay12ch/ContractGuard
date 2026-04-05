# ContractGuard AI 🛡️

> **AI-powered contract intelligence platform** — upload any contract and instantly get risk analysis, metadata extraction, vendor verification, interactive Q&A, and digital signature verification.

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/FastAPI-0.100+-009688?style=for-the-badge&logo=fastapi&logoColor=white" />
  <img src="https://img.shields.io/badge/React-19-61DAFB?style=for-the-badge&logo=react&logoColor=black" />
  <img src="https://img.shields.io/badge/Gemini_2.5_Pro-AI-4285F4?style=for-the-badge&logo=google&logoColor=white" />
  <img src="https://img.shields.io/badge/MongoDB_Atlas-47A248?style=for-the-badge&logo=mongodb&logoColor=white" />
</p>

---

## ✨ What is ContractGuard?

ContractGuard is a full-stack AI application that acts as your personal contract lawyer. Upload a PDF or DOCX file (or paste raw text) and ContractGuard will:

- 🔍 **Detect risky clauses** using a hybrid Gemini LLM + deterministic keyword scanner
- 📊 **Score your contract** using an ISO 31000 / NIST 800-30 compliant risk model
- 🏢 **Verify the vendor** with an AI-powered Know-Your-Business (KYB) assessment
- 📋 **Extract structured metadata** (parties, dates, payment terms, governing law)
- 💬 **Answer questions** about your contract in natural language (RAG + FAISS)
- ⚖️ **Compare two contracts** side-by-side with AI-generated diffs
- ✍️ **Verify digital signatures** via Zoho Sign integration (OAuth 2.0)

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────┐
│      React 19 + Vite Frontend (:5173)    │
│      TailwindCSS · TanStack Query        │
│  AnalyzeView · ContractsView · Compare   │
└──────────────────┬───────────────────────┘
                   │  REST API (JSON)
┌──────────────────▼───────────────────────┐
│       FastAPI Backend (:8000)            │
│                                          │
│  ┌─────────────┐  ┌────────────────────┐ │
│  │ Gemini 2.5  │  │  Async Indexing    │ │
│  │ Summarizer  │  │  Queue (bg thread) │ │
│  │ Analyzer    │  └────────────────────┘ │
│  │ Metadata    │  ┌────────────────────┐ │
│  │ QA Engine   │  │ In-Memory Cache    │ │
│  │ Vendor KYB  │  │ (eliminates DB     │ │
│  │ Comparator  │  │  round-trips)      │ │
│  └─────────────┘  └────────────────────┘ │
│                                          │
│  ┌─────────────┐  ┌────────────────────┐ │
│  │    FAISS    │  │   MongoDB Atlas    │ │
│  │ Vector Store│  │ (persistent store) │ │
│  └─────────────┘  └────────────────────┘ │
│                                          │
│  ┌─────────────────────────────────────┐ │
│  │  Zoho Sign API (OAuth 2.0)          │ │
│  │  Signature Verification + Audit     │ │
│  └─────────────────────────────────────┘ │
└──────────────────────────────────────────┘
```

---

## 🚀 Features

| Feature | Description | Engine |
|---------|-------------|--------|
| **Risk Analysis** | Detect risky clauses with severity, impact scores, and legal references | Gemini 2.5 Pro + Keyword Fallback |
| **Safety Scoring** | ISO 31000-compliant Risk Score & Safety Score (0-100) | Deterministic rules engine |
| **Vendor Verification** | KYB trust assessment with 5 weighted checks | Gemini AI |
| **Metadata Extraction** | Parties, dates, payment terms, governing law | Gemini AI |
| **Interactive Q&A** | Ask natural-language questions about any contract | RAG + FAISS vector search |
| **Contract Comparison** | Side-by-side AI diff of two contracts | Gemini AI |
| **Digital Signatures** | Verify signature status and audit trail | Zoho Sign API |
| **Dual Input Modes** | Upload PDF/DOCX files or paste raw contract text | FastAPI + PyPDF + python-docx |
| **Persistent Storage** | All results cached in MongoDB for instant re-access | Motor (async) |

---

## 📦 Tech Stack

### Backend
| Layer | Technology |
|-------|-----------|
| Web Framework | FastAPI + Uvicorn |
| AI / LLM | Google Gemini 2.5 Pro (`google-genai`) |
| Vector Search | FAISS + Sentence Transformers |
| Database | MongoDB Atlas (async via Motor) |
| Document Parsing | PyPDF, python-docx |
| Signatures | Zoho Sign API (OAuth 2.0, httpx) |

### Frontend
| Layer | Technology |
|-------|-----------|
| Framework | React 19 + TypeScript + Vite |
| Styling | TailwindCSS v3 |
| Data Fetching | TanStack Query (React Query) v5 |
| HTTP Client | Axios |
| Routing | React Router v7 |

---

## ⚙️ Scoring Methodology

### Risk Score (0–100) — ISO 31000 / NIST 800-30 Aligned
Computed deterministically from detected clauses — **never taken from the LLM directly**:

```
Risk Score = min(100, Σ(impact_i × severity_weight_i))

Severity weights:
  High   = 1.0   (max damage potential)
  Medium = 0.6   (moderate damage)
  Low    = 0.25  (informational)

Safety Score = 100 - Risk Score
```

| Safety Score | Risk Level |
|---|---|
| ≥ 80 | 🟢 Low Risk |
| ≥ 60 | 🟡 Moderate Risk |
| ≥ 40 | 🟠 High Risk |
| < 40 | 🔴 Very High Risk |

### Vendor Trust Score (0–100)
AI-assessed KYB based on 5 weighted checks:

| Check | Points |
|-------|--------|
| Company Recognition | 25 |
| Active Status | 25 |
| Timeline Consistency | 20 |
| Name Legitimacy | 15 |
| Jurisdiction Alignment | 15 |

| Score | Trust Level |
|---|---|
| ≥ 75 | ✅ Verified |
| ≥ 40 | ⚠️ Caution |
| < 40 | ❌ Unverified |

---

## 🛠️ Local Setup

### Prerequisites
- **Python 3.11+**
- **Node.js 18+**
- **MongoDB** (local or [MongoDB Atlas](https://www.mongodb.com/atlas))
- A **Google Gemini API key** (from [Google AI Studio](https://aistudio.google.com))

### 1. Clone the Repository
```bash
git clone https://github.com/your-username/ContractGuard.git
cd ContractGuard
```

### 2. Configure Environment Variables
Create a `.env` file in the root directory:

```env
# Required
GEMINI_API_KEY=your_gemini_api_key_here
MONGO_URI=mongodb+srv://user:pass@cluster.mongodb.net/
MONGO_DB_NAME=contractguard

# Optional – AI model selection
GEMINI_MODEL=gemini-2.5-pro

# Optional – Zoho Sign integration
ZOHO_CLIENT_ID=your_zoho_client_id
ZOHO_CLIENT_SECRET=your_zoho_client_secret
ZOHO_REFRESH_TOKEN=your_zoho_refresh_token
ZOHO_API_DOMAIN=https://sign.zoho.in

# Optional – Performance tuning
ASYNC_INDEXING_ENABLED=true
PRECOMPUTE_EMBEDDINGS_ON_UPLOAD=false
PREWARM_EMBEDDER_ON_STARTUP=false
UPLOAD_MAX_BYTES=5242880
SUMMARY_MAX_CHARS=2000
LOG_LEVEL=INFO
```

### 3. Start the Backend
```bash
# Install dependencies
pip install -r requirements.txt

# Run the FastAPI server
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

The API will be available at `http://localhost:8000`.  
Interactive docs: `http://localhost:8000/docs`

### 4. Start the Frontend
```bash
cd frontend-ui

# Install dependencies (first time only)
npm install

# Start the dev server
npm run dev
```

Open [http://localhost:5173](http://localhost:5173) in your browser.

---

## 🌐 API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Health check |
| `POST` | `/upload` | Upload contract (PDF / DOCX) |
| `POST` | `/ingest-text` | Ingest plain-text contract |
| `GET` | `/contracts` | List all contracts |
| `GET` | `/contracts/{id}/status` | Get indexing status |
| `DELETE` | `/contracts/{id}` | Delete a contract |
| `POST` | `/summary` | Generate AI summary |
| `POST` | `/risks` | Risk analysis + Safety Score |
| `POST` | `/extract-metadata` | Structured metadata extraction |
| `POST` | `/verify-vendor` | Vendor KYB assessment |
| `POST` | `/ask` | Interactive Q&A (with session memory) |
| `POST` | `/compare` | Side-by-side contract comparison |
| `POST` | `/verify-signature` | Zoho Sign verification |
| `POST` | `/audit-trail` | Zoho Sign audit trail |
| `GET` | `/zoho-status` | Check Zoho integration status |
| `POST` | `/clear` | Clear all data (new session) |

Full interactive API docs available at `/docs` when the server is running.

---

## 🔑 Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GEMINI_API_KEY` | ✅ | — | Google AI API key |
| `MONGO_URI` | ✅ | `mongodb://localhost:27017` | MongoDB connection string |
| `MONGO_DB_NAME` | ✅ | `contractguard` | MongoDB database name |
| `GEMINI_MODEL` | ❌ | `gemini-2.5-pro` | Gemini model to use |
| `ASYNC_INDEXING_ENABLED` | ❌ | `true` | Enable background FAISS indexing |
| `PRECOMPUTE_EMBEDDINGS_ON_UPLOAD` | ❌ | `false` | Compute embeddings synchronously on upload |
| `PREWARM_EMBEDDER_ON_STARTUP` | ❌ | `false` | Load embedding model on startup |
| `UPLOAD_MAX_BYTES` | ❌ | `5242880` (5 MB) | Max file upload size |
| `SUMMARY_MAX_CHARS` | ❌ | `2000` | Max summary length |
| `LOG_LEVEL` | ❌ | `INFO` | Log verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `OCR_ENABLED` | ❌ | `false` | Enable OCR for scanned PDFs (requires Ollama) |
| `OLLAMA_BASE_URL` | ❌ | `http://127.0.0.1:11434` | Ollama API URL (for OCR) |
| `ZOHO_CLIENT_ID` | ❌ | — | Zoho Sign OAuth client ID |
| `ZOHO_CLIENT_SECRET` | ❌ | — | Zoho Sign OAuth client secret |
| `ZOHO_REFRESH_TOKEN` | ❌ | — | Zoho Sign refresh token |
| `ZOHO_API_DOMAIN` | ❌ | — | `https://sign.zoho.in` or `https://sign.zoho.com` |

---

## 📁 Project Structure

```
ContractGuard/
├── backend/
│   ├── main.py                  # FastAPI app + all API routes
│   ├── api/
│   │   ├── schemas.py           # Pydantic request/response models
│   │   └── errors.py            # HTTP error mapping
│   ├── contracts/
│   │   ├── analyzer.py          # Risk analysis (LLM + keyword fallback)
│   │   ├── summarizer.py        # AI contract summarization
│   │   ├── metadata_extractor.py # Structured metadata extraction
│   │   ├── vendor_verifier.py   # KYB vendor verification
│   │   ├── comparator.py        # Side-by-side contract comparison
│   │   ├── embedder.py          # FAISS vector store + retrieval
│   │   ├── qa_chain.py          # Extractive Q&A over chunks
│   │   ├── chat_engine.py       # Conversational Q&A with history
│   │   ├── parser.py            # PDF / DOCX text extraction
│   │   ├── ocr.py               # OCR via Ollama (optional)
│   │   ├── store.py             # MongoDB async storage layer
│   │   ├── services.py          # ContractService orchestration
│   │   ├── gemini_client.py     # Gemini API client wrapper
│   │   ├── session_manager.py   # Chat session ID management
│   │   └── zoho_sign.py         # Zoho Sign API integration
│   ├── core/
│   │   ├── config.py            # Centralized settings (env vars)
│   │   ├── exceptions.py        # Custom exception hierarchy
│   │   └── logging_config.py    # Structured logging setup
│   └── ingestion/
│       ├── queue.py             # Async background indexing queue
│       └── upload_validation.py # File type + size validation
│
├── frontend-ui/
│   ├── src/
│   │   ├── App.tsx              # App shell + routing + sidebar
│   │   ├── api.ts               # Typed API client (axios)
│   │   ├── components/
│   │   │   ├── AnalyzeView.tsx  # Main contract analysis dashboard
│   │   │   ├── ContractsView.tsx # Recent scans + contract history
│   │   │   ├── CompareView.tsx  # Side-by-side contract comparison
│   │   │   └── MarkdownText.tsx # Markdown renderer component
│   │   ├── index.css            # Global styles + design tokens
│   │   └── main.tsx             # React app entry point
│   ├── package.json
│   └── vite.config.ts
│
├── requirements.txt             # Python dependencies
└── .env                         # Local environment variables (not committed)
```

---

## 🚢 Deployment

The backend can be deployed anywhere Python + uvicorn runs:

```bash
# Production start command
uvicorn backend.main:app --host 0.0.0.0 --port $PORT
```

The frontend is a standard Vite SPA and can be deployed to Vercel, Netlify, or any static host:

```bash
cd frontend-ui
npm run build
# Output in dist/
```

---

## 📜 License

MIT — see [LICENSE](LICENSE) for details.

---

<p align="center">Built with ❤️</p>
