from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import store
from .config import Config
from .llm import NobodyWhoEngine
from .routes import attachments, chat, conversations, models


def create_app(cfg: Config) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store.init_db(cfg.db_path)
        app.state.cfg = cfg
        app.state.stops = {}
        app.state.engine = NobodyWhoEngine(cfg)
        # The model is NOT loaded here: loading is a native call that holds the
        # GIL for ~3s and would freeze the event loop, stalling the initial
        # conversation requests. Instead the desktop app calls POST /api/warmup
        # once it has loaded the conversation list (and again every few seconds
        # while nothing is loaded), so the load runs on a background thread after
        # the UI is up (see engine.start_warmup). A first message before warmup
        # finishes still works (it waits on the same lock).
        print("[app] engine ready (model warms via /api/warmup)")
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
            "model_loaded": eng.model_loaded(),
            "model_error": eng.model_error,
            # Download/switch progress, so the UI can show a % while a model
            # downloads or loads.
            "model_task": eng.task_status(),
            "file_uploads": eng.cfg.file_uploads,
        }

    @app.post("/api/warmup")
    def warmup():
        # Kick off the model load in the background (idempotent). The desktop app
        # calls this once the conversation list has loaded, so the GIL-holding
        # load never stalls the initial UI requests.
        eng = app.state.engine
        eng.start_warmup()
        return {
            "model_loaded": eng.model_loaded(),
            "model_error": eng.model_error,
        }

    @app.post("/api/shutdown")
    def shutdown():
        # Sent by the desktop app when its window closes. Stop any answer being
        # generated (it is saved as "stopped"), let uvicorn finish the in-flight
        # requests, then main() ends the process (see backend/main.py).
        for conv_id in list(app.state.stops):
            chat.stop_generation(app, conv_id)
        server = getattr(app.state, "server", None)
        if server is not None:
            server.should_exit = True
        return {"ok": True}

    return app
