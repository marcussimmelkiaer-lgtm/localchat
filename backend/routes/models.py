from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Request

from .. import models_catalog
from ..schemas import DeleteModelRequest, DownloadModelRequest, SwitchModelRequest

router = APIRouter(prefix="/api/models", tags=["models"])


@router.get("")
def list_models(request: Request):
    """Active model + curated catalog (with downloaded/active flags) + all cached
    GGUFs (including custom downloads not in the catalog)."""
    eng = request.app.state.engine
    active = eng.current_model()
    data = models_catalog.build_catalog(active.get("path"))
    return {"active": active, **data}


@router.get("/status")
def model_status(request: Request):
    """Current download/switch task state, polled by the UI while one runs."""
    return request.app.state.engine.task_status()


@router.post("/download")
def download_model(req: DownloadModelRequest, request: Request):
    # A download that then switches would swap the live model — block it while a
    # generation is in flight (see switch_model for why app.state.stops is used).
    if req.then_switch and request.app.state.stops:
        raise HTTPException(status_code=409, detail="Stop generation before switching models.")
    res = request.app.state.engine.start_download(req.spec, req.then_switch, req.extra_specs)
    if not res.get("ok"):
        raise HTTPException(status_code=409, detail=res.get("error", "Cannot start download."))
    return {"ok": True}


@router.post("/switch")
def switch_model(req: SwitchModelRequest, request: Request):
    # app.state.stops holds a stop-event per in-flight generation. It's registered
    # synchronously when a /chat/stream request starts (before the response
    # returns), so it has no startup race — unlike the engine's _active dict,
    # which is only populated once the worker thread reaches generation. Check it
    # here to reliably block a switch while any chat is generating.
    if request.app.state.stops:
        raise HTTPException(status_code=409, detail="Stop generation before switching models.")
    res = request.app.state.engine.start_switch(req.path)
    if not res.get("ok"):
        raise HTTPException(status_code=409, detail=res.get("error", "Cannot switch model."))
    return {"ok": True}


@router.delete("")
def delete_model(req: DeleteModelRequest, request: Request):
    """Remove a cached GGUF to reclaim disk.

    Guards (cross-platform, no hardcoded cache dir):
      - refuse while a download/switch task is running;
      - refuse the active model (compared via os.path.samefile);
      - only ever delete a path NobodyWho itself reports as a cached model."""
    eng = request.app.state.engine
    path = req.path
    if eng.task_status().get("status") in ("downloading", "loading"):
        raise HTTPException(status_code=409, detail="A model task is running.")

    active = eng.current_model().get("path")
    if active and os.path.isfile(active) and os.path.isfile(path):
        try:
            if os.path.samefile(active, path):
                raise HTTPException(status_code=409, detail="Cannot delete the active model.")
        except HTTPException:
            raise
        except OSError:
            pass

    if not models_catalog.is_cached_path(path):
        raise HTTPException(status_code=400, detail="Not a known cached model file.")

    try:
        os.remove(path)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Could not delete: {e}")

    active = eng.current_model()
    return {"ok": True, "active": active, **models_catalog.build_catalog(active.get("path"))}
