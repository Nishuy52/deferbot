"""Supabase database operations."""
import os
from functools import lru_cache
from supabase import create_client, Client

HQ_PLATOON = "HQ"  # OC acts as PC for this platoon

@lru_cache(maxsize=1)
def _client() -> Client:
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])


def _db() -> Client:
    return _client()


# ── Users ──────────────────────────────────────────────────────────────────

def get_user(chat_id: str) -> dict | None:
    r = _db().table("users").select("*").eq("id", chat_id).execute()
    return r.data[0] if r.data else None


def create_pending_user(chat_id: str) -> dict:
    item = {"id": chat_id, "name": "", "reg_step": "name"}
    _db().table("users").insert(item).execute()
    return item


def update_user(chat_id: str, **fields) -> None:
    _db().table("users").update(fields).eq("id", chat_id).execute()


def set_role(chat_id: str, role: str) -> None:
    update_user(chat_id, role=role)


def set_flag(chat_id: str, flag: str, value: bool) -> None:
    if flag == "submit_to_oc":
        update_user(chat_id, pc_can_submit_to_oc=value)
    else:
        raise ValueError(f"Unknown flag: {flag}")


def create_user(chat_id: str, name: str, platoon: str, role: str = "user") -> dict:
    """Create a fully-registered user (bypasses registration flow)."""
    item = {"id": chat_id, "name": name, "platoon": platoon, "role": role}
    r = _db().table("users").insert(item).execute()
    return r.data[0]


def delete_user(chat_id: str) -> None:
    _db().table("users").delete().eq("id", chat_id).execute()


def get_users_by_role(role: str) -> list[dict]:
    if role == "oc":
        # Admins are OCs with extra permissions — include them
        r = _db().table("users").select("*").in_("role", ["oc", "admin"]).execute()
    else:
        r = _db().table("users").select("*").eq("role", role).execute()
    return r.data


def get_pcs_for_platoon(platoon: str) -> list[dict]:
    r = _db().table("users").select("*").eq("role", "pc").eq("platoon", platoon).execute()
    return r.data


def platoon_has_pc(platoon: str) -> bool:
    """True if the platoon has at least one registered PC."""
    return bool(get_pcs_for_platoon(platoon))


def get_ocs_for_platoon(platoon: str) -> list[dict]:
    """OCs/admins belonging to the given platoon (fallback PC reviewers)."""
    r = (
        _db().table("users").select("*")
        .in_("role", ["oc", "admin"])
        .eq("platoon", platoon)
        .execute()
    )
    return r.data


def get_approvers_for_applicant(applicant: dict) -> tuple[list[dict], bool]:
    """Return (approvers, oc_acts_as_pc).

    oc_acts_as_pc is True when an OC reviews this app at the PC stage — either
    because the applicant is HQ (any OC), or (fallback) because the applicant's
    platoon has no registered PC, in which case that platoon's own OCs review it.
    """
    raw = applicant.get("platoon") or ""
    if raw.upper() == HQ_PLATOON:
        return get_users_by_role("oc"), True
    if not platoon_has_pc(raw):
        return get_ocs_for_platoon(raw), True
    return get_pcs_for_platoon(raw), False


# ── Platoon Change Requests ──────────────────────────────────────────────────

def create_platoon_change_request(user_id: str, from_platoon: str | None,
                                  to_platoon: str) -> dict:
    r = _db().table("platoon_change_requests").insert({
        "user_id": user_id,
        "from_platoon": from_platoon,
        "to_platoon": to_platoon,
    }).execute()
    return r.data[0]


def get_platoon_change_request(req_id: int) -> dict | None:
    """Get a change request with requester info from the view."""
    r = (
        _db().table("platoon_change_requests_full")
        .select("*").eq("id", req_id).execute()
    )
    return r.data[0] if r.data else None


def get_active_platoon_change_request(user_id: str) -> dict | None:
    """The user's existing pending request, if any (blocks duplicates)."""
    r = (
        _db().table("platoon_change_requests")
        .select("*")
        .eq("user_id", user_id)
        .eq("status", "pending")
        .order("id", desc=True)
        .limit(1)
        .execute()
    )
    return r.data[0] if r.data else None


def get_pending_changes_for_platoon(platoon: str) -> list[dict]:
    """Pending requests where the incoming (requested) platoon is `platoon` (for a PC)."""
    r = (
        _db().table("platoon_change_requests_full")
        .select("*")
        .eq("status", "pending")
        .eq("to_platoon", platoon)
        .order("id", desc=True)
        .execute()
    )
    return r.data


def get_all_pending_changes() -> list[dict]:
    """All pending requests (for OC/admin)."""
    r = (
        _db().table("platoon_change_requests_full")
        .select("*")
        .eq("status", "pending")
        .order("id", desc=True)
        .execute()
    )
    return r.data


def update_platoon_change_request(req_id: int, **fields) -> None:
    _db().table("platoon_change_requests").update(fields).eq("id", req_id).execute()


# ── Applications ───────────────────────────────────────────────────────────

TERMINAL = {"approved", "rejected"}


def get_active_application(applicant_id: str) -> dict | None:
    r = (
        _db().table("applications")
        .select("*")
        .eq("applicant_id", applicant_id)
        .not_.in_("status", list(TERMINAL))
        .order("id", desc=True)
        .limit(1)
        .execute()
    )
    return r.data[0] if r.data else None


def get_past_applications(applicant_id: str) -> list[dict]:
    r = (
        _db().table("applications")
        .select("id, status")
        .eq("applicant_id", applicant_id)
        .in_("status", list(TERMINAL))
        .order("id", desc=True)
        .execute()
    )
    return r.data


def create_application(applicant_id: str) -> dict:
    r = _db().table("applications").insert({"applicant_id": applicant_id}).execute()
    return r.data[0]


def get_application(app_id: int) -> dict | None:
    r = _db().table("applications").select("*").eq("id", app_id).execute()
    return r.data[0] if r.data else None


def get_application_full(app_id: int) -> dict | None:
    """Get application with applicant and reviewer info from the view."""
    r = _db().table("applications_full").select("*").eq("id", app_id).execute()
    return r.data[0] if r.data else None


def update_application(app_id: int, **fields) -> None:
    _db().table("applications").update(fields).eq("id", app_id).execute()


def get_pending_for_pc(platoon: str) -> list[dict]:
    """pending_pc applications belonging to the given platoon."""
    r = (
        _db().table("applications_full")
        .select("*")
        .eq("status", "pending_pc")
        .eq("applicant_platoon", platoon)
        .execute()
    )
    return r.data


def get_active_for_pc(platoon: str) -> list[dict]:
    """Non-terminal applications for a PC's platoon (for /list_active)."""
    r = (
        _db().table("applications_full")
        .select("*")
        .eq("applicant_platoon", platoon)
        .not_.in_("status", list(TERMINAL))
        .order("id", desc=True)
        .execute()
    )
    return r.data


def get_all_for_pc(platoon: str) -> list[dict]:
    """All applications for a PC's platoon (for /list_all)."""
    r = (
        _db().table("applications_full")
        .select("*")
        .eq("applicant_platoon", platoon)
        .order("id", desc=True)
        .execute()
    )
    return r.data


def get_pending_for_oc(oc_platoon: str | None = None) -> list[dict]:
    """pending_oc applications + pending_pc apps the OC handles as PC.

    The PC-stage apps are HQ apps (any OC) plus, when oc_platoon is given and that
    platoon has no registered PC, that platoon's own pending_pc apps (fallback).
    """
    oc = (
        _db().table("applications_full")
        .select("*")
        .eq("status", "pending_oc")
        .execute()
    ).data
    hq = (
        _db().table("applications_full")
        .select("*")
        .eq("status", "pending_pc")
        .eq("applicant_platoon", HQ_PLATOON)
        .execute()
    ).data
    fallback = []
    if oc_platoon and oc_platoon.upper() != HQ_PLATOON and not platoon_has_pc(oc_platoon):
        fallback = (
            _db().table("applications_full")
            .select("*")
            .eq("status", "pending_pc")
            .eq("applicant_platoon", oc_platoon)
            .execute()
        ).data
    return oc + hq + fallback


def get_active_for_oc() -> list[dict]:
    """Non-terminal applications across all platoons (for OC /list_active)."""
    r = (
        _db().table("applications_full")
        .select("*")
        .not_.in_("status", list(TERMINAL))
        .order("applicant_platoon")
        .order("id", desc=True)
        .execute()
    )
    return r.data


def get_all_applications(status: str | None = None) -> list[dict]:
    q = _db().table("applications_full").select("*")
    if status:
        q = q.eq("status", status)
    return q.order("applicant_platoon").order("id", desc=True).execute().data


# ── Documents ──────────────────────────────────────────────────────────────

def add_document(app_id: int, doc_type: str, storage_path: str,
                  file_id: str | None = None, mimetype: str | None = None) -> None:
    """Insert a document (multiple files per doc_type allowed)."""
    row = {
        "application_id": app_id,
        "doc_type": doc_type,
        "storage_path": storage_path,
    }
    if file_id:
        row["file_id"] = file_id
    if mimetype:
        row["mimetype"] = mimetype
    _db().table("documents").insert(row).execute()


def get_documents(app_id: int) -> list[dict]:
    r = _db().table("documents").select("*").eq("application_id", app_id).execute()
    return r.data


def get_uploaded_doc_types(app_id: int) -> list[str]:
    """Return unique doc types that have at least one file uploaded."""
    return list({d["doc_type"] for d in get_documents(app_id)})


def get_doc_counts(app_id: int) -> dict[str, int]:
    """Return {doc_type: count} for an application."""
    counts: dict[str, int] = {}
    for d in get_documents(app_id):
        counts[d["doc_type"]] = counts.get(d["doc_type"], 0) + 1
    return counts


def delete_docs_by_type(app_id: int, doc_type: str) -> None:
    """Remove all files for a specific doc_type in an application."""
    _db().table("documents").delete().eq("application_id", app_id).eq("doc_type", doc_type).execute()


# ── Audit Log ──────────────────────────────────────────────────────────────

def log_action(app_id: int | None, actor_id: str, action: str, note: str | None = None) -> None:
    _db().table("audit_log").insert({
        "application_id": app_id,
        "actor_id": actor_id,
        "action": action,
        "note": note,
    }).execute()


def get_last_action(app_id: int, action_prefix: str) -> dict | None:
    """Get the most recent audit log entry matching an action prefix (e.g. 'pc_approved')."""
    r = (
        _db().table("audit_log")
        .select("*")
        .eq("application_id", app_id)
        .like("action", f"{action_prefix}%")
        .order("id", desc=True)
        .limit(1)
        .execute()
    )
    return r.data[0] if r.data else None
