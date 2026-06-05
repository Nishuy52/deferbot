# Configuration Guide

Everything a new unit normally needs to change lives in **two YAML files**. No
Python changes are required to adopt the bot for your own unit:

| File | Controls |
|---|---|
| [`bot/config/platoons.yaml`](../bot/config/platoons.yaml) | The platoon list shown during registration |
| [`bot/config/deferment_docs.yaml`](../bot/config/deferment_docs.yaml) | The deferment types and the documents required for each |

After editing either file, redeploy with `vercel --prod` (changes take effect on
the next deployment). When testing locally, just restart `flask`.

---

## 1. Platoons (`platoons.yaml`)

This is the menu soldiers pick from when they register. Edit it to match your
unit's sub-units:

```yaml
# Platoon list — edit here to update the registration menu.
platoons:
  - SCT
  - SIG
  - PNR
  - MTR
  - HQ
```

Notes:

- **Names are free-form.** Use whatever your unit calls its platoons/sections.
- **`HQ` is special.** Soldiers registered under `HQ` skip the PC queue — their
  applications go straight to the OC, who reviews them directly. Keep an `HQ`
  entry if you want a headquarters group with no platoon commander. (The name is
  matched case-insensitively; the constant is defined as `HQ_PLATOON` in
  [`bot/db.py`](../bot/db.py) if you ever need to rename it.)
- **PC-less platoons fall back to the OC automatically.** For any non-HQ platoon
  with no registered PC, that platoon's OC acts as the PC until you register one
  — no config needed. See the "PC-less platoon fallback" section in
  [CLAUDE.md](../CLAUDE.md) / the [User Guide](user-guide.md).

The order in the file is the order shown in the menu, and a soldier registers by
replying with the number.

---

## 2. Deferment types & required documents (`deferment_docs.yaml`)

This file defines both the deferment **types** shown in the `/apply` menu and the
**documents** required for each. The structure is:

```yaml
<type_key>:                      # internal id — lowercase, no spaces
  label: "Exchange Programme"    # what the soldier sees in the menu
  docs:
    - key: acceptance_letter     # internal id for this document
      label: "Acceptance letter / signed contract ..."   # instructions shown to the soldier
    - key: visa
      label: "Visa or Visa Application (submit whichever is available)"
```

### Adding a new deferment type

Append a new top-level block. For example, to add a "Medical Appointment" type:

```yaml
medical:
  label: "Medical Appointment (Overseas)"
  docs:
    - key: appointment_letter
      label: "Letter from the clinic/hospital stating the appointment date"
    - key: referral
      label: "Local doctor's referral or memo"
```

It will automatically appear as the next number in the `/apply` menu — the menu
is generated from this file (`format_type_menu` in
[`bot/config/docs.py`](../bot/config/docs.py)), so there is nothing else to wire up.

### Editing the documents for an existing type

Add, remove, or reword entries under a type's `docs:` list. Each `label` is free
text shown verbatim to the soldier as the upload instruction — make it as
specific as you like (the existing entries include guidance like "must show
start and end dates").

### Rules and gotchas

- **`key` values must be unique within a type** and should stay stable. They are
  used as storage filename prefixes (`{app_id}/{doc_type}_{file_id}.{ext}`), so
  renaming a `key` only affects new uploads — existing apps keep their old keys.
- **`label` is the only field soldiers see.** `key` is internal.
- **Soldiers upload by number.** Documents are tagged by replying with the
  position number (1, 2, 3…) matching the order in this file, so order matters.
- **At least one document per type** is expected. A type with an empty `docs:`
  list will skip the upload step.
- **The `other` type** is a catch-all — it prompts the soldier for a free-text
  reason before the document step. This behaviour is keyed off the type, so keep
  an `other` entry if you want that free-text path.
- **YAML is whitespace-sensitive.** Use 2-space indentation and quote any label
  containing a colon (`:`) or other punctuation, as the existing entries do.

---

## 3. What is *not* in config (NS-specific by design)

The bot is purpose-built for the NS deferment workflow, so the following are part
of the application logic rather than configuration. A typical NS unit will not
need to change them, but they are listed here so you know the boundary:

| Concept | Where it lives | Notes |
|---|---|---|
| Role hierarchy (user → PC → OC → CO) | `bot/handlers/approval.py`, `bot/db.py` | The PC → OC → CO review chain is hardcoded. |
| IPPT / NSFit gating | `bot/handlers/application.py` | "Have you completed IPPT?" step and the `pending_ippt` hold. |
| OneNS portal step | `bot/handlers/approval.py`, `application.py` | The `/applied` → `pending_co` → CO-decision flow. |
| Status names & transitions | `bot/handlers/approval.py`, `bot/diagram.py` | See the state machine in the [User Guide](user-guide.md). |

If you need to repurpose the bot for a non-NS workflow (different roles or
terminology), these are the files to edit — but that is a code change, not a
configuration change.

---

## 4. Validating your changes

Both YAML files are parsed at startup, so a syntax error will surface
immediately. After editing, run a quick parse check before deploying:

```bash
python -c "import bot.config.platoons, bot.config.docs; print('config OK')"
```

If that prints `config OK`, both files loaded cleanly. Then redeploy
(`vercel --prod`) or restart your local `flask` process and run `/apply` to see
your menu.
