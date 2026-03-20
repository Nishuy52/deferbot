# Installation Guide

This guide walks through setting up the NS Deferment Bot from scratch. Estimated time: 20–30 minutes.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Telegram account | To create the bot via BotFather |
| [Supabase](https://supabase.com) account | Free tier is sufficient |
| [Vercel](https://vercel.com) account | Free Hobby tier is sufficient |
| Node.js (any recent version) | Only needed to install the Vercel CLI |
| Git | To clone the repository |

---

## Step 1 — Create the Telegram bot

1. Open Telegram and search for **@BotFather**.
2. Send `/newbot` and follow the prompts (choose a name and username).
3. Copy the **token** BotFather gives you — it looks like `123456789:ABC-DEF1234ghIkl-zyx57W2v1u123ew11`.

---

## Step 2 — Set up Supabase

1. Go to [supabase.com](https://supabase.com) → **New project**. Pick a region close to your users.
2. Once the project is ready, go to **Settings → API** and note:
   - **Project URL** (e.g. `https://xxxx.supabase.co`)
   - **service_role** key (under "Project API keys" — not the anon key)
3. **Run the schema** — go to **SQL Editor** → paste the contents of `supabase/init.sql` → click **Run**.
4. **Create storage bucket** — go to **Storage** → **New bucket** → name it `documents` → set it to **Private** → save.

---

## Step 3 — Clone the repo and deploy to Vercel

```bash
git clone <your-repo-url>
cd deferment_bot

npm install -g vercel   # install Vercel CLI (one-time)
vercel                  # follow prompts to link/create project
```

When asked about framework, select **Other**. Vercel will detect `vercel.json` and configure the serverless Flask handler automatically.

---

## Step 4 — Set environment variables

In the **Vercel dashboard → your project → Settings → Environment Variables**, add:

| Variable | Value |
|---|---|
| `TELEGRAM_TOKEN` | Token from BotFather (Step 1) |
| `SUPABASE_URL` | Project URL from Supabase (Step 2) |
| `SUPABASE_SERVICE_KEY` | service_role key from Supabase (Step 2) |

After adding variables, redeploy:

```bash
vercel --prod
```

Copy your deployment URL (e.g. `https://deferment-bot.vercel.app`).

---

## Step 5 — Register the webhook with Telegram

Replace `<TOKEN>` and `<VERCEL_URL>` with your values:

```bash
curl "https://api.telegram.org/bot<TOKEN>/setWebhook?url=<VERCEL_URL>/webhook"
```

You should get back: `{"ok":true,"result":true}`

The webhook only needs to be registered once. It persists across redeployments.

---

## Step 6 — Configure platoons

Edit `bot/config/platoons.yaml` to list your unit's platoons:

```yaml
platoons:
  - 1 PLT
  - 2 PLT
  - 3 PLT
  - HQ
```

The special platoon name `HQ` is reserved — HQ soldiers' applications skip the PC queue and go directly to the OC. All other platoon names are free-form.

After editing, redeploy:

```bash
vercel --prod
```

---

## Step 7 — First-time admin setup

1. **Find your Telegram chat ID** — message your bot `/start`. The bot will show your chat ID in the registration confirmation message.
2. **Promote yourself to admin** — since no admin exists yet, you need to set your role directly in Supabase:

   In the Supabase **SQL Editor**, run:
   ```sql
   UPDATE users SET role = 'admin' WHERE id = '<your_chat_id>';
   ```

3. **Promote platoon commanders** — once you are admin, use the bot:
   ```
   /setrole <chat_id> pc     — platoon commander
   /setrole <chat_id> oc     — officer commanding
   /setrole <chat_id> admin  — additional admin
   ```

   PCs can only see and act on applications from their own platoon. Assign each PC to the correct platoon during registration.

---

## Step 8 — Verify the setup

Send `/start` to your bot. You should be prompted to register (name and platoon). After registering, send `/help` to see the available commands.

---

## Updating after code changes

```bash
vercel --prod
```

No need to re-register the webhook after redeployment.

---

## Environment variables reference

| Variable | Where to find it | Example |
|---|---|---|
| `TELEGRAM_TOKEN` | BotFather → `/newbot` → copy token | `123456:ABC-DEF...` |
| `SUPABASE_URL` | Supabase → Settings → API → Project URL | `https://xxxx.supabase.co` |
| `SUPABASE_SERVICE_KEY` | Supabase → Settings → API → service_role key | `eyJhbGci...` |

---

## Troubleshooting

**Bot doesn't respond**
- Check the webhook is registered: `curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"`
- Check Vercel function logs: Vercel dashboard → your project → **Deployments** → latest → **Functions**

**Database errors**
- Confirm `supabase/init.sql` was run successfully (no red errors in SQL Editor)
- Confirm `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` match your project (not another one)

**Storage errors**
- Confirm the `documents` bucket exists and is set to **Private**
