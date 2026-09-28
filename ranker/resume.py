"""Turn an uploaded resume into plain text for Jev (which accepts text only)."""
from __future__ import annotations

import io

MAX_CHARS = 20_000  # about 5k tokens. The resume rides along on every Jev call, so keep it bounded.


class ResumeError(ValueError):
    pass


def resume_to_text(filename: str, data: bytes) -> str:
    name = filename.lower()
    if name.endswith(".pdf"):
        from pypdf import PdfReader

        try:
            reader = PdfReader(io.BytesIO(data))
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
        except Exception as e:  # corrupt or encrypted PDF
            raise ResumeError(f"Couldn't read that PDF ({e.__class__.__name__}).") from e
        if len(text.strip()) < 50:
            raise ResumeError(
                "That PDF has almost no selectable text, so it's probably a scanned image. "
                "Export it again as a text PDF, or paste the text instead."
            )
    else:
        text = data.decode("utf-8", errors="ignore")
    text = " ".join(text.split())  # collapse PDF line-break noise
    return text[:MAX_CHARS]
