"""Platoon change requests: soldier submits, incoming-platoon PC or any OC approves.

Reuses the approval module's two-step review pattern. A reviewer's current request is
tracked in `users.viewing_change_id` (the change-request twin of `viewing_app_id`), and the
follow-up note/reason is collected via `review_step` values in REVIEW_STEPS.
"""
from datetime import datetime, timezone

from bot import db
from bot.config.platoons import format_platoon_menu, platoon_from_index, PLATOONS
from bot.telegram import send, notify, notify_many, esc

_NOW = lambda: datetime.now(timezone.utc).isoformat()

# review_step values owned by this module (approval.handle delegates these here)
REVIEW_STEPS = {"awaiting_change_approve_note", "awaiting_change_reject_reason"}


# ── Helpers ─────────────────────────────────────────────────────────────────

def _can_act_on(user: dict, req: dict) -> bool:
    """True if this PC/OC may decide on the request (PC of the incoming platoon, or any OC)."""
    role = user["role"]
    if role in ("oc", "admin"):
        return True
    return (user.get("platoon") or "").upper() == (req.get("to_platoon") or "").upper()


def _clear_context(chat_id: str) -> None:
    db.update_user(chat_id, viewing_change_id=None, review_step=None)


def _fmt_line(req: dict) -> str:
    """One-line summary for /pending, e.g. '#P3 Tan Wei Ming — SCT → SIG — Pending'."""
    name = esc(req.get("requester_name") or "?")
    frm = esc(req.get("from_platoon") or "?")
    to = esc(req.get("to_platoon") or "?")
    return f"\\#P{req['id']} {name} — {frm} → {to} — Pending"


def _notify_reviewers(req: dict, requester_name: str) -> None:
    """Notify the incoming platoon's PCs and all OCs of a new request."""
    recipients = {u["id"]: u for u in db.get_pcs_for_platoon(req["to_platoon"])}
    for oc in db.get_users_by_role("oc"):
        recipients[oc["id"]] = oc
    notify_many(
        list(recipients.values()),
        f"🔁 *Platoon change request \\#P{req['id']}*\n"
        f"{esc(requester_name)} wants {esc(req.get('from_platoon') or '?')} → {esc(req['to_platoon'])}\n"
        f"Use /view P{req['id']} to review\\.",
    )


# ── Soldier command: /changeplatoon ─────────────────────────────────────────

def start(chat_id: str, user: dict, args: list[str]) -> None:
    """Handle /changeplatoon [number] for a soldier."""
    if user.get("role", "user") != "user":
        send(chat_id, "❌ Only soldiers can request a platoon change\\. "
                      "Reviewers' platoons are managed by the OC\\.")
        return

    current = user.get("platoon")

    # No argument → show the menu.
    if not args:
        existing = db.get_active_platoon_change_request(chat_id)
        if existing:
            send(chat_id,
                 f"⏳ You already have a pending platoon change request "
                 f"\\(\\#P{existing['id']}: {esc(existing.get('from_platoon') or '?')} → "
                 f"{esc(existing['to_platoon'])}\\)\\.\nPlease wait for it to be reviewed\\.")
            return
        send(chat_id,
             f"*Request a platoon change*\n\n"
             f"Your current platoon: *{esc(current or '?')}*\n\n"
             f"Reply with `/changeplatoon <number>` to request a move to:\n\n"
             f"{format_platoon_menu()}")
        return

    # With argument → create the request.
    n = int(args[0]) if args[0].isdigit() else 0
    target = platoon_from_index(n)
    if not target:
        send(chat_id,
             f"Please pick a number 1–{len(PLATOONS)}\\.\n\n{format_platoon_menu()}")
        return

    if (current or "").upper() == target.upper():
        send(chat_id, f"You are already in *{esc(target)}*\\. No change needed\\.")
        return

    existing = db.get_active_platoon_change_request(chat_id)
    if existing:
        send(chat_id,
             f"⏳ You already have a pending platoon change request "
             f"\\(\\#P{existing['id']}: {esc(existing.get('from_platoon') or '?')} → "
             f"{esc(existing['to_platoon'])}\\)\\.\nPlease wait for it to be reviewed\\.")
        return

    req = db.create_platoon_change_request(chat_id, current, target)
    db.log_action(None, chat_id, "platoon_change_requested", f"{current} -> {target}")
    send(chat_id,
         f"✅ Platoon change request \\#P{req['id']} submitted: "
         f"*{esc(current or '?')} → {esc(target)}*\\.\n\n"
         f"The {esc(target)} PC or an OC will review it\\. You'll be notified of the outcome\\.")
    _notify_reviewers(req, user.get("name") or "?")


# ── Reviewer: /pending section ──────────────────────────────────────────────

def pending_section(user: dict) -> str | None:
    """Return a formatted block of pending change requests for this reviewer, or None."""
    role = user["role"]
    if role in ("oc", "admin"):
        reqs = db.get_all_pending_changes()
    else:
        reqs = db.get_pending_changes_for_platoon(user.get("platoon") or "")
    if not reqs:
        return None
    lines = "\n".join(_fmt_line(r) for r in reqs)
    return (
        "*Pending platoon change requests:*\n\n"
        + lines
        + "\n\n_To review: /view P<id\\>, then /approve or /reject_"
    )


# ── Reviewer: /view P<id> ───────────────────────────────────────────────────

def view(chat_id: str, user: dict, req_id: int) -> None:
    req = db.get_platoon_change_request(req_id)
    if not req:
        send(chat_id, f"Platoon change request \\#P{req_id} not found\\.")
        return

    # Enter change-review context (mutually exclusive with application review context).
    db.update_user(chat_id, viewing_change_id=req_id, viewing_app_id=None, review_step=None)

    status_label = {"pending": "Pending", "approved": "Approved", "rejected": "Rejected"}.get(
        req["status"], req["status"])
    lines = [
        f"*Platoon change request \\#P{req_id}*",
        f"Soldier: {esc(req.get('requester_name') or '?')}",
        f"Change: {esc(req.get('from_platoon') or '?')} → {esc(req['to_platoon'])}",
        f"Status: {status_label}",
    ]
    if req.get("decision_note"):
        lines.append(f"Note: {esc(req['decision_note'])}")

    if req["status"] == "pending" and _can_act_on(user, req):
        lines.append(
            "\n/approve — approve \\(soldier is moved to the new platoon\\)\n"
            "/reject — reject \\(will ask for reason\\)")
    elif req["status"] == "pending":
        lines.append("\n_Only the incoming platoon's PC or an OC can act on this request\\._")
    else:
        lines.append("\n_This request has already been decided\\._")

    send(chat_id, "\n".join(lines))


# ── Reviewer: /approve, /reject (enter step) ────────────────────────────────

def _load_actionable(chat_id: str, user: dict, req_id: int, verb: str) -> dict | None:
    req = db.get_platoon_change_request(req_id)
    if not req:
        send(chat_id, f"Platoon change request \\#P{req_id} not found\\.")
        return None
    if not _can_act_on(user, req):
        send(chat_id, "❌ Only the incoming platoon's PC or an OC can act on this request\\.")
        return None
    if req["status"] != "pending":
        send(chat_id, f"Request \\#P{req_id} has already been decided\\.")
        return None
    return req


def approve(chat_id: str, user: dict, req_id: int) -> None:
    req = _load_actionable(chat_id, user, req_id, "approve")
    if not req:
        return
    db.update_user(chat_id, viewing_change_id=req_id, review_step="awaiting_change_approve_note")
    send(chat_id,
         f"Approving \\#P{req_id}: {esc(req.get('requester_name') or '?')} "
         f"{esc(req.get('from_platoon') or '?')} → {esc(req['to_platoon'])}\\.\n\n"
         f"Any note? \\(optional\\)\nReply with a note, /skip, or /cancel\\.")


def reject(chat_id: str, user: dict, req_id: int) -> None:
    req = _load_actionable(chat_id, user, req_id, "reject")
    if not req:
        return
    db.update_user(chat_id, viewing_change_id=req_id, review_step="awaiting_change_reject_reason")
    send(chat_id,
         f"Rejecting \\#P{req_id}: {esc(req.get('requester_name') or '?')} "
         f"{esc(req.get('from_platoon') or '?')} → {esc(req['to_platoon'])}\\.\n\n"
         f"Please provide a reason \\(or /cancel\\):")


# ── Reviewer: step handler (note/reason input) ──────────────────────────────

def handle_review_step(chat_id: str, user: dict, text: str, step: str) -> None:
    if text.lower().strip() == "/cancel":
        _clear_context(chat_id)
        send(chat_id, "Action cancelled\\.\nUse /pending to review other requests\\.")
        return

    req_id = user.get("viewing_change_id")
    req = db.get_platoon_change_request(req_id) if req_id else None
    if not req:
        _clear_context(chat_id)
        send(chat_id, "No platoon change request in context\\. Use /view P<id\\> first\\.")
        return

    if req["status"] != "pending":
        _clear_context(chat_id)
        send(chat_id, f"Request \\#P{req['id']} has already been decided\\.")
        return

    if step == "awaiting_change_approve_note":
        _execute_approve(chat_id, user, req, text)
    elif step == "awaiting_change_reject_reason":
        _execute_reject(chat_id, user, req, text)


def _execute_approve(chat_id: str, user: dict, req: dict, text: str) -> None:
    note = None if text.strip().lower() == "/skip" else text.strip()
    _clear_context(chat_id)

    soldier_id = req["user_id"]
    target = req["to_platoon"]

    db.update_user(soldier_id, platoon=target)
    db.update_platoon_change_request(
        req["id"], status="approved", decided_by=chat_id,
        decision_note=note, resolved_at=_NOW())
    db.log_action(None, chat_id, "platoon_change_approved",
                  f"#{req['id']} {req.get('from_platoon')} -> {target}"
                  + (f" | {note}" if note else ""))

    notify(soldier_id,
           f"✅ *Platoon change approved\\!*\n"
           f"You are now in *{esc(target)}*\\."
           + (f"\nNote: {esc(note)}" if note else ""))

    # If the soldier has an in-progress application, it auto-routes to the new platoon's
    # PC (applications_full derives applicant_platoon from users.platoon). Flag the new PCs.
    active = db.get_active_application(soldier_id)
    if active and active["status"] not in ("oc_approved", "pending_co"):
        for pc in db.get_pcs_for_platoon(target):
            notify(pc["id"],
                   f"ℹ️ {esc(req.get('requester_name') or '?')} moved into {esc(target)} "
                   f"with an active application \\(\\#{active['id']}\\) now in your queue\\. "
                   f"Use /pending to review\\.")

    send(chat_id,
         f"✅ \\#P{req['id']} approved\\. {esc(req.get('requester_name') or '?')} moved to "
         f"{esc(target)}\\.\nUse /pending to review next\\.")


def _execute_reject(chat_id: str, user: dict, req: dict, text: str) -> None:
    reason = text.strip()
    if not reason or reason.lower() == "/skip":
        send(chat_id, "A reason is required for rejection\\. Please provide one:")
        return

    _clear_context(chat_id)
    db.update_platoon_change_request(
        req["id"], status="rejected", decided_by=chat_id,
        decision_note=reason, resolved_at=_NOW())
    db.log_action(None, chat_id, "platoon_change_rejected",
                  f"#{req['id']} {req.get('from_platoon')} -> {req['to_platoon']} | {reason}")

    notify(req["user_id"],
           f"❌ *Platoon change request \\#P{req['id']} rejected\\.*\n"
           f"You remain in *{esc(req.get('from_platoon') or '?')}*\\.\n\n"
           f"Reason: {esc(reason)}")

    send(chat_id,
         f"\\#P{req['id']} rejected\\. {esc(req.get('requester_name') or '?')} notified\\.\n"
         f"Use /pending to review next\\.")
