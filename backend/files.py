from __future__ import annotations

import base64
import io

# Attachment text extraction. Incoming attachments arrive as
# {name, mime, data_b64} in the chat POST body; we decode them, pull out plain
# text (CSV verbatim, PDF via pypdf), and return lightweight stored metadata
# {name, mime, size, text}. The extracted `text` is what the model reads — it is
# folded in front of the user's typed message at prompt-build time (fold_content)
# and is NOT shown in the chat bubble (the UI shows a chip from name/mime/size).
#
# Nothing here raises: an undecodable / unsupported / empty file becomes a short
# bracketed note instead of failing the whole request.

MAX_FILE_BYTES = 15 * 1024 * 1024  # reject a single file larger than this
MAX_CHARS_PER_FILE = 8000          # cap extracted text per file (n_ctx budget)
TRUNC_MARKER = "\n\n[…truncated]"


def _b64_to_bytes(data_b64: str) -> bytes:
    # Tolerate a full data URL ("data:<mime>;base64,XXXX") or bare base64.
    s = data_b64 or ""
    if s.startswith("data:"):
        comma = s.find(",")
        if comma != -1:
            s = s[comma + 1 :]
    return base64.b64decode(s, validate=False)


def _is_csv(name: str, mime: str) -> bool:
    return mime in ("text/csv", "application/csv") or name.lower().endswith(".csv")


def _is_pdf(name: str, mime: str) -> bool:
    return mime == "application/pdf" or name.lower().endswith(".pdf")


def _is_xlsx(name: str, mime: str) -> bool:
    return (
        mime == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        or name.lower().endswith(".xlsx")
    )


def _is_xls(name: str, mime: str) -> bool:
    return mime == "application/vnd.ms-excel" or name.lower().endswith(".xls")


def _is_docx(name: str, mime: str) -> bool:
    return (
        mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        or name.lower().endswith(".docx")
    )


def _join_sheet(title: str, rows: list[str]) -> str:
    return f"# Sheet: {title}\n" + "\n".join(rows)


def _decode_text(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1", errors="replace")


def _extract_pdf(raw: bytes) -> str:
    try:
        from pypdf import PdfReader
    except Exception as e:  # noqa: BLE001
        return f"[could not read PDF: {e}]"
    try:
        reader = PdfReader(io.BytesIO(raw))
        parts = []
        for page in reader.pages:
            try:
                parts.append(page.extract_text() or "")
            except Exception:  # noqa: BLE001
                continue
        text = "\n".join(p for p in parts if p).strip()
        return text or "[no extractable text — the PDF may be scanned/image-only]"
    except Exception as e:  # noqa: BLE001
        return f"[could not read PDF: {e}]"


def _extract_xlsx(raw: bytes) -> str:
    try:
        import openpyxl
    except Exception as e:  # noqa: BLE001
        return f"[could not read Excel file: {e}]"
    try:
        wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    except Exception as e:  # noqa: BLE001
        return f"[could not read Excel file: {e}]"
    try:
        parts, total = [], 0
        for ws in wb.worksheets:
            rows = []
            for row in ws.iter_rows(values_only=True):
                cells = ["" if v is None else str(v) for v in row]
                if not any(c.strip() for c in cells):
                    continue
                line = ",".join(cells)
                rows.append(line)
                total += len(line) + 1
                if total > MAX_CHARS_PER_FILE:  # stop early on huge sheets
                    break
            if rows:
                parts.append(_join_sheet(ws.title, rows))
            if total > MAX_CHARS_PER_FILE:
                break
        text = "\n\n".join(parts).strip()
        return text or "[no data in spreadsheet]"
    finally:
        try:
            wb.close()
        except Exception:  # noqa: BLE001
            pass


def _extract_xls(raw: bytes) -> str:
    try:
        import xlrd
    except Exception as e:  # noqa: BLE001
        return f"[could not read Excel file: {e}]"
    try:
        book = xlrd.open_workbook(file_contents=raw)
    except Exception as e:  # noqa: BLE001
        return f"[could not read Excel file: {e}]"
    parts, total = [], 0
    for sheet in book.sheets():
        rows = []
        for r in range(sheet.nrows):
            cells = ["" if v is None else str(v) for v in sheet.row_values(r)]
            if not any(c.strip() for c in cells):
                continue
            line = ",".join(cells)
            rows.append(line)
            total += len(line) + 1
            if total > MAX_CHARS_PER_FILE:
                break
        if rows:
            parts.append(_join_sheet(sheet.name, rows))
        if total > MAX_CHARS_PER_FILE:
            break
    text = "\n\n".join(parts).strip()
    return text or "[no data in spreadsheet]"


def _extract_docx(raw: bytes) -> str:
    try:
        import docx
    except Exception as e:  # noqa: BLE001
        return f"[could not read Word file: {e}]"
    try:
        doc = docx.Document(io.BytesIO(raw))
    except Exception as e:  # noqa: BLE001
        return f"[could not read Word file: {e}]"
    parts = [p.text for p in doc.paragraphs if p.text and p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            if any(cells):
                parts.append(" | ".join(cells))
    text = "\n".join(parts).strip()
    return text or "[no extractable text]"


def _cap(text: str) -> str:
    if len(text) > MAX_CHARS_PER_FILE:
        return text[:MAX_CHARS_PER_FILE] + TRUNC_MARKER
    return text


def extract_attachment(att: dict) -> dict:
    """Decode + extract one incoming {name, mime, data_b64} attachment.

    Returns stored metadata {name, mime, size, text}. Never raises."""
    name = (att.get("name") or "file").strip()
    mime = (att.get("mime") or "").strip()
    try:
        raw = _b64_to_bytes(att.get("data_b64") or "")
    except Exception:  # noqa: BLE001
        return {"name": name, "mime": mime, "size": 0, "text": "[could not decode file]"}

    size = len(raw)
    if size == 0:
        text = "[empty file]"
    elif size > MAX_FILE_BYTES:
        text = f"[file too large to read: {size} bytes]"
    elif _is_csv(name, mime):
        text = _cap(_decode_text(raw).strip()) or "[empty file]"
    elif _is_pdf(name, mime):
        text = _cap(_extract_pdf(raw))
    elif _is_xlsx(name, mime):
        text = _cap(_extract_xlsx(raw))
    elif _is_xls(name, mime):
        text = _cap(_extract_xls(raw))
    elif _is_docx(name, mime):
        text = _cap(_extract_docx(raw))
    elif mime.startswith("text/"):
        text = _cap(_decode_text(raw).strip()) or "[empty file]"
    else:
        text = f"[unsupported file type: {mime or 'unknown'}]"

    return {"name": name, "mime": mime, "size": size, "text": text}


def fold_content(content: str, attachments: list[dict] | None) -> str:
    """Build the text the model sees: each attachment's extracted text as a
    labelled fenced block, then the user's typed message."""
    if not attachments:
        return content
    blocks = []
    for a in attachments:
        text = (a or {}).get("text") or ""
        if not text:
            continue
        name = (a or {}).get("name") or "file"
        blocks.append(f"[Attached file: {name}]\n```\n{text}\n```")
    if not blocks:
        return content
    prefix = "\n\n".join(blocks)
    return f"{prefix}\n\n{content}" if content else prefix
