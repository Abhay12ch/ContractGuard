"""Streamlit UI for ContractGuard AI demo flow."""

import os
import time
import tempfile
import uuid
import json
import copy
import html
import re
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
    from backend.contracts.analyzer import analyze_contract
    from backend.contracts.comparator import compare_contracts
    from backend.contracts.embedder import build_faiss_store, chunk_contract_text, retrieve_relevant_chunks
    from backend.contracts.parser import extract_text_from_file
    from backend.contracts.qa_chain import answer_question

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
    if "upload_queue" not in st.session_state:
        st.session_state.upload_queue = []
    if "processing_count" not in st.session_state:
        st.session_state.processing_count = 0
    if "failed_count" not in st.session_state:
        st.session_state.failed_count = 0
    if "active_dashboard_tab" not in st.session_state:
        st.session_state.active_dashboard_tab = "Upload"
    if "contracts_show_filters" not in st.session_state:
        st.session_state.contracts_show_filters = False
    if "contracts_status_filter" not in st.session_state:
        st.session_state.contracts_status_filter = "All"
    if "contracts_search" not in st.session_state:
        st.session_state.contracts_search = ""
    if "analytics_view_tab" not in st.session_state:
        st.session_state.analytics_view_tab = "Overview"


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.2f} KB"
    return f"{size_bytes / (1024 * 1024):.2f} MB"


def _normalize_queue_status(status: str) -> str:
    value = str(status or "").strip().lower()
    if value == "ready":
        return "Completed"
    if value == "processing":
        return "Processing"
    if value == "failed":
        return "Failed"
    if value in {"completed", "failed", "processing"}:
        return value.title()
    return "Completed"


def _status_progress(status_label: str) -> int:
    normalized = _normalize_queue_status(status_label)
    if normalized == "Completed":
        return 100
    if normalized == "Failed":
        return 100
    return 45


def _refresh_upload_metrics() -> None:
    queue = st.session_state.upload_queue
    st.session_state.processing_count = sum(
        1 for item in queue if _normalize_queue_status(item.get("status", "")) == "Processing"
    )
    st.session_state.failed_count = sum(
        1 for item in queue if _normalize_queue_status(item.get("status", "")) == "Failed"
    )


def _queue_size_for_contract(contract_id: str) -> int:
    normalized = str(contract_id or "").strip()
    for item in st.session_state.upload_queue:
        if str(item.get("contract_id", "")).strip() == normalized:
            return max(int(item.get("size_bytes", 0)), 0)
    return 0


def _queue_upload_item(filename: str, contract_id: str, size_bytes: int, status: str) -> None:
    normalized_status = _normalize_queue_status(status)
    normalized_contract_id = str(contract_id or "").strip()
    existing_item = None

    if normalized_contract_id and normalized_contract_id != "N/A":
        for item in st.session_state.upload_queue:
            if str(item.get("contract_id", "")).strip() == normalized_contract_id:
                existing_item = item
                break

    if existing_item is not None:
        existing_item["filename"] = filename
        existing_item["size_bytes"] = max(int(size_bytes), 0)
        existing_item["status"] = normalized_status
    else:
        st.session_state.upload_queue.insert(
            0,
            {
                "filename": filename,
                "contract_id": normalized_contract_id or "N/A",
                "size_bytes": max(int(size_bytes), 0),
                "status": normalized_status,
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    st.session_state.upload_queue = st.session_state.upload_queue[:20]
    _refresh_upload_metrics()


def _collect_contract_rows() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    # Use analyzed contracts as source of truth and enrich with latest queue metadata.
    queue_by_contract_id: Dict[str, Dict[str, Any]] = {}
    for item in st.session_state.upload_queue:
        contract_id = str(item.get("contract_id", "")).strip()
        if not contract_id or contract_id == "N/A":
            continue
        if contract_id in queue_by_contract_id:
            continue
        queue_by_contract_id[contract_id] = item

    for contract_id, filename in st.session_state.known_contracts.items():
        queue_item = queue_by_contract_id.get(str(contract_id), {})
        uploaded_at_raw = str(queue_item.get("uploaded_at", "")).strip()
        uploaded_display = "-"
        uploaded_sort = ""
        if uploaded_at_raw:
            try:
                dt = datetime.fromisoformat(uploaded_at_raw)
                uploaded_display = (
                    f"{dt.strftime('%b')} {dt.day}, {dt.year} at {dt.strftime('%I:%M %p')}"
                )
                uploaded_sort = uploaded_at_raw
            except ValueError:
                uploaded_display = uploaded_at_raw
                uploaded_sort = uploaded_at_raw

        rows.append(
            {
                "filename": str(filename),
                "contract_id": str(contract_id),
                "status": _normalize_queue_status(queue_item.get("status", "Completed")),
                "uploaded": uploaded_display,
                "uploaded_sort": uploaded_sort,
                "size_bytes": max(int(queue_item.get("size_bytes", 0)), 0),
                "progress": _status_progress(queue_item.get("status", "Completed")),
            }
        )

    rows.sort(key=lambda row: row.get("uploaded_sort", ""), reverse=True)
    return rows


def _render_contracts_tab() -> None:
    all_rows = _collect_contract_rows()
    total_count = len(all_rows)

    panel_left, panel_right = st.columns([3.5, 1.5])
    with panel_left:
        st.markdown("### Advanced Search & Filters")
    with panel_right:
        action_left, action_right = st.columns(2)
        with action_left:
            if st.button("Reset", key="contracts_reset", use_container_width=True):
                st.session_state.contracts_search = ""
                st.session_state.contracts_status_filter = "All"
                st.rerun()
        with action_right:
            toggle_text = "Hide Filters" if st.session_state.contracts_show_filters else "Show Filters"
            if st.button(toggle_text, key="contracts_toggle_filters", use_container_width=True):
                st.session_state.contracts_show_filters = not st.session_state.contracts_show_filters
                st.rerun()

    st.markdown("<div class='contracts-filter-shell'>", unsafe_allow_html=True)
    st.text_input(
        "Search Contracts",
        placeholder="Search by filename, contract ID, or content...",
        key="contracts_search",
    )
    if st.session_state.contracts_show_filters:
        st.selectbox(
            "Status",
            options=["All", "Processing", "Completed", "Failed"],
            key="contracts_status_filter",
        )
    st.markdown("</div>", unsafe_allow_html=True)

    query = st.session_state.contracts_search.strip().lower()
    selected_status = st.session_state.contracts_status_filter.lower()

    filtered_rows = []
    for row in all_rows:
        if selected_status != "all" and row["status"].lower() != selected_status:
            continue
        searchable = f"{row['filename']} {row['contract_id']}".lower()
        if query and query not in searchable:
            continue
        filtered_rows.append(row)

    contracts_head_html = (
        '<div class="contracts-list-head">'
        '<h3 class="contracts-list-title">'
        f'Contract List <span class="contracts-total-pill">{len(filtered_rows)} total</span>'
        '</h3>'
        '</div>'
    )
    st.markdown(contracts_head_html, unsafe_allow_html=True)

    if not filtered_rows:
        st.info("No contracts matched the current filters.")
        return

    table_rows_html = []
    for row in filtered_rows:
        status_lower = row["status"].lower()
        if status_lower == "failed":
            status_class = "failed"
        elif status_lower == "processing":
            status_class = "processing"
        else:
            status_class = "completed"
        progress_pct = max(0, min(int(row["progress"]), 100))
        table_rows_html.append(
            (
                '<tr>'
                '<td>'
                f'<div class="ct-filename">{html.escape(row["filename"])}</div>'
                f'<div class="ct-id">ID: {html.escape(row["contract_id"])}</div>'
                '</td>'
                f'<td><span class="ct-status {status_class}">{html.escape(row["status"])}</span></td>'
                f'<td>{html.escape(row["uploaded"])}</td>'
                f'<td>{_format_size(row["size_bytes"])}</td>'
                '<td>'
                '<div class="ct-progress-wrap">'
                f'<div class="ct-progress-bar"><span style="width:{progress_pct}%;"></span></div>'
                f'<div class="ct-progress-text">{progress_pct}%</div>'
                '</div>'
                '</td>'
                '<td class="ct-actions">...</td>'
                '</tr>'
            )
        )

    contracts_table_html = (
        '<div class="contracts-table-shell">'
        '<table class="contracts-table">'
        '<thead>'
        '<tr>'
        '<th>Filename</th>'
        '<th>Status</th>'
        '<th>Uploaded</th>'
        '<th>Size</th>'
        '<th>Progress</th>'
        '<th>Actions</th>'
        '</tr>'
        '</thead>'
        '<tbody>'
        f"{''.join(table_rows_html)}"
        '</tbody>'
        '</table>'
        '</div>'
    )
    st.markdown(contracts_table_html, unsafe_allow_html=True)

    st.caption(f"Showing {len(filtered_rows)} of {total_count} contracts")


def _extract_match(text: str, patterns: List[str]) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        value = ""
        if match.groups():
            value = str(match.group(1)).strip(" .,:;\n\t")
        else:
            value = str(match.group(0)).strip(" .,:;\n\t")
        if value:
            return value
    return ""


def _confidence_from_value(value: str) -> int:
    # Confidence reflects whether the value was extracted from analyzed content.
    return 88 if value else 0


def _analytics_data_model() -> Dict[str, Any]:
    risk_data = st.session_state.risk_data or {}
    summary_text = str((st.session_state.summary_data or {}).get("summary", "")).strip()
    risks = risk_data.get("risks", []) or []

    evidence_blob = " ".join(
        f"{str(item.get('title', ''))}. {str(item.get('evidence', ''))}"
        for item in risks
    )
    analysis_text = " ".join([summary_text, evidence_blob]).strip()

    customer_value = _extract_match(
        analysis_text,
        [
            r"customer\s*[:\-]\s*([A-Za-z0-9&.,'\-\s]{3,80})",
            r"client\s*[:\-]\s*([A-Za-z0-9&.,'\-\s]{3,80})",
            r"between\s+([A-Za-z0-9&.,'\-\s]{3,60})\s+and",
        ],
    )
    vendor_value = _extract_match(
        analysis_text,
        [
            r"vendor\s*[:\-]\s*([A-Za-z0-9&.,'\-\s]{3,80})",
            r"supplier\s*[:\-]\s*([A-Za-z0-9&.,'\-\s]{3,80})",
            r"between\s+[A-Za-z0-9&.,'\-\s]{3,60}\s+and\s+([A-Za-z0-9&.,'\-\s]{3,60})",
        ],
    )
    payment_terms_value = _extract_match(
        analysis_text,
        [
            r"(net\s*\d{1,3})",
            r"payment\s+within\s+\d{1,3}\s+days",
            r"due\s+on\s+receipt",
            r"advance\s+payment",
        ],
    )
    billing_cycle_value = _extract_match(
        analysis_text,
        [
            r"(\$\s?[\d,]+(?:\.\d{2})?\s+per\s+(?:month|year|quarter|week))",
            r"billing\s+cycle\s*[:\-]\s*([A-Za-z\s]{3,40})",
            r"(monthly|quarterly|annually|yearly|weekly)\s+billing",
        ],
    )
    renewal_terms_value = _extract_match(
        analysis_text,
        [
            r"([^.\n]{0,80}auto-?renew[^.\n]{0,140})",
            r"([^.\n]{0,80}renewal[^.\n]{0,140})",
            r"([^.\n]{0,80}term\s+of\s+\d+\s+(?:month|year)[^.\n]{0,120})",
        ],
    )

    customer_conf = _confidence_from_value(customer_value)
    vendor_conf = _confidence_from_value(vendor_value)
    payment_conf = _confidence_from_value(payment_terms_value)
    billing_conf = _confidence_from_value(billing_cycle_value)
    terms_conf = _confidence_from_value(renewal_terms_value)

    field_values = [
        customer_value,
        vendor_value,
        payment_terms_value,
        billing_cycle_value,
        renewal_terms_value,
    ]
    field_confs = [customer_conf, vendor_conf, payment_conf, billing_conf, terms_conf]
    extracted_fields = sum(1 for value in field_values if value)
    identified_gaps = 5 - extracted_fields
    extracted_confs = [conf for conf in field_confs if conf > 0]
    avg_conf = int(round(sum(extracted_confs) / len(extracted_confs))) if extracted_confs else 0

    terms_text = renewal_terms_value or "No renewal terms extracted from current analysis."

    data_quality_rows = [
        ("Customer Name", customer_conf),
        ("Vendor Name", vendor_conf),
        ("Payment Terms", payment_conf),
        ("Billing Cycle", billing_conf),
        ("Renewal Terms", terms_conf),
    ]

    return {
        "extracted_fields": extracted_fields,
        "avg_conf": avg_conf,
        "gaps": identified_gaps,
        "party": {
            "customer_label": "Customer Name",
            "customer_value": customer_value or "Not found in analysis",
            "vendor_label": "Vendor Name",
            "vendor_value": vendor_value or "Not found in analysis",
            "customer_conf": customer_conf,
            "vendor_conf": vendor_conf,
        },
        "financial": {
            "payment_label": "Payment Terms",
            "payment_value": payment_terms_value or "Not found in analysis",
            "billing_label": "Billing Cycle",
            "billing_value": billing_cycle_value or "Not found in analysis",
            "payment_conf": payment_conf,
            "billing_conf": billing_conf,
        },
        "terms": {
            "title": "Renewal Terms",
            "confidence": terms_conf,
            "text": terms_text,
        },
        "quality_rows": data_quality_rows,
    }


def _render_analytics_tab() -> None:
    if not st.session_state.contract_id or not st.session_state.risk_data or not st.session_state.summary_data:
        st.info("Run contract analysis first. Analytics is populated from the latest analyzed contract.")
        return

    model = _analytics_data_model()

    tab1, tab2, tab3 = st.columns(3)
    with tab1:
        if st.button(
            "Overview",
            key="analytics_tab_overview",
            use_container_width=True,
            type="primary" if st.session_state.analytics_view_tab == "Overview" else "secondary",
        ):
            st.session_state.analytics_view_tab = "Overview"
    with tab2:
        if st.button(
            "Extracted Data",
            key="analytics_tab_extracted",
            use_container_width=True,
            type="primary" if st.session_state.analytics_view_tab == "Extracted Data" else "secondary",
        ):
            st.session_state.analytics_view_tab = "Extracted Data"
    with tab3:
        if st.button(
            "Processing Status",
            key="analytics_tab_processing",
            use_container_width=True,
            type="primary" if st.session_state.analytics_view_tab == "Processing Status" else "secondary",
        ):
            st.session_state.analytics_view_tab = "Processing Status"

    st.markdown(
        f"""
        <div class="aq-overview-card">
            <div class="aq-overview-title">Data Quality Overview</div>
            <div class="aq-kpi-grid">
                <div class="aq-kpi-item">
                    <div class="aq-kpi-value blue">{model['extracted_fields']}</div>
                    <div class="aq-kpi-label">Fields Extracted</div>
                </div>
                <div class="aq-kpi-item">
                    <div class="aq-kpi-value green">{model['avg_conf']}%</div>
                    <div class="aq-kpi-label">Average Confidence</div>
                </div>
                <div class="aq-kpi-item">
                    <div class="aq-kpi-value orange">{model['gaps']}</div>
                    <div class="aq-kpi-label">Identified Gaps</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.session_state.analytics_view_tab == "Processing Status":
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.write("Processing pipeline health")
        st.progress(1.0 if st.session_state.processing_count == 0 else 0.45)
        st.write(f"In queue: {len(st.session_state.upload_queue)}")
        st.write(f"Currently processing: {st.session_state.processing_count}")
        st.write(f"Failed: {st.session_state.failed_count}")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    row_one_a, row_one_b = st.columns(2)
    with row_one_a:
        st.markdown(
            f"""
            <div class="aq-panel green">
                <div class="aq-panel-title">Party Information</div>
                <div class="aq-chip-row soft-green">
                    <div>
                        <div class="aq-chip-label">{html.escape(model['party']['customer_label'])}</div>
                        <div class="aq-chip-value">{html.escape(model['party']['customer_value'])}</div>
                    </div>
                    <span class="aq-conf amber">{model['party']['customer_conf']}%</span>
                </div>
                <div class="aq-chip-row soft-green">
                    <div>
                        <div class="aq-chip-label">{html.escape(model['party']['vendor_label'])}</div>
                        <div class="aq-chip-value">{html.escape(model['party']['vendor_value'])}</div>
                    </div>
                    <span class="aq-conf amber">{model['party']['vendor_conf']}%</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with row_one_b:
        st.markdown(
            f"""
            <div class="aq-panel blue">
                <div class="aq-panel-title">Financial Information</div>
                <div class="aq-chip-row soft-blue">
                    <div>
                        <div class="aq-chip-label">{html.escape(model['financial']['payment_label'])}</div>
                        <div class="aq-chip-value">{html.escape(model['financial']['payment_value'])}</div>
                    </div>
                    <span class="aq-conf green">{model['financial']['payment_conf']}%</span>
                </div>
                <div class="aq-chip-row soft-blue">
                    <div>
                        <div class="aq-chip-label">{html.escape(model['financial']['billing_label'])}</div>
                        <div class="aq-chip-value">{html.escape(model['financial']['billing_value'])}</div>
                    </div>
                    <span class="aq-conf green">{model['financial']['billing_conf']}%</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    row_two_a, row_two_b = st.columns(2)
    with row_two_a:
        st.markdown(
            f"""
            <div class="aq-panel purple tall">
                <div class="aq-panel-title">Contract Terms</div>
                <div class="aq-chip-row soft-purple">
                    <div>
                        <div class="aq-chip-label">{html.escape(model['terms']['title'])}</div>
                    </div>
                    <span class="aq-conf amber">{model['terms']['confidence']}%</span>
                </div>
                <div class="aq-terms-body">{html.escape(model['terms']['text'])}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with row_two_b:
        quality_rows_html = []
        for label, conf in model["quality_rows"]:
            bar_pct = max(0, min(int(conf), 100))
            quality_rows_html.append(
                (
                    f'<div class="aq-quality-row">'
                    f'<div class="aq-quality-label">{html.escape(label)}</div>'
                    f'<div class="aq-quality-meter">'
                    f'<div class="aq-quality-track"><span style="width:{bar_pct}%;"></span></div>'
                    f'<div class="aq-quality-val">{bar_pct}%</div>'
                    f'</div>'
                    f'</div>'
                )
            )

        quality_panel_html = (
            '<div class="aq-panel orange tall">'
            '<div class="aq-panel-title">Data Quality</div>'
            f"{''.join(quality_rows_html)}"
            '</div>'
        )

        st.markdown(
            quality_panel_html,
            unsafe_allow_html=True,
        )


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
            "status": "ready",
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

    if path == "/compare":
        contract_id_a = str(payload.get("contract_id_a", "")).strip()
        contract_id_b = str(payload.get("contract_id_b", "")).strip()
        text_a = st.session_state.local_contract_store.get(contract_id_a)
        text_b = st.session_state.local_contract_store.get(contract_id_b)
        if not text_a or not text_b:
            return _LocalResponse(404, {"detail": "Unknown contract_id. Upload or ingest first."})
        details = compare_contracts(text_a, text_b)
        return _LocalResponse(
            200,
            {
                "contract_id_a": contract_id_a,
                "contract_id_b": contract_id_b,
                "summary": str(details.get("summary", "Comparison not implemented yet")),
                "details": details,
            },
        )

    return _LocalResponse(404, {"detail": f"Unsupported local endpoint: {path}"})


def _local_get(path: str, **kwargs) -> _LocalResponse:
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

    if path == "/":
        return _LocalResponse(200, {"message": "ContractGuard backend is running"})

    status_match = re.match(r"^/contracts/([^/]+)/status$", path)
    if status_match:
        contract_id = status_match.group(1)
        text = st.session_state.local_contract_store.get(contract_id)
        if text is None:
            return _LocalResponse(404, {"detail": f"Contract '{contract_id}' was not found."})

        vector_store = st.session_state.local_vector_stores.get(contract_id) or {}
        embedding_count = int(vector_store.get("embedding_count", 0))
        status_value = "ready" if embedding_count > 0 else "processing"
        return _LocalResponse(
            200,
            {
                "contract_id": contract_id,
                "status": status_value,
                "embedding_count": embedding_count,
                "error": None,
            },
        )

    return _LocalResponse(404, {"detail": f"Unsupported local endpoint: {path}"})


def _resolve_runtime_base_url() -> str:
    parsed = urlparse(API_BASE_URL)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return API_BASE_URL
    return DEFAULT_RENDER_BACKEND_URL


def _api_post(path: str, **kwargs):
    # Local-first mode avoids long blocking waits when the backend service is cold/unavailable.
    if RUNNING_ON_RENDER and PREFER_LOCAL_ON_RENDER and LOCAL_MODE_AVAILABLE:
        return _local_post(path, **kwargs)

    base_url = _resolve_runtime_base_url()

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


def _api_get(path: str, **kwargs):
    if RUNNING_ON_RENDER and PREFER_LOCAL_ON_RENDER and LOCAL_MODE_AVAILABLE:
        return _local_get(path, **kwargs)

    base_url = _resolve_runtime_base_url()

    timeout_seconds = kwargs.pop("timeout", 45)
    attempts = 4
    delay_seconds = 2
    last_exc: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            response = requests.get(f"{base_url}{path}", timeout=timeout_seconds, **kwargs)
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
                return _local_get(path, **kwargs)
            raise

    if last_exc is not None:
        if LOCAL_MODE_AVAILABLE:
            return _local_get(path, **kwargs)
        raise last_exc

    raise RuntimeError("Backend request failed after retries.")


def _fetch_contract_status(contract_id: str) -> dict | None:
    normalized = str(contract_id or "").strip()
    if not normalized:
        return None
    try:
        response = _api_get(f"/contracts/{normalized}/status")
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict):
            return payload
    except (requests.RequestException, RuntimeError):
        return None
    return None


def _wait_for_contract_ready(
    contract_id: str,
    *,
    timeout_seconds: int = 90,
    poll_interval_seconds: float = 1.25,
) -> dict | None:
    deadline = time.time() + timeout_seconds
    latest_payload: dict | None = None

    while time.time() < deadline:
        latest_payload = _fetch_contract_status(contract_id)
        if latest_payload is None:
            return None
        status_value = str(latest_payload.get("status", "")).strip().lower()
        if status_value in {"ready", "failed"}:
            return latest_payload
        time.sleep(poll_interval_seconds)

    return latest_payload


def _status_value(payload: dict | None) -> str:
    if not payload:
        return ""
    return str(payload.get("status", "")).strip().lower()


def _update_queue_status_from_backend(contract_id: str, filename: str, size_bytes: int) -> dict | None:
    payload = _fetch_contract_status(contract_id)
    if payload:
        _queue_upload_item(
            filename=filename,
            contract_id=contract_id,
            size_bytes=size_bytes,
            status=str(payload.get("status", "processing")),
        )
    return payload


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

        .dashboard-head {
            margin-top: 0.2rem;
            margin-bottom: 0.65rem;
        }

        .dashboard-title {
            margin: 0;
            font-family: 'Space Grotesk', sans-serif;
            font-size: 2rem;
            color: #1f2a33;
            line-height: 1.1;
        }

        .dashboard-sub {
            margin: 0.3rem 0 0 0;
            color: #5d6a74;
            font-size: 0.98rem;
            font-weight: 600;
        }

        .metric-card {
            border: 1px solid rgba(31, 42, 51, 0.18);
            border-radius: 12px;
            background: rgba(255, 255, 255, 0.74);
            box-shadow: 0 5px 16px rgba(31, 42, 51, 0.08);
            padding: 0.95rem 1rem;
            min-height: 98px;
        }

        .metric-label {
            font-size: 0.95rem;
            color: #324557;
            font-weight: 700;
            margin-bottom: 0.62rem;
        }

        .metric-value {
            font-size: 2rem;
            color: #163247;
            font-family: 'Space Grotesk', sans-serif;
            font-weight: 700;
            line-height: 1;
        }

        .metric-completed .metric-value {
            color: #166534;
        }

        .metric-failed .metric-value {
            color: #b91c1c;
        }

        .tab-strip {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 0.6rem;
            margin: 1rem 0 0.9rem 0;
        }

        .tab-chip {
            border: 1px solid rgba(31, 42, 51, 0.17);
            border-radius: 10px;
            background: rgba(255, 255, 255, 0.64);
            padding: 0.58rem 0.8rem;
            text-align: center;
            font-weight: 700;
            color: #304458;
        }

        .tab-chip.active {
            border-color: rgba(15, 118, 110, 0.42);
            background: rgba(223, 247, 243, 0.76);
            color: #0f5f58;
        }

        .upload-shell {
            border: 1px solid rgba(31, 42, 51, 0.2);
            border-radius: 14px;
            background: rgba(255, 255, 255, 0.68);
            box-shadow: 0 8px 22px rgba(31, 42, 51, 0.07);
            padding: 1rem 1rem 0.85rem 1rem;
        }

        .upload-top {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.7rem;
            margin-bottom: 0.8rem;
        }

        .upload-title {
            margin: 0;
            color: #203447;
            font-size: 1.06rem;
            font-weight: 800;
            font-family: 'Space Grotesk', sans-serif;
        }

        .upload-done-pill {
            border-radius: 999px;
            background: #16a34a;
            color: #ffffff;
            font-size: 0.8rem;
            font-weight: 700;
            padding: 0.25rem 0.62rem;
            border: 1px solid rgba(22, 163, 74, 0.3);
        }

        .upload-hint {
            margin-top: 0.45rem;
            border: 1px solid rgba(31, 42, 51, 0.2);
            border-radius: 10px;
            padding: 0.64rem 0.72rem;
            background: rgba(246, 250, 251, 0.84);
            color: #5c6873;
            font-size: 0.91rem;
        }

        .queue-shell {
            margin-top: 1.2rem;
            border: 1px solid rgba(31, 42, 51, 0.2);
            border-radius: 14px;
            padding: 0.95rem;
            background: rgba(255, 255, 255, 0.65);
        }

        .queue-head {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 0.75rem;
        }

        .queue-title {
            margin: 0;
            font-size: 1.02rem;
            color: #203447;
            font-weight: 800;
        }

        .queue-count {
            border: 1px solid rgba(31, 42, 51, 0.24);
            border-radius: 8px;
            color: #304458;
            background: rgba(255, 255, 255, 0.72);
            padding: 0.2rem 0.45rem;
            font-size: 0.81rem;
            font-weight: 700;
        }

        .queue-item {
            border: 1px solid rgba(31, 42, 51, 0.18);
            border-radius: 10px;
            padding: 0.64rem 0.72rem;
            background: rgba(255, 255, 255, 0.8);
            margin-bottom: 0.56rem;
        }

        .queue-item-main {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.5rem;
        }

        .queue-file {
            margin: 0;
            color: #1f3142;
            font-weight: 700;
            font-size: 0.93rem;
        }

        .queue-meta {
            margin: 0.2rem 0 0 0;
            color: #60717e;
            font-size: 0.86rem;
        }

        .queue-size {
            color: #4b5f71;
            font-weight: 700;
            font-size: 0.86rem;
        }

        .queue-status {
            border-radius: 999px;
            font-size: 0.76rem;
            font-weight: 800;
            padding: 0.17rem 0.52rem;
            border: 1px solid transparent;
            margin-left: 0.38rem;
        }

        .queue-status.completed {
            background: rgba(22, 163, 74, 0.14);
            color: #166534;
            border-color: rgba(22, 163, 74, 0.35);
        }

        .queue-status.processing {
            background: rgba(234, 179, 8, 0.14);
            color: #854d0e;
            border-color: rgba(234, 179, 8, 0.36);
        }

        .queue-status.failed {
            background: rgba(220, 38, 38, 0.14);
            color: #991b1b;
            border-color: rgba(220, 38, 38, 0.34);
        }

        .st-key-nav_upload button,
        .st-key-nav_contracts button,
        .st-key-nav_analytics button {
            border-radius: 10px;
            border: 1px solid rgba(31, 42, 51, 0.17);
            background: rgba(255, 255, 255, 0.64);
            color: #304458;
            font-weight: 800;
            min-height: 2.25rem;
        }

        .st-key-nav_upload button[kind="primary"],
        .st-key-nav_contracts button[kind="primary"],
        .st-key-nav_analytics button[kind="primary"] {
            border-color: rgba(15, 118, 110, 0.42);
            background: rgba(223, 247, 243, 0.76);
            color: #0f5f58;
            box-shadow: 0 8px 18px rgba(15, 118, 110, 0.12);
        }

        .contracts-filter-shell {
            border: 1px solid rgba(31, 42, 51, 0.2);
            border-radius: 12px;
            padding: 0.8rem 0.9rem;
            margin-bottom: 1rem;
            background: rgba(255, 255, 255, 0.68);
        }

        .contracts-list-head {
            border: 1px solid rgba(31, 42, 51, 0.2);
            border-bottom: none;
            border-radius: 12px 12px 0 0;
            background: rgba(255, 255, 255, 0.74);
            padding: 0.8rem 0.95rem;
            margin-top: 0.45rem;
        }

        .contracts-list-title {
            margin: 0;
            color: #203447;
            font-size: 1.03rem;
            font-weight: 800;
            display: flex;
            align-items: center;
            gap: 0.65rem;
        }

        .contracts-total-pill {
            border: 1px solid rgba(31, 42, 51, 0.2);
            border-radius: 8px;
            font-size: 0.82rem;
            padding: 0.18rem 0.42rem;
            background: rgba(255, 255, 255, 0.75);
            color: #324557;
        }

        .contracts-table-shell {
            border: 1px solid rgba(31, 42, 51, 0.2);
            border-radius: 0 0 12px 12px;
            overflow: hidden;
            background: rgba(255, 255, 255, 0.82);
            box-shadow: 0 7px 20px rgba(31, 42, 51, 0.07);
        }

        .contracts-table {
            width: 100%;
            border-collapse: collapse;
        }

        .contracts-table th,
        .contracts-table td {
            border-bottom: 1px solid rgba(31, 42, 51, 0.15);
            text-align: left;
            padding: 0.62rem 0.75rem;
            vertical-align: middle;
            font-size: 0.9rem;
            color: #33495d;
        }

        .contracts-table thead th {
            background: rgba(247, 252, 251, 0.92);
            color: #586772;
            font-size: 0.85rem;
            font-weight: 800;
        }

        .contracts-table tbody tr:last-child td {
            border-bottom: none;
        }

        .ct-filename {
            color: #1f3246;
            font-weight: 700;
            line-height: 1.18;
            margin-bottom: 0.16rem;
        }

        .ct-id {
            color: #687786;
            font-size: 0.84rem;
        }

        .ct-status {
            border-radius: 7px;
            font-size: 0.8rem;
            font-weight: 800;
            padding: 0.2rem 0.42rem;
            border: 1px solid transparent;
        }

        .ct-status.completed {
            background: #1f4560;
            color: #ffffff;
        }

        .ct-status.processing {
            background: rgba(234, 179, 8, 0.15);
            color: #854d0e;
            border-color: rgba(234, 179, 8, 0.35);
        }

        .ct-status.failed {
            background: rgba(220, 38, 38, 0.15);
            color: #991b1b;
            border-color: rgba(220, 38, 38, 0.34);
        }

        .ct-progress-wrap {
            display: flex;
            align-items: center;
            gap: 0.45rem;
        }

        .ct-progress-bar {
            width: 70px;
            height: 7px;
            border-radius: 999px;
            background: rgba(236, 72, 153, 0.2);
            overflow: hidden;
        }

        .ct-progress-bar span {
            display: block;
            height: 100%;
            background: linear-gradient(90deg, #ec4899, #f43f5e);
        }

        .ct-progress-text {
            font-weight: 700;
            color: #546272;
            font-size: 0.84rem;
        }

        .ct-actions {
            color: #6f7f8e;
            font-weight: 700;
        }

        .st-key-analytics_tab_overview button,
        .st-key-analytics_tab_extracted button,
        .st-key-analytics_tab_processing button {
            border-radius: 10px;
            border: 1px solid rgba(31, 42, 51, 0.16);
            background: rgba(255, 255, 255, 0.72);
            color: #31475a;
            font-weight: 800;
            min-height: 2.35rem;
        }

        .st-key-analytics_tab_overview button[kind="primary"],
        .st-key-analytics_tab_extracted button[kind="primary"],
        .st-key-analytics_tab_processing button[kind="primary"] {
            border-color: rgba(47, 114, 255, 0.3);
            box-shadow: 0 8px 16px rgba(47, 114, 255, 0.1);
        }

        .aq-overview-card {
            margin-top: 0.78rem;
            border: 1px solid rgba(31, 42, 51, 0.2);
            border-left: 3px solid #3b82f6;
            border-radius: 12px;
            padding: 0.95rem 1rem;
            background: rgba(255, 255, 255, 0.74);
        }

        .aq-overview-title {
            font-size: 1.02rem;
            color: #253d51;
            font-weight: 800;
            margin-bottom: 0.72rem;
        }

        .aq-kpi-grid {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 0.75rem;
        }

        .aq-kpi-item {
            text-align: center;
        }

        .aq-kpi-value {
            font-size: 2rem;
            font-family: 'Space Grotesk', sans-serif;
            font-weight: 700;
            line-height: 1;
            margin-bottom: 0.32rem;
        }

        .aq-kpi-value.blue {
            color: #2563eb;
        }

        .aq-kpi-value.green {
            color: #16a34a;
        }

        .aq-kpi-value.orange {
            color: #ea580c;
        }

        .aq-kpi-label {
            color: #677786;
            font-size: 0.91rem;
            font-weight: 700;
        }

        .aq-panel {
            margin-top: 1rem;
            border: 1px solid rgba(31, 42, 51, 0.2);
            border-radius: 12px;
            background: rgba(255, 255, 255, 0.76);
            padding: 0.9rem 0.9rem 0.7rem 0.9rem;
        }

        .aq-panel.green {
            border-left: 3px solid #22c55e;
        }

        .aq-panel.blue {
            border-left: 3px solid #3b82f6;
        }

        .aq-panel.purple {
            border-left: 3px solid #a855f7;
        }

        .aq-panel.orange {
            border-left: 3px solid #f97316;
        }

        .aq-panel.tall {
            min-height: 400px;
        }

        .aq-panel-title {
            color: #223a4f;
            font-weight: 800;
            font-size: 1rem;
            margin-bottom: 0.7rem;
        }

        .aq-chip-row {
            border-radius: 9px;
            padding: 0.68rem 0.62rem;
            margin-bottom: 0.62rem;
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 0.45rem;
        }

        .aq-chip-row.soft-green {
            background: rgba(214, 236, 221, 0.62);
        }

        .aq-chip-row.soft-blue {
            background: rgba(217, 230, 246, 0.62);
        }

        .aq-chip-row.soft-purple {
            background: rgba(235, 224, 250, 0.62);
        }

        .aq-chip-label {
            color: #1f4861;
            font-size: 0.98rem;
            font-weight: 700;
            line-height: 1.15;
        }

        .aq-chip-value {
            color: #19435b;
            margin-top: 0.4rem;
            font-size: 1.55rem;
            font-family: 'Space Grotesk', sans-serif;
            font-weight: 700;
            line-height: 1.1;
        }

        .aq-conf {
            border-radius: 7px;
            color: #ffffff;
            padding: 0.17rem 0.45rem;
            font-size: 0.82rem;
            font-weight: 800;
            border: 1px solid transparent;
            white-space: nowrap;
        }

        .aq-conf.green {
            background: #16a34a;
        }

        .aq-conf.amber {
            background: #ca8a04;
        }

        .aq-terms-body {
            margin-top: 0.2rem;
            color: #7c3aed;
            font-size: 0.94rem;
            line-height: 1.34;
            font-weight: 700;
            max-height: 320px;
            overflow: auto;
            padding-right: 0.2rem;
        }

        .aq-quality-row {
            border-radius: 9px;
            background: rgba(248, 242, 234, 0.9);
            padding: 0.55rem 0.58rem;
            margin-bottom: 0.5rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.55rem;
        }

        .aq-quality-label {
            color: #b45309;
            font-weight: 700;
            font-size: 0.92rem;
        }

        .aq-quality-meter {
            display: flex;
            align-items: center;
            gap: 0.42rem;
        }

        .aq-quality-track {
            width: 74px;
            height: 7px;
            border-radius: 999px;
            background: rgba(148, 163, 184, 0.35);
            overflow: hidden;
        }

        .aq-quality-track span {
            display: block;
            height: 100%;
            background: linear-gradient(90deg, #ec4899, #f43f5e);
        }

        .aq-quality-val {
            color: #ea580c;
            font-size: 0.87rem;
            font-weight: 800;
            min-width: 35px;
            text-align: right;
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

        risk_compare = details.get("risk_comparison", {}) or {}
        if risk_compare:
            pdf.ln(1)
            pdf.multi_cell(
                0,
                7,
                _safe_pdf_text(
                    f"{_translate_for_ui('Risk Score Comparison', report_lang_code)}:\n"
                    f"A Safety: {int(risk_compare.get('contract_a_safety_score', 0))}/100 | "
                    f"A Risk: {int(risk_compare.get('contract_a_risk_score', 100))}/100 | "
                    f"A Level: {risk_compare.get('contract_a_risk_level', 'Unknown')}\n"
                    f"B Safety: {int(risk_compare.get('contract_b_safety_score', 0))}/100 | "
                    f"B Risk: {int(risk_compare.get('contract_b_risk_score', 100))}/100 | "
                    f"B Level: {risk_compare.get('contract_b_risk_level', 'Unknown')}\n"
                    f"{_translate_for_ui('Safer Contract', report_lang_code)}: "
                    f"{risk_compare.get('safer_contract', 'Tie')} "
                    f"({_translate_for_ui('Safety Score Gap', report_lang_code)}: "
                    f"{int(risk_compare.get('safety_score_gap', 0))})"
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

    risk_comparison = dict(details.get("risk_comparison", {}) or {})
    if risk_comparison:
        risk_comparison["contract_a_risk_level"] = _translate_for_ui(
            str(risk_comparison.get("contract_a_risk_level", "Unknown")), target_lang
        )
        risk_comparison["contract_b_risk_level"] = _translate_for_ui(
            str(risk_comparison.get("contract_b_risk_level", "Unknown")), target_lang
        )
        risk_comparison["safer_contract"] = _translate_for_ui(
            str(risk_comparison.get("safer_contract", "Tie")), target_lang
        )
    details["risk_comparison"] = risk_comparison

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
_refresh_upload_metrics()
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
    <div class="dashboard-head">
        <h1 class="dashboard-title">Contract Intelligence</h1>
        <p class="dashboard-sub">Upload, process, and analyze your contracts with AI-powered extraction</p>
    </div>
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

total_contracts = len(st.session_state.known_contracts)
completed_contracts = sum(
    1 for item in st.session_state.upload_queue if str(item.get("status", "")).lower() == "completed"
)

metric_cols = st.columns(4)
with metric_cols[0]:
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-label">Total Contracts</div>
            <div class="metric-value">{total_contracts}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with metric_cols[1]:
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-label">Processing</div>
            <div class="metric-value">{st.session_state.processing_count}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with metric_cols[2]:
    st.markdown(
        f"""
        <div class="metric-card metric-completed">
            <div class="metric-label">Completed</div>
            <div class="metric-value">{completed_contracts}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with metric_cols[3]:
    st.markdown(
        f"""
        <div class="metric-card metric-failed">
            <div class="metric-label">Failed</div>
            <div class="metric-value">{st.session_state.failed_count}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

tab_col_1, tab_col_2, tab_col_3 = st.columns(3)
with tab_col_1:
    if st.button(
        "Upload",
        key="nav_upload",
        use_container_width=True,
        type="primary" if st.session_state.active_dashboard_tab == "Upload" else "secondary",
    ):
        st.session_state.active_dashboard_tab = "Upload"
with tab_col_2:
    if st.button(
        "Contracts",
        key="nav_contracts",
        use_container_width=True,
        type="primary" if st.session_state.active_dashboard_tab == "Contracts" else "secondary",
    ):
        st.session_state.active_dashboard_tab = "Contracts"
with tab_col_3:
    if st.button(
        "Analytics",
        key="nav_analytics",
        use_container_width=True,
        type="primary" if st.session_state.active_dashboard_tab == "Analytics" else "secondary",
    ):
        st.session_state.active_dashboard_tab = "Analytics"

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
if st.session_state.active_dashboard_tab == "Contracts":
    _render_contracts_tab()
    st.stop()

if st.session_state.active_dashboard_tab == "Analytics":
    _render_analytics_tab()
    st.stop()

completed_badge_count = sum(
    1 for item in st.session_state.upload_queue if str(item.get("status", "")).lower() == "completed"
)
st.markdown(
    f"""
    <div class="upload-shell">
        <div class="upload-top">
            <h3 class="upload-title">Upload Contracts</h3>
            <span class="upload-done-pill">{completed_badge_count} completed</span>
        </div>
    """,
    unsafe_allow_html=True,
)

tab_upload, tab_text = st.tabs(["Upload File", "Paste Text"])

with tab_upload:
    st.markdown(
        """
        <div style="text-align:center;border:2px dashed rgba(236, 72, 153, 0.35);border-radius:12px;padding:2rem 1rem;background:rgba(252, 245, 250, 0.55);margin-bottom:0.65rem;">
            <div style="font-size:2rem;line-height:1;">📄</div>
            <div style="margin-top:0.45rem;font-weight:800;color:#2b3f52;">Drag &amp; drop contracts or click to browse</div>
            <div style="margin-top:0.22rem;color:#6a7682;font-size:0.9rem;">Supports PDF files up to 50MB</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    uploaded_file = st.file_uploader("Choose Files", type=["pdf", "docx"])
    process_file_clicked = st.button("Process Uploaded Contract", type="primary", use_container_width=True)

with tab_text:
    manual_title = st.text_input("Text Title", value="Pasted Contract Text")
    manual_text = st.text_area(
        "Paste contract text",
        height=220,
        placeholder="Paste full contract text here...",
    )
    process_text_clicked = st.button("Analyze Pasted Text", use_container_width=True)

st.markdown(
    """
    <div class="upload-hint">
        Files are processed in the background. You can continue using the application while processing completes.
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown("</div>", unsafe_allow_html=True)

if process_file_clicked:
    if uploaded_file is None:
        st.warning("Please upload a contract file first.")
    else:
        with st.spinner("Uploading and analyzing contract..."):
            try:
                file_bytes = uploaded_file.getvalue()
                file_size = int(getattr(uploaded_file, "size", len(file_bytes)))
                files = {
                    "file": (
                        uploaded_file.name,
                        file_bytes,
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
                _queue_upload_item(
                    filename=filename,
                    contract_id=contract_id,
                    size_bytes=file_size,
                    status=str(upload_json.get("status", "processing")),
                )

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
                status_payload = _update_queue_status_from_backend(contract_id, filename, file_size)
                status_value = _status_value(status_payload) or str(upload_json.get("status", "")).strip().lower()
                if status_value == "failed":
                    error_detail = ""
                    if status_payload:
                        error_detail = str(status_payload.get("error", "")).strip()
                    st.error(
                        "Analysis generated summary/risk outputs, but indexing failed. "
                        + (f"Details: {error_detail}" if error_detail else "")
                    )
                elif status_value == "processing":
                    st.info(
                        "Analysis is available. Contract indexing is still processing, "
                        "so Q&A may take a moment to become ready."
                    )
                else:
                    st.success("Analysis complete.")
            except (requests.RequestException, RuntimeError) as exc:
                _queue_upload_item(
                    filename=getattr(uploaded_file, "name", "Uploaded File"),
                    contract_id="N/A",
                    size_bytes=int(getattr(uploaded_file, "size", 0)),
                    status="Failed",
                )
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
                text_size = len(manual_text.encode("utf-8"))
                st.session_state.contract_id = contract_id
                st.session_state.upload_name = filename
                _remember_contract(contract_id, filename)
                _queue_upload_item(
                    filename=filename,
                    contract_id=contract_id,
                    size_bytes=text_size,
                    status=str(ingest_json.get("status", "processing")),
                )

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
                status_payload = _update_queue_status_from_backend(contract_id, filename, text_size)
                status_value = _status_value(status_payload) or str(ingest_json.get("status", "")).strip().lower()
                if status_value == "failed":
                    error_detail = ""
                    if status_payload:
                        error_detail = str(status_payload.get("error", "")).strip()
                    st.error(
                        "Text analysis generated outputs, but indexing failed. "
                        + (f"Details: {error_detail}" if error_detail else "")
                    )
                elif status_value == "processing":
                    st.info(
                        "Text analysis is available. Contract indexing is still processing, "
                        "so Q&A may take a moment to become ready."
                    )
                else:
                    st.success("Text analysis complete.")
            except (requests.RequestException, RuntimeError) as exc:
                _queue_upload_item(
                    filename=manual_title or "Pasted Contract Text",
                    contract_id="N/A",
                    size_bytes=len(manual_text.encode("utf-8")),
                    status="Failed",
                )
                st.error(f"API error: {exc}")

queue_items = st.session_state.upload_queue
st.markdown(
    f"""
    <div class="queue-shell">
        <div class="queue-head">
            <h3 class="queue-title">Upload Queue</h3>
            <span class="queue-count">{len(queue_items)} files</span>
        </div>
    """,
    unsafe_allow_html=True,
)

if not queue_items:
    st.info("No files processed yet.")
else:
    for item in queue_items[:8]:
        status = str(item.get("status", "Completed")).strip().lower()
        if status == "failed":
            status_class = "failed"
        elif status == "processing":
            status_class = "processing"
        else:
            status_class = "completed"
        st.markdown(
            f"""
            <div class="queue-item">
                <div class="queue-item-main">
                    <div>
                        <p class="queue-file">{item.get('filename', 'Unknown file')}
                            <span class="queue-status {status_class}">{item.get('status', 'Completed')}</span>
                        </p>
                        <p class="queue-meta">Contract ID: {item.get('contract_id', 'N/A')}</p>
                    </div>
                    <div class="queue-size">{_format_size(int(item.get('size_bytes', 0)))}</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

st.markdown("</div>", unsafe_allow_html=True)

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
                    active_contract_id = st.session_state.contract_id
                    queue_size = _queue_size_for_contract(active_contract_id)
                    status_payload = _update_queue_status_from_backend(
                        active_contract_id,
                        st.session_state.upload_name,
                        queue_size,
                    )
                    current_status = _status_value(status_payload)

                    if current_status == "failed":
                        detail = str((status_payload or {}).get("error", "")).strip()
                        raise RuntimeError(
                            "Contract indexing failed, so Q&A is unavailable right now. "
                            + (f"Details: {detail}" if detail else "")
                        )

                    if current_status == "processing":
                        waited_payload = _wait_for_contract_ready(active_contract_id)
                        if waited_payload is not None:
                            _queue_upload_item(
                                filename=st.session_state.upload_name,
                                contract_id=active_contract_id,
                                size_bytes=queue_size,
                                status=str(waited_payload.get("status", "processing")),
                            )
                        current_status = _status_value(waited_payload)
                        if current_status == "failed":
                            detail = str((waited_payload or {}).get("error", "")).strip()
                            raise RuntimeError(
                                "Contract indexing failed, so Q&A is unavailable right now. "
                                + (f"Details: {detail}" if detail else "")
                            )
                        if current_status != "ready":
                            raise RuntimeError(
                                "Contract indexing is still in progress. "
                                "Please retry in a few seconds."
                            )

                    qa_resp = _api_post(
                        "/ask",
                        json={
                            "contract_id": st.session_state.contract_id,
                            "question": question.strip(),
                            "top_k": 4,
                        },
                    )
                    if qa_resp.status_code == 409:
                        waited_payload = _wait_for_contract_ready(st.session_state.contract_id)
                        if waited_payload is not None:
                            _queue_upload_item(
                                filename=st.session_state.upload_name,
                                contract_id=st.session_state.contract_id,
                                size_bytes=queue_size,
                                status=str(waited_payload.get("status", "processing")),
                            )
                        if _status_value(waited_payload) == "ready":
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
                    message = str(exc)
                    if "still in progress" in message.lower():
                        st.warning(message)
                    else:
                        st.error(f"Q&A error: {message}")

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
        risk_compare = details.get("risk_comparison", {}) or {}

        st.markdown("### Comparison Outcome")
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.write(compare_data.get("summary", "No summary available."))
        st.write(f"Winner: {winner}")
        st.markdown("</div>", unsafe_allow_html=True)

        if risk_compare:
            lang = st.session_state.selected_language_code
            st.markdown(f"### {_translate_for_ui('Risk Score Comparison', lang)}")

            score_col_a, score_col_b, score_col_c = st.columns(3)
            with score_col_a:
                st.metric(
                    _translate_for_ui("Contract A Safety", lang),
                    f"{int(risk_compare.get('contract_a_safety_score', 0))}/100",
                    f"Risk {int(risk_compare.get('contract_a_risk_score', 100))}/100",
                )
                st.caption(
                    f"{_translate_for_ui('Risk Level', lang)}: "
                    f"{risk_compare.get('contract_a_risk_level', 'Unknown')}"
                )
            with score_col_b:
                st.metric(
                    _translate_for_ui("Contract B Safety", lang),
                    f"{int(risk_compare.get('contract_b_safety_score', 0))}/100",
                    f"Risk {int(risk_compare.get('contract_b_risk_score', 100))}/100",
                )
                st.caption(
                    f"{_translate_for_ui('Risk Level', lang)}: "
                    f"{risk_compare.get('contract_b_risk_level', 'Unknown')}"
                )
            with score_col_c:
                st.metric(
                    _translate_for_ui("Safer Contract", lang),
                    str(risk_compare.get("safer_contract", "Tie")),
                )
                st.caption(
                    f"{_translate_for_ui('Safety Score Gap', lang)}: "
                    f"{int(risk_compare.get('safety_score_gap', 0))}"
                )

        category_rows = details.get("category_comparison", [])
        if category_rows:
            st.markdown("### Category Breakdown")
            st.table(category_rows)
