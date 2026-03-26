"""Application wizard state machine with IPPT gating, doc tagging, edits, and OneNS/CO flow."""
from bot import db, storage
from bot.storage import MAX_FILE_SIZE, FileTooLargeError
from bot.config.docs import (
    TYPE_KEYS, get_type_label, get_required_docs,
    get_missing_docs, format_type_menu, type_key_from_index,
    get_doc_label, doc_key_from_index,
)
from bot.telegram import send, notify, notify_many, esc


def get_menu(role: str, chat_id: str | None = None) -> str:
    """Return the role-appropriate main menu."""
    header = "*NS Deferment Bot*\n\n"

    if role in ("pc", "oc", "admin"):
        if role == "pc" and chat_id:
            u = db.get_user(chat_id)
            platoon = u.get("platoon") if u else None
            pending = db.get_pending_for_pc(platoon) if platoon else []
        else:
            pending = db.get_pending_for_oc()
        count = len(pending) if pending else 0
        noun = "application" if count == 1 else "applications"
        pending_line = f"📋 *{count} {noun} pending your approval\\.*\n\n"

        if role == "pc":
            return (
                header + pending_line +
                "/pending — Review pending applications\n"
                "/list\\_active — View active applications\n"
                "/apply — Apply for deferment\n"
                "/status — Check my status\n"
                "/help — Help"
            )
        else:  # oc or admin
            help_label = "/help — Help & admin commands" if role == "admin" else "/help — Help"
            return (
                header + pending_line +
                "/pending — Review pending applications\n"
                "/list\\_active — View all active applications\n"
                "/list — View all applications\n"
                "/co\\_status — Update CO decisions\n"
                "/apply — Apply for deferment\n"
                "/status — Check my status\n" +
                help_label
            )

    # Default: regular user
    return (
        header +
        "/apply — Apply for deferment\n"
        "/status — Check my status\n"
        "/help — Help"
    )

HELP_USER = (
    "*Commands:*\n"
    "/apply — Start a deferment application\n"
    "/status — Check your current application\n"
    "/withdraw — Cancel your active application\n"
    "/edit\\_docs — Edit your uploaded documents\n"
    "/edit\\_ippt — Update your IPPT status\n"
    "/applied — Confirm you've applied on OneNS\n"
    "/co\\_approved — Report CO approved\n"
    "/co\\_rejected — Report CO rejected\n"
    "/resubmit — Resubmit after revision/CO rejection\n"
    "/help — This message"
)

HELP_PC = (
    "*PC Commands:*\n"
    "/pending — Applications awaiting your approval\n"
    "/list\\_active — Active applications from your platoon\n"
    "/list\\_all — All applications from your platoon\n"
    "/view <id\\> — View an application \\(enters review context\\)\n"
    "/approve — Approve \\(after /view\\)\n"
    "/reject — Reject \\(after /view\\)\n"
    "/revise — Send back for revision \\(after /view\\)\n"
    "/edit\\_decision — Edit your past decision"
)

HELP_OC = (
    "*OC Commands:*\n"
    "/pending — HQ pending \\+ all pending OC\n"
    "/list\\_active — All active applications by platoon\n"
    "/list\\_all — All applications by platoon\n"
    "/list \\[status\\] — All applications \\(optional filter\\)\n"
    "/view <id\\> — View an application\n"
    "/approve — Approve \\(after /view\\)\n"
    "/reject — Reject \\(after /view\\)\n"
    "/revise — Send back for revision \\(after /view\\)\n"
    "/edit\\_decision — Edit your past decision\n"
    "/co\\_status <id\\> approved\\|rejected — Update CO decision\n"
    "/setstatus <id\\> approved\\|rejected — Manually set outcome"
)

HELP_ADMIN = (
    "*Admin Commands:*\n"
    "/setrole <chat\\_id\\> <role\\> — Set user role\n"
    "/setflag <chat\\_id\\> <flag\\> — Set user flag\n"
    "/removeflag <chat\\_id\\> <flag\\> — Remove user flag\n"
    "/unregister <chat\\_id\\> — Delete a user\n"
    "/createuser <id\\> \\| <name\\> \\| <platoon\\> \\[\\| <role\\>\\] — Create a user\n"
    "/createusers <count\\> \\| <platoon\\> \\[\\| <role\\>\\] — Bulk create test users\n"
    "/simulate <id\\> \\| <msg\\> — Send a message as another user\n"
    "/simulatemode <id\\> — Enter persistent simulate mode \\(off to exit\\)\n"
    "/skipdocs <id\\> — Auto\\-fill documents with dummy data"
)


def get_help(role: str) -> str:
    """Return help text appropriate for the user's role."""
    sections = [HELP_USER]
    if role in ("pc", "oc", "admin"):
        sections.append(HELP_PC)
    if role in ("oc", "admin"):
        sections.append(HELP_OC)
    if role == "admin":
        sections.append(HELP_ADMIN)
    return "\n\n".join(sections)

# Statuses where the user can still edit docs/IPPT
_EDITABLE = {"draft", "pending_ippt", "pending_pc"}
# Statuses where user has an active (non-terminal) application
_USER_ACTIVE_CMDS = {"/withdraw", "/status", "/edit_docs", "/edit_ippt",
                     "/applied", "/co_approved", "/co_rejected", "/resubmit"}


def handle(chat_id: str, user: dict, text: str, media: dict | None,
           reply_media: dict | None = None) -> None:
    app = db.get_active_application(chat_id)
    if not app:
        _no_app(chat_id, user, text)
        return
    _wizard(chat_id, user, app, text, media, reply_media)


def _no_app(chat_id: str, user: dict, text: str) -> None:
    role = user.get("role", "user") if user else "user"
    t = text.lower()
    if t in ("", "hi", "hello", "/start", "start"):
        send(chat_id, get_menu(role, chat_id))
    elif t == "/apply":
        db.create_application(chat_id)
        send(chat_id, f"*Start a deferment application*\n\nSelect your deferment type:\n\n{format_type_menu(esc)}\n\nReply with a number\\.")
    elif t == "/status":
        past = db.get_past_applications(chat_id)
        msg = "You have no active application\\."
        if past:
            msg += "\n\n" + _fmt_past_apps(past)
        send(chat_id, msg)
    elif t == "/help":
        send(chat_id, HELP_USER)
    else:
        send(chat_id, get_menu(role, chat_id))


def _wizard(chat_id: str, user: dict, app: dict, text: str, media: dict | None,
            reply_media: dict | None = None) -> None:
    t = text.lower().strip()

    # Global commands available during any step
    if t == "/withdraw":
        db.update_application(app["id"], status="rejected")
        db.log_action(app["id"], chat_id, "withdrawn")

        # Notify PCs and OCs
        approvers, _ = db.get_approvers_for_applicant(user)
        ocs = db.get_users_by_role("oc")
        all_notified = {u["id"]: u for u in approvers + ocs}
        notify_many(
            list(all_notified.values()),
            f"ℹ️ *Application \\#{app['id']} withdrawn*\n"
            f"{esc(user['name'])} \\({esc(user.get('platoon') or '?')}\\)"
        )
        send(chat_id, "Your application has been withdrawn\\.\nUse /apply to start a new application\\.")
        return

    if t == "/status":
        past = db.get_past_applications(chat_id)
        send(chat_id, _fmt_status(app, past))
        return

    if t == "/help":
        send(chat_id, HELP_USER)
        return

    # Post-submit edit commands
    if t == "/edit_docs":
        _handle_edit_docs(chat_id, app)
        return
    if t == "/edit_ippt":
        _handle_edit_ippt_start(chat_id, app)
        return

    # OneNS / CO commands (post-OC approval)
    if t == "/applied":
        _handle_applied(chat_id, user, app)
        return
    if t in ("/co_approved", "/co_rejected"):
        _handle_co_status(chat_id, user, app, t)
        return
    if t == "/resubmit":
        _handle_resubmit(chat_id, user, app)
        return

    # Wizard steps
    step = app["current_step"]
    if step == "type_select":
        _step_type(chat_id, app, text)
    elif step == "other_detail":
        _step_other_detail(chat_id, app, text)
    elif step == "ippt_check":
        _step_ippt(chat_id, app, text)
    elif step == "doc_collect":
        _step_docs(chat_id, app, text, media, reply_media)
    elif step == "confirm":
        _step_confirm(chat_id, user, app, text)
    elif step == "edit_ippt":
        _step_edit_ippt(chat_id, user, app, text)
    elif step == "edit_docs":
        _step_edit_docs(chat_id, app, text, media, reply_media)
    elif step == "co_rejection_reason":
        _step_co_rejection_reason(chat_id, user, app, text)
    elif step == "submitted":
        _handle_submitted_msg(chat_id, app)
    else:
        send(chat_id, "Unexpected state\\. Use /withdraw to cancel and start over\\.")


# ── Wizard Steps ──────────────────────────────────────────────────────────

def _step_type(chat_id: str, app: dict, text: str) -> None:
    n = int(text) if text.isdigit() else 0
    key = type_key_from_index(n)
    if not key:
        send(chat_id, f"Please reply with a number 1–{len(TYPE_KEYS)}\\.\n\n{format_type_menu(esc)}")
        return
    if key == "other":
        db.update_application(app["id"], type="other", current_step="other_detail")
        send(chat_id, "Please briefly describe your reason for deferment:")
        return
    db.update_application(app["id"], type=key, current_step="ippt_check")
    send(chat_id, f"Selected: *{esc(get_type_label(key))}*\n\nHave you passed your IPPT/completed your mandatory NSFit?\nReply *yes* or *no*\\.You can still proceed if not yet complete\\. Your PC will only be notified after you update your IPPT status\\.")


def _step_other_detail(chat_id: str, app: dict, text: str) -> None:
    if len(text) < 3:
        send(chat_id, "Please provide a brief description\\.")
        return
    db.update_application(app["id"], type_detail=text, current_step="ippt_check")
    send(chat_id, "Have you passed your IPPT/completed your mandatory NSFit?\nReply *yes* or *no*\\. You can still proceed if not yet complete\\. Your PC will only be notified after you update your IPPT status\\.")


def _step_ippt(chat_id: str, app: dict, text: str) -> None:
    t = text.lower()
    if t not in ("yes", "no", "y", "n"):
        send(chat_id, "Please reply *yes* or *no*\\. You can still proceed\\. Your PC will only be notified after you update your IPPT status\\.")
        return
    done = t.startswith("y")
    db.update_application(app["id"], ippt_done=done, current_step="doc_collect")

    docs = get_required_docs(app["type"])
    checklist = _format_checklist(docs, {}, app["type"])
    if not done:
        warning = (
            "⚠️ *Note: IPPT not completed\\.*\n"
            "You can still proceed\\. Your PC will only be notified after you update your IPPT status\\.\n"
            "Use /edit\\_ippt to update later\\.\n\n"
        )
    else:
        warning = ""
    send(chat_id,
         f"{warning}*Documents required for {esc(get_type_label(app['type']))}:*\n\n"
         f"{checklist}\n\n"
         f"Send each file as a photo or document with just the number as the caption\\.\n\n"
         f"Example: To upload document 1, attach the file and type *1* in the caption field\\.\n\n"
         f"Or send the file first, then reply to it with the number\\.\n"
         f"You can send multiple files per category\\.")


def _save_tagged_file(chat_id: str, app: dict, media_dict: dict, doc: dict) -> bool:
    """Validate, save, and log a tagged document. Returns True on success."""
    if media_dict.get("file_size") and media_dict["file_size"] > MAX_FILE_SIZE:
        send(chat_id, "⚠️ File too large\\. Maximum size is 10 MB\\. Please compress and resend\\.")
        return False
    try:
        path = storage.save_media(app["id"], doc["key"], media_dict["file_id"], media_dict["mimetype"])
    except FileTooLargeError:
        send(chat_id, "⚠️ File too large\\. Maximum size is 10 MB\\. Please compress and resend\\.")
        return False
    db.add_document(app["id"], doc["key"], path,
                    file_id=media_dict["file_id"], mimetype=media_dict["mimetype"])
    db.log_action(app["id"], chat_id, "doc_uploaded", doc["key"])
    return True


def _step_docs(chat_id: str, app: dict, text: str, media: dict | None,
               reply_media: dict | None = None) -> None:
    required = get_required_docs(app["type"])
    uploaded_types = db.get_uploaded_doc_types(app["id"])
    counts = db.get_doc_counts(app["id"])

    # Reply-based tagging: user replies to a file message with a category number
    if not media and reply_media and text.strip().isdigit():
        doc = doc_key_from_index(app["type"], int(text.strip()))
        if not doc:
            send(chat_id, f"Invalid number\\. Please use 1–{len(required)}\\.")
            return
        if not _save_tagged_file(chat_id, app, reply_media, doc):
            return
        counts = db.get_doc_counts(app["id"])
        uploaded_types = db.get_uploaded_doc_types(app["id"])
        remaining = get_missing_docs(app["type"], uploaded_types)
        checklist = _format_checklist(required, counts, app["type"])
        if not remaining:
            send(chat_id,
                 f"✅ Received: *{esc(doc['label'])}*\n\n{checklist}\n\n"
                 f"All categories have at least one file\\.\n"
                 f"Send more files or type /done to review and submit\\.")
        else:
            send(chat_id, f"✅ Received: *{esc(doc['label'])}*\n\n{checklist}\n\nSend the next document with its number as the caption, or reply to it with the number\\.")
        return

    if not media:
        # Text-only message during doc collection
        t = text.lower().strip()
        missing = get_missing_docs(app["type"], uploaded_types)

        if t == "/done" and not missing:
            # All categories filled — move to confirm
            db.update_application(app["id"], current_step="confirm")
            summary = _build_summary(app)
            send(chat_id,
                 f"{summary}\n\n"
                 f"/confirm — submit application\n"
                 f"/edit\\_docs — change documents\n"
                 f"/edit\\_ippt — update IPPT status\n"
                 f"/withdraw — cancel")
            return

        if t == "/done" and missing:
            labels = ", ".join(esc(d["label"]) for d in missing)
            send(chat_id, f"⚠️ Still missing: {labels}\n\nSend each file with its number as the caption, or reply to it with the number\\.")
            return

        checklist = _format_checklist(required, counts, app["type"])
        if not missing:
            send(chat_id,
                 f"*Document checklist:*\n\n{checklist}\n\n"
                 f"Send more files or type /done to review and submit\\.")
        else:
            send(chat_id,
                 f"*Document checklist:*\n\n{checklist}\n\n"
                 f"Send each file with just the number as the caption \\(e\\.g\\. *1*\\)\\.\n"
                 f"Or send the file first, then reply to it with the number\\.")
        return

    # Media received — determine category from caption
    caption = text.strip()
    if not caption or not caption.isdigit():
        checklist = _format_checklist(required, counts, app["type"])
        send(chat_id,
             f"Please add just the document number as the caption \\(e\\.g\\. *1*\\)\\.\n"
             f"Or send the file first, then reply to it with the number\\.\n\n{checklist}")
        return

    doc = doc_key_from_index(app["type"], int(caption))
    if not doc:
        send(chat_id, f"Invalid number\\. Please use 1–{len(required)}\\.")
        return

    if not _save_tagged_file(chat_id, app, media, doc):
        return

    # Refresh counts
    counts = db.get_doc_counts(app["id"])
    uploaded_types = db.get_uploaded_doc_types(app["id"])
    remaining = get_missing_docs(app["type"], uploaded_types)
    checklist = _format_checklist(required, counts, app["type"])

    if not remaining:
        send(chat_id,
             f"✅ Received: *{esc(doc['label'])}*\n\n{checklist}\n\n"
             f"All categories have at least one file\\.\n"
             f"Send more files or type /done to review and submit\\.")
    else:
        send(chat_id, f"✅ Received: *{esc(doc['label'])}*\n\n{checklist}\n\nSend the next document with its number as the caption, or reply to it with the number\\.")


def _step_confirm(chat_id: str, user: dict, app: dict, text: str) -> None:
    t = text.lower().strip()
    if t != "/confirm":
        summary = _build_summary(app)
        send(chat_id,
             f"{summary}\n\n"
             f"/confirm — submit application\n"
             f"/edit\\_docs — change documents\n"
             f"/edit\\_ippt — update IPPT status\n"
             f"/withdraw — cancel")
        return

    # Check document completeness before submission
    uploaded_types = db.get_uploaded_doc_types(app["id"])
    missing = get_missing_docs(app["type"], uploaded_types)
    if missing:
        labels = ", ".join(esc(d["label"]) for d in missing)
        send(chat_id, f"⚠️ Missing documents: {labels}\n\nPlease upload all required documents before submitting\\.")
        return

    # Refresh app for IPPT status
    app = db.get_application(app["id"])

    # Determine approvers and status
    approvers, is_hq = db.get_approvers_for_applicant(user)
    if user.get("role") in ("pc", "oc", "admin") and not is_hq:
        approvers = db.get_users_by_role("oc")
        new_status = "pending_oc"
    elif app.get("ippt_done"):
        new_status = "pending_pc" if not is_hq else "pending_pc"
    else:
        new_status = "pending_ippt"

    from datetime import datetime, timezone
    db.update_application(app["id"], status=new_status, current_step="submitted",
                          submitted_at=datetime.now(timezone.utc).isoformat())
    db.log_action(app["id"], chat_id, "submitted")

    if new_status == "pending_ippt":
        notify_many(
            approvers,
            f"📋 *New deferment application \\#{app['id']}*\n"
            f"From: {esc(user['name'])} \\({esc(user.get('platoon') or '?')}\\)\n"
            f"Type: {esc(get_type_label(app['type']))}\n"
            f"IPPT: ⚠️ Not done — will appear in your queue after IPPT is updated\\."
        )
        send(chat_id,
             f"⚠️ *Application \\#{app['id']} submitted\\!*\n"
             f"Your IPPT is not yet completed\\. Your PC will be notified once you update your IPPT status\\.\n"
             f"Use /edit\\_ippt to update\\.")
    else:
        role_label = "OC (acting as PC)" if is_hq else ("OC" if new_status == "pending_oc" else "PC")
        notify_many(
            approvers,
            f"📋 *New deferment application \\#{app['id']}*\n"
            f"From: {esc(user['name'])} \\({esc(user.get('platoon') or '?')}\\)\n"
            f"Type: {esc(get_type_label(app['type']))}\n"
            f"IPPT: {'✅ Done' if app.get('ippt_done') else '⚠️ Not done'}\n\n"
            f"Use /view {app['id']} to review\\."
        )
        send(chat_id,
             f"✅ *Application \\#{app['id']} submitted\\!*\n"
             f"Pending {role_label} approval\\. You'll be notified of updates\\.")


# ── Post-Submit Edit Handlers ─────────────────────────────────────────────

def _handle_edit_docs(chat_id: str, app: dict) -> None:
    status = app["status"]
    if status == "co_rejected":
        # Allow doc edits after CO rejection
        db.update_application(app["id"], current_step="edit_docs")
        _show_edit_docs(chat_id, app)
        return
    if status == "revision_requested":
        # Already in revision mode — just show the doc editor
        db.update_application(app["id"], current_step="edit_docs")
        _show_edit_docs(chat_id, app)
        return
    if status not in _EDITABLE:
        send(chat_id, "❌ You cannot edit documents after your application has been reviewed\\.")
        return
    prev_step = app["current_step"]
    db.update_application(app["id"], current_step="edit_docs")
    _show_edit_docs(chat_id, app)


def _show_edit_docs(chat_id: str, app: dict) -> None:
    required = get_required_docs(app["type"])
    counts = db.get_doc_counts(app["id"])
    checklist = _format_checklist(required, counts, app["type"])
    send(chat_id,
         f"*Edit documents:*\n\n{checklist}\n\n"
         f"To add a file, attach it with just the number as the caption \\(e\\.g\\. *1*\\)\\.\n"
         f"Or reply to a sent file with the number\\.\n"
         f"/clear <number\\> — remove all files for a category\n"
         f"/done — finish editing")


def _step_edit_docs(chat_id: str, app: dict, text: str, media: dict | None,
                    reply_media: dict | None = None) -> None:
    t = text.lower().strip()
    required = get_required_docs(app["type"])
    counts = db.get_doc_counts(app["id"])

    if t == "/done":
        # Return to appropriate step
        uploaded_types = db.get_uploaded_doc_types(app["id"])
        missing = get_missing_docs(app["type"], uploaded_types)
        if missing:
            labels = ", ".join(esc(d["label"]) for d in missing)
            send(chat_id, f"⚠️ Still missing: {labels}\\. Please upload before finishing\\.")
            return
        # Determine where to return based on status
        status = app["status"]
        if status in ("revision_requested", "co_rejected"):
            db.update_application(app["id"], current_step="submitted")
            send(chat_id, "Documents updated\\. Use /resubmit when ready to resubmit\\.")
        elif status == "draft":
            db.update_application(app["id"], current_step="confirm")
            summary = _build_summary(app)
            send(chat_id, f"Documents updated\\.\n\n{summary}\n\n/confirm — submit application")
        else:
            db.update_application(app["id"], current_step="submitted")
            send(chat_id, "Documents updated\\. Your application remains under review\\.")
        return

    if t.startswith("/clear"):
        parts = t.split()
        if len(parts) < 2 or not parts[1].isdigit():
            send(chat_id, f"Usage: /clear <number\\> \\(1–{len(required)}\\)")
            return
        doc = doc_key_from_index(app["type"], int(parts[1]))
        if not doc:
            send(chat_id, f"Invalid number\\. Please use 1–{len(required)}\\.")
            return
        db.delete_docs_by_type(app["id"], doc["key"])
        db.log_action(app["id"], chat_id, "docs_cleared", doc["key"])
        counts = db.get_doc_counts(app["id"])
        checklist = _format_checklist(required, counts, app["type"])
        send(chat_id, f"🗑️ Cleared: *{esc(doc['label'])}*\n\n{checklist}")
        return

    # Reply-based tagging: user replies to a file message with a category number
    if not media and reply_media and t.isdigit():
        doc = doc_key_from_index(app["type"], int(t))
        if not doc:
            send(chat_id, f"Invalid number\\. Please use 1–{len(required)}\\.")
            return
        if not _save_tagged_file(chat_id, app, reply_media, doc):
            return
        counts = db.get_doc_counts(app["id"])
        checklist = _format_checklist(required, counts, app["type"])
        send(chat_id, f"✅ Received: *{esc(doc['label'])}*\n\n{checklist}")
        return

    if media:
        caption = text.strip()
        if not caption or not caption.isdigit():
            checklist = _format_checklist(required, counts, app["type"])
            send(chat_id,
                 f"Please add just the document number as the caption \\(e\\.g\\. *1*\\)\\.\n\n{checklist}"
                 f"Or reply to a sent file with the number\\.\n\n{checklist}")
            return
        doc = doc_key_from_index(app["type"], int(caption))
        if not doc:
            send(chat_id, f"Invalid number\\. Please use 1–{len(required)}\\.")
            return
        if not _save_tagged_file(chat_id, app, media, doc):
            return
        counts = db.get_doc_counts(app["id"])
        checklist = _format_checklist(required, counts, app["type"])
        send(chat_id, f"✅ Received: *{esc(doc['label'])}*\n\n{checklist}")
        return

    # Text with no media and not a command — show checklist
    _show_edit_docs(chat_id, app)


def _handle_edit_ippt_start(chat_id: str, app: dict) -> None:
    if app["status"] not in _EDITABLE:
        send(chat_id, "❌ You cannot update IPPT status after your application has been reviewed\\.")
        return
    db.update_application(app["id"], current_step="edit_ippt")
    current = "✅ Done" if app.get("ippt_done") else "⚠️ Not done"
    send(chat_id,
         f"*Update IPPT status*\n"
         f"Current: {current}\n\n"
         f"Have you passed your IPPT/completed your mandatory NSFit?\n"
         f"Reply *yes* or *no*\\.")


def _step_edit_ippt(chat_id: str, user: dict, app: dict, text: str) -> None:
    t = text.lower()
    if t not in ("yes", "no", "y", "n"):
        send(chat_id, "Please reply *yes* or *no*\\.")
        return

    done = t.startswith("y")
    was_pending_ippt = app["status"] == "pending_ippt"

    db.update_application(app["id"], ippt_done=done, current_step="submitted")
    db.log_action(app["id"], chat_id, "ippt_updated", "done" if done else "not_done")

    if was_pending_ippt and done:
        # Transition from pending_ippt to pending_pc and notify PC
        db.update_application(app["id"], status="pending_pc")
        approvers, is_hq = db.get_approvers_for_applicant(user)
        notify_many(
            approvers,
            f"📋 *New deferment application \\#{app['id']}*\n"
            f"From: {user['name']} \\({user.get('platoon') or '?'}\\)\n"
            f"Type: {esc(get_type_label(app['type']))}\n"
            f"IPPT: ✅ Done\n\n"
            f"Use /view {app['id']} to review\\."
        )
        send(chat_id,
             f"✅ IPPT status updated to *Done*\\.\n"
             f"Your PC has been notified and your application is now pending review\\.")
    elif app["status"] == "draft":
        db.update_application(app["id"], current_step="confirm")
        send(chat_id, f"IPPT status updated to *{'Done' if done else 'Not done'}*\\.\nUse /confirm to review and submit\\.")
    else:
        send(chat_id, f"IPPT status updated to *{'Done' if done else 'Not done'}*\\.")


# ── OneNS / CO Flow ───────────────────────────────────────────────────────

def _handle_applied(chat_id: str, user: dict, app: dict) -> None:
    if app["status"] != "oc_approved":
        send(chat_id, "This command is only available after OC approval\\.")
        return

    from datetime import datetime, timezone
    db.update_application(app["id"], status="pending_co")
    db.log_action(app["id"], chat_id, "onens_applied")

    # Notify PC and OC
    approvers, _ = db.get_approvers_for_applicant(user)
    ocs = db.get_users_by_role("oc")
    all_notify = {u["id"]: u for u in approvers + ocs}
    notify_many(
        list(all_notify.values()),
        f"📋 *Application \\#{app['id']}*\n"
        f"{esc(user['name'])} has applied on OneNS\\. Awaiting CO decision\\."
    )
    send(chat_id,
         f"✅ Noted\\. Your application is now *Pending CO approval*\\.\n"
         f"Use /co\\_approved or /co\\_rejected to update when you receive a decision\\.")


def _handle_co_status(chat_id: str, user: dict, app: dict, cmd: str) -> None:
    if app["status"] not in ("pending_co", "co_rejected"):
        send(chat_id, "This command is only available when awaiting CO decision\\.")
        return

    if cmd == "/co_approved":
        from datetime import datetime, timezone
        db.update_application(app["id"], status="approved",
                              resolved_at=datetime.now(timezone.utc).isoformat())
        db.log_action(app["id"], chat_id, "co_approved")

        approvers, _ = db.get_approvers_for_applicant(user)
        ocs = db.get_users_by_role("oc")
        all_notify = {u["id"]: u for u in approvers + ocs}
        notify_many(
            list(all_notify.values()),
            f"🎉 *Application \\#{app['id']} — CO APPROVED\\!*\n"
            f"{esc(user['name'])}'s deferment has been approved by CO\\."
        )
        send(chat_id, f"🎉 *Application \\#{app['id']} — CO APPROVED\\!*\nYour deferment application is complete\\.")

    elif cmd == "/co_rejected":
        db.update_application(app["id"], status="co_rejected", current_step="co_rejection_reason")
        db.log_action(app["id"], chat_id, "co_rejected")

        # Notify PCs and OCs immediately
        approvers, _ = db.get_approvers_for_applicant(user)
        ocs = db.get_users_by_role("oc")
        all_notified = {u["id"]: u for u in approvers + ocs}
        notify_many(
            list(all_notified.values()),
            f"❌ *Application \\#{app['id']} — CO Rejected*\n"
            f"{esc(user['name'])}'s application has been rejected by CO\\.\n"
            f"Awaiting rejection reason from applicant\\."
        )
        send(chat_id,
             "❌ CO has rejected your application\\.\n"
             "Please provide the rejection reason from OneNS:")


def _step_co_rejection_reason(chat_id: str, user: dict, app: dict, text: str) -> None:
    if len(text.strip()) < 3:
        send(chat_id, "Please provide the rejection reason from OneNS\\.")
        return

    db.update_application(app["id"], co_rejection_reason=text.strip(), current_step="submitted")
    db.log_action(app["id"], chat_id, "co_rejection_reason", text.strip())

    # Notify PC and OC
    approvers, _ = db.get_approvers_for_applicant(user)
    ocs = db.get_users_by_role("oc")
    all_notify = {u["id"]: u for u in approvers + ocs}
    notify_many(
        list(all_notify.values()),
        f"❌ *Application \\#{app['id']} — CO Rejected*\n"
        f"{esc(user['name'])}\n"
        f"Reason: {esc(text.strip())}"
    )
    send(chat_id,
         f"Rejection reason recorded\\.\n\n"
         f"You can re\\-upload documents and resubmit:\n"
         f"/edit\\_docs — update documents\n"
         f"/resubmit — resubmit for review")


def _handle_resubmit(chat_id: str, user: dict, app: dict) -> None:
    if app["status"] not in ("co_rejected", "revision_requested"):
        send(chat_id, "This command is not available for your current application status\\.")
        return

    # Check documents are complete
    uploaded_types = db.get_uploaded_doc_types(app["id"])
    missing = get_missing_docs(app["type"], uploaded_types)
    if missing:
        labels = ", ".join(d["label"] for d in missing)
        send(chat_id, f"⚠️ Missing documents: {labels}\\.\nUse /edit\\_docs to upload, then /resubmit\\.")
        return

    from datetime import datetime, timezone

    if app["status"] == "co_rejected":
        # Skip PC, go straight to OC
        db.update_application(app["id"], status="pending_oc", current_step="submitted",
                              submitted_at=datetime.now(timezone.utc).isoformat())
        db.log_action(app["id"], chat_id, "resubmitted_to_oc")
        approvers, _ = db.get_approvers_for_applicant(user)
        ocs = db.get_users_by_role("oc")
        all_notify = {u["id"]: u for u in approvers + ocs}
        notify_many(
            list(all_notify.values()),
            f"📋 *Application \\#{app['id']} resubmitted after CO rejection*\n"
            f"From: {esc(user['name'])} \\({esc(user.get('platoon') or '?')}\\)\n"
            f"Use /view {app['id']} to review\\."
        )
        send(chat_id, f"✅ Application \\#{app['id']} resubmitted\\. You'll be notified of updates\\.")

    elif app["status"] == "revision_requested":
        # Go back to pending_pc
        db.update_application(app["id"], status="pending_pc", current_step="submitted",
                              submitted_at=datetime.now(timezone.utc).isoformat())
        db.log_action(app["id"], chat_id, "resubmitted")
        approvers, is_hq = db.get_approvers_for_applicant(user)
        role_label = "OC (acting as PC)" if is_hq else "PC"
        notify_many(
            approvers,
            f"📋 *Application \\#{app['id']} resubmitted after revision*\n"
            f"From: {user['name']} \\({user.get('platoon') or '?'}\\)\n"
            f"Use /view {app['id']} to review\\."
        )
        send(chat_id, f"✅ Application \\#{app['id']} resubmitted\\. Pending {role_label} review\\. You'll be notified of updates\\.")


def _handle_submitted_msg(chat_id: str, app: dict) -> None:
    """Handle messages when application is submitted but user sends text."""
    status = app["status"]
    labels = {
        "pending_ippt": (
            f"⚠️ Your application is awaiting IPPT completion\\.\n"
            f"Use /edit\\_ippt to update your IPPT status\\.\n"
            f"Use /edit\\_docs to update documents\\."
        ),
        "pending_pc": (
            f"Your application is pending PC review\\.\n"
            f"Use /edit\\_docs or /edit\\_ippt to make changes before review\\."
        ),
        "pending_oc": (
            f"Your application is pending OC review\\.\n"
            f"Use /edit\\_docs or /edit\\_ippt to make changes while waiting\\."
        ),
        "oc_approved": (
            f"🎉 Your application has been approved by OC\\!\n"
            f"Please apply on OneNS and reply /applied when done\\."
        ),
        "pending_co": (
            f"Your application is pending CO approval\\.\n"
            f"Use /co\\_approved or /co\\_rejected to update\\."
        ),
        "co_rejected": (
            f"Your application was rejected by CO\\.\n"
            f"/edit\\_docs — update documents\n"
            f"/resubmit — resubmit for review"
        ),
        "revision_requested": (
            f"⚠️ Revision requested\\.\n"
            f"Note: {esc(app.get('revision_note') or '—')}\n\n"
            f"/edit\\_docs — update documents\n"
            f"/resubmit — resubmit for review"
        ),
    }
    msg = labels.get(status, _fmt_status(app))
    send(chat_id, msg)


# ── Formatting Helpers ────────────────────────────────────────────────────

def _format_checklist(required: list[dict], counts: dict[str, int], type_key: str) -> str:
    """Format a numbered document checklist with counts."""
    lines = []
    for i, d in enumerate(required):
        count = counts.get(d["key"], 0)
        label = esc(d["label"])
        if count > 0:
            lines.append(f"{i+1}\\. {label} ✅ \\({count}\\)")
        else:
            lines.append(f"{i+1}\\. {label} ☐")
    return "\n".join(lines)


def _build_summary(app: dict) -> str:
    """Build application summary with human-readable doc labels and counts."""
    # Refresh app data
    app = db.get_application(app["id"]) or app
    docs = db.get_documents(app["id"])
    counts = db.get_doc_counts(app["id"])
    required = get_required_docs(app["type"])

    doc_lines = []
    for d in required:
        count = counts.get(d["key"], 0)
        if count > 0:
            doc_lines.append(f"  • {esc(d['label'])} \\({count}\\)")

    lines = [
        f"*Application \\#{app['id']} Summary*",
        f"Type: {esc(get_type_label(app['type']))}",
        f"IPPT: {'✅ Done' if app.get('ippt_done') else '⚠️ Not done'}",
        f"Documents:",
    ] + doc_lines

    if app.get("revision_note"):
        lines.append(f"\n⚠️ *Revision note:* {esc(app['revision_note'])}")
    return "\n".join(lines)


def _fmt_past_apps(past: list[dict]) -> str:
    labels = {"approved": "✅ Approved", "rejected": "❌ Rejected"}
    entries = ", ".join(
        f"\\#{p['id']} \\({labels.get(p['status'], p['status'])}\\)"
        for p in past
    )
    return f"Past applications: {entries}"


def _fmt_status(app: dict, past: list[dict] | None = None) -> str:
    labels = {
        "draft": "In progress \\(not submitted\\)",
        "pending_ippt": "⚠️ Awaiting IPPT completion",
        "pending_pc": "Awaiting PC approval",
        "pending_oc": "Awaiting OC approval",
        "revision_requested": "⚠️ Revision requested — please update documents",
        "oc_approved": "✅ OC Approved — apply on OneNS",
        "pending_co": "Pending CO approval",
        "approved": "✅ Approved",
        "co_rejected": "❌ CO Rejected",
        "rejected": "❌ Rejected",
    }
    hints = {
        "pending_ippt": "/edit\\_ippt — update IPPT status\n/edit\\_docs — update documents",
        "pending_pc": "/edit\\_docs — update documents\n/edit\\_ippt — update IPPT status",
        "pending_oc": "/edit\\_docs — update documents\n/edit\\_ippt — update IPPT status",
        "revision_requested": "/edit\\_docs — update documents\n/resubmit — resubmit for review",
        "oc_approved": "/applied — confirm you applied on OneNS",
        "pending_co": "/co\\_approved or /co\\_rejected — update CO decision",
        "co_rejected": "/edit\\_docs — update documents\n/resubmit — resubmit for review",
    }
    lines = [
        f"*Application \\#{app['id']}*",
        f"Type: {esc(get_type_label(app['type'])) if app.get('type') else 'Not selected'}",
        f"Status: {labels.get(app['status'], app['status'])}",
    ]
    if app.get("revision_note"):
        lines.append(f"Note: {esc(app['revision_note'])}")
    if app.get("co_rejection_reason"):
        lines.append(f"CO rejection reason: {esc(app['co_rejection_reason'])}")
    hint = hints.get(app["status"])
    if hint:
        lines.append(f"\n{hint}")
    if past:
        lines.append("")
        lines.append(_fmt_past_apps(past))
    return "\n".join(lines)
