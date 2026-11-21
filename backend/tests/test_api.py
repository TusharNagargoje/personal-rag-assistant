from fastapi.testclient import TestClient
from uuid import uuid4

from app.main import app


def test_health_and_security_headers():
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_private_routes_require_authentication():
    with TestClient(app) as client:
        response = client.get("/api/v1/documents/")
    assert response.status_code == 401


def test_upload_to_cited_chat_without_external_llm_key():
    with TestClient(app) as client:
        email = f"test-{uuid4().hex}@example.com"
        registration = client.post("/api/v1/auth/register", json={"email": email, "password": "secure-test-password"})
        assert registration.status_code == 201
        login = client.post("/api/v1/auth/login", json={"email": email, "password": "secure-test-password"})
        assert login.status_code == 200
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        upload = client.post(
            "/api/v1/documents/upload",
            headers=headers,
            files={"files": ("sample.md", b"# RAG\n\nRetrieval augmented generation retrieves relevant source passages and uses them as context for a language model response.", "text/markdown")},
        )
        assert upload.status_code == 202
        document = upload.json()[0]
        indexed = client.get(f"/api/v1/documents/{document['id']}", headers=headers)
        assert indexed.status_code == 200
        assert indexed.json()["status"] == "indexed"
        session = client.post("/api/v1/chat/sessions", headers=headers, json={"title": "Sample question"})
        assert session.status_code == 201
        chat = client.post(
            f"/api/v1/chat/sessions/{session.json()['id']}/messages",
            headers=headers,
            json={"content": "What does retrieval augmented generation do?", "stream": True},
        )
        assert chat.status_code == 200
        assert '"type": "done"' in chat.text
        assert '"filename": "sample.md"' in chat.text
