from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from .. import store

# Serves stored image attachments so the UI can render thumbnails after a
# reload (the live optimistic message renders from a local object URL instead).
# Only files that a message's own attachment metadata points at are served, and
# only if flagged as an image — never an arbitrary path.

router = APIRouter(prefix="/api/attachments", tags=["attachments"])


@router.get("/{message_id}/{idx}")
def get_attachment(message_id: str, idx: int):
    msg = store.get_message(message_id)
    if not msg:
        raise HTTPException(status_code=404, detail="message not found")
    atts = msg.get("attachments") or []
    if idx < 0 or idx >= len(atts):
        raise HTTPException(status_code=404, detail="attachment not found")
    a = atts[idx] or {}
    path = a.get("path")
    if not (a.get("is_image") and path and os.path.isfile(path)):
        raise HTTPException(status_code=404, detail="no image for this attachment")
    # Images are re-encoded to JPEG on save (see files.save_image).
    return FileResponse(path, media_type="image/jpeg")
