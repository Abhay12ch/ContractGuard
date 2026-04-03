# ContractGuard AI

AI-powered contract analysis system for summaries, risky clause detection, contract risk scoring, interactive Q&A, and contract comparison.

---

## 1. Roadmap

### Phase 1 — Setup
- Initialize Python environment and install dependencies from `requirements.txt`.
- Configure LLM API key (Gemini or OpenAI) via `.env`.

### Phase 2 — Document Ingestion
- Implement PDF parsing with **PyPDF (pypdf)** and DOCX parsing with **python-docx** in `backend/contracts/parser.py`.
- Add text chunking and preprocessing for long contracts.

### Phase 3 — Embeddings & Vector Store
- Implement embeddings + FAISS index in `backend/contracts/embedder.py`.
- Store contract chunks and provide retrieval utilities.

### Phase 4 — Core AI Features
- Plain-language summary generation.
- Risky clause detection (penalties, liability, non-compete, termination, auto-renewal).
- Contract Risk Score (0–100) computation in `backend/contracts/analyzer.py`.
- Interactive Q&A over a contract using retrieval + LLM in `backend/contracts/qa_chain.py`.

### Phase 5 — Contract Comparison
- Implement comparison logic in `backend/contracts/comparator.py`.
- Highlight better/worse terms between two contracts.

### Phase 6 — API & Frontend
- Expose FastAPI endpoints in `backend/main.py`:
   - `/upload`, `/ingest-text`, `/contracts/{contract_id}/status`, `/summary`, `/risks`, `/ask`, `/compare`.
- Build Streamlit UI in `frontend/app.py`:
  - Upload contract, show summary, risk score, risky clauses, Q&A, and comparison view.

### Phase 7 — (Optional) Knowledge Graph
- Extract clause relationships and visualize a Clause Knowledge Graph.

---

## 2. Project Structure

```text
ContractGuard/
├── ContractGuard_Hackathon_Brief.pdf   # Hackathon problem statement
├── README.md                           # Roadmap and structure (this file)
├── requirements.txt                    # Python dependencies
├── requirements-dev.txt                # Dev/testing dependencies
├── .env.example                        # Environment variable template
├── pytest.ini                          # Pytest configuration
├── backend/
│   ├── main.py                         # FastAPI entrypoint
│   ├── api/
│   │   ├── errors.py                   # Domain exception -> HTTP mapping
│   │   └── schemas.py                  # API request/response contracts
│   ├── core/
│   │   ├── config.py                   # Environment-driven backend settings
│   │   └── exceptions.py               # Domain-specific exception hierarchy
│   ├── contracts/
│   │   ├── analyzer.py                 # Risk detection + Contract Risk Score
│   │   ├── comparator.py               # Contract comparison logic
│   │   ├── embedder.py                 # Embeddings + FAISS vector store
│   │   ├── parser.py                   # PDF/DOCX text extraction
│   │   ├── qa_chain.py                 # Retrieval-based Q&A over contracts
│   │   ├── services.py                 # Contract orchestration service layer
│   │   └── store.py                    # Thread-safe in-memory contract storage
│   ├── ingestion/
│   │   ├── queue.py                    # Background indexing worker queue
│   │   └── upload_validation.py        # Upload hardening (size/type/signature)
│   └── training/
│       └── build_training_corpus.py    # Retriever corpus builder utilities
├── frontend/
│   └── app.py                          # Streamlit UI
├── tests/
│   ├── test_api_smoke.py               # Backend API + async ingestion tests
│   └── test_embedder_provider.py       # Embedding provider behavior tests
└── datasets/
   └── (sample datasets/corpus)
```

---

## 3. Quick Start

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Configure environment:
   ```bash
   cp .env.example .env
   ```
   Then fill in `GEMINI_API_KEY` if you want Gemini-powered answers.
   By default, embeddings use `EMBEDDING_PROVIDER=auto` (Gemini when available, local fallback otherwise).
3. Run backend (dev):
   ```bash
   uvicorn backend.main:app --reload
   ```
4. Run frontend:
   ```bash
   streamlit run frontend/app.py
   ```
5. (Optional) Run smoke tests:
   ```bash
   pip install -r requirements-dev.txt
   pytest
   ```

---

## 4. Deploy On Render (GitHub Blueprint)

This repository includes `render.yaml`, so you can deploy directly from GitHub using Render Blueprint.

1. Push this project to GitHub.
2. In Render, click **New +** -> **Blueprint**.
3. Connect your GitHub repo and select this repository.
4. Render will detect `render.yaml` and create two services:
   - `contractguard-backend` (FastAPI)
   - `contractguard-frontend` (Streamlit)
5. After services are created, set environment variables in Render:
   - Backend service:
     - `GEMINI_API_KEY` (required for Gemini-powered answers)
   - Frontend service:
     - `API_BASE_URL` = your deployed backend URL, for example: `https://contractguard-backend.onrender.com`
6. Redeploy the frontend after setting `API_BASE_URL`.

### Notes

- The app supports PDF and DOCX uploads.
- Uploads are strictly validated by size, content-type, and file signature.
- Indexing runs asynchronously with status tracking.
- Data is still stored in memory, so uploaded contracts reset on service restart.
