import time

from fastapi.testclient import TestClient

from backend.main import app


def test_health_check() -> None:
    with TestClient(app) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert response.json()["message"] == "ContractGuard backend is running"


def test_ingest_summary_and_risks_flow() -> None:
    with TestClient(app) as client:
        ingest = client.post(
            "/ingest-text",
            json={
                "title": "Smoke Contract",
                "text": "Payment schedule is net 30 days. Liability is limited to direct damages.",
            },
        )
        assert ingest.status_code == 200

        contract_id = ingest.json()["contract_id"]

        summary = client.post("/summary", json={"contract_id": contract_id, "max_chars": 250})
        assert summary.status_code == 200
        assert "summary" in summary.json()

        risks = client.post("/risks", json={"contract_id": contract_id})
        assert risks.status_code == 200
        payload = risks.json()
        assert payload["contract_id"] == contract_id
        assert "risk_level" in payload


def test_compare_flow() -> None:
    with TestClient(app) as client:
        ingest_a = client.post(
            "/ingest-text",
            json={
                "title": "Contract A",
                "text": "Auto renewal applies and early termination fee may be charged.",
            },
        )
        ingest_b = client.post(
            "/ingest-text",
            json={
                "title": "Contract B",
                "text": "Termination for convenience with notice and payment schedule net 30.",
            },
        )

        assert ingest_a.status_code == 200
        assert ingest_b.status_code == 200

        contract_id_a = ingest_a.json()["contract_id"]
        contract_id_b = ingest_b.json()["contract_id"]

        compare = client.post(
            "/compare",
            json={"contract_id_a": contract_id_a, "contract_id_b": contract_id_b},
        )
        assert compare.status_code == 200

        payload = compare.json()
        assert payload["contract_id_a"] == contract_id_a
        assert payload["contract_id_b"] == contract_id_b
        assert "summary" in payload
        assert "details" in payload


def test_contract_status_transitions_to_ready() -> None:
    with TestClient(app) as client:
        ingest = client.post(
            "/ingest-text",
            json={
                "title": "Async Contract",
                "text": "This contract includes payment terms and a liability clause for analysis.",
            },
        )
        assert ingest.status_code == 200
        contract_id = ingest.json()["contract_id"]

        terminal_status = None
        for _ in range(150):
            status_response = client.get(f"/contracts/{contract_id}/status")
            assert status_response.status_code == 200
            status_payload = status_response.json()
            terminal_status = status_payload["status"]
            if terminal_status in {"ready", "failed"}:
                break
            time.sleep(0.2)

        assert terminal_status == "ready"


def test_ask_returns_clause_grounded_answer() -> None:
    with TestClient(app) as client:
        ingest = client.post(
            "/ingest-text",
            json={
                "title": "Obligations and Remedies Contract",
                "text": (
                    "Party B will pay INR 2,00,000 within 15 days. "
                    "Boundary will be demarcated within 30 days. "
                    "In case of dispute, parties may approach the district court for settlement. "
                    "A penalty applies for non-compliance with payment terms."
                ),
            },
        )
        assert ingest.status_code == 200
        contract_id = ingest.json()["contract_id"]

        terminal_status = None
        for _ in range(150):
            status_response = client.get(f"/contracts/{contract_id}/status")
            assert status_response.status_code == 200
            status_payload = status_response.json()
            terminal_status = status_payload["status"]
            if terminal_status in {"ready", "failed"}:
                break
            time.sleep(0.2)

        assert terminal_status == "ready"

        ask = client.post(
            "/ask",
            json={
                "contract_id": contract_id,
                "question": "What are the main obligations and remedies in this contract?",
                "top_k": 4,
            },
        )
        assert ask.status_code == 200
        payload = ask.json()
        answer = payload.get("answer", "")

        assert payload.get("retrieved_chunks_count", 0) >= 1
        assert "Risk type:" not in answer
        lower_answer = answer.lower()
        uses_extractive_fallback = (
            "grounded in uploaded contract text" in answer
            and "Obligations found:" in answer
        )
        uses_llm_answer = ("obligation" in lower_answer) and (
            "remed" in lower_answer or "dispute" in lower_answer
        )
        assert uses_extractive_fallback or uses_llm_answer


def test_upload_rejects_invalid_content_type() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/upload",
            files={"file": ("bad.pdf", b"%PDF-1.7\n", "application/octet-stream")},
        )

        assert response.status_code == 415
        assert "Unsupported content-type" in response.json()["detail"]


def test_upload_rejects_invalid_signature() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/upload",
            files={"file": ("fake.pdf", b"not-a-real-pdf", "application/pdf")},
        )

        assert response.status_code == 400
        assert "signature is invalid" in response.json()["detail"]
