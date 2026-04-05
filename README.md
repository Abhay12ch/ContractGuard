# ContractGuard AI

> AI-powered contract analysis platform with risk detection, vendor verification, metadata extraction, and interactive Q&A.

## Features

| Layer | What It Does | Tech |
|-------|-------------|------|
| **Contract Analysis** | AI-generated summary, risk scoring, clause detection | Gemini 2.5 Pro |
| **Risk Detection** | ISO 31000-compliant scoring with dual Risk/Safety scores | Deterministic rules engine |
| **Vendor Verification** | Know-Your-Business (KYB) assessment of contract vendors | Gemini AI assessment |
| **Metadata Extraction** | Parties, dates, financial terms, governing law | Structured AI extraction |
| **Digital Signatures** | Zoho Sign integration for signature verification | Zoho Sign API (OAuth 2.0) |
| **Interactive Q&A** | Ask questions about any uploaded contract | RAG + vector search |
| **Contract Comparison** | Side-by-side analysis of two contracts | AI-powered diff |

## Architecture

```
┌─────────────────────────────────┐
│   React/Vite Frontend (5173)    │
│   TailwindCSS + Material Icons  │
└──────────────┬──────────────────┘
               │ REST API
┌──────────────▼──────────────────┐
│   FastAPI Backend (8000)        │
│   ┌───────────────────────────┐ │
│   │ Gemini AI (Summarizer,    │ │
│   │ Analyzer, Metadata, QA,   │ │
│   │ Vendor Verifier)          │ │
│   ├───────────────────────────┤ │
│   │ Zoho Sign (OAuth 2.0)    │ │
│   ├───────────────────────────┤ │
│   │ FAISS Vector Store        │ │
│   ├───────────────────────────┤ │
│   │ MongoDB (persistent store)│ │
│   └───────────────────────────┘ │
└─────────────────────────────────┘
```

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- MongoDB (cloud or local)

### 1. Backend Setup
```bash
pip install -r requirements.txt

# Set environment variables in .env
# Required: GEMINI_API_KEY, MONGO_URI, MONGO_DB_NAME

python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Frontend Setup
```bash
cd frontend-ui
npm install
npm run dev
```

Open http://localhost:5173 in your browser.

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GEMINI_API_KEY` | ✅ | Google AI API key |
| `GEMINI_MODEL` | | Model name (default: `gemini-2.5-pro`) |
| `MONGO_URI` | ✅ | MongoDB connection string |
| `MONGO_DB_NAME` | ✅ | Database name |
| `ZOHO_CLIENT_ID` | | Zoho Sign OAuth client ID |
| `ZOHO_CLIENT_SECRET` | | Zoho Sign OAuth client secret |
| `ZOHO_REFRESH_TOKEN` | | Zoho Sign refresh token |
| `ZOHO_API_DOMAIN` | | `https://sign.zoho.in` or `.com` |

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/upload` | Upload contract (PDF/DOCX) |
| POST | `/ingest-text` | Ingest plain text contract |
| POST | `/summary` | AI-generated summary |
| POST | `/risks` | Risk analysis + safety score |
| POST | `/extract-metadata` | Structured metadata extraction |
| POST | `/verify-vendor` | Vendor KYB verification |
| POST | `/verify-signature` | Zoho Sign verification |
| POST | `/audit-trail` | Zoho Sign audit trail |
| POST | `/ask` | Interactive Q&A |
| POST | `/compare` | Compare two contracts |
| GET | `/contracts` | List all contracts |
| DELETE | `/contracts/{id}` | Delete a contract |
| POST | `/clear` | Clear all data |

## Scoring System

### Risk Score (0–100)
Deterministic, ISO 31000/NIST 800-30 compliant: `Σ(impact × severity_weight)`

### Safety Score (0–100)
`100 - risk_score`

### Trust Score (0–100)
Vendor verification based on 5 weighted checks:
- Company Recognition (25 pts)
- Active Status (25 pts)
- Timeline Consistency (20 pts)
- Name Consistency (15 pts)
- Jurisdiction Alignment (15 pts)

## Tech Stack

- **Frontend**: React 19, Vite, TailwindCSS, TanStack Query
- **Backend**: Python, FastAPI, Uvicorn
- **AI**: Google Gemini 2.5 Pro
- **Database**: MongoDB Atlas (via Motor async driver)
- **Vector Search**: FAISS + Sentence Transformers
- **Signatures**: Zoho Sign API (OAuth 2.0)

## License

MIT
