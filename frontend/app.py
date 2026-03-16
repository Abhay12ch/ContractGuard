"""Streamlit UI for ContractGuard AI demo flow."""

import os
import time
import tempfile
import uuid
from pathlib import Path
from typing import Dict, List
from urllib.parse import urlparse
import requests
import streamlit as st


RUNNING_ON_RENDER = os.getenv("RENDER", "").lower() == "true"
DEFAULT_RENDER_BACKEND_URL = "https://contractguard-backend.onrender.com"
PREFER_LOCAL_ON_RENDER = os.getenv("PREFER_LOCAL_ON_RENDER", "true").lower() == "true"

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


def _init_state() -> None:
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


st.set_page_config(page_title="ContractGuard AI", layout="wide")
_init_state()

if RUNNING_ON_RENDER and "onrender.com" not in API_BASE_URL:
    st.error(
        "API_BASE_URL looks invalid. Set it in Render frontend environment "
        "variables to your backend URL (for example, https://contractguard-backend.onrender.com)."
    )

# 1) Header
st.title("ContractGuard AI")
st.caption("Upload a contract, get a safety score, summary, clause risks, and instant Q&A")
st.caption(f"Backend endpoint: {API_BASE_URL}")
if LOCAL_MODE_AVAILABLE:
    mode = "Local-first" if (RUNNING_ON_RENDER and PREFER_LOCAL_ON_RENDER) else "Fallback"
    st.caption(f"Processing mode: {mode} (local processing available)")

# 2) Upload Contract Section
st.subheader("Upload Contract")
tab_upload, tab_text = st.tabs(["Upload File", "Paste Text"])

with tab_upload:
    uploaded_file = st.file_uploader("Upload PDF or DOCX", type=["pdf", "docx"])
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
                st.session_state.contract_id = contract_id
                st.session_state.upload_name = upload_json.get("filename", uploaded_file.name)

                risks_resp = _api_post("/risks", json={"contract_id": contract_id})
                risks_resp.raise_for_status()
                st.session_state.risk_data = risks_resp.json()

                summary_resp = _api_post("/summary", json={"contract_id": contract_id, "max_chars": 900})
                summary_resp.raise_for_status()
                st.session_state.summary_data = summary_resp.json()

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
                st.session_state.contract_id = contract_id
                st.session_state.upload_name = ingest_json.get("filename", "Pasted Contract Text")

                risks_resp = _api_post("/risks", json={"contract_id": contract_id})
                risks_resp.raise_for_status()
                st.session_state.risk_data = risks_resp.json()

                summary_resp = _api_post("/summary", json={"contract_id": contract_id, "max_chars": 900})
                summary_resp.raise_for_status()
                st.session_state.summary_data = summary_resp.json()

                st.success("Text analysis complete.")
            except (requests.RequestException, RuntimeError) as exc:
                st.error(f"API error: {exc}")

if st.session_state.contract_id:
    st.caption(f"Active contract: {st.session_state.upload_name}")

if st.session_state.risk_data and st.session_state.summary_data:
    left_col, right_col = st.columns([1, 2])

    # 3) Contract Risk Score Panel
    with left_col:
        st.subheader("Contract Risk Score")
        safety_score = int(st.session_state.risk_data.get("safety_score", 0))
        risk_level = st.session_state.risk_data.get("risk_level", "Unknown")
        detected_count = int(st.session_state.risk_data.get("detected_clause_count", 0))

        st.metric(label="Safety Score", value=f"{safety_score}/100")
        st.progress(safety_score / 100)
        st.write(f"Risk Level: **{risk_level}**")
        st.write(f"Detected Risky Clauses: **{detected_count}**")

    # 4) Contract Summary Panel
    with right_col:
        st.subheader("Contract Summary")
        st.write(st.session_state.summary_data.get("summary", "No summary available."))

    # 5) Risky Clauses Panel
    st.subheader("Risky Clauses")
    risks = st.session_state.risk_data.get("risks", [])
    if not risks:
        st.info("No risky clauses detected by keyword scan.")
    else:
        for idx, item in enumerate(risks, start=1):
            title = item.get("title", "Unknown Clause")
            sev = item.get("severity", "Unknown")
            keyword = item.get("keyword", "-")
            evidence = item.get("evidence", "")
            impact = item.get("impact", 0)

            with st.expander(f"{idx}. {title} | Severity: {sev} | Impact: {impact}"):
                st.write(f"Matched keyword: **{keyword}**")
                st.write(f"Evidence: {evidence}")

    # 6) Contract Q&A Section
    st.subheader("Contract Q&A")
    question = st.text_input("Ask a question about this contract")
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
                    st.write(f"Retrieved Chunks: **{qa_json.get('retrieved_chunks_count', 0)}**")
                except (requests.RequestException, RuntimeError) as exc:
                    st.error(f"Q&A error: {exc}")

    if st.session_state.qa_answer:
        st.markdown("### Answer")
        st.write(st.session_state.qa_answer)
