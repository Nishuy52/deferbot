# NS Deferment Bot

A Telegram bot that manages NS deferment applications end-to-end: soldiers submit applications, platoon commanders (PC) review them, the OC gives final unit approval, and the CO decision is recorded after the soldier applies on OneNS. Built on a fully free-tier stack.

**Stack:** Python · Flask · Vercel (serverless) · Supabase (PostgreSQL + Storage) · Telegram Bot API

---

## Documentation

| Guide | Description |
|---|---|
| [Installation Guide](doc/installation.md) | Step-by-step setup from scratch |
| [User Guide](doc/user-guide.md) | Flow diagrams, state machine, notification matrix |
| [Testing Commands](doc/testing.md) | Full test suite using admin simulation commands |

---

## Quick Start

1. Create a Telegram bot via @BotFather and note the token.
2. Create a Supabase project, run `supabase/init.sql`, and create a private `documents` storage bucket.
3. Deploy to Vercel and set `TELEGRAM_TOKEN`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`.
4. Register the webhook: `curl "https://api.telegram.org/bot<TOKEN>/setWebhook?url=<VERCEL_URL>/webhook"`

See [doc/installation.md](doc/installation.md) for the full walkthrough.

---

## Commands

**All users**
```
/start        — Main menu
/apply        — Start a deferment application
/status       — Check current application status
/withdraw     — Cancel active application
/edit_docs    — Edit uploaded documents (before review)
/edit_ippt    — Update IPPT completion status (before review)
/applied      — Confirm you've applied on OneNS (after OC approval)
/co_approved  — Report CO approved your application
/co_rejected  — Report CO rejected your application
/resubmit     — Resubmit after revision request or CO rejection
/help         — Command list
```

**PC (platoon commanders)**
```
/pending              — Applications awaiting your approval
/list_active          — Active (non-terminal) applications from your platoon
/list_all             — All applications from your platoon
/view <id>            — View full application + documents (enters review context)
/approve              — Approve (after /view; prompts for optional comment)
/reject               — Reject (after /view; prompts for required reason)
/revise               — Send back for revision (after /view; prompts for note)
/edit_decision        — Edit your past decision (only if OC hasn't acted)
```

**OC only**
```
/list_active          — All active applications, sorted by platoon
/list_all             — All applications, sorted by platoon
/list [status]        — All applications (optional status filter)
/pending              — HQ pending_pc + all pending_oc
/view <id>            — View application (shows which PC reviewed)
/approve              — Approve (after /view)
/reject               — Reject (after /view)
/revise               — Send back for revision (after /view)
/edit_decision        — Edit your past decision (only if user hasn't applied on OneNS)
/co_status <id> approved|rejected  — Update CO decision
/setstatus <id> approved|rejected  — Manually set final outcome
```

**Admin**
```
/setrole <chat_id> user|pc|oc|admin
/unregister <chat_id>
/createuser <chat_id> | <name> | <platoon> [| <role>]
/createusers <count> | <platoon> [| <role>]
/simulate <chat_id> | <message>
/simulatemode <chat_id>
/simulatemode off
/skipdocs <chat_id>
```

---

## Application Statuses

| Status | Description |
|---|---|
| `draft` | Application in progress, not yet submitted |
| `pending_ippt` | Submitted but IPPT not done; PC can see but not act |
| `pending_pc` | Awaiting PC review |
| `pending_oc` | Awaiting OC review |
| `revision_requested` | Sent back for document revision |
| `oc_approved` | OC approved; user must apply on OneNS |
| `pending_co` | Applied on OneNS; awaiting CO decision |
| `approved` | CO approved (final) |
| `co_rejected` | CO rejected; user can re-upload + resubmit to OC |
| `rejected` | Rejected by PC or OC (final) |

---

## Cost

| Service | Free tier |
|---|---|
| Vercel (Hobby) | Unlimited deployments, 100 GB bandwidth/month |
| Supabase (Free) | 500 MB DB, 1 GB storage, 50k API calls/day |
| Telegram Bot API | Completely free |

At unit scale (~100 users, occasional applications): **$0/month**.
