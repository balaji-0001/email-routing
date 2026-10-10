# Email Management SaaS

A team email-management platform: one workspace where a team connects its Gmail, Microsoft 365 and IMAP/SMTP inboxes and works them together, with collaboration, AI and automation on top.

## What works today

- Accounts: sign up, sign in, sign out, "remember me", change password, and password reset by email once SMTP is configured.
- Workspaces: each account creates a workspace and becomes its owner. Workspace settings, the team list and roles are real.
- Security: server-side sessions in an HttpOnly cookie, a list of where you are signed in, and an audit log of sign-ins and changes.

Everything else (connecting inboxes, mail, labels, AI, automation, webhooks) is not built yet. Those screens say so and show no sample data.

## Requirements

- Node.js 22.9 or newer and pnpm
- Python 3.12 or newer (developed on 3.14)
- MySQL 8

## First run

```bash
pnpm install
pnpm setup      # Python environment, local MySQL, database tables
pnpm dev        # database, API and web app together
```

- Web app: http://localhost:5173
- API: http://localhost:5000 (interactive docs at `/api/docs`, health check at `/api/healthz`)

`pnpm setup` and `pnpm dev` start a MySQL server that keeps its data in `./local-mysql` and listens only on `127.0.0.1:3308`. They look for the MySQL programs in `MYSQL_HOME`, then `./local-mysql/server`, then your `PATH`. To use a database you already run, set `DATABASE_URL` instead.

The web dev server forwards `/api` to the API, so the browser reaches both on one origin.

## Configuration

Copy `.env.example` to `.env` in the repo root. Variables set in your shell take precedence over the file.

| Variable | Default | Purpose |
| --- | --- | --- |
| `PORT` | `5000` | Port the API listens on |
| `DATABASE_URL` | `mysql+pymysql://root@127.0.0.1:3308/email_management` | MySQL connection |
| `APP_URL` | `http://localhost:5173` | Address of the web app, for email links and the same-origin check |
| `APP_ENV` | `development` | `production` turns on secure cookies and hides the API docs |
| `SMTP_HOST`, `SMTP_FROM` and the other `SMTP_*` | none | Outgoing email; password reset stays unavailable until these are set |
| `MYSQL_HOME` | none | Folder of the MySQL server used by `pnpm db:start` |
| `WEB_PORT` | `5173` | Port of the web dev server |
| `BASE_PATH` | `/` | Base path the web app is served from |

## Commands

| Command | What it does |
| --- | --- |
| `pnpm dev` | Start MySQL if needed, apply migrations, run the API and the web app |
| `pnpm dev:api` / `pnpm dev:web` | Run only one of them |
| `pnpm db:start` / `pnpm db:stop` / `pnpm db:status` | Control the local MySQL |
| `pnpm db:migrate` | Apply database migrations |
| `pnpm test` | Backend tests, against the `email_management_test` database |
| `pnpm typecheck` | Typecheck the web app |
| `pnpm build` | Typecheck and build the web app into `frontend/dist/public` |

New migration: `cd backend`, then `.venv/Scripts/python -m alembic revision -m "what changed"` (`.venv/bin/python` on macOS and Linux).

## Where things live

| Path | Contents |
| --- | --- |
| `frontend/` | Web app: React, Vite, Tailwind |
| `frontend/src/lib/api.ts` | The one place the web app calls the backend |
| `backend/app/api` | HTTP routes |
| `backend/app/services` | Business logic |
| `backend/app/repositories` | Database queries |
| `backend/app/models` | Tables |
| `backend/migrations` | Alembic migrations |
| `backend/tests` | Backend tests |
| `scripts/tasks.mjs` | The dev tasks behind the `pnpm` commands |
| `docs/prd.md` | What the product must do, and what is built so far |
| `docs/architecture.md` | How it is built: stack, tables, API, sign-in, security |
| `docs/rules.md` | Rules for anyone, person or AI agent, changing the code |
| `docs/design.md` | Colours, type, layout and components |
| `docs/tasks.md` | What is done, what is next, what is waiting on a decision |
| `docs/memory.md` | Current state, decisions with their reasons, known pitfalls |
| `docs/` (other files) | The project proposal and the original UI brief |

## Connecting Gmail with Google sign-in

Gmail mailboxes connect through a Google app that you own. One-time setup:

1. In [Google Cloud Console](https://console.cloud.google.com/), create a project (or pick one).
2. **APIs & Services > Library**: enable the **Gmail API**.
3. **APIs & Services > OAuth consent screen**: choose **External**, fill in the app name and your email, and add the scopes `gmail.modify` and `gmail.send`. While the app is in **Testing**, add every Gmail address you want to connect under **Test users**.
4. **APIs & Services > Credentials > Create credentials > OAuth client ID**: type **Web application**. Under **Authorized redirect URIs** add `http://localhost:5173/api/v1/email-accounts/oauth/google/callback` (replace the first part with your `APP_URL` when deployed).
5. Put the client ID and secret in `.env` as `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`, then restart `pnpm dev`.
6. In the app: **Email accounts > Add account > Google / Gmail > Sign in with Google**. Repeat for each mailbox.

Good to know:

- While the Google app is in **Testing**, Google ends each connection after 7 days. The account then shows **Needs reconnecting**; click **Reconnect**. Publishing the app ("In production") removes the limit.
- Offering Gmail to the public needs Google's verification, because reading and sending mail are restricted permissions.
- Until the two settings are present, the Gmail screen says so and offers the app-password connection instead.

## API conventions

Routes live under `/api/v1`. A successful response is `{"data": ...}`; a failure is `{"error": {"code", "message", "details"}}`. The session is a cookie, so requests that change something are only accepted from `APP_URL`.
