"""Streamlit UI for ContractGuard AI demo flow."""

import os
from urllib.parse import urlparse
import requests
import streamlit as st


RUNNING_ON_RENDER = os.getenv("RENDER", "").lower() == "true"


def _normalize_api_base_url() -> str:
    """Normalize configured API base URL and apply safe Render fallback."""
    configured = os.getenv("API_BASE_URL", "").strip().rstrip("/")

    if configured:
        parsed = urlparse(configured)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return configured

        # Common misconfiguration: host without scheme.
        if not parsed.scheme and parsed.path and "." in parsed.path:
            return f"https://{parsed.path}"

    if RUNNING_ON_RENDER:
        return "https://contractguard-backend.onrender.com"

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


def _api_post(path: str, **kwargs):
    parsed = urlparse(API_BASE_URL)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError(
            "Invalid API_BASE_URL configuration. Set API_BASE_URL to a full URL, "
            "for example: https://contractguard-backend.onrender.com"
        )
    return requests.post(f"{API_BASE_URL}{path}", timeout=90, **kwargs)


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
