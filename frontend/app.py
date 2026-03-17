"""Streamlit UI for ContractGuard AI demo flow."""

import os
import time
import tempfile
import uuid
import json
import copy
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any
from urllib.parse import urlparse
import requests
import streamlit as st


RUNNING_ON_RENDER = os.getenv("RENDER", "").lower() == "true"
DEFAULT_RENDER_BACKEND_URL = "https://contractguard-backend.onrender.com"
PREFER_LOCAL_ON_RENDER = os.getenv("PREFER_LOCAL_ON_RENDER", "true").lower() == "true"
AUTH_USERNAME = os.getenv("CONTRACTGUARD_LOGIN_USER", "admin")
AUTH_PASSWORD = os.getenv("CONTRACTGUARD_LOGIN_PASSWORD", "contractguard123")

LOCAL_MODE_AVAILABLE = False
LOCAL_MODE_IMPORT_ERROR = ""

try:
    from backend.analyzer import analyze_contract
    from backend.embedder import build_faiss_store, chunk_contract_text, retrieve_relevant_chunks
    from backend.parser import extract_text_from_file
    from backend.qa_chain import answer_question

    LOCAL_MODE_AVAILABLE = True
except Exception as local_import_exc:
    LOCAL_MODE_IMPORT_ERROR = str(local_import_exc)


class _LocalResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            detail = self._payload.get("detail", "Local processing error")
            raise requests.HTTPError(f"{self.status_code} Error: {detail}")


def _normalize_api_base_url() -> str:
    """Normalize configured API base URL and apply safe Render fallback."""
    configured = os.getenv("API_BASE_URL", "").strip().rstrip("/")

    if configured:
        parsed = urlparse(configured)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return configured

        # Common misconfiguration: host without scheme. Accept only host-like values.
        if not parsed.scheme and parsed.path:
            host_candidate = parsed.path.strip("/")
            if "." in host_candidate:
                return f"https://{host_candidate}"

    if RUNNING_ON_RENDER:
        return DEFAULT_RENDER_BACKEND_URL

    return "http://127.0.0.1:8000"


API_BASE_URL = _normalize_api_base_url()

LANGUAGE_OPTIONS: Dict[str, str] = {
    "English": "en",
    "Assamese": "as",
    "Bengali": "bn",
    "Bodo": "brx",
    "Dogri": "doi",
    "Gujarati": "gu",
    "Hindi": "hi",
    "Kannada": "kn",
    "Kashmiri": "ks",
    "Konkani": "gom",
    "Maithili": "mai",
    "Malayalam": "ml",
    "Manipuri (Meitei)": "mni",
    "Marathi": "mr",
    "Nepali": "ne",
    "Odia": "or",
    "Punjabi": "pa",
    "Sanskrit": "sa",
    "Santali": "sat",
    "Sindhi": "sd",
    "Tamil": "ta",
    "Telugu": "te",
    "Urdu": "ur",
}

# Some Indian language variants are not directly supported by free translation endpoints.
# Map them to a close, commonly understood fallback for better real-world coverage.
TRANSLATION_CODE_FALLBACKS: Dict[str, str] = {
    "brx": "hi",   # Bodo -> Hindi fallback
    "doi": "hi",   # Dogri -> Hindi fallback
    "gom": "mr",   # Konkani -> Marathi fallback
    "mai": "hi",   # Maithili -> Hindi fallback
    "mni": "bn",   # Meitei -> Bengali fallback
    "sat": "bn",   # Santali -> Bengali fallback
}


def _init_state() -> None:
    if "is_authenticated" not in st.session_state:
        st.session_state.is_authenticated = False
    if "auth_user" not in st.session_state:
        st.session_state.auth_user = ""
    if "contract_id" not in st.session_state:
        st.session_state.contract_id = ""
    if "risk_data" not in st.session_state:
        st.session_state.risk_data = None
    if "summary_data" not in st.session_state:
        st.session_state.summary_data = None
    if "upload_name" not in st.session_state:
        st.session_state.upload_name = ""
    if "qa_answer" not in st.session_state:
        st.session_state.qa_answer = ""
    if "qa_input" not in st.session_state:
        st.session_state.qa_input = ""
    if "qa_history" not in st.session_state:
        st.session_state.qa_history = []
    if "known_contracts" not in st.session_state:
        st.session_state.known_contracts = {}
    if "analysis_cache" not in st.session_state:
        st.session_state.analysis_cache = {}
    if "compare_result" not in st.session_state:
        st.session_state.compare_result = None
    if "selected_language" not in st.session_state:
        st.session_state.selected_language = "English"
    if "selected_language_code" not in st.session_state:
        st.session_state.selected_language_code = "en"
    if "top_language_selector" not in st.session_state:
        st.session_state.top_language_selector = "English"
    if "workspace_sidebar_open" not in st.session_state:
        st.session_state.workspace_sidebar_open = True
    if "local_contract_store" not in st.session_state:
        st.session_state.local_contract_store = {}
    if "local_contract_chunks" not in st.session_state:
        st.session_state.local_contract_chunks = {}
    if "local_vector_stores" not in st.session_state:
        st.session_state.local_vector_stores = {}


def _local_store_contract(text: str, filename: str) -> _LocalResponse:
    contract_id = str(uuid.uuid4())
    st.session_state.local_contract_store[contract_id] = text
    chunks = chunk_contract_text(text)
    st.session_state.local_contract_chunks[contract_id] = chunks
    st.session_state.local_vector_stores[contract_id] = build_faiss_store(chunks)

    return _LocalResponse(
        200,
        {
            "contract_id": contract_id,
            "filename": filename,
            "text_preview": text[:300].replace("\n", " "),
            "chunk_count": len(chunks),
            "embedding_count": int(
                st.session_state.local_vector_stores[contract_id].get("embedding_count", 0)
            ),
        },
    )


def _local_post(path: str, **kwargs) -> _LocalResponse:
    if not LOCAL_MODE_AVAILABLE:
        return _LocalResponse(
            503,
            {
                "detail": (
                    "Remote backend unavailable and local fallback dependencies are missing: "
                    f"{LOCAL_MODE_IMPORT_ERROR}"
                )
            },
        )

    if path == "/ingest-text":
        payload = kwargs.get("json", {})
        raw_text = str(payload.get("text", "")).strip()
        title = str(payload.get("title", "Pasted Contract Text")).strip() or "Pasted Contract Text"
        if not raw_text:
            return _LocalResponse(400, {"detail": "Text input cannot be empty"})
        return _local_store_contract(raw_text, title)

    if path == "/upload":
        file_tuple = (kwargs.get("files") or {}).get("file")
        if not file_tuple:
            return _LocalResponse(400, {"detail": "No file payload provided"})

        filename = str(file_tuple[0])
        contents = file_tuple[1]
        suffix = Path(filename).suffix.lower()
        if suffix not in {".pdf", ".docx"}:
            return _LocalResponse(400, {"detail": "Only PDF and DOCX files are supported"})

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(contents)
            tmp_path = Path(tmp.name)

        try:
            text = extract_text_from_file(str(tmp_path))
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass

        if not text or not text.strip():
            return _LocalResponse(400, {"detail": "Could not extract text from contract"})

        return _local_store_contract(text, filename)

    payload = kwargs.get("json", {})
    contract_id = str(payload.get("contract_id", ""))
    text = st.session_state.local_contract_store.get(contract_id)
    if path in {"/risks", "/summary", "/ask"} and not text:
        return _LocalResponse(404, {"detail": "Unknown contract_id. Upload or ingest first."})

    if path == "/risks":
        result = analyze_contract(text)
        return _LocalResponse(
            200,
            {
                "contract_id": contract_id,
                "risk_score": int(result.get("risk_score", result.get("safety_score", 0))),
                "safety_score": int(result.get("safety_score", result.get("risk_score", 0))),
                "risk_level": result.get("risk_level", "Unknown"),
                "detected_clause_count": int(
                    result.get("detected_clause_count", len(result.get("risks", [])))
                ),
                "risks": result.get("risks", []),
            },
        )

    if path == "/summary":
        max_chars = int(payload.get("max_chars", 600))
        max_chars = max(100, min(max_chars, 2000))
        return _LocalResponse(200, {"contract_id": contract_id, "summary": text[:max_chars]})

    if path == "/ask":
        question = str(payload.get("question", "")).strip()
        if not question:
            return _LocalResponse(400, {"detail": "Question cannot be empty"})
        top_k = int(payload.get("top_k", 4))
        vector_store = st.session_state.local_vector_stores.get(contract_id)
        if vector_store is None:
            return _LocalResponse(404, {"detail": "No vector store found for this contract."})
        chunks = retrieve_relevant_chunks(question=question, vector_store=vector_store, top_k=top_k)
        answer = answer_question(question, chunks)
        return _LocalResponse(
            200,
            {
                "contract_id": contract_id,
                "question": question,
                "answer": answer,
                "retrieved_chunks_count": len(chunks),
            },
        )

    return _LocalResponse(404, {"detail": f"Unsupported local endpoint: {path}"})


def _api_post(path: str, **kwargs):
    # Local-first mode avoids long blocking waits when the backend service is cold/unavailable.
    if RUNNING_ON_RENDER and PREFER_LOCAL_ON_RENDER and LOCAL_MODE_AVAILABLE:
        return _local_post(path, **kwargs)

    parsed = urlparse(API_BASE_URL)
    base_url = API_BASE_URL

    # Final runtime safety-net for any malformed env at deployment/runtime.
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        base_url = DEFAULT_RENDER_BACKEND_URL

    # Render free-tier services may return transient 503/timeouts during cold start.
    # Warm the service and retry briefly before surfacing an error to the user.
    timeout_seconds = kwargs.pop("timeout", 180)
    attempts = 4
    delay_seconds = 4
    last_exc: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            if attempt == 1:
                try:
                    requests.get(f"{base_url}/", timeout=20)
                except requests.RequestException:
                    pass

            response = requests.post(f"{base_url}{path}", timeout=timeout_seconds, **kwargs)
            if response.status_code in {502, 503, 504} and attempt < attempts:
                time.sleep(delay_seconds)
                continue
            return response
        except requests.RequestException as exc:
            last_exc = exc
            if attempt < attempts:
                time.sleep(delay_seconds)
                continue
            if LOCAL_MODE_AVAILABLE:
                return _local_post(path, **kwargs)
            raise

    if last_exc is not None:
        if LOCAL_MODE_AVAILABLE:
            return _local_post(path, **kwargs)
        raise last_exc

    raise RuntimeError("Backend request failed after retries.")


def _inject_theme() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=Manrope:wght@400;600;700&display=swap');

        :root {
            --bg-1: #f4efe6;
            --bg-2: #d8e8ea;
            --ink: #1f2a33;
            --ink-soft: #4c5a67;
            --accent: #0f766e;
            --accent-soft: #14b8a6;
            --warn: #b45309;
            --danger: #b91c1c;
            --card: rgba(255, 255, 255, 0.72);
            --stroke: rgba(31, 42, 51, 0.12);
            --success: #166534;
        }

        [data-testid="stAppViewContainer"] {
            background:
                radial-gradient(900px 500px at 92% -10%, rgba(20, 184, 166, 0.22), transparent 60%),
                radial-gradient(700px 420px at -10% 20%, rgba(15, 118, 110, 0.15), transparent 58%),
                linear-gradient(145deg, var(--bg-1) 0%, var(--bg-2) 100%);
            color: var(--ink);
            font-family: 'Manrope', sans-serif;
        }

        .main .block-container {
            max-width: 1180px;
            padding-top: 1.4rem;
            padding-bottom: 2.6rem;
        }

        h1, h2, h3 {
            font-family: 'Space Grotesk', sans-serif;
            color: var(--ink);
            letter-spacing: -0.02em;
        }

        .hero-wrap {
            border: 1px solid var(--stroke);
            background: linear-gradient(125deg, rgba(255, 255, 255, 0.84), rgba(255, 255, 255, 0.58));
            backdrop-filter: blur(10px);
            border-radius: 18px;
            padding: 1.2rem 1.4rem;
            box-shadow: 0 12px 40px rgba(31, 42, 51, 0.08);
            animation: fadeUp 0.6s ease-out both;
        }

        .hero-kicker {
            font-size: 0.84rem;
            text-transform: uppercase;
            letter-spacing: 0.11em;
            font-weight: 700;
            color: var(--accent);
        }

        .hero-title {
            margin: 0.3rem 0 0.6rem 0;
            font-size: 2.1rem;
            line-height: 1.1;
        }

        .hero-sub {
            color: var(--ink-soft);
            font-size: 1rem;
            margin-bottom: 0;
        }

        .stat-chip {
            display: inline-flex;
            align-items: center;
            gap: 0.45rem;
            border: 1px solid var(--stroke);
            border-radius: 999px;
            padding: 0.3rem 0.7rem;
            background: rgba(255, 255, 255, 0.8);
            font-size: 0.82rem;
            margin-right: 0.4rem;
            margin-top: 0.5rem;
        }

        .card {
            border: 1px solid var(--stroke);
            background: var(--card);
            border-radius: 16px;
            padding: 1rem 1rem 0.7rem 1rem;
            box-shadow: 0 7px 24px rgba(31, 42, 51, 0.07);
            animation: fadeUp 0.55s ease-out both;
        }

        .risk-badge {
            border-radius: 999px;
            padding: 0.24rem 0.64rem;
            font-size: 0.78rem;
            font-weight: 700;
            display: inline-block;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            margin-top: 0.35rem;
        }

        .risk-low {
            color: #065f46;
            background: rgba(16, 185, 129, 0.16);
            border: 1px solid rgba(16, 185, 129, 0.4);
        }

        .risk-medium {
            color: #92400e;
            background: rgba(251, 191, 36, 0.18);
            border: 1px solid rgba(217, 119, 6, 0.35);
        }

        .risk-high {
            color: #991b1b;
            background: rgba(239, 68, 68, 0.14);
            border: 1px solid rgba(239, 68, 68, 0.38);
        }

        .severity-pill {
            border-radius: 999px;
            font-size: 0.72rem;
            padding: 0.18rem 0.55rem;
            border: 1px solid var(--stroke);
            background: rgba(255, 255, 255, 0.74);
            font-weight: 700;
        }

        [data-testid="stMetric"] {
            background: rgba(255, 255, 255, 0.86);
            border: 1px solid var(--stroke);
            border-radius: 14px;
            padding: 0.55rem;
        }

        [data-testid="stProgressBar"] > div > div {
            background: linear-gradient(90deg, var(--accent) 0%, var(--accent-soft) 100%);
        }

        .stTextInput > div > div > input,
        .stTextArea textarea {
            border-radius: 11px;
            border: 1px solid rgba(31, 42, 51, 0.2);
            background: rgba(255, 255, 255, 0.86);
        }

        .stButton button {
            border-radius: 11px;
            border: 1px solid rgba(15, 118, 110, 0.28);
            font-weight: 700;
            transition: transform 140ms ease, box-shadow 140ms ease;
        }

        .stButton button:hover {
            transform: translateY(-1px);
            box-shadow: 0 8px 16px rgba(15, 118, 110, 0.16);
        }

        .st-key-top_language_selector {
            display: flex;
            justify-content: flex-end;
            align-items: center;
        }

        .st-key-top_language_selector [data-testid="stSelectbox"] {
            width: 100%;
            max-width: 290px;
        }

        .st-key-top_language_selector [data-baseweb="select"] > div {
            border-radius: 999px;
            border: 1px solid rgba(15, 118, 110, 0.42);
            background: linear-gradient(140deg, rgba(255, 255, 255, 0.94), rgba(233, 246, 244, 0.95));
            min-height: 2.35rem;
            box-shadow: 0 6px 16px rgba(15, 118, 110, 0.12);
        }

        .st-key-top_language_selector [data-baseweb="select"] span,
        .st-key-top_language_selector [data-baseweb="select"] div {
            color: var(--ink);
            font-weight: 700;
        }

        .divider {
            height: 1px;
            border: 0;
            background: linear-gradient(90deg, transparent, rgba(31, 42, 51, 0.24), transparent);
            margin: 1.2rem 0;
        }

        .auth-shell {
            border: 1px solid var(--stroke);
            background: linear-gradient(125deg, rgba(255, 255, 255, 0.9), rgba(247, 252, 251, 0.82));
            border-radius: 20px;
            padding: 1.3rem;
            box-shadow: 0 14px 34px rgba(31, 42, 51, 0.09);
            margin-top: 1.2rem;
        }

        .auth-title {
            font-family: 'Space Grotesk', sans-serif;
            font-size: 2rem;
            margin: 0;
            color: var(--ink);
            line-height: 1.15;
        }

        .auth-sub {
            color: var(--ink-soft);
            margin-top: 0.65rem;
            margin-bottom: 0;
            font-size: 0.98rem;
        }

        .auth-point {
            border: 1px solid var(--stroke);
            background: rgba(255, 255, 255, 0.8);
            border-radius: 12px;
            padding: 0.55rem 0.75rem;
            margin-bottom: 0.55rem;
            color: var(--ink);
            font-size: 0.92rem;
            font-weight: 600;
        }

        @keyframes fadeUp {
            from {
                opacity: 0;
                transform: translateY(10px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _risk_badge_class(risk_level: str) -> str:
    level = risk_level.lower()
    if "high" in level:
        return "risk-high"
    if "medium" in level:
        return "risk-medium"
    return "risk-low"


def _remember_contract(contract_id: str, filename: str) -> None:
    st.session_state.known_contracts[contract_id] = filename


def _cache_analysis(contract_id: str, risk_data: dict, summary_data: dict) -> None:
    st.session_state.analysis_cache[contract_id] = {
        "risk": risk_data,
        "summary": summary_data,
    }


def _set_active_contract(contract_id: str) -> None:
    st.session_state.contract_id = contract_id
    st.session_state.upload_name = st.session_state.known_contracts.get(contract_id, "Unknown Contract")
    cached = st.session_state.analysis_cache.get(contract_id)
    if cached:
        st.session_state.risk_data = cached.get("risk")
        st.session_state.summary_data = cached.get("summary")


def _analysis_report_json() -> str:
    ui_language = st.session_state.selected_language_code
    translated_risk = _translated_risk_data(st.session_state.risk_data or {}, ui_language)
    translated_summary = _translate_for_ui(
        str((st.session_state.summary_data or {}).get("summary", "")),
        ui_language,
    )
    translated_qa_history = [
        {
            "question": _translate_for_ui(str(item.get("question", "")), ui_language),
            "answer": _translate_for_ui(str(item.get("answer", "")), ui_language),
            "contract": item.get("contract", ""),
        }
        for item in st.session_state.qa_history
    ]

    safety_score = int((st.session_state.risk_data or {}).get("safety_score", 0))
    detected_count = int((st.session_state.risk_data or {}).get("detected_clause_count", 0))

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "report_language": st.session_state.selected_language,
        "report_language_code": ui_language,
        "contract": {
            "contract_id": st.session_state.contract_id,
            "contract_name": st.session_state.upload_name,
        },
        "analysis_overview": {
            "safety_score": safety_score,
            "detected_clause_count": detected_count,
            "risk_level": (st.session_state.risk_data or {}).get("risk_level", "Unknown"),
            "risk_level_translated": translated_risk.get("risk_level", "Unknown"),
        },
        "analysis_original": {
            "risk_data": st.session_state.risk_data,
            "summary_data": st.session_state.summary_data,
            "qa_history": st.session_state.qa_history,
            "compare_result": st.session_state.compare_result,
        },
        "analysis_translated": {
            "risk_data": translated_risk,
            "summary": translated_summary,
            "qa_history": translated_qa_history,
            "compare_result": _translated_compare_data(st.session_state.compare_result or {}, ui_language),
        },
    }
    return json.dumps(payload, indent=2)


def _safe_pdf_text(text: str) -> str:
    """FPDF core fonts do not support full Unicode; degrade safely for report output."""
    return (text or "").encode("latin-1", "replace").decode("latin-1")


def _analysis_report_pdf_bytes(report_lang_code: str, report_lang_name: str) -> bytes:
    # Lazy import keeps startup resilient when optional dependency is missing.
    from fpdf import FPDF

    risk_data = st.session_state.risk_data or {}
    summary_data = st.session_state.summary_data or {}
    compare_result = st.session_state.compare_result or {}

    display_risk_data = _translated_risk_data(risk_data, report_lang_code)
    display_summary = _translate_for_ui(str(summary_data.get("summary", "No summary available.")), report_lang_code)
    display_compare = _translated_compare_data(compare_result, report_lang_code)
    display_qa_history = [
        {
            "question": _translate_for_ui(str(item.get("question", "")), report_lang_code),
            "answer": _translate_for_ui(str(item.get("answer", "")), report_lang_code),
        }
        for item in st.session_state.qa_history
    ]

    # Section labels also adapt to chosen report language.
    title_label = _translate_for_ui("ContractGuard Analysis Report", report_lang_code)
    generated_label = _translate_for_ui("Generated", report_lang_code)
    contract_label = _translate_for_ui("Contract", report_lang_code)
    contract_id_label = _translate_for_ui("Contract ID", report_lang_code)
    report_language_label = _translate_for_ui("Report Language", report_lang_code)
    overview_label = _translate_for_ui("Overview", report_lang_code)
    summary_label = _translate_for_ui("Summary", report_lang_code)
    risky_clauses_label = _translate_for_ui("Risky Clauses", report_lang_code)
    recent_qa_label = _translate_for_ui("Recent Q&A", report_lang_code)
    comparison_label = _translate_for_ui("Comparison Outcome", report_lang_code)
    safety_score_label = _translate_for_ui("Safety Score", report_lang_code)
    risk_level_label = _translate_for_ui("Risk Level", report_lang_code)
    clause_count_label = _translate_for_ui("Detected Risky Clauses", report_lang_code)
    severity_label = _translate_for_ui("Severity", report_lang_code)
    impact_label = _translate_for_ui("Impact", report_lang_code)
    evidence_label = _translate_for_ui("Evidence", report_lang_code)
    winner_label = _translate_for_ui("Winner", report_lang_code)
    no_risky_label = _translate_for_ui("No risky clauses detected.", report_lang_code)

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, _safe_pdf_text(title_label), ln=True)

    pdf.set_font("Helvetica", size=11)
    pdf.cell(0, 8, _safe_pdf_text(f"{generated_label}: {datetime.now(timezone.utc).isoformat()}"), ln=True)
    pdf.cell(0, 8, _safe_pdf_text(f"{contract_label}: {st.session_state.upload_name}"), ln=True)
    pdf.cell(0, 8, _safe_pdf_text(f"{contract_id_label}: {st.session_state.contract_id}"), ln=True)
    pdf.cell(0, 8, _safe_pdf_text(f"{report_language_label}: {report_lang_name}"), ln=True)
    pdf.ln(2)

    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 9, _safe_pdf_text(overview_label), ln=True)
    pdf.set_font("Helvetica", size=11)
    pdf.multi_cell(0, 7, _safe_pdf_text(
        f"{safety_score_label}: {int(display_risk_data.get('safety_score', 0))}/100\n"
        f"{risk_level_label}: {display_risk_data.get('risk_level', 'Unknown')}\n"
        f"{clause_count_label}: {int(display_risk_data.get('detected_clause_count', 0))}"
    ))
    pdf.ln(1)

    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 9, _safe_pdf_text(summary_label), ln=True)
    pdf.set_font("Helvetica", size=11)
    pdf.multi_cell(0, 7, _safe_pdf_text(display_summary))
    pdf.ln(1)

    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 9, _safe_pdf_text(risky_clauses_label), ln=True)
    pdf.set_font("Helvetica", size=11)
    risks = display_risk_data.get("risks", [])
    if not risks:
        pdf.multi_cell(0, 7, _safe_pdf_text(no_risky_label))
    else:
        for idx, item in enumerate(risks, start=1):
            title = item.get("title", "Unknown Clause")
            sev = item.get("severity", "Unknown")
            impact = item.get("impact", 0)
            evidence = item.get("evidence", "")
            pdf.multi_cell(
                0,
                7,
                _safe_pdf_text(
                    f"{idx}. {title} | {severity_label}: {sev} | {impact_label}: {impact}\n"
                    f"{evidence_label}: {evidence}"
                ),
            )
            pdf.ln(1)

    if display_qa_history:
        pdf.set_font("Helvetica", "B", 13)
        pdf.cell(0, 9, _safe_pdf_text(recent_qa_label), ln=True)
        pdf.set_font("Helvetica", size=11)
        for idx, qa_item in enumerate(display_qa_history[:5], start=1):
            pdf.multi_cell(
                0,
                7,
                _safe_pdf_text(
                    f"Q{idx}: {qa_item.get('question', '')}\n"
                    f"A{idx}: {qa_item.get('answer', '')}"
                ),
            )
            pdf.ln(1)

    details = display_compare.get("details", {})
    if details:
        pdf.set_font("Helvetica", "B", 13)
        pdf.cell(0, 9, _safe_pdf_text(comparison_label), ln=True)
        pdf.set_font("Helvetica", size=11)
        pdf.multi_cell(
            0,
            7,
            _safe_pdf_text(
                f"{winner_label}: {details.get('winner', 'Tie')}\n"
                f"{summary_label}: {display_compare.get('summary', '')}"
            ),
        )

    output = pdf.output(dest="S")
    return output.encode("latin-1") if isinstance(output, str) else bytes(output)


def _effective_translation_code(lang_code: str) -> str:
    return TRANSLATION_CODE_FALLBACKS.get(lang_code, lang_code)


def _on_language_change() -> None:
    selected = st.session_state.top_language_selector
    st.session_state.selected_language = selected
    st.session_state.selected_language_code = LANGUAGE_OPTIONS[selected]


def _render_login_landing() -> None:
    st.markdown(
        """
        <div class="auth-shell">
            <p class="hero-kicker">Secure Access</p>
            <h2 class="auth-title">Welcome to ContractGuard AI</h2>
            <p class="auth-sub">Sign in to access contract analysis, multilingual insights, Q&A, and report download features.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    left_col, right_col = st.columns([1.25, 1])
    with left_col:
        st.markdown('<div class="auth-point">Risk score dashboard for uploaded contracts</div>', unsafe_allow_html=True)
        st.markdown('<div class="auth-point">Clause-level explanation and impact highlighting</div>', unsafe_allow_html=True)
        st.markdown('<div class="auth-point">Ask questions and export analyzed PDF reports</div>', unsafe_allow_html=True)
    with right_col:
        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("Username", placeholder="Enter username")
            password = st.text_input("Password", type="password", placeholder="Enter password")
            submit = st.form_submit_button("Sign In", use_container_width=True)

        guest_login = st.button("Continue as Guest", use_container_width=True)

        if submit:
            if username == AUTH_USERNAME and password == AUTH_PASSWORD:
                st.session_state.is_authenticated = True
                st.session_state.auth_user = username
                st.success("Login successful")
                st.rerun()
            else:
                st.error("Invalid username or password.")

        if guest_login:
            st.session_state.is_authenticated = True
            st.session_state.auth_user = "guest"
            st.success("Guest session started")
            st.rerun()

        if AUTH_USERNAME == "admin" and AUTH_PASSWORD == "contractguard123":
            st.caption("Default demo credentials: admin / contractguard123")


@st.cache_data(show_spinner=False, ttl=86400)
def _translate_text_cached(text: str, target_lang: str) -> str:
    """Translate text using a public Google endpoint and cache results for speed."""
    if not text or target_lang == "en":
        return text

    target_lang = _effective_translation_code(target_lang)

    chunks = [text[i : i + 1400] for i in range(0, len(text), 1400)]
    translated_parts: List[str] = []

    for chunk in chunks:
        response = requests.get(
            "https://translate.googleapis.com/translate_a/single",
            params={
                "client": "gtx",
                "sl": "auto",
                "tl": target_lang,
                "dt": "t",
                "q": chunk,
            },
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        translated_chunk = "".join(part[0] for part in payload[0] if part and part[0])
        translated_parts.append(translated_chunk)

    return "".join(translated_parts)


def _translate_for_ui(text: str, target_lang: str) -> str:
    if target_lang == "en" or not text:
        return text
    try:
        return _translate_text_cached(text, target_lang)
    except Exception:
        return text


def _translated_risk_data(risk_data: Dict[str, Any], target_lang: str) -> Dict[str, Any]:
    if target_lang == "en" or not risk_data:
        return risk_data

    translated = copy.deepcopy(risk_data)
    translated["risk_level"] = _translate_for_ui(str(risk_data.get("risk_level", "Unknown")), target_lang)
    translated_risks = []

    for risk in risk_data.get("risks", []):
        item = dict(risk)
        item["title"] = _translate_for_ui(str(risk.get("title", "Unknown Clause")), target_lang)
        item["severity"] = _translate_for_ui(str(risk.get("severity", "Unknown")), target_lang)
        item["evidence"] = _translate_for_ui(str(risk.get("evidence", "")), target_lang)
        translated_risks.append(item)

    translated["risks"] = translated_risks
    return translated


def _translated_compare_data(compare_data: Dict[str, Any], target_lang: str) -> Dict[str, Any]:
    if target_lang == "en" or not compare_data:
        return compare_data

    translated = copy.deepcopy(compare_data)
    translated["summary"] = _translate_for_ui(str(compare_data.get("summary", "")), target_lang)
    details = translated.get("details", {})
    details["summary"] = _translate_for_ui(str(details.get("summary", "")), target_lang)
    details["winner"] = _translate_for_ui(str(details.get("winner", "Tie")), target_lang)

    translated_rows = []
    for row in details.get("category_comparison", []):
        row_copy = dict(row)
        row_copy["label"] = _translate_for_ui(str(row.get("label", "")), target_lang)
        row_copy["contract_a_verdict"] = _translate_for_ui(
            str(row.get("contract_a_verdict", "")), target_lang
        )
        row_copy["contract_b_verdict"] = _translate_for_ui(
            str(row.get("contract_b_verdict", "")), target_lang
        )
        translated_rows.append(row_copy)

    details["category_comparison"] = translated_rows
    translated["details"] = details
    return translated


st.set_page_config(page_title="ContractGuard AI", layout="wide")
_init_state()
_inject_theme()

if not st.session_state.is_authenticated:
    _render_login_landing()
    st.stop()

if RUNNING_ON_RENDER and "onrender.com" not in API_BASE_URL:
    st.error(
        "API_BASE_URL looks invalid. Set it in Render frontend environment "
        "variables to your backend URL (for example, https://contractguard-backend.onrender.com)."
    )

# 1) Header
st.markdown(
    """
    <section class="hero-wrap">
        <div class="hero-kicker">Contract Intelligence</div>
        <h1 class="hero-title">ContractGuard AI</h1>
        <p class="hero-sub">Upload or paste a contract and get rapid risk insights, a focused summary, and clause-aware Q&A in one place.</p>
    </section>
    """,
    unsafe_allow_html=True,
)

nav_left, nav_right = st.columns([3, 2])
with nav_right:
    st.markdown("<div style='text-align:right;color:#1f2a33;font-weight:700;font-size:0.9rem;margin-top:0.2rem;'>Language</div>", unsafe_allow_html=True)
    current_lang = st.selectbox(
        "Language",
        options=list(LANGUAGE_OPTIONS.keys()),
        index=list(LANGUAGE_OPTIONS.keys()).index(st.session_state.selected_language),
        label_visibility="collapsed",
        key="top_language_selector",
        on_change=_on_language_change,
    )
    if current_lang != st.session_state.selected_language:
        st.session_state.selected_language = current_lang
        st.session_state.selected_language_code = LANGUAGE_OPTIONS[current_lang]
        st.rerun()

if st.session_state.selected_language_code != "en":
    st.caption(
        "Dynamic content is translated when available. "
        "If a language variant is unsupported by the translation service, English text is shown."
    )

st.markdown("<hr class='divider' />", unsafe_allow_html=True)

with st.sidebar:
    st.subheader("Workspace")
    toggle_label = "Minimize Workspace" if st.session_state.workspace_sidebar_open else "Open Workspace"
    if st.button(toggle_label, use_container_width=True):
        st.session_state.workspace_sidebar_open = not st.session_state.workspace_sidebar_open
        st.rerun()

    if st.session_state.workspace_sidebar_open:
        if st.session_state.known_contracts:
            selected_contract = st.selectbox(
                "Switch active contract",
                options=list(st.session_state.known_contracts.keys()),
                format_func=lambda cid: st.session_state.known_contracts.get(cid, cid),
                index=max(
                    0,
                    list(st.session_state.known_contracts.keys()).index(st.session_state.contract_id)
                    if st.session_state.contract_id in st.session_state.known_contracts
                    else 0,
                ),
            )
            if selected_contract != st.session_state.contract_id:
                _set_active_contract(selected_contract)
                st.rerun()

            if st.session_state.risk_data and st.session_state.summary_data:
                try:
                    report_lang_choices = [
                        f"Selected language ({st.session_state.selected_language})"
                    ] + [
                        lang for lang in LANGUAGE_OPTIONS.keys() if lang != st.session_state.selected_language
                    ]
                    report_lang_choice = st.selectbox(
                        "Report language",
                        options=report_lang_choices,
                        index=0,
                        key="report_language_select",
                    )

                    if report_lang_choice.startswith("Selected language"):
                        report_lang_name = st.session_state.selected_language
                        report_lang_code = st.session_state.selected_language_code
                    else:
                        report_lang_name = report_lang_choice
                        report_lang_code = LANGUAGE_OPTIONS[report_lang_name]

                    pdf_data = _analysis_report_pdf_bytes(report_lang_code, report_lang_name)
                    st.download_button(
                        label="Download Analyzed Report (PDF)",
                        data=pdf_data,
                        file_name=f"analysis_{st.session_state.contract_id[:8]}.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                    )
                except Exception as pdf_exc:
                    st.warning(
                        "PDF report generation is unavailable right now. "
                        "Install frontend dependencies and retry. "
                        f"Details: {pdf_exc}"
                    )
        else:
            st.info("No contracts analyzed yet.")

    st.markdown("---")
    if st.button("Logout", use_container_width=True):
        st.session_state.is_authenticated = False
        st.session_state.auth_user = ""
        st.rerun()

# 2) Upload Contract Section
st.subheader("Contract Ingestion")
tab_upload, tab_text = st.tabs(["Upload File", "Paste Text"])

with tab_upload:
    uploaded_file = st.file_uploader("Drop PDF or DOCX", type=["pdf", "docx"])
    process_file_clicked = st.button("Analyze Uploaded Contract", type="primary", use_container_width=True)

with tab_text:
    manual_title = st.text_input("Text Title", value="Pasted Contract Text")
    manual_text = st.text_area(
        "Paste contract text",
        height=220,
        placeholder="Paste full contract text here...",
    )
    process_text_clicked = st.button("Analyze Pasted Text", use_container_width=True)

if process_file_clicked:
    if uploaded_file is None:
        st.warning("Please upload a contract file first.")
    else:
        with st.spinner("Uploading and analyzing contract..."):
            try:
                files = {
                    "file": (
                        uploaded_file.name,
                        uploaded_file.getvalue(),
                        uploaded_file.type or "application/octet-stream",
                    )
                }
                upload_resp = _api_post("/upload", files=files)
                upload_resp.raise_for_status()
                upload_json = upload_resp.json()

                contract_id = upload_json["contract_id"]
                filename = upload_json.get("filename", uploaded_file.name)
                st.session_state.contract_id = contract_id
                st.session_state.upload_name = filename
                _remember_contract(contract_id, filename)

                risks_resp = _api_post("/risks", json={"contract_id": contract_id})
                risks_resp.raise_for_status()
                st.session_state.risk_data = risks_resp.json()

                summary_resp = _api_post("/summary", json={"contract_id": contract_id, "max_chars": 900})
                summary_resp.raise_for_status()
                st.session_state.summary_data = summary_resp.json()
                _cache_analysis(
                    contract_id,
                    st.session_state.risk_data,
                    st.session_state.summary_data,
                )

                st.success("Analysis complete.")
            except (requests.RequestException, RuntimeError) as exc:
                st.error(f"API error: {exc}")

if process_text_clicked:
    if not manual_text.strip():
        st.warning("Please paste contract text first.")
    else:
        with st.spinner("Analyzing pasted text..."):
            try:
                ingest_resp = _api_post(
                    "/ingest-text",
                    json={"text": manual_text, "title": manual_title},
                )
                ingest_resp.raise_for_status()
                ingest_json = ingest_resp.json()

                contract_id = ingest_json["contract_id"]
                filename = ingest_json.get("filename", "Pasted Contract Text")
                st.session_state.contract_id = contract_id
                st.session_state.upload_name = filename
                _remember_contract(contract_id, filename)

                risks_resp = _api_post("/risks", json={"contract_id": contract_id})
                risks_resp.raise_for_status()
                st.session_state.risk_data = risks_resp.json()

                summary_resp = _api_post("/summary", json={"contract_id": contract_id, "max_chars": 900})
                summary_resp.raise_for_status()
                st.session_state.summary_data = summary_resp.json()
                _cache_analysis(
                    contract_id,
                    st.session_state.risk_data,
                    st.session_state.summary_data,
                )

                st.success("Text analysis complete.")
            except (requests.RequestException, RuntimeError) as exc:
                st.error(f"API error: {exc}")

if st.session_state.contract_id:
    ui_language = st.session_state.selected_language_code
    active_contract_label = _translate_for_ui("Active Contract", ui_language)
    st.markdown(
        f"<span class='stat-chip'>{active_contract_label}: {st.session_state.upload_name}</span>",
        unsafe_allow_html=True,
    )

if st.session_state.risk_data and st.session_state.summary_data:
    ui_language = st.session_state.selected_language_code
    display_risk_data = _translated_risk_data(st.session_state.risk_data, ui_language)
    display_summary_text = _translate_for_ui(
        str(st.session_state.summary_data.get("summary", "No summary available.")),
        ui_language,
    )

    left_col, right_col = st.columns([1, 2])

    # 3) Contract Risk Score Panel
    with left_col:
        st.subheader("Contract Risk Score")
        safety_score = int(display_risk_data.get("safety_score", 0))
        risk_level = display_risk_data.get("risk_level", "Unknown")
        detected_count = int(display_risk_data.get("detected_clause_count", 0))
        badge_class = _risk_badge_class(risk_level)

        st.metric(label="Safety Score", value=f"{safety_score}/100")
        st.progress(safety_score / 100)
        st.markdown(
            f"<span class='risk-badge {badge_class}'>Risk Level: {risk_level}</span>",
            unsafe_allow_html=True,
        )
        st.write(f"Detected Risky Clauses: {detected_count}")

    # 4) Contract Summary Panel
    with right_col:
        st.subheader("Contract Summary")
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.write(display_summary_text)
        st.markdown("</div>", unsafe_allow_html=True)

    # 5) Risky Clauses Panel
    st.subheader("Risky Clauses")
    risks = display_risk_data.get("risks", [])
    if not risks:
        st.info("No risky clauses detected by keyword scan.")
    else:
        for idx, item in enumerate(risks, start=1):
            title = item.get("title", "Unknown Clause")
            sev = item.get("severity", "Unknown")
            keyword = item.get("keyword", "-")
            evidence = item.get("evidence", "")
            impact = item.get("impact", 0)

            with st.expander(f"{idx}. {title} | Impact: {impact}"):
                st.markdown(f"<span class='severity-pill'>Severity: {sev}</span>", unsafe_allow_html=True)
                st.write(f"Matched keyword: {keyword}")
                st.write(f"Evidence: {evidence}")

    # 6) Contract Q&A Section
    st.subheader("Contract Q&A")
    quick_questions = [
        "What are the termination conditions?",
        "Are there any auto-renewal clauses?",
        "What liability limits are defined?",
    ]
    qcol1, qcol2, qcol3 = st.columns(3)
    if qcol1.button(quick_questions[0], use_container_width=True):
        st.session_state.qa_input = quick_questions[0]
    if qcol2.button(quick_questions[1], use_container_width=True):
        st.session_state.qa_input = quick_questions[1]
    if qcol3.button(quick_questions[2], use_container_width=True):
        st.session_state.qa_input = quick_questions[2]

    question = st.text_input(
        "Ask a question about this contract",
        key="qa_input",
        placeholder="Example: Is there a penalty for delayed delivery?",
    )
    ask_clicked = st.button("Ask Question", use_container_width=True)

    if ask_clicked:
        if not question.strip():
            st.warning("Please enter a question.")
        else:
            with st.spinner("Finding relevant clauses and generating answer..."):
                try:
                    qa_resp = _api_post(
                        "/ask",
                        json={
                            "contract_id": st.session_state.contract_id,
                            "question": question.strip(),
                            "top_k": 4,
                        },
                    )
                    qa_resp.raise_for_status()
                    qa_json = qa_resp.json()
                    st.session_state.qa_answer = qa_json.get("answer", "No answer generated.")
                    st.session_state.qa_history.insert(
                        0,
                        {
                            "question": question.strip(),
                            "answer": st.session_state.qa_answer,
                            "contract": st.session_state.upload_name,
                        },
                    )
                    st.session_state.qa_history = st.session_state.qa_history[:10]
                    st.markdown(
                        f"<span class='stat-chip'>Retrieved Chunks: {qa_json.get('retrieved_chunks_count', 0)}</span>",
                        unsafe_allow_html=True,
                    )
                except (requests.RequestException, RuntimeError) as exc:
                    st.error(f"Q&A error: {exc}")

    if st.session_state.qa_answer:
        st.markdown("### Answer")
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.write(_translate_for_ui(st.session_state.qa_answer, ui_language))
        st.markdown("</div>", unsafe_allow_html=True)

    if st.session_state.qa_history:
        st.markdown("### Recent Q&A")
        for idx, qa_item in enumerate(st.session_state.qa_history[:5], start=1):
            translated_q = _translate_for_ui(str(qa_item["question"]), ui_language)
            translated_a = _translate_for_ui(str(qa_item["answer"]), ui_language)
            with st.expander(f"{idx}. {translated_q} ({qa_item['contract']})"):
                st.write(translated_a)

st.markdown("<hr class='divider' />", unsafe_allow_html=True)
st.subheader("Compare Contracts")
if len(st.session_state.known_contracts) < 2:
    st.info("Analyze at least two contracts to enable side-by-side comparison.")
else:
    known_ids = list(st.session_state.known_contracts.keys())
    col_a, col_b = st.columns(2)
    with col_a:
        contract_a = st.selectbox(
            "Contract A",
            options=known_ids,
            format_func=lambda cid: st.session_state.known_contracts.get(cid, cid),
            key="compare_a",
        )
    with col_b:
        default_b_index = 1 if len(known_ids) > 1 else 0
        contract_b = st.selectbox(
            "Contract B",
            options=known_ids,
            format_func=lambda cid: st.session_state.known_contracts.get(cid, cid),
            index=default_b_index,
            key="compare_b",
        )

    compare_clicked = st.button("Compare Selected Contracts", use_container_width=True)
    if compare_clicked:
        if contract_a == contract_b:
            st.warning("Select two different contracts for comparison.")
        else:
            with st.spinner("Comparing contracts..."):
                try:
                    compare_resp = _api_post(
                        "/compare",
                        json={"contract_id_a": contract_a, "contract_id_b": contract_b},
                    )
                    compare_resp.raise_for_status()
                    st.session_state.compare_result = compare_resp.json()
                except (requests.RequestException, RuntimeError) as exc:
                    st.error(f"Comparison error: {exc}")

    if st.session_state.compare_result:
        compare_data = _translated_compare_data(
            st.session_state.compare_result,
            st.session_state.selected_language_code,
        )
        details = compare_data.get("details", {})
        winner = details.get("winner", "Tie")

        st.markdown("### Comparison Outcome")
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.write(compare_data.get("summary", "No summary available."))
        st.write(f"Winner: {winner}")
        st.markdown("</div>", unsafe_allow_html=True)

        category_rows = details.get("category_comparison", [])
        if category_rows:
            st.markdown("### Category Breakdown")
            st.table(category_rows)
