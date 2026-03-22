"""Supabase Storage for deferment documents, downloaded from Telegram."""
import os
import requests
from bot.db import _client

BUCKET = "documents"
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
_TG = lambda: f"https://api.telegram.org/bot{os.environ['TELEGRAM_TOKEN']}"


class FileTooLargeError(Exception):
    """Raised when a downloaded file exceeds MAX_FILE_SIZE."""
    def __init__(self, size: int):
        self.size = size
        super().__init__(f"File size {size} exceeds {MAX_FILE_SIZE} byte limit")


def save_media(application_id: int, doc_type: str, file_id: str, mimetype: str) -> str:
    """Download file from Telegram and upload to Supabase Storage. Returns storage path."""
    # Get Telegram download URL
    resp = requests.get(f"{_TG()}/getFile", params={"file_id": file_id}, timeout=10)
    resp.raise_for_status()
    tg_path = resp.json()["result"]["file_path"]

    # Download the file
    token = os.environ["TELEGRAM_TOKEN"]
    dl = requests.get(f"https://api.telegram.org/file/bot{token}/{tg_path}", timeout=30)
    dl.raise_for_status()

    if len(dl.content) > MAX_FILE_SIZE:
        raise FileTooLargeError(len(dl.content))

    # Upload to Supabase Storage
    ext = _ext(mimetype)
    path = f"{application_id}/{doc_type}_{file_id[:8]}.{ext}"
    _client().storage.from_(BUCKET).upload(
        path=path,
        file=dl.content,
        file_options={"content-type": mimetype, "upsert": "true"},
    )
    return path


def _ext(mimetype: str) -> str:
    return {"image/jpeg": "jpg", "image/png": "png",
            "image/webp": "webp", "application/pdf": "pdf"}.get(mimetype, "bin")
