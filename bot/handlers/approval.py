"""PC/OC approval commands with context-aware review, decision editing, and co-status."""
import re
from datetime import datetime, timezone

from bot import db
from bot.config.docs import get_type_label, get_required_docs, get_doc_label
from bot.handlers import platoon_change
from bot.telegram import send, send_file, notify, notify_many, esc

_NOW = lambda: datetime.now(timezone.utc).isoformat()

# Review steps for context-aware flow
_REVIEW_STEPS = {
    "awaiting_approve_comment", "awaiting_reject_reason", "awaiting_revise_note",
    "awaiting_edit_action", "awaiting_edit_approve_comment",
    "awaiting_edit_reject_reason", "awaiting_edit_revise_note",
}


def handle(chat_id: str, user: dict, cmd: str, args: list[str]) -> bool:
    """Return True if command was handled."""
    # Check if user is in a review context step
    review_step = user.get("review_step")
    if review_step in platoon_change.REVIEW_STEPS:
        platoon_change.handle_review_step(chat_id, user, cmd, review_step)
        return True
    if review_step in _REVIEW_STEPS:
        _handle_review_step(chat_id, user, cmd, args, review_step)
        return True

    dispatch = {
        "/pending": _pending,
        "/list_active": _list_active,
        "/list_all": _list_all,
        "/approve": _approve,
        "/reject": _reject,
        "/revise": _revise,
        "/view": _view,
        "/list": _list,
        "/setstatus": _setstatus,
        "/co_status": _co_status,
        "/edit_decision": _edit_decision,
        "/remind": _remind,
        "/summary": _summary,
    }
    fn = dispatch.get(cmd)
    if fn:
        fn(chat_id, user, args)
        return True
    return False


# ── Helpers ───────────────────────────────────────────────────────────────

def _parse_id(args: list[str], pos: int = 0) -> int | None:
    try:
        return int(args[pos])
    except (IndexError, ValueError):
        return None


def _can_act_on(user: dict, app: dict) -> bool:
    """True if this PC/OC is allowed to act on this application."""
    role = user["role"]
    if role in ("oc", "admin"):
        return True
    return (user.get("platoon") or "").upper() == (app.get("applicant_platoon") or "").upper()


def _is_hq_app(app: dict) -> bool:
    return (app.get("applicant_platoon") or "").upper() == db.HQ_PLATOON


def _oc_acts_as_pc(user: dict, app: dict) -> bool:
    """True if this OC should review this pending_pc app as the PC.

    HQ apps are handled by any OC; otherwise an OC may act as PC only for their
    own platoon and only when that platoon has no registered PC (fallback).
    """
    if app.get("status") != "pending_pc":
        return False
    if _is_hq_app(app):
        return True
    platoon = (app.get("applicant_platoon") or "").upper()
    if not platoon or platoon != (user.get("platoon") or "").upper():
        return False
    return not db.platoon_has_pc(app.get("applicant_platoon") or "")


def _clear_review_context(chat_id: str) -> None:
    db.update_user(chat_id, viewing_app_id=None, viewing_change_id=None, review_step=None)


def _change_target(user: dict, args: list[str]) -> int | None:
    """Resolve a platoon-change-request id from a 'P<id>' arg or the viewing context."""
    if args:
        m = re.fullmatch(r"[Pp](\d+)", args[0])
        return int(m.group(1)) if m else None
    return user.get("viewing_change_id")


def _get_viewing_app(user: dict) -> dict | None:
    """Get the app the reviewer is currently viewing."""
    app_id = user.get("viewing_app_id")
    if not app_id:
        return None
    return db.get_application_full(app_id)


def _action_label(status: str, role: str, app: dict) -> str:
    """Determine what action is available for this app given viewer's role."""
    is_hq = _is_hq_app(app)
    if role == "pc":
        if status == "pending_pc":
            return "Review"
        return "—"
    elif role in ("oc", "admin"):
        if status == "pending_oc":
            return "Review"
        if status == "pending_pc" and is_hq:
            return "Review \\(as PC\\)"
        return "—"
    return "—"


def _can_edit_decision(user: dict, app: dict) -> bool:
    """Check if the reviewer can still edit their decision on this app."""
    role = user["role"]
    status = app.get("status", "")
    if role == "pc":
        # PC can edit if OC hasn't acted (status is still pending_oc)
        return status == "pending_oc"
    elif role in ("oc", "admin"):
        # OC can edit only before user applies on OneNS
        return status == "oc_approved"
    return False


def _status_display(status: str) -> str:
    """Human-readable status for list views."""
    labels = {
        "draft": "Draft",
        "draft_confirm": "Ready to Submit",
        "pending_ippt": "Awaiting IPPT",
        "pending_pc": "Pending PC",
        "pending_oc": "Pending OC",
        "revision_requested": "Revision Requested",
        "oc_approved": "OC Approved",
        "pending_co": "Pending CO",
        "approved": "Approved",
        "co_rejected": "CO Rejected",
        "rejected": "Rejected",
    }
    return labels.get(status, status)


def _format_app_line(a: dict) -> str:
    """Format a single application as a unified line."""
    name = esc(a.get("applicant_name", "?"))
    platoon = esc(a.get("applicant_platoon") or "?")
    app_type = esc(get_type_label(a["type"]))
    status = _status_display(a["status"])
    return f"\\#{a['id']} {name} \\({platoon}\\) — {app_type} — {status}"


def _format_app_list(apps: list[dict], user: dict) -> str:
    """Format a flat list of applications."""
    if not apps:
        return "No applications found\\."
    return "\n".join(_format_app_line(a) for a in apps)


def _format_app_list_by_platoon(apps: list[dict], user: dict) -> str:
    """Format applications grouped by platoon (for OC view)."""
    if not apps:
        return "No applications found\\."
    grouped: dict[str, list] = {}
    for a in apps:
        plt = a.get("applicant_platoon") or "Unknown"
        grouped.setdefault(plt, []).append(a)

    sections = []
    for plt in sorted(grouped.keys()):
        header = f"*── {esc(plt)} ──*"
        lines = [_format_app_line(a) for a in grouped[plt]]
        sections.append(f"{header}\n" + "\n".join(lines))
    return "\n\n".join(sections)


# ── Summary Command ───────────────────────────────────────────────────────

# Pipeline order used to sort the verbose roster
_STATUS_LABEL: dict[str, str] = {
    "draft":               "Draft",
    "pending_ippt":        "Awaiting IPPT",
    "pending_pc":          "Pending PC",
    "revision_requested":  "Revision Requested",
    "pending_oc":          "Pending OC",
    "oc_approved":         "OC Approved",
    "pending_co":          "Pending CO",
    "co_rejected":         "CO Rejected",
    "approved":            "Approved",
    "rejected":            "Rejected",
}
_STATUS_ORDER = list(_STATUS_LABEL.keys())


def _summary(chat_id: str, user: dict, args: list[str]) -> None:
    """Per-platoon breakdown of pending and approved application counts.
    Pass -v for a verbose roster of each soldier and their current stage."""
    verbose = "-v" in args
    role = user["role"]
    if role == "pc":
        apps = db.get_all_for_pc(user.get("platoon") or "")
    else:
        apps = db.get_all_applications()

    if not apps:
        send(chat_id, "No applications found\\.")
        return

    grouped: dict[str, list] = {}
    for a in apps:
        plt = a.get("applicant_platoon") or "Unknown"
        grouped.setdefault(plt, []).append(a)

    sections = []
    for plt in sorted(grouped.keys()):
        plt_apps = grouped[plt]
        counts: dict[str, int] = {}
        for a in plt_apps:
            s = a["status"]
            counts[s] = counts.get(s, 0) + 1

        drafts = counts.get("draft", 0) + counts.get("draft_confirm", 0)
        awaiting_ippt = counts.get("pending_ippt", 0)
        pending_pc = counts.get("pending_pc", 0)
        pending_oc = counts.get("pending_oc", 0)
        oc_approved = counts.get("oc_approved", 0)
        revision_requested = counts.get("revision_requested", 0)
        pending_co = counts.get("pending_co", 0)
        all_pending = sum(counts.get(s, 0) for s in counts if s != "approved" and s != "rejected")
        all_approved = counts.get("approved", 0)
        total = all_pending + all_approved

        lines = [
            f"*── {esc(plt)} ──*",
            f"*All pending \\+ approved: {total}*",
            f"*All approved: {all_approved}*",
            f"*Total pending: {all_pending}*",
            f"Drafts: {drafts}",
            f"Awaiting IPPT: {awaiting_ippt}",
            f"Pending PC: {pending_pc}",
            f"Revision Requested: {revision_requested}",
            f"Pending OC: {pending_oc}",
            f"OC Approved: {oc_approved}",
            f"Pending CO: {pending_co}",
        ]

        if verbose:
            sorted_apps = sorted(
                (a for a in plt_apps if a["status"] != "rejected"),
                key=lambda a: _STATUS_ORDER.index(a["status"]) if a["status"] in _STATUS_ORDER else 999,
            )
            lines.append("\n_Deferments:_")
            for a in sorted_apps:
                label = _STATUS_LABEL.get(a["status"], a["status"])
                name = esc(a.get("applicant_name") or "Unknown")
                lines.append(f"  • {name} — _{esc(label)}_")

        sections.append("\n".join(lines))

    send(chat_id, "📊 *Application Summary*\n\n" + "\n\n".join(sections))


# ── Remind Command ────────────────────────────────────────────────────────

_USER_ACTION_STATUSES = {"draft", "draft_confirm", "pending_ippt", "revision_requested", "oc_approved", "co_rejected", "pending_co"}
# pending_co soldiers have already submitted on OneNS — withdraw is not meaningful for them
_NO_WITHDRAW_STATUSES = {"pending_co"}

_REMIND_MSGS = {
    "draft": (
        "📋 *Reminder: Your deferment application is still a draft\\.* "
        "Use /apply to continue filling it in\\."
    ),
    "draft_confirm": (
        "📋 *Reminder: Your documents are ready — use /confirm to submit your application\\.*"
    ),
    "pending_ippt": (
        "🏃 *Reminder: Your application is waiting on your IPPT/NSFit completion\\.* "
        "Use /edit\\_ippt to update your status once done\\."
    ),
    "revision_requested": (
        "📝 *Reminder: Revisions have been requested on your application\\.* "
        "Use /resubmit to upload updated documents\\."
    ),
    "oc_approved": (
        "✅ *Reminder: Your application has been approved by the OC\\.* "
        "Please apply on OneNS and then use /applied to confirm\\."
    ),
    "co_rejected": (
        "❌ *Reminder: Your CO has rejected your deferment application\\.* "
        "Use /resubmit to submit an updated application\\."
    ),
    "pending_co": (
        "🏛️ *Reminder: Your application is pending your CO's decision\\.* "
        "Check OneNS for the outcome, then use /co\\_approved or /co\\_rejected to report it\\."
    ),
}
_WITHDRAW_NOTE = "\n\n_If you are no longer applying, use /withdraw to cancel\\._"


def _remind(chat_id: str, user: dict, args: list[str]) -> None:
    """Broadcast status-specific reminders to all users/reviewers with pending actions."""
    apps = db.get_active_for_oc()

    # --- Applicant reminders ---
    # Keep only the most recent active app per applicant (get_active_for_oc orders by
    # platoon then id desc, so we can't rely on list order for global deduplication).
    latest: dict[str, dict] = {}
    for app in apps:
        aid = app["applicant_id"]
        if aid not in latest or app["id"] > latest[aid]["id"]:
            latest[aid] = app

    applicant_count = 0
    status_counts: dict[str, int] = {}
    for app in latest.values():
        status = app["status"]
        remind_key = (
            "draft_confirm"
            if status == "draft" and app.get("current_step") == "confirm"
            else status
        )
        if remind_key not in _USER_ACTION_STATUSES:
            continue
        trailer = "" if remind_key in _NO_WITHDRAW_STATUSES else _WITHDRAW_NOTE
        send(app["applicant_id"], _REMIND_MSGS[remind_key] + trailer)
        applicant_count += 1
        status_counts[remind_key] = status_counts.get(remind_key, 0) + 1

    # --- PC / fallback-OC reminders ---
    # Group non-HQ pending_pc apps by platoon. Notify each platoon's PCs; if a
    # platoon has no PC, notify that platoon's OCs (fallback reviewers) instead.
    platoon_counts: dict[str, int] = {}
    for app in apps:
        if app["status"] == "pending_pc" and not _is_hq_app(app):
            platoon = app.get("applicant_platoon") or ""
            if not platoon:
                continue
            platoon_counts[platoon] = platoon_counts.get(platoon, 0) + 1

    pc_notified: set[str] = set()
    fallback_oc_notified: set[str] = set()
    pc_app_total = 0
    fallback_app_total = 0
    for platoon, count in platoon_counts.items():
        noun = "application" if count == 1 else "applications"
        pcs = db.get_pcs_for_platoon(platoon)
        if pcs:
            pc_app_total += count
            for pc in pcs:
                if pc["id"] not in pc_notified:
                    send(pc["id"],
                         f"📋 *Reminder: You have {count} {noun} from "
                         f"{esc(platoon)} pending your review\\.* "
                         f"Use /pending to see them\\.")
                    pc_notified.add(pc["id"])
        else:
            fallback_app_total += count
            for oc in db.get_ocs_for_platoon(platoon):
                if oc["id"] not in fallback_oc_notified:
                    send(oc["id"],
                         f"📋 *Reminder: You have {count} {noun} from "
                         f"{esc(platoon)} pending your review \\(acting as PC\\)\\.* "
                         f"Use /pending to see them\\.")
                    fallback_oc_notified.add(oc["id"])

    # --- OC reminders ---
    # pending_oc apps + HQ pending_pc apps; pending_co is excluded because
    # the CO decision is an external process with no bot action for the OC.
    # Caller is excluded from OC broadcast (they get the summary instead).
    oc_app_count = sum(
        1 for a in apps
        if a["status"] == "pending_oc" or (a["status"] == "pending_pc" and _is_hq_app(a))
    )
    oc_notified: set[str] = set()
    if oc_app_count > 0:
        noun = "application" if oc_app_count == 1 else "applications"
        for oc in db.get_users_by_role("oc"):
            if oc["id"] != chat_id and oc["id"] not in oc_notified:
                send(oc["id"],
                     f"📋 *Reminder: You have {oc_app_count} {noun} pending your review\\.* "
                     f"Use /pending to see them\\.")
                oc_notified.add(oc["id"])

    # --- Summary to caller ---
    if not applicant_count and not pc_notified and not fallback_oc_notified and not oc_notified:
        send(chat_id, "✅ No reminders to send — no pending actions found\\.")
        return

    lines = []
    if applicant_count:
        breakdown = ", ".join(
            f"{_status_display(s)}: {n}" for s, n in status_counts.items()
        )
        noun = "soldier" if applicant_count == 1 else "soldiers"
        lines.append(f"• {applicant_count} {noun} \\({esc(breakdown)}\\)")
    if pc_notified:
        noun_pc = "PC" if len(pc_notified) == 1 else "PCs"
        noun_app = "application" if pc_app_total == 1 else "applications"
        lines.append(f"• {len(pc_notified)} {noun_pc} \\({pc_app_total} {noun_app} pending\\)")
    if fallback_oc_notified:
        noun_oc = "OC" if len(fallback_oc_notified) == 1 else "OCs"
        noun_app = "application" if fallback_app_total == 1 else "applications"
        lines.append(f"• {len(fallback_oc_notified)} {noun_oc} acting as PC \\({fallback_app_total} {noun_app} pending\\)")
    if oc_notified:
        noun_oc = "OC" if len(oc_notified) == 1 else "OCs"
        noun_app = "application" if oc_app_count == 1 else "applications"
        lines.append(f"• {len(oc_notified)} {noun_oc} \\({oc_app_count} {noun_app} pending\\)")

    send(chat_id, "✅ *Reminders sent:*\n" + "\n".join(lines))


# ── List Commands ─────────────────────────────────────────────────────────

def _list_active(chat_id: str, user: dict, args: list[str]) -> None:
    role = user["role"]
    if role == "pc":
        apps = db.get_active_for_pc(user.get("platoon") or "")
        if not apps:
            send(chat_id, "No active applications\\.\nUse /pending to check for applications awaiting review\\.")
            return
        platoon = user.get("platoon", "?")
        header = f"*Active Applications \\({platoon}\\):*\n\n"
        send(chat_id, header + _format_app_list(apps, user))
    elif role in ("oc", "admin"):
        apps = db.get_active_for_oc()
        if not apps:
            send(chat_id, "No active applications\\.\nUse /pending to check for applications awaiting review\\.")
            return
        send(chat_id, "*Active Applications:*\n\n" + _format_app_list_by_platoon(apps, user))


def _list_all(chat_id: str, user: dict, args: list[str]) -> None:
    role = user["role"]
    if role == "pc":
        apps = db.get_all_for_pc(user.get("platoon") or "")
        if not apps:
            send(chat_id, "No applications found\\.")
            return
        platoon = user.get("platoon", "?")
        header = f"*All Applications \\({platoon}\\):*\n\n"
        send(chat_id, header + _format_app_list(apps, user))
    elif role in ("oc", "admin"):
        apps = db.get_all_applications()
        if not apps:
            send(chat_id, "No applications found\\.")
            return
        send(chat_id, "*All Applications:*\n\n" + _format_app_list_by_platoon(apps, user))


def _pending(chat_id: str, user: dict, args: list[str]) -> None:
    role = user["role"]
    if role in ("oc", "admin"):
        apps = db.get_pending_for_oc(user.get("platoon"))
    else:
        apps = db.get_pending_for_pc(user.get("platoon") or "")

    change_section = platoon_change.pending_section(user)

    if not apps:
        if change_section:
            send(chat_id, change_section)
            return
        send(chat_id, "No pending applications\\.\nUse /list\\_active to view all active applications\\.")
        return

    msg = (
        "*Pending applications:*\n\n"
        + _format_app_list(apps, user)
        + "\n\n_To review: /view <id\\>, then /approve, /reject, or /revise_"
    )
    if change_section:
        msg += "\n\n" + change_section
    send(chat_id, msg)


def _list(chat_id: str, user: dict, args: list[str]) -> None:
    status = args[0] if args else None
    valid = {"draft", "pending_ippt", "pending_pc", "pending_oc", "revision_requested",
             "oc_approved", "pending_co", "approved", "co_rejected", "rejected"}
    apps = db.get_all_applications(status if status in valid else None)
    if not apps:
        send(chat_id, "No applications found\\.")
        return
    header = f"*Applications \\({_status_display(status)}\\):*" if status in valid else "*All applications:*"
    send(chat_id, f"{header}\n\n" + _format_app_list(apps, user))


# ── View (enters review context) ─────────────────────────────────────────

def _view(chat_id: str, user: dict, args: list[str]) -> None:
    if args and re.fullmatch(r"[Pp]\d+", args[0]):
        platoon_change.view(chat_id, user, int(args[0][1:]))
        return

    app_id = _parse_id(args)
    if not app_id:
        send(chat_id, "Usage: /view <id\\>")
        return

    app = db.get_application_full(app_id)
    if not app:
        send(chat_id, f"Application \\#{app_id} not found\\.")
        return

    # Set review context
    db.update_user(chat_id, viewing_app_id=app_id, viewing_change_id=None, review_step=None)

    applicant = db.get_user(app["applicant_id"])
    docs = db.get_documents(app_id)
    counts = db.get_doc_counts(app_id)
    required = get_required_docs(app["type"])

    lines = [
        f"*Application \\#{app_id}*",
        f"Applicant: {esc(applicant['name'])} \\({esc(applicant.get('platoon') or '?')}\\)",
        f"Type: {esc(get_type_label(app['type']))}",
        f"IPPT: {'✅ Done' if app.get('ippt_done') else '⚠️ Not done'}",
        f"Status: {_status_display(app['status'])}",
    ]

    # Show reviewer info for OC
    if app.get("reviewed_by") and user["role"] in ("oc", "admin"):
        reviewer_name = esc(app.get("reviewer_name", "?"))
        reviewer_platoon = esc(app.get("reviewer_platoon", "?"))
        reviewer_role = esc((app.get("reviewer_role") or "?").upper())
        lines.append(f"Reviewed by: {reviewer_name} \\({reviewer_role}, {reviewer_platoon}\\)")

    # Show the most recent PC-level action with a note
    pc_action = db.get_last_action(app_id, "pc_")
    if pc_action and pc_action.get("note"):
        action_label = "PC comment" if "approved" in pc_action["action"] else "PC note"
        lines.append(f"{action_label}: {esc(pc_action['note'])}")

    # Show the most recent OC-level action with a note
    oc_action = db.get_last_action(app_id, "oc_")
    if oc_action and oc_action.get("note"):
        action_label = "OC comment" if "approved" in oc_action["action"] else "OC note"
        lines.append(f"{action_label}: {esc(oc_action['note'])}")

    if app.get("revision_note"):
        lines.append(f"Revision note: {esc(app['revision_note'])}")
    if app.get("co_rejection_reason"):
        lines.append(f"CO rejection reason: {esc(app['co_rejection_reason'])}")

    lines.append(f"\nDocuments \\({len(docs)} files\\):")
    for d in required:
        count = counts.get(d["key"], 0)
        if count > 0:
            lines.append(f"  • {esc(d['label'])} \\({count} file{'s' if count > 1 else ''}\\)")

    # Show available actions
    role = user["role"]
    status = app["status"]

    can_review = False
    if role == "pc" and status == "pending_pc":
        can_review = True
    elif role in ("oc", "admin"):
        if status == "pending_oc" or _oc_acts_as_pc(user, app):
            can_review = True

    if can_review:
        lines.append(
            f"\n/approve — approve \\(will ask for optional comment\\)\n"
            f"/reject — reject \\(will ask for reason\\)\n"
            f"/revise — send back for revision"
        )

    can_edit = _can_edit_decision(user, app)
    if can_edit:
        lines.append(f"\n/edit\\_decision — edit your previous decision")

    if not can_review and not can_edit:
        lines.append(f"\n_No actions available for this application\\._")

    send(chat_id, "\n".join(lines))

    # Send actual document files
    for d in docs:
        if d.get("file_id"):
            label = get_doc_label(app["type"], d["doc_type"])
            send_file(chat_id, d["file_id"],
                      d.get("mimetype", "application/pdf"),
                      caption=label)


# ── Context-Aware Review Actions ──────────────────────────────────────────

def _approve(chat_id: str, user: dict, args: list[str]) -> None:
    change_id = _change_target(user, args)
    if change_id is not None:
        platoon_change.approve(chat_id, user, change_id)
        return

    # Try context-aware first (no args needed)
    app = _get_viewing_app(user)
    if not app and args:
        app_id = _parse_id(args)
        if app_id:
            app = db.get_application_full(app_id)

    if not app:
        send(chat_id, "Usage: /approve <id\\> or use /view <id\\> first\\.")
        return

    if not _can_act_on(user, app):
        send(chat_id, "❌ You can only approve applications from your platoon\\.")
        return

    role = user["role"]
    status = app["status"]

    # Validate approvable state
    if role == "pc" and status != "pending_pc":
        send(chat_id, f"Application \\#{app['id']} is not awaiting PC approval\\.")
        return
    elif role in ("oc", "admin"):
        if not (status == "pending_oc" or _oc_acts_as_pc(user, app)):
            send(chat_id, f"Application \\#{app['id']} is not in an approvable state \\(status: {_status_display(status)}\\)\\.")
            return

    # Enter comment step
    db.update_user(chat_id, viewing_app_id=app["id"], viewing_change_id=None, review_step="awaiting_approve_comment")
    name = esc(app.get("applicant_name") or "?")
    send(chat_id, f"Approving *{name}*'s application \\#{app['id']}\\.\n\nAny comments? \\(optional\\)\nReply with your comment, /skip, or /cancel\\.")


def _reject(chat_id: str, user: dict, args: list[str]) -> None:
    change_id = _change_target(user, args)
    if change_id is not None:
        platoon_change.reject(chat_id, user, change_id)
        return

    app = _get_viewing_app(user)
    if not app and args:
        app_id = _parse_id(args)
        if app_id:
            app = db.get_application_full(app_id)

    if not app:
        send(chat_id, "Usage: /reject <id\\> or use /view <id\\> first\\.")
        return

    if not _can_act_on(user, app):
        send(chat_id, "❌ You can only reject applications from your platoon\\.")
        return

    status = app["status"]
    role = user["role"]

    if role == "pc" and status != "pending_pc":
        send(chat_id, f"Application \\#{app['id']} is not awaiting PC approval\\.")
        return
    elif role in ("oc", "admin"):
        if not (status == "pending_oc" or _oc_acts_as_pc(user, app)):
            send(chat_id, f"Application \\#{app['id']} is not in a rejectable state\\.")
            return

    db.update_user(chat_id, viewing_app_id=app["id"], viewing_change_id=None, review_step="awaiting_reject_reason")
    name = esc(app.get("applicant_name") or "?")
    send(chat_id, f"Rejecting *{name}*'s application \\#{app['id']}\\.\n\nPlease provide a reason \\(or /cancel\\):")


def _revise(chat_id: str, user: dict, args: list[str]) -> None:
    app = _get_viewing_app(user)
    if not app and args:
        app_id = _parse_id(args)
        if app_id:
            app = db.get_application_full(app_id)

    if not app:
        send(chat_id, "Usage: /revise <id\\> or use /view <id\\> first\\.")
        return

    if not _can_act_on(user, app):
        send(chat_id, "❌ You can only revise applications from your platoon\\.")
        return

    status = app["status"]
    role = user["role"]

    if role == "pc" and status != "pending_pc":
        send(chat_id, f"Application \\#{app['id']} is not awaiting PC approval\\.")
        return
    elif role in ("oc", "admin"):
        if not (status == "pending_oc" or _oc_acts_as_pc(user, app)):
            send(chat_id, f"Application \\#{app['id']} is not in a revisable state\\.")
            return

    db.update_user(chat_id, viewing_app_id=app["id"], viewing_change_id=None, review_step="awaiting_revise_note")
    name = esc(app.get("applicant_name") or "?")
    send(chat_id, f"Sending *{name}*'s application \\#{app['id']} back for revision\\.\n\nWhat needs to be revised? \\(/cancel to abort\\)")


# ── Review Step Handler ───────────────────────────────────────────────────

def _handle_review_step(chat_id: str, user: dict, cmd: str, args: list[str], step: str) -> None:
    """Handle the second step of a two-step review action (comment/reason input)."""
    # Allow cancellation
    text = cmd  # The full text/command
    if text.lower().strip() == "/cancel":
        _clear_review_context(chat_id)
        send(chat_id, "Review action cancelled\\.\nUse /pending to review other applications\\.")
        return

    app_id = user.get("viewing_app_id")
    if not app_id:
        _clear_review_context(chat_id)
        send(chat_id, "No application in review context\\. Use /view <id\\> first\\.")
        return

    app = db.get_application_full(app_id)
    if not app:
        _clear_review_context(chat_id)
        send(chat_id, f"Application \\#{app_id} not found\\.")
        return

    if step == "awaiting_approve_comment":
        _execute_approve(chat_id, user, app, text)
    elif step == "awaiting_reject_reason":
        _execute_reject(chat_id, user, app, text)
    elif step == "awaiting_revise_note":
        _execute_revise(chat_id, user, app, text)
    elif step == "awaiting_edit_action":
        _execute_edit_action(chat_id, user, app, text)
    elif step == "awaiting_edit_approve_comment":
        _execute_edit_approve(chat_id, user, app, text)
    elif step == "awaiting_edit_reject_reason":
        _execute_edit_reject(chat_id, user, app, text)
    elif step == "awaiting_edit_revise_note":
        _execute_edit_revise(chat_id, user, app, text)


def _execute_approve(chat_id: str, user: dict, app: dict, text: str) -> None:
    comment = None if text.strip().lower() == "/skip" else text.strip()
    _clear_review_context(chat_id)

    role = user["role"]
    is_hq = _is_hq_app(app)
    acts_as_pc = _oc_acts_as_pc(user, app)

    if role == "pc":
        db.update_application(app["id"], status="pending_oc", reviewed_by=chat_id)
        db.log_action(app["id"], chat_id, "pc_approved", comment)
        notify(app["applicant_id"],
               f"✅ Application \\#{app['id']} approved by PC — now awaiting OC approval\\."
               + (f"\nComment: {esc(comment)}" if comment else ""))
        for oc in db.get_users_by_role("oc"):
            notify(oc["id"],
                   f"📋 *Application \\#{app['id']} forwarded by PC*\n"
                   f"{esc(app.get('applicant_name') or '?')} \\({esc(app.get('applicant_platoon') or '?')}\\)\n"
                   f"Use /view {app['id']} to review\\.")
        send(chat_id, f"✅ Application \\#{app['id']} forwarded to OC\\.\nUse /pending to review next application\\.")

    elif role in ("oc", "admin"):
        db.update_application(app["id"], status="oc_approved", reviewed_by=chat_id)
        if acts_as_pc and is_hq:
            db.log_action(app["id"], chat_id, "oc_approved_hq_direct", comment)
        elif acts_as_pc:
            db.log_action(app["id"], chat_id, "oc_approved_pc_fallback", comment)
        else:
            db.log_action(app["id"], chat_id, "oc_approved", comment)

        notify(app["applicant_id"],
               f"🎉 *Application \\#{app['id']} approved by OC\\!*\n"
               f"Please apply on OneNS and reply /applied when done\\."
               + (f"\nComment: {esc(comment)}" if comment else ""))

        # Notify PC
        pcs = db.get_pcs_for_platoon(app.get("applicant_platoon") or "")
        notify_many(pcs,
                    f"✅ *Application \\#{app['id']} approved by OC*\n"
                    f"{esc(app.get('applicant_name') or '?')} \\({esc(app.get('applicant_platoon') or '?')}\\)"
                    + (f"\nComment: {esc(comment)}" if comment else ""))

        if acts_as_pc and is_hq:
            note = " \\(HQ direct\\)"
        elif acts_as_pc:
            note = " \\(acting as PC\\)"
        else:
            note = ""
        send(chat_id, f"✅ Application \\#{app['id']} approved{note}\\. Applicant notified to apply on OneNS\\.\nUse /pending to review next application\\.")


def _execute_reject(chat_id: str, user: dict, app: dict, text: str) -> None:
    reason = text.strip()
    if not reason or reason.lower() == "/skip":
        send(chat_id, "A reason is required for rejection\\. Please provide one:")
        return

    _clear_review_context(chat_id)

    role = user["role"]
    action = "pc_rejected" if role == "pc" else "oc_rejected"

    db.update_application(app["id"], status="rejected", resolved_at=_NOW())
    db.log_action(app["id"], chat_id, action, reason)

    notify(app["applicant_id"],
           f"❌ *Application \\#{app['id']} rejected\\.*\n\n"
           f"Reason: {esc(reason)}\n\n"
           f"You may start a new application with /apply\\.")

    # If OC rejects, notify PC too
    if role in ("oc", "admin"):
        pcs = db.get_pcs_for_platoon(app.get("applicant_platoon") or "")
        notify_many(pcs,
                    f"❌ *Application \\#{app['id']} rejected by OC*\n"
                    f"{esc(app.get('applicant_name') or '?')}\nReason: {esc(reason)}")

    send(chat_id, f"Application \\#{app['id']} rejected\\. Applicant notified\\.\nUse /pending to review next application\\.")


def _execute_revise(chat_id: str, user: dict, app: dict, text: str) -> None:
    note = text.strip()
    if not note or note.lower() == "/skip":
        send(chat_id, "Please describe what needs to be revised:")
        return

    _clear_review_context(chat_id)

    role = user["role"]
    action = "pc_revision_requested" if role == "pc" else "oc_revision_requested"

    db.update_application(app["id"], status="revision_requested",
                          current_step="submitted", revision_note=note)
    db.log_action(app["id"], chat_id, action, note)

    docs = get_required_docs(app["type"])
    doc_list = "\n".join(f"{i+1}\\. {d['label']}" for i, d in enumerate(docs))
    notify(
        app["applicant_id"],
        f"⚠️ *Application \\#{app['id']} sent back for revision\\.*\n\n"
        f"Note: {esc(note)}\n\n"
        f"Use /edit\\_docs to update your documents\\.\n"
        f"Use /resubmit when ready\\."
    )

    # If OC revises, notify PC too
    if role in ("oc", "admin"):
        pcs = db.get_pcs_for_platoon(app.get("applicant_platoon") or "")
        notify_many(pcs,
                    f"⚠️ *Application \\#{app['id']} sent back for revision by OC*\n"
                    f"{esc(app.get('applicant_name') or '?')}\nNote: {esc(note)}")

    send(chat_id, f"Application \\#{app['id']} sent back for revision\\. Applicant notified\\.\nUse /pending to review next application\\.")


# ── Decision Editing ──────────────────────────────────────────────────────

def _edit_decision(chat_id: str, user: dict, args: list[str]) -> None:
    app = _get_viewing_app(user)
    if not app and args:
        app_id = _parse_id(args)
        if app_id:
            app = db.get_application_full(app_id)

    if not app:
        send(chat_id, "Usage: /edit\\_decision <id\\> or use /view <id\\> first\\.")
        return

    if not _can_edit_decision(user, app):
        role = user["role"]
        if role == "pc":
            send(chat_id, "❌ You can no longer edit — OC has already reviewed this application\\.")
        else:
            send(chat_id, "❌ You can no longer edit — applicant has already applied on OneNS\\.")
        return

    # Show current decision
    role = user["role"]
    if role == "pc":
        action_log = db.get_last_action(app["id"], "pc_approved")
    else:
        action_log = db.get_last_action(app["id"], "oc_approved")

    current_comment = action_log.get("note") if action_log else None

    db.update_user(chat_id, viewing_app_id=app["id"], viewing_change_id=None, review_step="awaiting_edit_action")
    comment_line = f"Comment: {esc(current_comment)}" if current_comment else "Comment: —"
    send(chat_id,
         f"*Application \\#{app['id']} — Your current decision:*\n"
         f"✅ Approved\n"
         f"{comment_line}\n\n"
         f"What would you like to change?\n"
         f"/approve — keep approved \\(edit comment\\)\n"
         f"/reject — change to rejected\n"
         f"/revise — change to revision requested\n"
         f"/cancel — keep current decision")


def _execute_edit_action(chat_id: str, user: dict, app: dict, text: str) -> None:
    t = text.lower().strip()
    if t == "/approve":
        db.update_user(chat_id, review_step="awaiting_edit_approve_comment")
        send(chat_id, "Enter new comment \\(or /skip for no comment\\):")
    elif t == "/reject":
        db.update_user(chat_id, review_step="awaiting_edit_reject_reason")
        send(chat_id, "Please provide a reason for rejection:")
    elif t == "/revise":
        db.update_user(chat_id, review_step="awaiting_edit_revise_note")
        send(chat_id, "What needs to be revised?")
    elif t == "/cancel":
        _clear_review_context(chat_id)
        send(chat_id, "Decision unchanged\\.")
    else:
        send(chat_id, "Please reply with /approve, /reject, /revise, or /cancel\\.")


def _execute_edit_approve(chat_id: str, user: dict, app: dict, text: str) -> None:
    """Update the comment on an existing approval."""
    comment = None if text.strip().lower() == "/skip" else text.strip()
    _clear_review_context(chat_id)

    role = user["role"]
    action = "pc_approved_edited" if role == "pc" else "oc_approved_edited"
    db.log_action(app["id"], chat_id, action, comment)

    # Notify parties of comment change
    notify(app["applicant_id"],
           f"ℹ️ *Application \\#{app['id']}* — {role.upper()} updated their approval comment\\."
           + (f"\nNew comment: {esc(comment)}" if comment else ""))

    if role == "pc":
        for oc in db.get_users_by_role("oc"):
            notify(oc["id"], f"ℹ️ PC updated approval comment on \\#{app['id']}\\."
                   + (f"\nComment: {esc(comment)}" if comment else ""))
    else:
        pcs = db.get_pcs_for_platoon(app.get("applicant_platoon") or "")
        notify_many(pcs, f"ℹ️ OC updated approval comment on \\#{app['id']}\\."
                    + (f"\nComment: {esc(comment)}" if comment else ""))

    send(chat_id, f"✅ Approval comment updated for \\#{app['id']}\\.")


def _execute_edit_reject(chat_id: str, user: dict, app: dict, text: str) -> None:
    """Change an approval to a rejection."""
    reason = text.strip()
    if not reason or reason.lower() == "/skip":
        send(chat_id, "A reason is required\\. Please provide one:")
        return

    _clear_review_context(chat_id)

    role = user["role"]
    old_status = app["status"]

    db.update_application(app["id"], status="rejected", resolved_at=_NOW())
    db.log_action(app["id"], chat_id, f"{role}_decision_changed", f"Changed from approved to rejected. Reason: {reason}")

    notify(app["applicant_id"],
           f"❌ *Application \\#{app['id']}* — {role.upper()} has changed their decision to *rejected*\\.\n\n"
           f"Reason: {esc(reason)}\n\n"
           f"You may start a new application with /apply\\.")

    if role == "pc":
        for oc in db.get_users_by_role("oc"):
            notify(oc["id"],
                   f"⚠️ *PC changed decision on \\#{app['id']}* from Approved → Rejected\\.\n"
                   f"Reason: {esc(reason)}")
    else:
        pcs = db.get_pcs_for_platoon(app.get("applicant_platoon") or "")
        notify_many(pcs,
                    f"⚠️ *OC changed decision on \\#{app['id']}* from Approved → Rejected\\.\n"
                    f"Reason: {esc(reason)}")

    send(chat_id, f"Decision changed to rejected for \\#{app['id']}\\. All parties notified\\.")


def _execute_edit_revise(chat_id: str, user: dict, app: dict, text: str) -> None:
    """Change an approval to a revision request."""
    note = text.strip()
    if not note or note.lower() == "/skip":
        send(chat_id, "Please describe what needs to be revised:")
        return

    _clear_review_context(chat_id)

    role = user["role"]

    db.update_application(app["id"], status="revision_requested",
                          current_step="submitted", revision_note=note)
    db.log_action(app["id"], chat_id, f"{role}_decision_changed",
                  f"Changed from approved to revision_requested. Note: {note}")

    notify(
        app["applicant_id"],
        f"⚠️ *Application \\#{app['id']}* — {role.upper()} has changed their decision\\.\n"
        f"Your application needs revision\\.\n\n"
        f"Note: {esc(note)}\n\n"
        f"Use /edit\\_docs to update your documents\\.\n"
        f"Use /resubmit when ready\\."
    )

    if role == "pc":
        for oc in db.get_users_by_role("oc"):
            notify(oc["id"],
                   f"⚠️ *PC changed decision on \\#{app['id']}* from Approved → Revision Requested\\.\n"
                   f"Note: {esc(note)}")
    else:
        pcs = db.get_pcs_for_platoon(app.get("applicant_platoon") or "")
        notify_many(pcs,
                    f"⚠️ *OC changed decision on \\#{app['id']}* from Approved → Revision Requested\\.\n"
                    f"Note: {esc(note)}")

    send(chat_id, f"Decision changed to revision requested for \\#{app['id']}\\. All parties notified\\.")


# ── CO Status (OC only) ──────────────────────────────────────────────────

def _co_status(chat_id: str, user: dict, args: list[str]) -> None:
    app_id = _parse_id(args)
    co_decision = args[1] if len(args) > 1 else None
    if not app_id or co_decision not in ("approved", "rejected"):
        send(chat_id, "Usage: /co\\_status <id\\> approved\\|rejected")
        return

    app = db.get_application_full(app_id)
    if not app:
        send(chat_id, f"Application \\#{app_id} not found\\.")
        return

    if app["status"] not in ("pending_co", "co_rejected"):
        send(chat_id, f"Application \\#{app_id} is not awaiting CO decision\\.")
        return

    if co_decision == "approved":
        db.update_application(app_id, status="approved", resolved_at=_NOW())
        db.log_action(app_id, chat_id, "co_approved_by_oc")

        # Notify user and PC
        notify(app["applicant_id"],
               f"🎉 *Application \\#{app_id} — CO APPROVED\\!*\nYour deferment application is complete\\.")
        pcs = db.get_pcs_for_platoon(app.get("applicant_platoon") or "")
        notify_many(pcs,
                    f"🎉 *Application \\#{app_id} — CO APPROVED*\n{esc(app.get('applicant_name') or '?')}")
        send(chat_id, f"✅ Application \\#{app_id} marked as CO approved\\.")

    elif co_decision == "rejected":
        db.update_application(app_id, status="co_rejected", current_step="co_rejection_reason")
        db.log_action(app_id, chat_id, "co_rejected_by_oc")

        notify(app["applicant_id"],
               f"❌ *Application \\#{app_id} — CO Rejected\\.*\n"
               f"Please provide the rejection reason from OneNS\\.")
        pcs = db.get_pcs_for_platoon(app.get("applicant_platoon") or "")
        notify_many(pcs,
                    f"❌ *Application \\#{app_id} — CO Rejected*\n{esc(app.get('applicant_name') or '?')}")
        send(chat_id, f"Application \\#{app_id} marked as CO rejected\\. Applicant asked for reason\\.")


# ── Manual Override (OC) ──────────────────────────────────────────────────

def _setstatus(chat_id: str, user: dict, args: list[str]) -> None:
    app_id = _parse_id(args)
    status = args[1] if len(args) > 1 else None
    if not app_id or status not in ("approved", "rejected"):
        send(chat_id, "Usage: /setstatus <id\\> approved\\|rejected")
        return

    app = db.get_application(app_id)
    if not app:
        send(chat_id, f"Application \\#{app_id} not found\\.")
        return

    db.update_application(app_id, status=status, resolved_at=_NOW())
    db.log_action(app_id, chat_id, f"oc_set_{status}")
    msg = f"🎉 *Application \\#{app_id} APPROVED\\!*" if status == "approved" else f"❌ *Application \\#{app_id} has been rejected\\.*"
    notify(app["applicant_id"], msg)
    send(chat_id, f"Application \\#{app_id} marked as {status}\\.")
