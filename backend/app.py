from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import store
from .config import STATIC_DIR, Config
from .llm import build_engine
from .routes import attachments, chat, conversations, models


def create_app(cfg: Config) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store.init_db(cfg.db_path)
        app.state.cfg = cfg
        app.state.stops = {}
        app.state.engine = build_engine(cfg)
        # The model is NOT loaded here: loading is a native call that holds the
        # GIL for ~3s and would freeze the event loop, stalling the initial
        # conversation/SPA requests. Instead the frontend calls POST /api/warmup
        # once it has rendered the conversation list, so the load runs on a
        # background thread after the UI is up (see engine.start_warmup). A first
        # message before warmup finishes still works (it waits on the same lock).
        print(f"[app] engine ready: {app.state.engine.backend} (model warms via /api/warmup)")
        yield

    app = FastAPI(title="LocalChat", lifespan=lifespan)
    app.include_router(conversations.router)
    app.include_router(chat.router)
    app.include_router(models.router)
    app.include_router(attachments.router)

    @app.get("/healthz")
    def healthz():
        eng = app.state.engine
        return {
            "status": "ok",
            "backend": eng.backend,
            "model_loaded": eng.model_loaded(),
            "model_error": getattr(eng, "model_error", None),
            # Download/switch progress, so a first-run model download started by
            # the backend itself (packaged builds) can show a % in the UI.
            "model_task": eng.task_status(),
        }

    @app.post("/api/warmup")
    def warmup():
        # Kick off the model load in the background (idempotent). The frontend
        # calls this once the conversation list has rendered, so the GIL-holding
        # load never stalls the initial UI requests. Returns immediately.
        eng = app.state.engine
        eng.start_warmup()
        return {
            "model_loaded": eng.model_loaded(),
            "model_error": getattr(eng, "model_error", None),
        }

    # Serve the built SPA from the same origin (no CORS). Registered last so the
    # API routes above take precedence.
    if STATIC_DIR.exists():
        app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
    else:
        @app.get("/")
        def no_build():
            return JSONResponse(
                {"detail": "Frontend not built. Run `npm run build` in frontend/."},
                status_code=503,
            )

    return app
