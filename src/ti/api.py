"""FastAPI service with API-key authentication, RBAC, and audited access.

Run with: uvicorn ti.api:app --app-dir src --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field

from .agents import TranscriptAgentSystem
from .corpus import load_corpus
from .governance import AccessContext, AuthorizationError
from .retrieval import HybridRetriever


ROOT = Path(__file__).resolve().parents[2]
app = FastAPI(title="Transcript Intelligence API", version="2.0.0")


class AnalyzeRequest(BaseModel):
    meeting_id: str = Field(min_length=10, max_length=64)


def _configured_keys() -> dict[str, tuple[str, tuple[str, ...]]]:
    # Format: key=role:scope1|scope2,key2=admin:
    raw = os.getenv("TI_API_KEYS", "local-admin=admin:")
    result = {}
    for entry in raw.split(","):
        if "=" not in entry:
            continue
        key, config = entry.split("=", 1)
        role, _, scopes = config.partition(":")
        result[key] = (role, tuple(filter(None, scopes.split("|"))))
    return result


def access_context(x_api_key: str = Header(alias="X-API-Key")) -> AccessContext:
    config = _configured_keys().get(x_api_key)
    if not config:
        raise HTTPException(status_code=401, detail="Invalid API key")
    role, scopes = config
    return AccessContext(subject=f"api-key:{x_api_key[:4]}", role=role, account_scopes=scopes)


@lru_cache(maxsize=1)
def services() -> tuple[HybridRetriever, TranscriptAgentSystem]:
    chunks = load_corpus(ROOT / "data" / "raw")
    retriever = HybridRetriever(chunks)
    agent = TranscriptAgentSystem(ROOT / "data" / "raw", retriever, ROOT / "runtime")
    return retriever, agent


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/search")
def search(
    q: str = Query(min_length=3, max_length=500),
    account_domain: str = Query(default="", max_length=200),
    top_k: int = Query(default=5, ge=1, le=20),
    context: AccessContext = Depends(access_context),
):
    retriever, _ = services()
    try:
        return {"results": retriever.search(q, context, top_k=top_k, account_domain=account_domain)}
    except AuthorizationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@app.post("/v1/analyze")
def analyze(request: AnalyzeRequest, context: AccessContext = Depends(access_context)):
    _, agent = services()
    try:
        state = agent.analyze(request.meeting_id, context)
        return {
            "run_id": state.run_id,
            "status": state.status,
            "report": state.data.get("report"),
            "decisions": state.decisions,
            "policy_flags": state.policy_flags,
        }
    except AuthorizationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
