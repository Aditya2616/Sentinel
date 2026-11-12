"""FastAPI service: screening endpoints, audit, metrics, OpenAI-compatible proxy, and the web UI."""

from __future__ import annotations

import json
import os
import time
import uuid
from collections import OrderedDict
from pathlib import Path
from typing import Any, Literal

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .. import __version__
from ..audit import AuditLog
from ..rules import rule_catalogue
from ..screen import Decision, Sentinel

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
ACTION_RANK = {"allow": 0, "flag": 1, "block": 2}
RULES_ONLY_NOTICE = "Running in rules-only mode: no trained classifier was found, so only the pattern rules are active. Run `sentinel train` to enable the classifier."

Source = Literal["user", "document", "tool"]


class ScreenRequest(BaseModel):
    text: str = Field(max_length=200_000)
    source: Source = "user"
    log: bool = True


class BatchItem(BaseModel):
    text: str = Field(max_length=200_000)
    source: Source = "user"


class BatchRequest(BaseModel):
    items: list[BatchItem] = Field(max_length=100)
    log: bool = True


class DocumentItem(BaseModel):
    id: str | None = None
    text: str = Field(max_length=200_000)
    source: Literal["document", "tool"] = "document"


class DocumentsRequest(BaseModel):
    documents: list[DocumentItem] = Field(max_length=50)
    log: bool = True


def _public(d: Decision) -> dict[str, Any]:
    out = d.to_dict()
    if d.mode == "rules-only":
        out["notice"] = RULES_ONLY_NOTICE
    return out


def _message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") in (None, "text", "input_text"))
    return ""


class _LRU:
    def __init__(self, n: int = 512):
        self.n, self.d = n, OrderedDict()

    def get(self, k):
        if k in self.d:
            self.d.move_to_end(k)
            return self.d[k]
        return None

    def put(self, k, v):
        self.d[k] = v
        self.d.move_to_end(k)
        while len(self.d) > self.n:
            self.d.popitem(last=False)


def create_app(
    sentinel: Sentinel | None = None,
    audit: AuditLog | None = None,
    upstream_base_url: str | None = None,
    upstream_api_key: str | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    eval_path: Path | None = None,
    serve_ui: bool = True,
) -> FastAPI:
    audit = audit or AuditLog()
    if sentinel is None:
        sentinel = Sentinel.load(audit=audit)
    elif sentinel.audit is None:
        sentinel.audit = audit
    base = (upstream_base_url if upstream_base_url is not None else os.environ.get("SENTINEL_UPSTREAM_BASE_URL", "")).rstrip("/")
    key = upstream_api_key if upstream_api_key is not None else os.environ.get("SENTINEL_UPSTREAM_API_KEY", "")
    app = FastAPI(title="Sentinel", version=__version__, description="Prompt-injection screening layer and OpenAI-compatible proxy.")
    app.state.sentinel, app.state.audit = sentinel, audit
    cache = _LRU()

    def screen_cached(text: str, source: str, via: str, log: bool = True) -> Decision:
        """Chat clients resend the whole history every turn: only unseen messages are screened and logged."""
        k = (source, hash(text))
        hit = cache.get(k)
        if hit is not None:
            return hit
        d = sentinel.screen(text, source=source, via=via, log=log)
        cache.put(k, d)
        return d

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "version": __version__,
            "mode": sentinel.mode,
            "model": getattr(sentinel.classifier, "name", None),
            "thresholds": sentinel.thresholds.to_dict(),
            "proxy_upstream_configured": bool(base),
            "notice": RULES_ONLY_NOTICE if sentinel.classifier is None else None,
        }

    @app.post("/v1/screen")
    def screen(req: ScreenRequest) -> dict[str, Any]:
        return _public(sentinel.screen(req.text, source=req.source, via="screen", log=req.log))

    @app.post("/v1/screen/batch")
    def screen_batch(req: BatchRequest) -> dict[str, Any]:
        res = [_public(sentinel.screen(i.text, source=i.source, via="batch", log=req.log)) for i in req.items]
        return {"results": res, "mode": sentinel.mode}

    @app.post("/v1/screen/documents")
    def screen_documents(req: DocumentsRequest) -> dict[str, Any]:
        """Screen retrieved documents or tool outputs before they are placed in a model's context."""
        results, allowed = [], []
        for i, doc in enumerate(req.documents):
            d = sentinel.screen(doc.text, source=doc.source, via="document", log=req.log, extra={"doc_id": doc.id} if doc.id else None)
            r = _public(d)
            r["id"] = doc.id or str(i)
            results.append(r)
            if d.action != "block":
                allowed.append(r["id"])
        return {"results": results, "allowed_ids": allowed, "blocked_ids": [r["id"] for r in results if r["action"] == "block"], "mode": sentinel.mode}

    @app.get("/v1/audit")
    def get_audit(limit: int = Query(100, ge=1, le=1000), action: Literal["allow", "flag", "block"] | None = None, rule: str | None = None) -> dict[str, Any]:
        return {"entries": audit.read(limit, action, rule), "path": str(audit.path)}

    @app.get("/v1/rules")
    def rules() -> dict[str, Any]:
        return {"rules": rule_catalogue()}

    @app.get("/v1/metrics")
    def metrics() -> Any:
        p = eval_path or Path(os.environ.get("SENTINEL_EVAL_JSON", "docs/data/eval.json"))
        if not p.exists():
            raise HTTPException(404, "no evaluation recorded yet; run `sentinel eval`")
        return JSONResponse(json.loads(p.read_text(encoding="utf-8")))

    # ------------------------------------------------------------------ OpenAI-compatible proxy
    def refusal_body(model: str, d: Decision, worst: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": "chatcmpl-sentinel-" + uuid.uuid4().hex[:12],
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "This request was blocked by Sentinel: " + d.reason}, "finish_reason": "content_filter"}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "sentinel": {"action": "block", "reason": d.reason, "score": d.score, "rules": sorted({h.rule_id for h in d.hits}), "audit_id": worst.get("audit_id")},
        }

    def upstream_headers(request: Request) -> dict[str, str]:
        auth = request.headers.get("authorization")
        h = {"content-type": "application/json"}
        if auth:
            h["authorization"] = auth
        elif key:
            h["authorization"] = f"Bearer {key}"
        return h

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request) -> Any:
        try:
            body = await request.json()
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(400, "body must be JSON") from exc
        messages = body.get("messages")
        if not isinstance(messages, list) or not messages:
            raise HTTPException(400, "`messages` must be a non-empty list")
        worst: Decision | None = None
        worst_entry: dict[str, Any] = {}
        for m in messages:
            role = m.get("role") if isinstance(m, dict) else None
            if role not in ("user", "tool", "function"):
                continue  # system and assistant turns are the operator's own text
            text = _message_text(m.get("content"))
            if not text.strip():
                continue
            src = "user" if role == "user" else "tool"
            d = await run_in_threadpool(screen_cached, text, src, "proxy", True)
            if worst is None or ACTION_RANK[d.action] > ACTION_RANK[worst.action]:
                worst, worst_entry = d, {"audit_id": d.audit_id}
        headers = {"X-Sentinel-Decision": worst.action if worst else "allow", "X-Sentinel-Mode": sentinel.mode}
        if worst and worst.audit_id:
            headers["X-Sentinel-Audit-Id"] = worst.audit_id
        model = str(body.get("model", "unknown"))
        if worst and worst.action == "block":
            refusal = refusal_body(model, worst, worst_entry)
            if body.get("stream"):
                chunk = {"id": refusal["id"], "object": "chat.completion.chunk", "created": refusal["created"], "model": model, "choices": [{"index": 0, "delta": {"role": "assistant", "content": refusal["choices"][0]["message"]["content"]}, "finish_reason": "content_filter"}]}

                async def gen():
                    yield f"data: {json.dumps(chunk)}\n\n".encode()
                    yield b"data: [DONE]\n\n"

                return StreamingResponse(gen(), media_type="text/event-stream", headers=headers)
            return JSONResponse(refusal, headers=headers)
        if not base:
            return JSONResponse(
                {"error": {"message": "Sentinel screened this request (not blocked) but no upstream is configured. Set SENTINEL_UPSTREAM_BASE_URL to forward.", "type": "sentinel_no_upstream", "decision": worst.action if worst else "allow"}},
                status_code=503,
                headers=headers,
            )
        url = f"{base}/chat/completions"
        hdrs = upstream_headers(request)
        client = httpx.AsyncClient(transport=transport, timeout=httpx.Timeout(120.0, connect=10.0))
        try:
            if body.get("stream"):
                req = client.build_request("POST", url, headers=hdrs, json=body)
                resp = await client.send(req, stream=True)

                async def relay():
                    try:
                        if resp.is_stream_consumed:  # in-memory transports (tests) hand over a finished body
                            yield resp.content
                        else:
                            async for chunk in resp.aiter_raw():
                                yield chunk
                    finally:
                        await resp.aclose()
                        await client.aclose()

                return StreamingResponse(relay(), status_code=resp.status_code, media_type=resp.headers.get("content-type", "text/event-stream"), headers=headers)
            resp = await client.post(url, headers=hdrs, json=body)
            await client.aclose()
            ctype = resp.headers.get("content-type", "application/json")
            return JSONResponse(resp.json(), status_code=resp.status_code, headers=headers) if "json" in ctype else StreamingResponse(iter([resp.content]), status_code=resp.status_code, media_type=ctype, headers=headers)
        except httpx.HTTPError:
            await client.aclose()
            return JSONResponse({"error": {"message": "upstream request failed", "type": "sentinel_upstream_error"}}, status_code=502, headers=headers)

    @app.get("/v1/models")
    async def models(request: Request) -> Any:
        if not base:
            return JSONResponse({"object": "list", "data": [], "note": "no upstream configured"})
        async with httpx.AsyncClient(transport=transport, timeout=30.0) as client:
            try:
                r = await client.get(f"{base}/models", headers=upstream_headers(request))
                return JSONResponse(r.json(), status_code=r.status_code)
            except httpx.HTTPError:
                return JSONResponse({"error": {"message": "upstream request failed"}}, status_code=502)

    if serve_ui and WEB_DIR.exists():
        app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
    return app


def app_factory() -> FastAPI:
    """Entry point for `uvicorn sentinel.server.app:app_factory --factory`."""
    return create_app()
