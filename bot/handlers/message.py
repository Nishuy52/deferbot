"""Top-level message router: registration → commands → application wizard."""
from bot import db, diagram
import bot.telegram as tg
from bot.handlers import application, approval, admin
from bot.config.platoons import format_platoon_menu, platoon_from_index, PLATOONS

def _send_diagram(chat_id: str | int, caption: str | None = None) -> None:
    """Send the state machine diagram image to chat_id.
    First call on a fresh instance uploads the PNG (delivering it in one shot) and
    caches the returned file_id. Subsequent calls reuse the file_id via send_file.
    Failures are logged but never bubble up — text messages still go through.
    """
    import sys
    try:
        if diagram.cached_file_id is None:
            png = diagram.generate_png()
            file_id = tg.send_photo_bytes(chat_id, png, caption=caption)
            diagram.cached_file_id = file_id
        else:
            tg.send_file(chat_id, diagram.cached_file_id, "image/png", caption=caption)
    except Exception as e:
        print(f"[WARN] Could not send diagram: {e}", file=sys.stderr)


PC_CMDS = {"/pending", "/approve", "/reject", "/revise", "/view",
           "/list_active", "/list_all", "/edit_decision"}
OC_CMDS = {"/list", "/setstatus", "/co_status", "/remind"}
ADMIN_CMDS = {"/setrole", "/setflag", "/removeflag", "/unregister",
              "/createuser", "/createusers", "/simulate", "/simulatemode",
              "/skipdocs"}
# User commands handled directly by the application handler
USER_CMDS = {"/start", "/apply", "/status", "/withdraw", "/help",
             "/edit_docs", "/edit_ippt", "/applied", "/co_approved",
             "/co_rejected", "/resubmit", "/confirm"}


def _run_simulated(admin_id: str, target_id: str, text: str, media: dict | None,
                   reply_media: dict | None = None) -> None:
    """Execute a message as target_id but redirect all bot responses to admin_id."""
    original_send = tg.send

    def redirected_send(chat_id, msg):
        target_user = db.get_user(target_id)
        target_name = target_user["name"] if target_user else target_id
        recipient = db.get_user(str(chat_id))
        recipient_name = recipient["name"] if recipient else str(chat_id)
        prefix = f"\\[→ {tg.esc(recipient_name)}\\] " if str(chat_id) != target_id else ""
        original_send(admin_id, f"{prefix}{msg}")

    _orig_notify = tg.notify
    _orig_notify_many = tg.notify_many

    def redirected_notify_many(users, msg):
        for u in users:
            redirected_send(u["id"], msg)

    _orig_send_file = tg.send_file

    def redirected_send_file(chat_id, file_id, mimetype, caption=None):
        _orig_send_file(admin_id, file_id, mimetype, caption=caption)

    _orig_send_photo_bytes = tg.send_photo_bytes

    def redirected_send_photo_bytes(chat_id, png_bytes, caption=None):
        return _orig_send_photo_bytes(admin_id, png_bytes, caption=caption)

    # Patch the module-level attribute AND direct imports in sub-handlers
    tg.send = redirected_send
    tg.notify = redirected_send
    tg.notify_many = redirected_notify_many
    tg.send_file = redirected_send_file
    tg.send_photo_bytes = redirected_send_photo_bytes
    application.send = redirected_send
    application.notify = redirected_send
    application.notify_many = redirected_notify_many
    approval.send = redirected_send
    approval.notify = redirected_send
    approval.notify_many = redirected_notify_many
    approval.send_file = redirected_send_file
    try:
        _handle(target_id, text, media, reply_media)
    finally:
        tg.send = original_send
        tg.notify = _orig_notify
        tg.notify_many = _orig_notify_many
        tg.send_file = _orig_send_file
        tg.send_photo_bytes = _orig_send_photo_bytes
        application.send = original_send
        application.notify = _orig_notify
        application.notify_many = _orig_notify_many
        approval.send = original_send
        approval.notify = _orig_notify
        approval.notify_many = _orig_notify_many
        approval.send_file = _orig_send_file


def on_update(body: dict) -> None:
    from bot.telegram import parse_updates
    for msg in parse_updates(body):
        _handle(msg["chat_id"], msg["text"], msg["media"], msg.get("reply_media"))


def _handle(chat_id: str, text: str, media: dict | None, reply_media: dict | None = None) -> None:
    # Check if admin is in simulatemode — reroute their messages
    sim = admin.get_simulate_mode(chat_id)
    if sim:
        cmd = text.strip().lower().split()[0] if text.strip() else ""
        if cmd == "/simulatemode":
            # Allow exiting simulatemode normally
            user = db.get_user(chat_id)
            raw_args = text[len(cmd):].strip()
            admin.handle(chat_id, user, cmd, text.split()[1:], raw_args=raw_args)
            return
        # Redirect this message as the simulated user
        target_id = sim["target"]
        admin_id = sim["admin"]
        _run_simulated(admin_id, target_id, text, media, reply_media)
        return

    user = db.get_user(chat_id)

    # ── New user: wait for explicit start before registering ──────────────
    if not user:
        if text.strip().lower() not in ("start", "/start"):
            tg.send(chat_id,
                 "👋 *Welcome to the NS Deferment Bot\\!*\n\n"
                 "Type *start* to register and begin submitting deferment applications\\.")
            return
        db.create_pending_user(chat_id)
        _send_diagram(chat_id, "How the deferment process works")
        tg.send(chat_id,
             "👋 *Welcome to the NS Deferment Bot\\!*\n\n"
             "Let's get you registered\\.\n"
             "What is your *rank and full name*?\n"
             "_Example: 3SG Tan Wei Ming_")
        return

    # ── Mid-registration ──────────────────────────────────────────────────
    if user.get("reg_step") == "name":
        if len(text.strip()) < 2:
            tg.send(chat_id, "Please enter your rank and full name\\.\n_Example: CPL Tan Wei Ming_")
            return
        db.update_user(chat_id, name=text.strip(), reg_step="platoon")
        tg.send(chat_id,
             "⚠️ *Important:* Selecting the wrong platoon means your application will go to the wrong PC and you will *not* be able to submit deferments\\.\n\n"
             "What is your platoon? *Reply with just a number*\n\n"
             f"{format_platoon_menu()}\n\n"
             "*Reply with a number (e.g. 1)*\\.")
        return

    if user.get("reg_step") == "platoon":
        n = int(text.strip()) if text.strip().isdigit() else 0
        platoon = platoon_from_index(n)
        if not platoon:
            tg.send(chat_id,
                 f"Please reply with a number 1–{len(PLATOONS)}\\.\n\n"
                 f"{format_platoon_menu()}")
            return
        db.update_user(chat_id, platoon=platoon, reg_step=None)
        user = db.get_user(chat_id)  # refresh
        tg.send(chat_id,
             f"✅ Registered as *{user['name']}* \\({user['platoon']}\\)\\.\n\n"
             f"Your chat ID is `{chat_id}`\n"
             f"If you are a PC, please forward this chat ID to your OC so they can assign you the PC role\\.\n\n"
             + application.get_menu("user"))
        return

    # ── Check if user is in a review context (PC/OC mid-review step) ─────
    review_step = user.get("review_step")
    if review_step:
        # Route all input to the approval handler while in review context
        approval.handle(chat_id, user, text, [])
        return

    # ── Command routing ───────────────────────────────────────────────────
    parts = text.split()
    cmd = parts[0].lower() if parts else ""
    args = parts[1:]
    role = user.get("role", "user")

    # Role-aware help
    if cmd == "/help":
        _send_diagram(chat_id, "Application state machine")
        tg.send(chat_id, application.get_help(role))
        return

    if cmd in ADMIN_CMDS:
        if role != "admin":
            tg.send(chat_id, "❌ Admin access required\\.")
            return
        # Pass raw text after the command for pipe-separated commands
        raw_args = text[len(cmd):].strip()
        admin.handle(chat_id, user, cmd, args, raw_args=raw_args)
        return

    if cmd in OC_CMDS:
        if role not in ("oc", "admin"):
            tg.send(chat_id, "❌ OC access required\\.")
            return
        approval.handle(chat_id, user, cmd, args)
        return

    if cmd in PC_CMDS:
        if role not in ("pc", "oc", "admin"):
            tg.send(chat_id, "❌ PC access required\\.")
            return
        approval.handle(chat_id, user, cmd, args)
        return

    # ── Application wizard / user commands ────────────────────────────────
    application.handle(chat_id, user, text, media, reply_media)
