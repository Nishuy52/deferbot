"""Telegram Bot API client."""
import os
import re
import requests

_BASE = lambda: f"https://api.telegram.org/bot{os.environ['TELEGRAM_TOKEN']}"

# MarkdownV2 special characters that must be escaped in user-provided text
_MDV2_RE = re.compile(r'([_*\[\]()~`>#+\-=|{}.!\\])')


def esc(text: str) -> str:
    """Escape user-provided text for MarkdownV2 safe interpolation."""
    return _MDV2_RE.sub(r'\\\1', str(text))


def send(chat_id: str | int, text: str) -> None:
    import sys
    resp = requests.post(
        f"{_BASE()}/sendMessage",
        json={"chat_id": chat_id, "text": text, "parse_mode": "MarkdownV2"},
        timeout=10,
    )
    if resp.status_code == 400:
        body = resp.json() if resp.text else {}
        desc = body.get("description", "")
        # Undeliverable (chat not found, bot blocked, etc.) — log and move on
        if "chat not found" in desc or "bot was blocked" in desc:
            print(f"[WARN] Message undeliverable to {chat_id}: {desc}", file=sys.stderr)
            return
        # MarkdownV2 formatting error — retry as plain text so the user
        # still gets a response instead of silence.
        print(f"[WARN] MarkdownV2 rejected (400), falling back to plain text: {resp.text}", file=sys.stderr)
        fallback = requests.post(
            f"{_BASE()}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=10,
        )
        if fallback.status_code == 400:
            fb_desc = fallback.json().get("description", "") if fallback.text else ""
            if "chat not found" in fb_desc or "bot was blocked" in fb_desc:
                print(f"[WARN] Message undeliverable to {chat_id}: {fb_desc}", file=sys.stderr)
                return
        fallback.raise_for_status()
    else:
        resp.raise_for_status()


def send_file(chat_id: str | int, file_id: str, mimetype: str,
              caption: str | None = None) -> None:
    """Re-send a file by Telegram file_id."""
    import sys
    method = "sendPhoto" if mimetype.startswith("image/") else "sendDocument"
    data: dict = {"chat_id": chat_id}
    if mimetype.startswith("image/"):
        data["photo"] = file_id
    else:
        data["document"] = file_id
    if caption:
        data["caption"] = caption
    resp = requests.post(f"{_BASE()}/{method}", json=data, timeout=10)
    if resp.status_code == 400:
        body = resp.json() if resp.text else {}
        desc = body.get("description", "")
        if "chat not found" in desc or "bot was blocked" in desc:
            print(f"[WARN] File undeliverable to {chat_id}: {desc}", file=sys.stderr)
            return
    resp.raise_for_status()


def send_photo_bytes(chat_id: str | int, png_bytes: bytes,
                     caption: str | None = None) -> str:
    """Upload raw PNG bytes via sendPhoto (multipart). Returns Telegram file_id.
    Caption is plain text — no MarkdownV2 parse_mode applied.
    """
    import sys
    data: dict = {"chat_id": str(chat_id)}
    if caption:
        data["caption"] = caption
    resp = requests.post(
        f"{_BASE()}/sendPhoto",
        data=data,
        files={"photo": ("diagram.png", png_bytes, "image/png")},
        timeout=15,
    )
    if resp.status_code == 400:
        body = resp.json() if resp.text else {}
        desc = body.get("description", "")
        if "chat not found" in desc or "bot was blocked" in desc:
            print(f"[WARN] Photo undeliverable to {chat_id}: {desc}", file=sys.stderr)
            return ""
    resp.raise_for_status()
    photos = resp.json()["result"].get("photo", [])
    return photos[-1]["file_id"] if photos else ""


def notify(chat_id: str | int, text: str) -> None:
    send(chat_id, text)


def notify_many(users: list[dict], text: str) -> None:
    for u in users:
        send(u["id"], text)


def parse_updates(body: dict) -> list[dict]:
    """Normalise a Telegram webhook payload into a list of message dicts."""
    msg = body.get("message") or body.get("edited_message")
    if not msg:
        return []

    chat_id = str(msg["chat"]["id"])
    text = msg.get("text") or msg.get("caption") or ""
    media = None

    if "photo" in msg:
        photo = msg["photo"][-1]  # highest resolution
        media = {"file_id": photo["file_id"], "mimetype": "image/jpeg",
                 "file_size": photo.get("file_size")}
    elif "document" in msg:
        doc = msg["document"]
        media = {"file_id": doc["file_id"], "mimetype": doc.get("mime_type", "application/pdf"),
                 "file_size": doc.get("file_size")}

    return [{"chat_id": chat_id, "text": text.strip(), "media": media}]
