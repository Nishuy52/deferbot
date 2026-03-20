"""Admin commands for managing users and roles."""
from bot import db
from bot.telegram import send

VALID_ROLES = {"user", "pc", "oc", "admin"}
VALID_FLAGS: set[str] = set()  # No flags currently in use

# Commands that use pipe-separated args (raw text after the command)
_PIPE_CMDS = {"/createuser", "/createusers", "/simulate"}

# Simulate mode state: {admin_chat_id: {"target": target_id, "admin": admin_id}}
_simulate_sessions: dict[str, dict] = {}


def get_simulate_mode(chat_id: str) -> dict | None:
    """Return simulate session if this admin is in simulatemode."""
    return _simulate_sessions.get(chat_id)


def handle(chat_id: str, user: dict, cmd: str, args: list[str],
           raw_args: str = "") -> bool:
    dispatch = {
        "/setrole":      _setrole,
        "/setflag":      _setflag,
        "/removeflag":   _removeflag,
        "/unregister":   _unregister,
        "/createuser":   _createuser,
        "/createusers":  _createusers,
        "/simulate":     _simulate,
        "/simulatemode": _simulatemode,
        "/skipdocs":     _skipdocs,
    }
    fn = dispatch.get(cmd)
    if fn:
        if cmd in _PIPE_CMDS:
            fn(chat_id, raw_args)
        else:
            fn(chat_id, args)
        return True
    return False


def _setrole(chat_id: str, args: list[str]) -> None:
    if len(args) < 2:
        send(chat_id, "Usage: /setrole <chat\\_id\\> <role\\>\nRoles: user, pc, oc, admin")
        return
    target_id, role = args[0], args[1]
    if role not in VALID_ROLES:
        send(chat_id, f"Invalid role\\. Use: {', '.join(sorted(VALID_ROLES))}")
        return
    target = db.get_user(target_id)
    if not target:
        send(chat_id, f"User `{target_id}` not found\\. They must message the bot first\\.")
        return
    db.set_role(target_id, role)
    send(chat_id, f"✅ {target['name']} is now: *{role}*")


def _setflag(chat_id: str, args: list[str]) -> None:
    if len(args) < 2:
        send(chat_id, "Usage: /setflag <chat\\_id\\> <flag\\>\nFlags: submit\\_to\\_oc")
        return
    target_id, flag = args[0], args[1]
    if flag not in VALID_FLAGS:
        send(chat_id, f"Unknown flag: {flag}")
        return
    target = db.get_user(target_id)
    if not target:
        send(chat_id, f"User `{target_id}` not found\\.")
        return
    db.set_flag(target_id, flag, True)
    send(chat_id, f"✅ Flag `{flag}` set on {target['name']}\\.")


def _removeflag(chat_id: str, args: list[str]) -> None:
    if len(args) < 2:
        send(chat_id, "Usage: /removeflag <chat\\_id\\> <flag\\>")
        return
    target_id, flag = args[0], args[1]
    target = db.get_user(target_id)
    if not target:
        send(chat_id, f"User `{target_id}` not found\\.")
        return
    db.set_flag(target_id, flag, False)
    send(chat_id, f"✅ Flag `{flag}` removed from {target['name']}\\.")


def _unregister(chat_id: str, args: list[str]) -> None:
    if not args:
        send(chat_id, "Usage: /unregister <chat\\_id>")
        return
    target_id = args[0]
    target = db.get_user(target_id)
    if not target:
        send(chat_id, f"User `{target_id}` not found\\.")
        return
    db.delete_user(target_id)
    send(chat_id, f"✅ {target['name']} removed\\.")


def _createuser(chat_id: str, raw_args: str) -> None:
    """Create a single fully-registered user.
    Syntax: /createuser <chat_id> | <name> | <platoon> [| <role>]
    """
    parts = [p.strip() for p in raw_args.split("|")]
    if len(parts) < 3:
        send(chat_id,
             "Usage: /createuser <chat\\_id\\> \\| <name\\> \\| <platoon\\> \\[\\| <role\\>\\]")
        return

    target_id, name, platoon = parts[0], parts[1], parts[2].upper()
    role = parts[3] if len(parts) >= 4 else "user"

    if role not in VALID_ROLES:
        send(chat_id, f"Invalid role\\. Use: {', '.join(sorted(VALID_ROLES))}")
        return
    if db.get_user(target_id):
        send(chat_id, f"User `{target_id}` already exists\\.")
        return
    if not name:
        send(chat_id, "Name cannot be empty\\.")
        return

    db.create_user(target_id, name, platoon, role)
    send(chat_id, f"✅ Created *{name}* \\(`{target_id}`\\) — {platoon}, {role}")


def _createusers(chat_id: str, raw_args: str) -> None:
    """Bulk-create test users.
    Syntax: /createusers <count> | <platoon> [| <role>]
    """
    parts = [p.strip() for p in raw_args.split("|")]
    if len(parts) < 2:
        send(chat_id,
             "Usage: /createusers <count\\> \\| <platoon\\> \\[\\| <role\\>\\]")
        return

    try:
        count = int(parts[0])
    except ValueError:
        send(chat_id, "Count must be a number\\.")
        return

    if count < 1 or count > 50:
        send(chat_id, "Count must be between 1 and 50\\.")
        return

    platoon = parts[1].upper()
    role = parts[2] if len(parts) >= 3 else "user"

    if role not in VALID_ROLES:
        send(chat_id, f"Invalid role\\. Use: {', '.join(sorted(VALID_ROLES))}")
        return

    created = []
    n = 1
    while len(created) < count:
        tid = f"test_{n}"
        if not db.get_user(tid):
            db.create_user(tid, f"Test User {n}", platoon, role)
            created.append(tid)
        n += 1

    lines = "\n".join(f"• `{tid}` — Test User {tid.split('_')[1]}"
                      for tid in created)
    send(chat_id,
         f"✅ Created {len(created)} test users in *{platoon}* as *{role}*:\n{lines}")


def _simulate(chat_id: str, raw_args: str) -> None:
    """Send a text message as another user.
    Syntax: /simulate <chat_id> | <message>
    """
    parts = [p.strip() for p in raw_args.split("|", 1)]
    if len(parts) < 2:
        send(chat_id, "Usage: /simulate <chat\\_id\\> \\| <message\\>")
        return

    target_id, message = parts[0], parts[1]
    target = db.get_user(target_id)
    if not target:
        # Allow simulating unregistered users (for registration flow testing)
        pass

    from bot.handlers.message import _run_simulated
    _run_simulated(chat_id, target_id, message, None)


def _simulatemode(chat_id: str, args: list[str]) -> None:
    """Enter/exit persistent simulate mode.
    /simulatemode <chat_id> — enter mode
    /simulatemode off — exit mode
    """
    if not args:
        send(chat_id, "Usage: /simulatemode <chat\\_id\\> or /simulatemode off")
        return

    if args[0].lower() == "off":
        if chat_id in _simulate_sessions:
            del _simulate_sessions[chat_id]
            send(chat_id, "✅ Simulation ended\\. Back to admin mode\\.")
        else:
            send(chat_id, "No active simulation session\\.")
        return

    target_id = args[0]
    target = db.get_user(target_id)
    target_name = target["name"] if target else target_id
    _simulate_sessions[chat_id] = {"target": target_id, "admin": chat_id}
    from bot.telegram import esc
    send(chat_id,
         f"🔄 Now simulating *{esc(target_name)}* \\(`{esc(target_id)}`\\)\\.\n"
         f"All your messages \\(including file uploads\\) will be processed as this user\\.\n"
         f"Use /simulatemode off to exit\\.")


def _skipdocs(chat_id: str, args: list[str]) -> None:
    """Auto-fill all required documents with dummy data.
    Syntax: /skipdocs <chat_id>
    """
    if not args:
        send(chat_id, "Usage: /skipdocs <chat\\_id\\>")
        return

    target_id = args[0]
    target = db.get_user(target_id)
    if not target:
        send(chat_id, f"User `{target_id}` not found\\.")
        return

    app = db.get_active_application(target_id)
    if not app:
        send(chat_id, f"No active application for `{target_id}`\\.")
        return

    if app["current_step"] not in ("doc_collect", "edit_docs"):
        send(chat_id,
             f"Application is not in doc collection step \\(current: {app['current_step']}\\)\\.")
        return

    from bot.config.docs import get_required_docs, get_missing_docs
    uploaded_types = db.get_uploaded_doc_types(app["id"])
    missing = get_missing_docs(app["type"], uploaded_types)

    if not missing:
        send(chat_id, "All documents already uploaded\\.")
        return

    for doc in missing:
        dummy_path = f"{app['id']}/{doc['key']}_dummy.pdf"
        db.add_document(app["id"], doc["key"], dummy_path)
        db.log_action(app["id"], target_id, "doc_uploaded", f"{doc['key']} (dummy)")

    # Advance step to confirm if in doc_collect, stay in edit_docs otherwise
    if app["current_step"] == "doc_collect":
        db.update_application(app["id"], current_step="confirm")

    from bot.telegram import esc
    doc_names = ", ".join(esc(d["label"]) for d in missing)
    send(chat_id,
         f"✅ Filled dummy docs for `{esc(target_id)}`: {doc_names}\\.\n"
         f"Application step: *{esc(app['current_step'])}* → *confirm*")
