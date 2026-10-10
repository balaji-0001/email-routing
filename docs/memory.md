# Project Memory

**Last updated:** 2026-10-08

The running record of where the project stands, what was decided and why, and what tends to go wrong. Read it before starting work. Update it when a decision is made or something surprising is learned (see the end of this file). For rules see [rules.md](rules.md); for the plan see [tasks.md](tasks.md).

---

## 1. Where things stand

- **Product:** a shared team inbox for Gmail, Microsoft 365 and IMAP/SMTP mailboxes with collaboration, automation and AI. Full requirements in [prd.md](prd.md).
- **Built and working:**
  - Accounts (sign up, sign in, sign out, remember me, change password, reset by email)
  - Workspaces (create, settings, workspace switcher in top dropdown, invitations flow with token URL, member roles management, member removal, last owner protection)
  - Five workspace roles: `owner`, `admin`, `manager`, `agent`, `viewer` with API permission enforcement
  - Real email accounts connect via IMAP/SMTP, Gmail (App Passwords) and Outlook with live server credential verification and AES encrypted storage
  - Gmail by Google sign-in (OAuth 2.0 + Gmail API): connect, encrypted tokens, automatic refresh, sync by Gmail change history, send, reconnect, disconnect with revoke. **Built and tested against a stand-in for Google; not yet used with a real Gmail mailbox,** because the Google settings are not in `.env`. Until they are, the Gmail screen says so.
  - Real email sync engine fetching messages, folders, and MIME parsing
  - Unified inbox across all connected accounts with views (`inbox`, `sent`, `starred`, `archive`, `trash`, `drafts`) and batch actions
  - Conversation thread view with message details, star, archive, delete, and inline reply
  - Outbound email compose & sending via real SMTP with thread linking and audit logs
- **Stack against the proposal:** React, FastAPI and MySQL are in the code.
- **Verification:** 71 automated backend tests and a 39-point browser check of the mail screen on the test stack; pass against real MySQL (`email_management_test`), strict TypeScript typecheck passes, and production Vite build passes cleanly.
- **Nothing is committed.** Every change sits in the working tree.

## 2. How to run it

```bash
pnpm install    # once
pnpm setup      # once: Python environment, local MySQL, tables
pnpm dev        # MySQL if needed, migrations, API on 5000, web app on 5173
```

`pnpm test` runs the backend tests, `pnpm typecheck` and `pnpm build` check the web app. Details in the [README](../README.md).

## 3. Decisions

| Date | Decision | Why |
|------|----------|-----|
| 2026-10-07 | Remove everything Replit-specific; the project must run locally with no Replit dependency | Owner's request. The project had been generated on Replit. |
| 2026-10-07 | Backend is Python + FastAPI on MySQL; the imported Node/Express and PostgreSQL scaffold was deleted | The proposal specifies it. The owner chose this over keeping the scaffold when asked. |
| 2026-10-07 | Repo layout is `frontend/` and `backend/` | Follows from the stack decision; shown to the owner as a folder tree before doing it. |
| 2026-10-07 | No sample data anywhere; unbuilt screens show honest empty states | Owner chose "real empty states now" over keeping sample content until each feature is built. |
| 2026-10-07 | Sign-in uses server-side sessions in an HttpOnly cookie, not JWT | Sign-out and "sign out everywhere" must really end access. |
| 2026-10-07 | Layered backend: routes, services, repositories, models; services commit | The brief asked for "FastAPI → Services → Repositories → MySQL". |
| 2026-10-07 | SQLAlchemy is used synchronously | The same code has to run inside Celery workers later. |
| 2026-10-07 | The glass design is used everywhere: frosted panels over a soft coloured backdrop in the app, the full-strength backdrop on the sign-in screens | Built from a reference image the owner supplied. A plain white version of the app was tried the same day ("remove green and all those colours, keep simple white bg") and the owner then asked for "my glassy design back". Treat this as settled; do not flatten it. |
| 2026-10-07 | Type and controls are deliberately large (body about 14px, nothing under 12px) | The owner asked twice for bigger, more readable text. |
| 2026-10-07 | Social sign-in buttons and the Terms/Privacy line were removed from the sign-in screens | Neither exists; a button that does nothing breaks the no-fake rule. |
| 2026-10-07 | Local MySQL is a dedicated server on port 3308 with its data in `./local-mysql` | Keeps this project's data apart from other projects on the machine. |
| 2026-10-07 | Mailbox credentials encrypted with AES-GCM / Fernet | Prevent plain-text credentials in the database while allowing IMAP/SMTP worker decryption. |
| 2026-10-07 | Live IMAP/SMTP verification on connect | Catch incorrect host/port/passwords before storing the mailbox. |
| 2026-10-07 | 7-day token-based workspace invitations with role assignment | Allows invite link sharing and instant role binding upon sign-in/acceptance. |

## 4. What has been verified

- Backend: 43 automated tests pass against real MySQL, with the schema built from migrations (2026-10-07).
- Strict TypeScript typechecking (`pnpm typecheck`): 0 errors.
- Production web bundle build (`pnpm build`): succeeds with clean gzip chunk outputs.
- Whole flow in a real browser: 36 checks covering sign-up to sign-out, all screens free of sample wording, no sideways scrolling at three widths (2026-10-07, with the glass design).

## 5. Open items

Waiting on the owner (the full list with what each one blocks is in [tasks.md](tasks.md)):

- Commit the work.
- Answers needed before Phase 1: import window and freshness, email statuses, Redis on Windows, attachment storage, push or polling.
- Google and Microsoft developer credentials for connecting mailboxes.
- SMTP details so that password reset can send.
- "Organization" (the proposal's word) or "workspace" (the word in the code and screens): keep or rename.
- How the ON/OFF settings at the four levels combine when they disagree.
- Product name: "Northstar" is a working name.

Loose ends in the code:

- `artifacts/mockup-sandbox` is a leftover preview tool from the import. Nothing uses it. The AI agent's attempt to delete it was blocked, so it is still on disk.
- `frontend/src/index.css` still contains styles for the removed sample screens (mail rows, rule cards, the compose editor). Reuse them when those screens are built for real.
- `frontend/src/components/ui/` holds ready-made components that the app mostly does not use.

## 6. Things that will trip you up

- **Google limits each Gmail mailbox's requests per minute.** Importing faster than about 150 messages a minute returned "Quota exceeded ... Units per minute per user". The import paces itself (`IMPORT_PAGE_PAUSE` in `services/email_sync.py`) and stands back for 75 seconds when Google says so. Do not raise the pace without measuring.
- **Editing backend files while the app is importing can take the whole app down:** the automatic reload exits, and `pnpm dev` then stops the web app too. Stop the app, edit, test, start again.

- **The editor can roll back an agent's edits.** On 2026-10-07 the project was restored to an earlier checkpoint twice while an AI agent was working. Files the agent had written with its edit tools were reverted or deleted; changes made by scripts (the stylesheet) were not, which left the stylesheet and the components out of step for a while. After any interruption, check what is actually on disk before continuing, and ask the owner whether the rollback was intended before redoing the work.
- **The development database belongs to the owner.** `email_management` holds their real account. Tests and browser checks use `email_management_test`; a second stack for browser checks runs with `PORT=5001`, `WEB_PORT=5174`, `APP_URL=http://localhost:5174` and the test `DATABASE_URL`.
- **MySQL does not start after a reboot.** `pnpm dev` or `pnpm db:start` starts it. Its programs come from the folder named by `MYSQL_HOME` in `.env`, which on this machine points into another project's folder; if that folder moves, update the path.
- **Windows.** No `export` or `sh -c` in scripts; the dev tasks are plain Node in `scripts/tasks.mjs` for that reason. Start servers as their own processes or they die with the command that launched them.
- **A leftover hidden `cmd` window can hold `dev.log` open** after the servers are stopped, and the next start then fails silently. Stop every process from the previous run before starting again.
- **Newer Chrome returns a promise from `window.scrollTo`.** Returning it from a React effect crashes the page; wrap the call in braces.
- **Tailwind already defines keyframes named `ping`, `pulse`, `spin` and `bounce`.** Custom keyframes are prefixed `ns-` to avoid colliding with them.
- **The app's backdrop and its stylesheet go together.** `shell.tsx` mounts `<Aurora soft />` and the "glass surfaces" block in `index.css` makes the surfaces translucent. Change one without the other and the app turns either flat or unreadable.
- **In `index.css` the responsive blocks must stay last.** They once sat before the base rules and did nothing, so the mobile layout never applied.
- **Browser automation in a background tab is throttled to about two frames a second,** which makes animations look stuck. Use a separate headless browser for checks that depend on motion.
- **Validated email addresses must have a real-looking domain.** Addresses ending in `.test` or `.example` are rejected; tests use `@example.com`.
- **Google's review for mailbox access can take a long time** and may require an outside security assessment. Check the current requirements before promising a date for Gmail.

## 7. Timeline

**2026-10-10: audit and security pass**
- Independent security review of the backend, then fixes, each with a regression test in `backend/tests/test_security.py` (31 tests). No leak between workspaces was found; the problems were inside a workspace.
- Fixed: mail threaded by subject substring with no sender check (IMAP); replies threaded across mailboxes (a restricted mailbox's mail readable through an open one); "connect mailbox" usable to probe the server's own network (hosts are resolved and private addresses refused, only mail ports, encryption required, fixed error sentences, 10 tries per 10 minutes); an admin could make owners and remove the owner; managers could aim rules at mailboxes they cannot open; sending into another mailbox's conversation; an email that was sent but could not be saved was reported as failed (now `SENT_NOT_RECORDED`, never resent); duplicate stored emails under concurrent syncs (migration `0014`, unique per mailbox); overlong headers dropped the email; raw provider and SQL error text shown to users; "waiting" rules stalling behind non-matching mail; "Analyse now" ignoring the per-mailbox AI switch; invitations usable by anyone holding the link and more than once; mailbox grants surviving removal from the workspace; @mentions copying notes to people without access; nulls stored by PATCH; unknown batch actions accepted.
- Added: security headers on every answer (HSTS and CSP in production), refusal of cross-site changes by `Sec-Fetch-Site` as well as `Origin`, a 30 MB request cap, length limits on request fields, login limits per address and per place, per-person limits on sync and AI calls, and a start-up check: production refuses to start without `ENCRYPTION_KEY`, an https `APP_URL` and a real database user. Any `APP_ENV` that is not development/dev/local/test counts as production.
- Cleaned: 61 unused frontend files (the unused component kit, old hooks, the three pre-Outlook mail pages), 43 unused packages, two Tailwind plugins nothing used, stale "not available yet" texts for features that exist. CSS 250 KB -> 172 KB; the chart library now loads only with the Analytics page (main script 982 KB -> 578 KB). Two vulnerable build-time packages resolved. `tsconfig` now fails on unused code; `backend/ruff.toml` added.
- Not fixed, known: sign-up reveals whether an address is registered; rate limits live in one process's memory; `GET /contacts` and message search scan whole tables; IMAP sync re-downloads its latest 30 messages each minute; expired sessions and tokens are never purged; client IP behind a proxy depends on how the proxy is configured.
- 184 backend tests. Snapshot of the source before the audit: `local-mysql/backups/source-before-audit-2026-10-10.tar.gz`.

**2026-10-09**
- AI triage, draft-only (migration `0010`): tables `ai_settings`, `ai_account_settings`, `ai_analyses` (one per email; also the work queue), `ai_replies` (drafts awaiting approval). Code in `backend/app/ai/` (`base.py` provider interface, `gemini.py`, `triage.py` prompt, answer schema and safety checks), `services/ai_triage.py`, `api/ai.py`; screens in `frontend/src/pages/ai.tsx` (`/ai*`, Settings > AI controls, and the AI summary box in the reading pane).
- Needs `GEMINI_API_KEY` in `.env` (optional `AI_MODEL`, default `gemini-3.5-flash-lite`). Off until an owner or admin switches it on; emergency stop halts all analysis. New mail is queued after a sync and worked by a loop in `main.py`; automated senders (noreply and the like) are skipped without calling the AI.
- Nothing is sent by the AI. A draft goes out only through Approve & send, by someone who may send from that mailbox, for the exact text they saw (fingerprint check), once (claimed atomically), to the original sender, in the original thread, and not if someone already replied. Automatic Low/Medium sending is NOT built; the switch is shown disabled.
- Tested only against a stand-in for Gemini (`tests/test_ai_triage.py`, 14 tests; browser check `scratchpad/ai-e2e.cjs` with `run_test_api_ai.py`). Not yet run against the real Gemini API in this project.
- Also added: suggested rules panel and "Run on mail you already have" on the rules page (`POST /automation/run-recent`).
- Rule engine built (migration `0009`): tables `rules`, `rule_runs`, `automation_settings`, and `conversations.priority`. Code in `backend/app/automation/` (`conditions.py`, `actions.py`, `engine.py`), `services/automation.py`, `api/automation.py`; screens in `frontend/src/pages/automation.tsx` (`/automation`, `/automation/assignment`, `/automation/labels-priority`, Settings > Automation, and the Automations panel on the Overview).
- How it behaves: the only trigger is "a new email arrived". Rules run after a sync stores mail a mailbox has not seen before; a mailbox's first sync and the import of old mail never trigger rules. Conditions: mailbox, sender, recipient, subject, message text, attachments. Actions: add label, set priority, set status, assign, share out in turn, flag, archive, notify. Actions only change this app's own records; none sends email or calls a provider.
- One run per rule per email (unique key on `rule_runs`). A failed run keeps none of its changes, is recorded, and is retried twice more (after 1 and 5 minutes) by a loop in `main.py`. Automation is off for a workspace until an owner or admin switches it on; each mailbox and each rule has its own switch.
- Owners, admins and managers edit rules; everyone can see them. Run history is limited to mailboxes the reader can open.
- Still on the in-process loops: no Redis or Celery. Not built: AI, scheduled actions and follow-up reminders, webhooks.
- 101 backend tests (13 for automation). Browser check on the test stack: `scratchpad/auto-e2e.cjs` with `run_test_api_auto.py`, which must be restarted between runs.

**2026-10-08**
- Added Gmail by Google sign-in on top of the IMAP/SMTP work: migration `0003`, `providers/gmail.py`, `services/google_oauth.py`, three endpoints under `/email-accounts`, and the Gmail connect and reconnect screens.
- Fixed: a mailbox whose provider could not be built stayed stuck on "Syncing". Gmail conversations now follow Gmail's own threads instead of matching by subject.
- Added the optional `ENCRYPTION_KEY` setting; secrets saved before it was set stay readable.
- Gmail verified live: two real mailboxes connected by Google sign-in.
- Mail screen rebuilt in the style of Outlook (`frontend/src/pages/mail.tsx`, `frontend/src/mail.css`): command bar, folder pane, message list, reading pane. Added reply all, forward, attachments (sent as files, downloaded on demand from the mailbox), search across sender, subject and body, filters, labels (`/labels`), and Open / Pending / Closed status (migration `0005`). Email HTML is shown in a frame that cannot run scripts, with remote pictures off until asked. The earlier `pages/inbox.tsx`, `conversation.tsx` and `compose.tsx` are no longer routed to and can be deleted.
- Full inbox import for Gmail (migration `0004`): after connecting, older mail comes in 50 messages at a time in the background, resumable, about 100 messages a minute per mailbox. Mail already read in Gmail arrives as read. The inbox list has "Load more".

**2026-10-07**
- Ran the imported project locally for the first time; fixed what stopped it on Windows.
- Polished the interface and repaired the mobile layout.
- Removed all Replit files, packages and settings.
- Redesigned the sign-in screens from the owner's reference image and applied a glass style across the app, with larger type.
- Rebuilt the backend in FastAPI on MySQL; real accounts, workspaces, sessions and audit log; removed all sample data.
- Changed the app to plain white at the owner's request.
- Wrote the project documents in `docs/`.
- Restored the glass design when the owner asked for it back, and updated the documents to match.
- Rewrote the architecture document to follow the proposal after the owner said it was wrong; aligned the PRD, rules and tasks with it.

## 8. How to update this file

- Change "Last updated" and section 1 whenever the state moves.
- Add a row to Decisions for every choice someone might later question, with the reason.
- Move finished open items out; add new ones as they appear.
- Add to section 6 anything that cost time and could cost it again.
- Use absolute dates. Keep it short: this is a memory, not a diary.
