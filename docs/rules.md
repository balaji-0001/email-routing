# Rules

For anyone changing this repository, human or AI agent. Read this before the first change, and [memory.md](memory.md) for the current state. Where a rule has a reason that is not obvious, the reason follows it.

---

## 1. Product rules

1. **No sample data.** No fake emails, people, counts or activity anywhere in the product. A screen shows real data from the API or an empty state.
2. **Say when something is not available.** If a feature is not built, its screen says "isn't available yet" and offers no button that does nothing.
3. **Follow the proposal's stack.** React frontend; Python + FastAPI backend; MySQL; Redis + Celery for background work. Do not introduce a different backend language, database or queue.
4. **Keep existing routes and behaviour** unless the task is to change them. The list of pages is in `frontend/src/data.ts`.
5. **Requirements live in [prd.md](prd.md).** If a task needs a product decision that the PRD lists as an open question, ask; do not decide it in code.

## 2. How to work

1. **Look before changing.** Read the code involved first. The docs describe intent; the code is the truth.
2. **Work without asking for permission at each step.** Stop and ask only for a real product or architecture decision, or for credentials and access you cannot get yourself.
3. **When a choice changes what the owner will see** (page layout, folder structure, visual direction), show the result of each option rather than describing it.
4. **Change only what the task needs.** No drive-by refactors, renames or dependency upgrades.
5. **Check your work before saying it is done** (section 7), and report plainly what was verified and what was not.
6. **Keep the docs true** (section 10).

## 3. Backend

1. **Layers go one way:** `api/` (HTTP only) → `services/` (rules) → `repositories/` (queries) → `models/` (tables). A route never queries the database; a repository never raises HTTP errors.
2. **Services commit.** Each use case ends with one `db.commit()`. Repositories only `add` and `flush`. The request's session rolls back whatever is left. *Why: the commit must happen before the response is sent, or the next request can miss the change.*
3. **Every tenant query filters by workspace,** and the workspace comes from the signed-in identity (`Identity.workspace`), never from the request body or URL.
4. **Check permissions in the API layer** with the dependencies in `api/deps.py` (`current_identity`, `workspace_identity`, `workspace_manager`). Hiding a button in the web app is not a permission check.
5. **Validate every input** with a Pydantic schema in `schemas/`.
6. **Fail with `AppError(status, CODE, message)`.** The message is shown to the user: plain words, what happened and what to do. Never return stack traces or internal details.
7. **Responses use the envelope:** `{"data": ...}` on success, `{"error": {"code", "message", "details"}}` on failure. New routes go under `/api/v1`.
8. **Record an audit event** (`services/audit.record`) for anything a person changes in a workspace. Summaries are past tense without pronouns ("Renamed the workspace to X"), because the app shows them after "You" or a name.
9. **Times are UTC.** Use `utcnow()` from `core/database.py`; store naive UTC; return ISO 8601 with `Z`.
10. **Slow or scheduled work belongs in a Celery task,** not in a request: the API never talks to an email or AI provider itself. Tasks call the same services, receive ids rather than content, and must be safe to run twice.
11. **Email providers sit behind one adapter interface.** Nothing outside the adapters talks to Gmail, Microsoft Graph or IMAP directly.
12. **AI providers sit behind one adapter interface too.** An AI feature never calls a provider's API directly, so the provider stays a setting.
13. **Mail announces events; features subscribe.** Rules, AI, notifications and webhooks hook into events such as `message.received`. Do not add calls to them inside sync or send.
14. **A rule is data.** New automation features are added by registering a trigger, condition or action, not by special cases in the engine.
15. **Ask the settings resolver before any AI or automation action.** It is the only code that reads the ON/OFF switches at organization, email-account, team and user level. *Why: the proposal promises full control; one forgotten check breaks that promise.*

The proposal says "organization"; the code says `workspace`. They are the same thing. See [architecture.md](architecture.md) section 4.

## 4. Database

1. **Schema changes go through a new Alembic revision** in `backend/migrations/versions/`. Never edit a revision that has been applied, and never change tables by hand.
2. **Migrations are additive.** Add tables and nullable columns; do not drop or rewrite data. To rename: add, backfill, then remove in a later change.
3. **Table conventions:** plural snake_case names; `id` BIGINT primary key; `created_at` (and `updated_at` where rows change) as `DATETIME(6)`; foreign keys named `<thing>_id` and indexed; every customer-owned table has `workspace_id`.
4. **The development database belongs to the owner.** `email_management` holds their real account. Never create test accounts in it, never truncate or reset it, never run destructive SQL against it.
5. **Tests use `email_management_test` only.** The test setup refuses to run against a database whose name does not end in `_test`. Keep that check.

## 5. Frontend

1. **All API calls go through `frontend/src/lib/api.ts`.** Components never call `fetch`.
2. **Server data is read with TanStack Query** (`useQuery`, `useMutation`). Who is signed in comes from `useSession()` inside the app and `useMe()` at the gate.
3. **Use the shared pieces in `components/kit.tsx`** (Button, Field, EmptyState, PageHeading, toasts) before writing new ones.
4. **Every screen has three states:** loading (skeleton), empty (an `EmptyState` that says what will be here) and error (what went wrong and what to do).
5. **Follow [design.md](design.md).** The product uses the glass design everywhere: frosted, translucent surfaces over the coloured backdrop, dark navy text. Do not flatten it to plain white. *Why: a white version was tried and the owner asked for the glass design back.*
6. **Text is never smaller than 12px,** and body text is about 14px. *Why: the owner asked twice for larger, more readable type.*
7. **In `index.css`, the responsive `@media` blocks stay last.** *Why: they were once placed before the base rules and silently did nothing.*
8. **Keep it responsive.** Check at 1440, 900 and 390 pixels wide; nothing may scroll sideways.
9. **Copy:** sentence case, plain verbs, no filler. A button says what it does ("Save changes"), and the confirmation uses the same word ("Saved").

## 6. Security and secrets

1. **Never print, log, commit or paste a secret:** not `.env` values, passwords, tokens, API keys or connection strings with passwords.
2. **Secrets live in the git-ignored `.env`.** Add new settings to `.env.example` with a placeholder and a comment.
3. **Store tokens hashed, credentials encrypted.** Session and reset tokens are stored as SHA-256 hashes. Mailbox passwords and provider tokens must be encrypted at rest.
4. **Do not weaken sign-in:** keep argon2id, the HttpOnly `SameSite=Lax` cookie, the same-origin check, the rate limits, and the identical message for wrong password and unknown email.
5. **Email content is hostile input.** Sanitize it on the server and never insert it into the page as trusted HTML.
6. **Do not send message content to an AI provider** unless the settings resolver says that feature is on for that organization, email account, team and user.

## 7. Testing and verification

Before saying a change is done:

1. `pnpm test` — backend tests pass.
2. `pnpm typecheck` — the web app typechecks (strict mode).
3. `pnpm build` — the production build succeeds.
4. **Use the feature in a browser** for anything a user can see or click.

Rules for tests:

1. New backend behaviour gets a test in `backend/tests/`. Tests go through the HTTP API with `TestClient`, against real MySQL.
2. Browser checks run on a second stack pointed at the test database, never on the owner's development database: API with `PORT=5001`, web app with `WEB_PORT=5174`, plus `APP_URL=http://localhost:5174` and `DATABASE_URL=mysql+pymysql://root@127.0.0.1:3308/email_management_test`.
3. Do not delete or weaken a failing test to make it pass. Fix the cause.

## 8. Local environment

1. **Windows machine.** Scripts must work in PowerShell and cmd: no `export`, no `sh -c`. Put cross-platform logic in `scripts/tasks.mjs`.
2. **pnpm only.** `npm install` and `yarn` are refused on purpose.
3. **One command runs everything:** `pnpm dev`. Web app on 5173, API on 5000, MySQL on 3308 (local only, started by the same command; it does not start by itself after a reboot).
4. **Start long-running servers as their own processes** with output to a `.log` file (git-ignored), so they outlive the command that started them.
5. **Python packages go in `backend/requirements.txt`** (or `requirements-dev.txt` for test tools) and are installed into `backend/.venv`.

## 9. Git

1. **Do not commit or push unless asked.**
2. Never commit `.env`, `local-mysql/`, `backend/.venv/`, `node_modules/` or log files.
3. One change, one clear commit message saying what changed and why.

## 10. Keeping the docs current

After a piece of work, update what it made untrue:

| When | Update |
|------|--------|
| A task is finished, started or discovered | [tasks.md](tasks.md) |
| A decision is made, or something surprising is learned | [memory.md](memory.md) |
| A table, endpoint or component changes | [architecture.md](architecture.md) |
| A requirement is decided or changed | [prd.md](prd.md) |
| A colour, size or component style changes | [design.md](design.md) |
| How to run or configure the project changes | `README.md` and `.env.example` |
