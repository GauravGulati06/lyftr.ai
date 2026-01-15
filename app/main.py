import hashlib
import hmac
import json
import logging
import time
import uuid

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import ValidationError

from app.config import load_settings, sqlite_path_from_url
from app.logging_utils import configure_logging, log_json, now_iso
from app.metrics import Metrics
from app.models import MessagesResponse, MessageIn, StatsResponse, WebhookOk
from app.models import _validate_utc_z
from app.storage import check_db, compute_stats, ensure_schema, insert_message, list_messages


def _compute_sig(secret: str, raw_body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()


def create_app() -> FastAPI:
    settings = load_settings()
    logger = configure_logging(settings.log_level)
    metrics = Metrics()

    app = FastAPI()
    app.state.settings = settings
    app.state.logger = logger
    app.state.metrics = metrics
    app.state.db_path = sqlite_path_from_url(settings.database_url)
    app.state.schema_ok = False

    @app.on_event("startup")
    async def _startup() -> None:
        try:
            await ensure_schema(app.state.db_path)
            app.state.schema_ok = True
        except Exception:
            app.state.schema_ok = False

    @app.middleware("http")
    async def _request_middleware(request: Request, call_next):
        request_id = uuid.uuid4().hex
        request.state.request_id = request_id
        start = time.perf_counter()
        status = 500
        response = None

        try:
            response = await call_next(request)
            status = response.status_code
        except Exception as exc:
            status = 500
            request.state.log_level = logging.ERROR
            request.state.log_extra = {
                "result": "internal_error",
                "error": exc.__class__.__name__,
            }
            response = JSONResponse(status_code=500, content={"detail": "internal server error"})

        latency_ms = (time.perf_counter() - start) * 1000.0
        response.headers["X-Request-Id"] = request_id

        payload = {
            "ts": now_iso(),
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status": status,
            "latency_ms": round(latency_ms, 2),
        }

        extra = getattr(request.state, "log_extra", None)
        if isinstance(extra, dict):
            payload.update(extra)

        level = getattr(request.state, "log_level", logging.INFO)
        log_json(app.state.logger, level, payload)

        app.state.metrics.observe_http(request.url.path, status, latency_ms)
        return response

    @app.get("/health/live")
    async def health_live():
        return {"status": "live"}

    @app.get("/health/ready")
    async def health_ready():
        secret_ok = app.state.settings.webhook_secret is not None
        db_ok = app.state.schema_ok and await check_db(app.state.db_path)
        if secret_ok and db_ok:
            return {"status": "ready"}
        return JSONResponse(status_code=503, content={"status": "not_ready"})

    @app.post("/webhook", response_model=WebhookOk)
    async def webhook(request: Request, x_signature: str | None = Header(default=None, alias="X-Signature")):
        raw = await request.body()
        secret = app.state.settings.webhook_secret

        raw_for_json = raw[3:] if raw.startswith(b"\xef\xbb\xbf") else raw

        message_id_for_log = None
        try:
            parsed = json.loads(raw_for_json.decode("utf-8"))
            if isinstance(parsed, dict):
                mid = parsed.get("message_id")
                if isinstance(mid, str):
                    message_id_for_log = mid
        except Exception:
            pass

        if not secret:
            request.state.log_level = logging.ERROR
            request.state.log_extra = {
                "message_id": message_id_for_log,
                "dup": False,
                "result": "missing_secret",
            }
            raise HTTPException(status_code=503, detail="webhook secret not configured")

        expected = _compute_sig(secret, raw)
        if not x_signature or not hmac.compare_digest(expected, x_signature):
            app.state.metrics.inc_webhook("invalid_signature")
            request.state.log_level = logging.ERROR
            request.state.log_extra = {
                "message_id": message_id_for_log,
                "dup": False,
                "result": "invalid_signature",
            }
            return JSONResponse(status_code=401, content={"detail": "invalid signature"})

        try:
            msg = MessageIn.model_validate_json(raw_for_json)
        except ValidationError as e:
            app.state.metrics.inc_webhook("validation_error")
            request.state.log_level = logging.ERROR
            request.state.log_extra = {
                "message_id": message_id_for_log,
                "dup": False,
                "result": "validation_error",
            }
            return JSONResponse(status_code=422, content=jsonable_encoder({"detail": e.errors()}))

        created = await insert_message(app.state.db_path, msg)
        result = "created" if created else "duplicate"
        app.state.metrics.inc_webhook(result)

        request.state.log_extra = {
            "message_id": msg.message_id,
            "dup": not created,
            "result": result,
        }
        return {"status": "ok"}

    @app.get("/messages", response_model=MessagesResponse)
    async def get_messages(
        limit: int = Query(default=50, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
        from_msisdn: str | None = Query(default=None, alias="from"),
        since: str | None = Query(default=None),
        q: str | None = Query(default=None),
    ):
        if since is not None:
            try:
                _validate_utc_z(since)
            except Exception:
                raise HTTPException(status_code=422, detail=[{"loc": ["query", "since"], "msg": "invalid since", "type": "value_error"}])

        data, total = await list_messages(
            app.state.db_path,
            limit=limit,
            offset=offset,
            from_msisdn=from_msisdn,
            since=since,
            q=q,
        )
        return {"data": data, "total": total, "limit": limit, "offset": offset}

    @app.get("/stats", response_model=StatsResponse)
    async def stats():
        return await compute_stats(app.state.db_path)

    @app.get("/metrics")
    async def metrics_endpoint():
        return PlainTextResponse(content=app.state.metrics.render_prometheus(), media_type="text/plain")

    return app


app = create_app()
