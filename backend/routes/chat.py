from __future__ import annotations

import asyncio
import json
import queue
import threading

from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from .. import files, store
from ..files import extract_attachment
from ..schemas import ChatStreamRequest, RegenerateRequest, StopRequest

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/stream")
async def stream(req: ChatStreamRequest, request: Request):
    if not store.get_conversation(req.conversation_id):
        raise HTTPException(status_code=404, detail="conversation not found")
    # Decode + extract text from any attached files. We store the user's typed
    # text as `content` (what the bubble shows) and the extracted text inside the
    # attachment metadata; prompt_from_store folds it in front of the prompt so
    # the model sees the file contents without cluttering the chat bubble.
    # Images are stored to disk (downscaled) keyed by this message id, so the
    # vision model can read them by path and the UI can re-serve thumbnails.
    attachments = []
    for i, a in enumerate(req.attachments):
        meta = extract_attachment(a.model_dump())
        if meta.get("is_image"):
            try:
                meta["path"] = files.save_image(
                    a.data_b64, req.conversation_id, req.user_message_id, i
                )
            except Exception as e:  # noqa: BLE001 - fall back to a non-image note
                meta["is_image"] = False
                meta["text"] = f"[could not read image: {e}]"
        attachments.append(meta)
    # Persist the user turn + an empty assistant placeholder before generating.
    store.add_message(
        req.user_message_id,
        req.conversation_id,
        "user",
        req.content,
        status="done",
        attachments=attachments,
    )
    store.add_message(
        req.assistant_message_id, req.conversation_id, "assistant", "", status="streaming"
    )
    return _sse(request, req.conversation_id, req.assistant_message_id)


@router.post("/regenerate")
async def regenerate(req: RegenerateRequest, request: Request):
    if not store.get_conversation(req.conversation_id):
        raise HTTPException(status_code=404, detail="conversation not found")
    # Reset the existing assistant message; llm.prompt_from_store re-derives the
    # last user prompt and prior history, so this re-answers the last user turn.
    store.update_message(req.assistant_message_id, content="", status="streaming", error="")
    return _sse(request, req.conversation_id, req.assistant_message_id)


@router.post("/stop")
async def stop(req: StopRequest, request: Request):
    ev = request.app.state.stops.get(req.conversation_id)
    if ev:
        ev.set()
    try:
        request.app.state.engine.stop(req.conversation_id)
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True}


def _sse(request: Request, conv_id: str, assistant_id: str):
    app = request.app
    engine = app.state.engine
    q: "queue.Queue" = queue.Queue(maxsize=512)
    stop_event = threading.Event()
    app.state.stops[conv_id] = stop_event
    acc: list[str] = []
    state = {"stats": None, "error": None}

    def worker():
        try:
            for kind, data in engine.stream(conv_id, stop_event):
                q.put((kind, data))
        except Exception as e:  # noqa: BLE001
            q.put(("error", str(e)))
        finally:
            q.put(("__end__", None))

    threading.Thread(target=worker, daemon=True).start()

    async def gen():
        loop = asyncio.get_event_loop()
        try:
            while True:
                kind, data = await loop.run_in_executor(None, q.get)
                if kind == "token":
                    acc.append(data)
                    yield {"event": "token", "data": json.dumps({"text": data})}
                elif kind == "stats":
                    state["stats"] = data
                    yield {"event": "stats", "data": json.dumps(data)}
                elif kind == "error":
                    state["error"] = data
                    yield {"event": "error", "data": json.dumps({"message": data})}
                elif kind == "__end__":
                    break

            status = "error" if state["error"] else ("stopped" if stop_event.is_set() else "done")
            store.update_message(
                assistant_id,
                content="".join(acc),
                status=status,
                stats=state["stats"],
                error=state["error"],
            )
            store.touch_conversation(conv_id)
            yield {"event": "done", "data": json.dumps({"status": status})}
        except asyncio.CancelledError:
            # Client disconnected mid-stream — stop generation, persist partial.
            stop_event.set()
            try:
                engine.stop(conv_id)
            except Exception:  # noqa: BLE001
                pass
            store.update_message(
                assistant_id, content="".join(acc), status="stopped", stats=state["stats"]
            )
            store.touch_conversation(conv_id)
            raise
        finally:
            app.state.stops.pop(conv_id, None)

    return EventSourceResponse(
        gen(),
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )
