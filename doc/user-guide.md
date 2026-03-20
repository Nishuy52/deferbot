# User Guide — NS Deferment Bot

The NS Deferment Bot manages the end-to-end workflow for NS deferment applications within a unit. Soldiers submit applications via Telegram; platoon commanders (PC) and the officer commanding (OC) review and approve them; the CO decision is recorded after the soldier applies on OneNS.

**Roles:**
- **user** — Regular soldier. Submits and tracks applications.
- **pc** — Platoon commander. Reviews applications from their own platoon.
- **oc** — Officer commanding. Reviews all applications after PC; acts as PC for HQ soldiers.
- **admin** — Full access plus user management and testing commands.

---

## Diagram 1: Complete Application State Machine

```
                              ┌─────────┐
                              │  draft  │
                              └────┬────┘
                                   │ User confirms submission
                                   │
                      ┌────────────┴────────────┐
                      │                         │
                IPPT done                  IPPT not done
                      │                         │
                      ▼                         ▼
              ┌──────────────┐         ┌───────────────┐
              │  pending_pc  │         │ pending_ippt  │
              │              │         │               │
              │ PC notified  │         │ Visible in    │
              │ Appears in   │         │ /list_all but │
              │ /list_active │         │ NOT actionable│
              └──────┬───────┘         └───────┬───────┘
                     │                         │
                     │         User marks IPPT done
                     │         → notify PC
                     │                         │
                     │                         ▼
                     │                 ┌──────────────┐
                     │                 │  pending_pc  │
                     │                 └──────┬───────┘
                     │                        │
                     ├────────────────────────┘
                     │
            ┌────────┼────────────────┐
            │        │                │
       PC approves  PC rejects    PC revises
       (± comment)  (+ comment)   (+ comment)
            │        │                │
            ▼        ▼                ▼
     ┌───────────┐ ┌──────────┐ ┌───────────────────┐
     │pending_oc │ │ rejected │ │revision_requested │
     │           │ └──────────┘ │                   │
     │OC notified│              │User re-uploads    │
     └─────┬─────┘              │→ back to          │
           │                    │  pending_pc       │
           │                    └───────────────────┘
  ┌────────┼────────────────┐
  │        │                │
OC approves OC rejects   OC revises
(± comment) (+ comment)  (+ comment)
  │        │                │
  ▼        ▼                ▼
┌────────────┐ ┌────────┐ ┌───────────────────┐
│oc_approved │ │rejected│ │revision_requested │
│            │ └────────┘ │                   │
│"Apply on   │            │User re-uploads    │
│ OneNS"     │            │→ back to          │
└─────┬──────┘            │  pending_pc       │
      │                   └───────────────────┘
      │ User confirms
      │ OneNS applied
      ▼
┌───────────┐
│pending_co │
└─────┬─────┘
      │
 ┌────┴─────┐
 │          │
CO approves CO rejects
 │          │
 ▼          ▼
┌────────┐ ┌─────────────┐
│approved│ │ co_rejected │
│(FINAL) │ │             │
└────────┘ │User re-uploads│
           │docs → goes   │
           │straight to   │
           │pending_oc    │
           └──────────────┘
```

---

## Diagram 2: User Application Flow (Step by Step)

```
┌──────────────────────────────────────────────────────────────┐
│                   USER APPLICATION JOURNEY                    │
└──────────────────────────────────────────────────────────────┘

/apply
  │
  ▼
┌──────────────────────────────────┐
│ SELECT DEFERMENT TYPE            │
│                                  │
│ 1. Exchange Programme            │
│ 2. Internship (Credit-Bearing)   │
│ 3. Internship (Non-Credit)       │
│ 4. Off-Cycle School              │
│ 5. Overseas Vacation (Pre-Booked)│
│ 6. Other                         │
│                                  │
│ Reply with a number.             │
└──────────────┬───────────────────┘
               │
          ┌────┴────┐
          │         │
     Type 1-5    Type 6
          │         │
          │         ▼
          │    ┌─────────────────────┐
          │    │ Describe reason     │
          │    │ for deferment       │
          │    └──────────┬──────────┘
          │               │
          ├───────────────┘
          │
          ▼
┌──────────────────────────────┐
│ IPPT STATUS                  │
│                              │
│ Have you completed IPPT?     │
│ Reply yes or no.             │
│                              │
│ If no: ⚠️ "IPPT not done.   │
│ You can still proceed. Your  │
│ approver will only be        │
│ notified after you update    │
│ your IPPT status."           │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ UPLOAD DOCUMENTS             │
│                              │
│ Documents required:          │
│ (varies by deferment type)   │
│                              │
│ Send each file as a photo    │
│ or document. Include the     │
│ number (1, 2, 3...) as a    │
│ caption to tag the category. │
│                              │
│ Multiple files per category  │
│ are allowed.                 │
└──────────────┬───────────────┘
               │
               │ (user sends files with captions)
               │
               ▼
┌──────────────────────────────┐
│ UPDATED CHECKLIST            │
│                              │
│ 1. Acceptance letter  ✅ (2) │  ← file count shown
│ 2. Visa               ✅ (1) │
│                              │
│ Send the next document.      │
└──────────────┬───────────────┘
               │
               │ (all docs uploaded)
               │
               ▼
┌──────────────────────────────┐
│ REVIEW & CONFIRM             │
│                              │
│ Application #5 Summary       │
│ Type: Exchange Programme     │
│ IPPT: ✅ Done                │
│ Documents:                   │
│  • Acceptance letter (2)     │
│  • Visa (1)                  │
│                              │
│ Reply confirm to submit      │
│ /edit_docs  — change docs    │
│ /edit_ippt  — update IPPT    │
│ /withdraw   — cancel         │
└──────────────┬───────────────┘
               │ confirm
               ▼
┌──────────────────────────────┐
│ SUBMITTED                    │
│                              │
│ ✅ Application #5 submitted! │
│ Pending PC approval.         │
│                              │
│ (or if IPPT not done:)       │
│ ⚠️ Application submitted.   │
│ Your PC will be notified     │
│ once you update IPPT status. │
│ Use /edit_ippt to update.    │
└──────────────────────────────┘


POST-SUBMIT COMMANDS (before PC review):
  /edit_docs  — re-upload or add documents
  /edit_ippt  — mark IPPT as done/undone
  /status     — check current status
  /withdraw   — cancel application

After PC/OC reviews: edits are LOCKED.
```

---

## Diagram 3: PC Review Experience

```
┌──────────────────────────────────────────────────────────────┐
│                    PC REVIEW FLOW                             │
└──────────────────────────────────────────────────────────────┘

/list_active → Shows non-terminal apps from PC's platoon
               (ONLY shows pending_pc apps as "Review")
┌─────────────────────────────────────────┐
│ Active Applications (1 PLT)             │
│                                         │
│ Name             │ Status      │ Action │
│ ──────────────── │ ─────────── │ ────── │
│ CPL Tan Wei Ming │ Pending PC  │ Review │
│ PTE Lee Jun Hao  │ Pending OC  │ —      │
│ CPL Ahmad Ismail │ Pending CO  │ —      │
│ REC Wong Kai     │ Awaiting    │ —      │
│                  │  IPPT       │        │
└─────────────────────────────────────────┘

/list_all → Shows ALL apps from PC's platoon (including terminal)
┌─────────────────────────────────────────┐
│ All Applications (1 PLT)                │
│                                         │
│ Name             │ Status      │ Action │
│ ──────────────── │ ─────────── │ ────── │
│ CPL Tan Wei Ming │ Pending PC  │ Review │
│ PTE Lee Jun Hao  │ Approved    │ —      │
│ CPL Ahmad Ismail │ Rejected    │ —      │
└─────────────────────────────────────────┘

/view <id> → Enters review context
┌─────────────────────────────────────────┐
│ Application #5                          │
│ Applicant: CPL Tan Wei Ming (1 PLT)     │
│ Type: Exchange Programme                │
│ IPPT: ✅ Done                           │
│ Status: Pending PC                      │
│                                         │
│ Documents (3 files):                    │
│  • Acceptance letter (2 files)          │
│  • Visa (1 file)                        │
│                                         │
│ Reply:                                  │
│  /approve — approve (will ask for       │
│             optional comment)           │
│  /reject  — reject (will ask for        │
│             required reason)            │
│  /revise  — send back for revision      │
│             (will ask for note)         │
└─────────────────────────────────────────┘

  /approve →
  ┌───────────────────────────────┐
  │ Any comments? (optional)      │
  │ Reply with comment or /skip   │
  └───────────────────────────────┘
  → status = pending_oc
  → notify applicant + OC
  → comment visible to User + OC

  /reject →
  ┌───────────────────────────────┐
  │ Please provide a reason:      │
  └───────────────────────────────┘
  → status = rejected
  → notify applicant
  → comment visible to User + OC

  /revise →
  ┌───────────────────────────────┐
  │ What needs to be revised?     │
  └───────────────────────────────┘
  → status = revision_requested
  → notify applicant
```

---

## Diagram 4: OC Review Experience

```
┌──────────────────────────────────────────────────────────────┐
│                    OC REVIEW FLOW                             │
└──────────────────────────────────────────────────────────────┘

/list_active → Sorted by platoon, shows non-terminal apps
               (pending_oc shows "Review", others show "—")
               (HQ pending_pc shows "Review (as PC)")
┌─────────────────────────────────────────────────────┐
│ Active Applications                                 │
│                                                     │
│ ── 1 PLT ────────────────────────────────────────   │
│ Name             │ Status        │ Action           │
│ CPL Tan Wei Ming │ Pending OC    │ Review           │
│ PTE Lee Jun Hao  │ Pending CO    │ —                │
│                                                     │
│ ── 2 PLT ────────────────────────────────────────   │
│ CPL Muthu S.     │ Pending OC    │ Review           │
│                                                     │
│ ── HQ ───────────────────────────────────────────   │
│ SGT Lim Ah Kow  │ Pending PC    │ Review (as PC)   │
└─────────────────────────────────────────────────────┘

OC notified ONLY when PC approves (app enters pending_oc).

/view <id> →
┌─────────────────────────────────────────┐
│ Application #5                          │
│ Applicant: CPL Tan Wei Ming (1 PLT)     │
│ Type: Exchange Programme                │
│ IPPT: ✅ Done                           │
│ Status: Pending OC                      │
│                                         │
│ Reviewed by: 2LT Tan (PC, 1 PLT)       │ ← shows which PC
│ PC comment: "Documents look complete"   │ ← PC's comment if any
│                                         │
│ Documents (3 files):                    │
│  • Acceptance letter (2 files)          │
│  • Visa (1 file)                        │
│                                         │
│ Reply:                                  │
│  /approve — approve (→ prompts OneNS)   │
│  /reject  — reject (will ask reason)    │
│  /revise  — send back for revision      │
└─────────────────────────────────────────┘

OC approve/reject/revise works same as PC.
Comments visible to User + PC.
```

---

## Diagram 5: PC/OC Decision Editing

```
┌──────────────────────────────────────────────────────────────┐
│              EDITING PAST DECISIONS (PC & OC)                 │
└──────────────────────────────────────────────────────────────┘

RULE: A reviewer can edit their decision + comment ONLY if
      the next level has NOT yet acted on it.

  PC edit window:
  ┌─────────────────────────────────────────────────┐
  │ PC approved app #5 → status = pending_oc        │
  │                                                 │
  │ CAN EDIT if OC has NOT yet reviewed:            │
  │   /view 5 → sees own decision                   │
  │   /edit_decision → prompted for new action:     │
  │     /approve (change comment)                   │
  │     /reject  (change to reject + reason)        │
  │     /revise  (change to revision + note)        │
  │                                                 │
  │ LOCKED once OC approves/rejects/revises #5      │
  │ "You can no longer edit — OC has already        │
  │  reviewed this application."                    │
  └─────────────────────────────────────────────────┘

  OC edit window:
  ┌─────────────────────────────────────────────────┐
  │ OC approved app #5 → status = oc_approved       │
  │                                                 │
  │ CAN EDIT if user has NOT applied on OneNS:      │
  │   /view 5 → sees own decision                   │
  │   /edit_decision → prompted for new action:     │
  │     /approve (change comment)                   │
  │     /reject  (change to reject + reason)        │
  │     /revise  (change to revision + note)        │
  │                                                 │
  │ LOCKED once user confirms OneNS application     │
  │ (status = pending_co or later)                  │
  │ "You can no longer edit — applicant has already │
  │  applied on OneNS."                             │
  └─────────────────────────────────────────────────┘


FLOW FROM /list_all:

  PC/OC: /list_all
  ┌─────────────────────────────────────────────────┐
  │ All Applications                                │
  │                                                 │
  │ Name             │ Status      │ Action         │
  │ ──────────────── │ ─────────── │ ────────────── │
  │ CPL Tan Wei Ming │ Pending OC  │ Edit Decision  │ ← PC can edit
  │ PTE Lee Jun Hao  │ OC Approved │ —              │ ← PC locked (OC acted)
  │ CPL Ahmad Ismail │ Pending CO  │ —              │ ← OC locked (OneNS)
  │ REC Wong Kai     │ Pending OC  │ Edit Decision  │ ← OC can edit
  └─────────────────────────────────────────────────┘

  /view <id> then /edit_decision:

  ┌───────────────────────────────────────────┐
  │ Application #5 — Your current decision:   │
  │ ✅ Approved                                │
  │ Comment: "Documents look complete"         │
  │                                            │
  │ What would you like to change?             │
  │ /approve — keep approved (edit comment)    │
  │ /reject  — change to rejected              │
  │ /revise  — change to revision requested    │
  │ /cancel  — keep current decision           │
  └───────────────────────────────────────────┘

  On change:
  → Update status accordingly
  → Update audit log
  → Notify affected parties of the change
  → e.g. "PC has changed decision on #5 from
    Approved → Rejected. Reason: ..."
```

---

## Diagram 6: OneNS & CO Status Tracking

```
┌──────────────────────────────────────────────────────────────┐
│              POST-OC APPROVAL: OneNS + CO TRACKING            │
└──────────────────────────────────────────────────────────────┘

  OC approves
       │
       ▼
  status = "oc_approved"
  Bot → User:
  ┌────────────────────────────────────────┐
  │ 🎉 Application #5 approved by OC!     │
  │                                        │
  │ Next step: Apply on the OneNS portal.  │
  │ Reply /applied when you have submitted │
  │ your application on OneNS.             │
  └────────────────────────────────────────┘
       │
       │ User: /applied
       ▼
  status = "pending_co"
  → notify PC + OC: "User has applied on OneNS, awaiting CO decision"
       │
       ▼
  ┌────────────────────────────────────────┐
  │ Waiting for CO decision                │
  │                                        │
  │ User commands:                         │
  │   /co_approved  — CO approved          │
  │   /co_rejected  — CO rejected          │
  │   → notifies PC + OC                  │
  │                                        │
  │ OC commands:                           │
  │   /co_status <id> approved             │
  │   /co_status <id> rejected             │
  │   → notifies User + PC                │
  └────────────────────────────────────────┘
       │
  ┌────┴──────────┐
  │               │
  ▼               ▼
approved      co_rejected
(FINAL ✅)         │
                   ▼
  ┌────────────────────────────────────────┐
  │ Bot → User:                            │
  │ "CO has rejected your application.     │
  │ Please provide the rejection reason    │
  │ from OneNS."                           │
  │                                        │
  │ User sends reason → stored             │
  │ → notify PC + OC with reason           │
  │                                        │
  │ User can re-upload docs:               │
  │   /edit_docs → update documents        │
  │   /resubmit → goes to pending_oc       │
  │   (skips PC since PC already approved) │
  └────────────────────────────────────────┘
```

---

## Diagram 7: Notification Matrix

```
┌─────────────────────────────────┬──────┬──────┬──────┐
│ Event                           │ User │  PC  │  OC  │
├─────────────────────────────────┼──────┼──────┼──────┤
│ App submitted (IPPT done)       │      │  ✅  │      │
│ App submitted (IPPT NOT done)   │      │      │      │
│ User updates IPPT → done        │      │  ✅  │      │
│ User edits docs (pre-review)    │      │      │      │
│ PC approves (± comment)         │  ✅  │      │  ✅  │
│ PC rejects (+ comment)          │  ✅  │      │      │
│ PC revises (+ note)             │  ✅  │      │      │
│ OC approves (± comment)         │  ✅  │  ✅  │      │
│ OC rejects (+ comment)          │  ✅  │  ✅  │      │
│ OC revises (+ note)             │  ✅  │  ✅  │      │
│ User confirms OneNS applied     │      │  ✅  │  ✅  │
│ User updates CO status          │      │  ✅  │  ✅  │
│ OC updates CO status            │  ✅  │  ✅  │      │
│ CO rejected reason provided     │      │  ✅  │  ✅  │
│ User resubmits after CO reject  │      │      │  ✅  │
│ PC edits decision (pre-OC)      │  ✅  │      │  ✅  │
│ OC edits decision (pre-OneNS)   │  ✅  │  ✅  │      │
└─────────────────────────────────┴──────┴──────┴──────┘
```

---

## Diagram 8: Document Upload & Edit Flow

```
┌──────────────────────────────────────────────────────────────┐
│                 DOCUMENT UPLOAD MECHANICS                      │
└──────────────────────────────────────────────────────────────┘

DURING APPLICATION (doc_collect step):

  Bot shows numbered checklist:
  ┌────────────────────────────────────┐
  │ Documents required:                │
  │ 1. Acceptance letter          ☐   │
  │ 2. Visa                       ☐   │
  │                                    │
  │ Send each file with the number    │
  │ as a caption (e.g. send a photo   │
  │ with caption "1").                 │
  │ Multiple files per category OK.   │
  └────────────────────────────────────┘

  User sends photo with caption "1"
       │
       ▼
  ┌────────────────────────────────────┐
  │ ✅ Received: Acceptance letter     │
  │                                    │
  │ 1. Acceptance letter       ✅ (1) │
  │ 2. Visa                       ☐   │
  └────────────────────────────────────┘

  User sends another photo with caption "1"
       │
       ▼
  ┌────────────────────────────────────┐
  │ ✅ Received: Acceptance letter     │
  │                                    │
  │ 1. Acceptance letter       ✅ (2) │  ← count increments
  │ 2. Visa                       ☐   │
  └────────────────────────────────────┘

  User sends file WITHOUT caption:
       │
       ▼
  ┌────────────────────────────────────┐
  │ Please include the document number │
  │ as a caption when sending files.   │
  │                                    │
  │ 1. Acceptance letter       ✅ (2) │
  │ 2. Visa                       ☐   │
  └────────────────────────────────────┘


POST-SUBMIT EDIT (/edit_docs):

  Only available when status in:
    pending_ippt, pending_pc
  (NOT after PC/OC has reviewed)

  ┌────────────────────────────────────┐
  │ Current documents:                 │
  │ 1. Acceptance letter       ✅ (2) │
  │ 2. Visa                    ✅ (1) │
  │                                    │
  │ Send new files with caption to     │
  │ add/replace.                       │
  │ /clear <number> to remove all      │
  │ files for a category.              │
  │ /done when finished editing.       │
  └────────────────────────────────────┘
```

---

## Application Statuses

| Status | Description | Editable by User? |
|--------|-------------|-------------------|
| `draft` | In progress, not submitted | Yes (wizard) |
| `pending_ippt` | Submitted but IPPT not done; PC can see but not act | Yes (IPPT + docs) |
| `pending_pc` | Awaiting PC review | Yes (IPPT + docs) |
| `pending_oc` | Awaiting OC review | No |
| `revision_requested` | Sent back by PC or OC | Yes (docs) |
| `oc_approved` | OC approved; user must apply on OneNS | No |
| `pending_co` | Applied on OneNS; awaiting CO decision | No |
| `approved` | CO approved (final) | No |
| `co_rejected` | CO rejected; user can re-upload + resubmit to OC | Yes (docs) |
| `rejected` | Rejected by PC or OC (final) | No |

---

## Commands Reference

**All users:**
- `/apply` — Start a deferment application
- `/status` — Check your current application
- `/withdraw` — Cancel your active application
- `/edit_docs` — Edit uploaded documents (before review)
- `/edit_ippt` — Update IPPT completion status (before review)
- `/applied` — Confirm you've applied on OneNS (after OC approval)
- `/co_approved` — Report CO approved your application
- `/co_rejected` — Report CO rejected your application
- `/resubmit` — Resubmit after revision request or CO rejection
- `/help` — Command list

**PC (platoon commanders):**
- `/pending` — Applications awaiting your approval
- `/list_active` — Active (non-terminal) applications from your platoon
- `/list_all` — All applications from your platoon (including terminal)
- `/view <id>` — View full application + documents (enters review context)
- `/approve` — Approve (after /view; prompts for optional comment)
- `/reject` — Reject (after /view; prompts for required reason)
- `/revise` — Send back for revision (after /view; prompts for note)
- `/edit_decision` — Edit your past decision (only if OC hasn't acted)

**OC only:**
- `/list_active` — All active applications, sorted by platoon
- `/list_all` — All applications, sorted by platoon
- `/list [status]` — All applications (optional status filter)
- `/co_status <id> approved|rejected` — Update CO decision for an application
- `/setstatus <id> approved|rejected` — Manually set final outcome
- `/pending` — HQ pending_pc + all pending_oc
- `/view <id>` — View application (shows which PC reviewed)
- `/approve` — Approve (after /view; for HQ: direct; for others: OC approval)
- `/reject` — Reject (after /view)
- `/revise` — Send back for revision (after /view)
- `/edit_decision` — Edit your past decision (only if user hasn't applied on OneNS)

**Admin:**
- `/setrole <chat_id> user|pc|oc|admin`
- `/unregister <chat_id>`
- `/createuser <chat_id> | <name> | <platoon> [| <role>]` — Create a fully-registered user
- `/createusers <count> | <platoon> [| <role>]` — Bulk-create test users (auto-generated IDs & names)
- `/simulate <chat_id> | <message>` — Send a message as another user (for testing)
- `/simulatemode <chat_id>` — Enter persistent simulate mode (all messages routed as that user)
- `/simulatemode off` — Exit simulate mode
- `/skipdocs <chat_id>` — Auto-fill all required documents with dummy data (for testing)
