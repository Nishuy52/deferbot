# Testing Commands — NS Deferment Bot

All tests run from your single admin Telegram account using three simulation commands:

- **`/simulate <chat_id> | <message>`** — send a text message as any user (one-shot)
- **`/skipdocs <chat_id>`** — auto-fill all required docs with dummy data (skips upload)
- **`/simulatemode <chat_id>`** — persistent mode: all your messages (including file uploads) are processed as that user. `/simulatemode off` to exit.

**Format:** `← expected` = expected bot response (verify this). Application IDs are sequential — adjust if your DB already has apps.

---

## Phase 0: Setup

```
/createuser user1 | CPL Tan Wei Ming | 1 PLT | user
/createuser user2 | CPL Ahmad Bin Ali | 2 PLT | user
/createuser user3 | CPL Lee Jun Wei | HQ | user
/createuser pc1 | 3SG Lim Kah Hock | 1 PLT | pc
/createuser pc2 | 3SG Razali Bin Osman | 2 PLT | pc
/createuser oc1 | LTA Chen Zhi Hao | HQ | oc
/createuser admin2 | CPT Ng Wei Liang | HQ | admin
```

---

## Test 1: Full Happy Path — Internship (Credit-Bearing)

**Tests:** Apply → PC approve → OC approve → OneNS → CO approve

```
/simulate user1 | /apply
  ← Select deferment type (1-6)
/simulate user1 | 2
  ← Internship (Credit-Bearing). Have you completed your IPPT?
/simulate user1 | yes
  ← Documents required: 1. Signed internship contract  2. Credit-bearing proof
/skipdocs user1
  ← All documents filled (dummy). Summary shown. Reply confirm.
/simulate user1 | confirm
  ← Application #1 submitted! Pending PC approval.

/simulate pc1 | /pending
  ← Shows Application #1
/simulate pc1 | /view 1
  ← Full application details
/simulate pc1 | /approve
  ← Any comments? Reply or /skip
/simulate pc1 | Looks good
  ← Application #1 forwarded to OC.

/simulate oc1 | /pending
  ← Shows Application #1 (pending OC)
/simulate oc1 | /view 1
/simulate oc1 | /approve
  ← Any comments?
/simulate oc1 | /skip
  ← Application #1 approved.

/simulate user1 | /applied
  ← Noted. Pending CO approval.
/simulate user1 | /co_approved
  ← Application approved!
/simulate user1 | /status
  ← Shows approved status
```

---

## Test 2: IPPT Gating

**Tests:** IPPT "no" → pending_ippt → PC not notified → /edit_ippt → PC notified

```
/simulate user2 | /apply
  ← Select type (1-6)
/simulate user2 | 1
  ← Have you completed IPPT?
/simulate user2 | no
  ← Documents required (with IPPT warning): 1. Acceptance letter  2. Visa
/skipdocs user2
/simulate user2 | confirm
  ← Submitted! IPPT not done — PC notified after you update.
/simulate user2 | /status
  ← Shows pending_ippt

/simulate pc2 | /pending
  ← (empty — IPPT gated, no apps visible)

/simulate user2 | /edit_ippt
  ← Have you completed IPPT?
/simulate user2 | yes
  ← IPPT updated. [→ pc2] New application notification

/simulate pc2 | /pending
  ← Shows user2's application

--- Cleanup ---
/simulate pc2 | /view 2
/simulate pc2 | /reject
  ← Provide reason:
/simulate pc2 | Test cleanup
  ← Rejected.
```

---

## Test 3: Revision Flow

**Tests:** PC revises → user edits docs → resubmits

```
/simulate user1 | /apply
  ← Select type (1-6)
/simulate user1 | 3
  ← IPPT?
/simulate user1 | yes
  ← Docs required: 1. Signed contract  2. Employer ICT letter
/skipdocs user1
/simulate user1 | confirm
  ← Submitted!

/simulate pc1 | /view 3
/simulate pc1 | /revise
  ← What needs to be revised?
/simulate pc1 | Reupload contract with clearer dates
  ← Sent back for revision.
  ← [→ user1] Revision requested. Note: Reupload contract with clearer dates

/simulate user1 | /status
  ← Shows revision_requested + note
/simulate user1 | /edit_docs
  ← Shows doc checklist. Send files, /clear <n>, or /done
/simulate user1 | /clear 1
  ← Cleared: Signed contract
/skipdocs user1
  ← Docs re-filled
/simulate user1 | /done
  ← Documents updated. Use /resubmit.
/simulate user1 | /resubmit
  ← Resubmitted! Pending PC.

--- Cleanup ---
/simulate pc1 | /view 3
/simulate pc1 | /reject
/simulate pc1 | Cleanup
  ← Rejected.
```

---

## Test 4: PC Rejection

**Tests:** PC rejects application outright

```
/simulate user1 | /apply
/simulate user1 | 4
/simulate user1 | yes
  ← Docs: 1. Enrolment proof  2. Academic calendar
/skipdocs user1
/simulate user1 | confirm
  ← Submitted!

/simulate pc1 | /view 4
/simulate pc1 | /reject
  ← Provide reason:
/simulate pc1 | Insufficient documentation
  ← Rejected.
  ← [→ user1] Rejected. Reason: Insufficient documentation

/simulate user1 | /status
  ← Shows rejected
```

---

## Test 5: OC Rejection

**Tests:** PC approves → OC rejects

```
/simulate user1 | /apply
/simulate user1 | 5
/simulate user1 | yes
  ← Docs: 1. Booking receipts
/skipdocs user1
/simulate user1 | confirm
  ← Submitted!

/simulate pc1 | /view 5
/simulate pc1 | /approve
/simulate pc1 | /skip
  ← Forwarded to OC.

/simulate oc1 | /view 5
/simulate oc1 | /reject
  ← Provide reason:
/simulate oc1 | Dates don't qualify
  ← Rejected.
  ← [→ user1] Rejected by OC. Reason: Dates don't qualify
```

---

## Test 6: CO Rejection + Resubmit

**Tests:** Full approval → OneNS → CO rejects → edit docs → resubmit to OC (skips PC)

```
/simulate user1 | /apply
/simulate user1 | 1
/simulate user1 | yes
/skipdocs user1
/simulate user1 | confirm

/simulate pc1 | /view 6
/simulate pc1 | /approve
/simulate pc1 | /skip

/simulate oc1 | /view 6
/simulate oc1 | /approve
/simulate oc1 | /skip
  ← Approved. [→ user1] Apply on OneNS

/simulate user1 | /applied
  ← Pending CO approval.
/simulate user1 | /co_rejected
  ← Provide rejection reason from OneNS:
/simulate user1 | CO says dates conflict with exercise
  ← Recorded. Use /edit_docs and /resubmit.

/simulate user1 | /edit_docs
/simulate user1 | /clear 1
/skipdocs user1
/simulate user1 | /done
/simulate user1 | /resubmit
  ← Resubmitted to OC (skips PC)

/simulate oc1 | /view 6
/simulate oc1 | /approve
/simulate oc1 | /skip

/simulate user1 | /applied
/simulate user1 | /co_approved
  ← Application approved!
```

---

## Test 7: Decision Editing

**Tests:** PC approves → edits to revise → user resubmits → re-approves → OC approves → OC edit blocked

```
/simulate user1 | /apply
/simulate user1 | 2
/simulate user1 | yes
/skipdocs user1
/simulate user1 | confirm

/simulate pc1 | /view 7
/simulate pc1 | /approve
/simulate pc1 | Good to go
  ← Forwarded to OC.

/simulate pc1 | /edit_decision
  ← Current decision: Approved. Change? /approve /reject /revise /cancel
/simulate pc1 | /revise
  ← What needs revision?
/simulate pc1 | Actually need updated contract
  ← Changed to revision. [→ user1] Revision notification

/simulate user1 | /edit_docs
/skipdocs user1
/simulate user1 | /done
/simulate user1 | /resubmit

/simulate pc1 | /view 7
/simulate pc1 | /approve
/simulate pc1 | /skip

/simulate oc1 | /view 7
/simulate oc1 | /approve
/simulate oc1 | /skip

/simulate oc1 | /edit_decision
  ← BLOCKED (applicant already notified of oc_approved)
```

---

## Test 8: Withdraw + Re-apply

```
/simulate user1 | /apply
/simulate user1 | 3
/simulate user1 | yes
/skipdocs user1
/simulate user1 | confirm
  ← Submitted!

/simulate user1 | /withdraw
  ← Application withdrawn.

/simulate user1 | /apply
  ← Select deferment type (1-6) — new application allowed

/simulate user1 | /withdraw
```

---

## Test 9: All 6 Deferment Types (Doc Prompts)

**Tests:** Each type prompts the correct documents

```
--- 9A: Exchange Programme (type 1) ---
/simulate user1 | /apply
/simulate user1 | 1
/simulate user1 | yes
  ← VERIFY: 1. Acceptance letter  2. Visa
/skipdocs user1
/simulate user1 | confirm
/simulate user1 | /withdraw

--- 9B: Internship Credit-Bearing (type 2) ---
/simulate user1 | /apply
/simulate user1 | 2
/simulate user1 | yes
  ← VERIFY: 1. Signed internship contract  2. Credit-bearing proof
/skipdocs user1
/simulate user1 | confirm
/simulate user1 | /withdraw

--- 9C: Internship Non-Credit-Bearing (type 3) ---
/simulate user1 | /apply
/simulate user1 | 3
/simulate user1 | yes
  ← VERIFY: 1. Signed contract  2. Employer ICT letter
/skipdocs user1
/simulate user1 | confirm
/simulate user1 | /withdraw

--- 9D: Off-Cycle School (type 4) ---
/simulate user1 | /apply
/simulate user1 | 4
/simulate user1 | yes
  ← VERIFY: 1. Enrolment proof  2. Academic calendar
/skipdocs user1
/simulate user1 | confirm
/simulate user1 | /withdraw

--- 9E: Overseas Vacation (type 5) ---
/simulate user1 | /apply
/simulate user1 | 5
/simulate user1 | yes
  ← VERIFY: 1. Booking receipts (ONLY 1 doc required)
/skipdocs user1
/simulate user1 | confirm
/simulate user1 | /withdraw

--- 9F: Other (type 6) ---
/simulate user1 | /apply
/simulate user1 | 6
  ← Briefly describe reason:
/simulate user1 | Family emergency overseas requiring extended leave
  ← IPPT?
/simulate user1 | yes
  ← VERIFY: 1. Supporting document  2. Explanation letter
/skipdocs user1
/simulate user1 | confirm
/simulate user1 | /withdraw
```

---

## Test 10: HQ Platoon (OC as PC — Skips PC Queue)

**Tests:** HQ applicant → goes directly to OC queue, no PC step

```
/simulate user3 | /apply
/simulate user3 | 1
/simulate user3 | yes
/skipdocs user3
/simulate user3 | confirm
  ← Submitted (should go directly to OC queue, no PC step)

/simulate oc1 | /pending
  ← Shows user3's HQ application
/simulate oc1 | /view <id>
/simulate oc1 | /approve
/simulate oc1 | /skip
  ← oc_approved directly (no PC step)
```

---

## Test 11: Admin Commands

```
--- setrole ---
/setrole user1 pc
  ← CPL Tan Wei Ming is now: pc
/simulate user1 | /help
  ← VERIFY: PC commands visible
/simulate user1 | /pending
  ← Works (PC command accepted)
/setrole user1 user
  ← CPL Tan Wei Ming is now: user

--- unregister + re-register ---
/unregister user2
  ← CPL Ahmad Bin Ali removed.
/simulate user2 | hi
  ← Welcome! What is your full name and rank?
/simulate user2 | CPL Ahmad Bin Ali
  ← What is your platoon?
/simulate user2 | 2 PLT
  ← Registered

--- bulk create ---
/createusers 5 | 1 PLT | user
  ← Created 5 test users

--- help per role ---
/simulate user1 | /help
  ← User commands only
/simulate pc1 | /help
  ← User + PC commands
/simulate oc1 | /help
  ← User + PC + OC commands
/help
  ← User + PC + OC + Admin commands
```

---

## Test 12: OC List/Filter + Manual Overrides

> Several applications should exist from prior tests.

```
/simulate oc1 | /list_active
  ← Shows non-terminal apps grouped by platoon
/simulate oc1 | /list_all
  ← Shows all apps including rejected/approved
/simulate oc1 | /list pending_oc
  ← Filtered to pending_oc only
/simulate oc1 | /list approved
  ← Shows only approved apps
/simulate oc1 | /list rejected
  ← Shows only rejected apps

--- manual CO status (pick an app in pending_co) ---
/simulate oc1 | /co_status <id> approved
  ← CO decision recorded

--- manual override (pick any non-terminal app) ---
/simulate oc1 | /setstatus <id> rejected
  ← Status overridden
```

---

## Test 13: Edge Cases

```
--- Duplicate apply (user1 has active app) ---
/simulate user1 | /apply
  ← BLOCKED: Already have an active application

--- /approve without /view ---
/simulate pc1 | /approve
  ← No application selected

--- /view nonexistent ---
/simulate pc1 | /view 99999
  ← Application not found

--- Wrong-state commands ---
/simulate user2 | /resubmit
  ← Blocked (not in revision_requested or co_rejected)
/simulate user2 | /applied
  ← Blocked (not in oc_approved)
/simulate user2 | /co_approved
  ← Blocked (not in pending_co)
/simulate user2 | /status
  ← No active application

--- Non-command text ---
/simulate user1 | hello
  ← Shows menu or handles gracefully

--- Permission checks ---
/simulate user1 | /setrole user2 pc
  ← Admin access required
/simulate user1 | /createuser test99 | Test | HQ
  ← Admin access required
/simulate user2 | /pending
  ← PC access required
/simulate user2 | /view 1
  ← PC access required
/simulate pc1 | /list approved
  ← OC access required
/simulate pc1 | /setstatus 1 rejected
  ← OC access required
```

---

## Test 14: Multi-Platoon Isolation

**Tests:** PC can only see their own platoon's applications

```
/simulate user1 | /apply
/simulate user1 | 2
/simulate user1 | yes
/skipdocs user1
/simulate user1 | confirm

/simulate user2 | /apply
/simulate user2 | 3
/simulate user2 | yes
/skipdocs user2
/simulate user2 | confirm

/simulate pc1 | /pending
  ← Shows ONLY user1's application (NOT user2's)
/simulate pc1 | /list_active
  ← Shows only 1 PLT applications

/simulate pc2 | /pending
  ← Shows ONLY user2's application (NOT user1's)
/simulate pc2 | /list_active
  ← Shows only 2 PLT applications

/simulate pc1 | /view <user1_app_id>
/simulate pc1 | /approve
/simulate pc1 | /skip

/simulate pc2 | /view <user2_app_id>
/simulate pc2 | /approve
/simulate pc2 | /skip

/simulate oc1 | /pending
  ← Shows BOTH applications from different platoons
/simulate oc1 | /list_active
  ← Shows all active apps grouped by platoon
```

---

## Test 15: Real File Upload via /simulatemode

**Tests:** `/simulatemode` with actual file uploads to verify doc storage

```
/simulate user1 | /apply
/simulate user1 | 2
/simulate user1 | yes
  ← Documents required: 1. Signed internship contract  2. Credit-bearing proof

--- Enter simulate mode to upload real files as user1 ---
/simulatemode user1
  ← Now simulating user1. All messages go as user1. /simulatemode off to exit.

[Send any image/PDF with caption: 1]
  ← Received: Signed internship contract
[Send any image/PDF with caption: 2]
  ← All documents received! Summary shown.

--- Test bad uploads while in simulatemode ---
[Send .mp4 file]
  ← Rejects unsupported format
[Send file with no caption]
  ← Asks for number caption
[Send file with caption "hello"]
  ← Asks for valid number caption

--- Exit simulate mode and confirm ---
/simulatemode off
  ← Simulation ended. Back to admin mode.

/simulate user1 | confirm
  ← Application submitted!

--- Cleanup ---
/simulate user1 | /withdraw
```

---

## Verification Checklist

After all tests, check Supabase:

1. **`audit_log`** — entries for: submitted, doc_uploaded, ippt_updated, pc_approved, oc_approved, pc_rejected, oc_rejected, pc_revision_requested, oc_revision_requested, withdrawn, onens_applied, co_approved, co_rejected, decision_edited
2. **`documents`** — storage paths match `{app_id}/{doc_type}_{file_id}.{ext}` (or `_dummy.pdf` for /skipdocs)
3. **Supabase Storage** — uploaded files from /simulatemode are retrievable
4. **`applications`** — no apps stuck in unexpected states
5. **`users`** — all test users have correct roles and platoons
