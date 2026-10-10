# Technical Architecture

**Product:** Email SaaS Platform — centralized email management with team collaboration, AI and automation
**Version:** 2.0
**Date:** 2026-10-07
**Source:** [email-saas-project-proposal.pdf](email-saas-project-proposal.pdf)
**Requirements:** [prd.md](prd.md) · **Tasks:** [tasks.md](tasks.md)

This document describes the architecture the proposal specifies, from end to end, and how each part is designed. Every part is marked **Built** (in the code today) or **Not built**. Where the proposal leaves something open, the question is listed in section 16 instead of being decided here.

---

## 1. What the Proposal Specifies

### 1.1 Technology

| Layer | Proposal | In the code today |
|-------|----------|-------------------|
| Frontend | **React** | Built: React 19, TypeScript, Vite, Tailwind CSS |
| Backend | **Python + FastAPI** | Built: FastAPI, Pydantic 2, SQLAlchemy 2, Alembic |
| Database | **MySQL** | Built: MySQL 8.4 |
| Queue | **Redis + Celery** | Not built: the first task of Phase 1 |

Nothing outside this stack is introduced: no second backend language, no other database, no other queue.

### 1.2 Required qualities

The proposal: "The architecture will be multi-tenant, secure and scalable, allowing additional email providers, AI providers and automation features to be added later."

| Quality | Where it is designed |
|---------|----------------------|
| Multi-tenant | Section 4 |
| Secure | Section 11 |
| Scalable | Section 12 |
| More email providers, AI providers and automation features later | Section 6 |

### 1.3 What it must do

| Proposal section | Contents | Designed in |
|------------------|----------|-------------|
| Core Features | Connect Gmail, Outlook/Microsoft 365 and IMAP/SMTP accounts; unified inbox; send, reply, reply all, forward, attachments; search, filters, labels, folders, email status; teams, users, roles, assignment; internal notes and notifications | Sections 5.1 and 5.2 |
| AI Features | Summarization, generated replies, classification, priority and sentiment, smart routing, AI auto-reply | Section 5.3 |
| Automation | Rule-based filters, auto assignment, auto labels and priority, automatic notifications, auto-reply workflows, scheduled actions, webhooks | Section 5.4 |
| Full Control | Every AI and automation feature has an ON/OFF setting at organization, email-account, team and user level | Section 5.5 |
| Development Approach | Five phases | Section 13 |

---

## 2. System Overview

```
                               Browser
                                  │  HTTPS
                     ┌────────────▼────────────┐
        FRONTEND     │      React web app      │   Outlook-like dashboard
                     └────────────┬────────────┘
                                  │  /api/v1  (REST, JSON)
                     ┌────────────▼────────────┐
        BACKEND      │         FastAPI         │
                     │ routes → services →     │
                     │ repositories            │
                     └──────┬───────────┬──────┘
                            │           │ queue a job
                  ┌─────────▼───┐   ┌───▼──────────┐
        DATABASE  │    MySQL    │   │    Redis     │   QUEUE
                  └─────────▲───┘   └───┬──────────┘
                            │           │
                     ┌──────┴───────────▼──────┐
                     │  Celery workers + beat  │   the same services as the API
                     │  sync · send · rules ·  │
                     │  AI · webhooks · timers │
                     └───┬─────────┬─────────┬─┘
                         │         │         │
              Email providers   AI providers   Customer systems
              Gmail             (chosen per    (webhooks)
              Microsoft 365     organization)
              IMAP / SMTP
```

One rule shapes everything: **the API answers quickly and never talks to an email or AI provider itself.** Anything slow, repeated or scheduled is a Celery job, queued through Redis. Both the API and the workers read and write MySQL, which is the single source of truth.

Built today: the React app, the FastAPI application and MySQL. Not built: Redis, the Celery workers and every connection on the bottom row.

---

## 3. Components

### 3.1 Frontend — React · Built (shell and account screens)

- **Responsibility:** everything the user sees. One dashboard for all connected accounts, laid out like a mail client: navigation and folders on the left, the message list in the middle, the open conversation beside it, a header with search, notifications and the profile menu.
- **Talks to:** the API only, and only through `frontend/src/lib/api.ts`.
- **Structure:** `App.tsx` decides which screen a visitor may open (sign-in, organization setup, or the app); `components/shell.tsx` is the sidebar and header; `components/kit.tsx` holds shared pieces; `pages/` holds the screens; `lib/session.tsx` holds who is signed in.
- **Server data:** TanStack Query. Routing: wouter.
- **Provider-neutral screens:** a mailbox looks and behaves the same whether it is Gmail, Microsoft 365 or IMAP/SMTP; only the connect screen differs.

### 3.2 Backend — Python + FastAPI · Built (accounts and organizations)

One application, in layers that only call downward:

```
backend/app/
  api/            HTTP routes: read the request, call a service, shape the response      Built
  services/       business rules; each use case commits its own transaction              Built
  repositories/   database queries only                                                  Built
  models/         tables                                                                 Built
  schemas/        request and response shapes (Pydantic)                                 Built
  core/           settings, database session, security helpers, errors, rate limits      Built
  providers/      email provider adapters: gmail, microsoft, imap_smtp                   Phase 1
  events/         internal events that connect mail to rules, AI, notifications, webhooks Phase 1
  tasks/          Celery tasks: thin wrappers that call services                         Phase 1
  worker.py       the Celery application                                                 Phase 1
  automation/     triggers, conditions, actions and the rule engine                      Phase 2
  ai/             AI provider adapters and the AI features                               Phase 3
```

The folders marked with a phase do not exist yet; this is where they go.

### 3.3 Database — MySQL · Built

The single source of truth for organizations, people, mail, rules, settings and history. Schema changes are Alembic migrations and are additive. The data model is in section 7.

### 3.4 Queue — Redis + Celery · Not built

- **Redis** is the Celery broker and result store, and also holds shared rate-limit counters, short locks (for example "one sync per mailbox at a time") and small caches.
- **Celery workers** run the jobs. They import the same `services/` and `repositories/` as the API, so a rule is written once and behaves the same in a request and in a job. This is why database access is synchronous.
- **Celery beat** starts timed work: polling mailboxes, refreshing provider tokens, running scheduled actions, cleanup.

The queues are in section 8.

---

## 4. Multi-Tenancy and the Four Levels

The proposal names four levels: **organization, email account, team and user.** They form the tenancy model.

```
Organization                         the customer; the tenant
 ├── Users            each with one role: Owner, Admin, Manager, Agent or Viewer
 ├── Teams            groups of users                                        Phase 2
 ├── Email accounts   Gmail, Microsoft 365 or IMAP/SMTP mailboxes            Phase 1
 │     └── Folders → Conversations → Messages → Attachments
 └── Settings         ON/OFF and configuration at each of the four levels    Phases 2 to 4
```

- **Isolation is by row.** Every table that holds customer data carries the organization's id. The organization is always taken from the signed-in session (or, in a worker, from the job's own record), never from anything a client sends. Every query for customer data filters on it.
- **Built:** organizations, users, roles, and the isolation itself, which `backend/tests/test_workspace.py` checks with two organizations that must not see each other.
- **Not built:** teams, email accounts and the settings levels.

**Naming.** The proposal says *organization*. The code and the screens say *workspace*: the table is `workspaces`, the column is `workspace_id`, the screen is "Workspace settings". They are the same thing. This document says organization when describing the design and uses the real names when it names tables, columns and endpoints. Whether to rename is question 1 in section 16.

---

## 5. Feature Areas

### 5.1 Core email (Phase 1) · Not built

| Proposal item | Design |
|---------------|--------|
| Connect multiple Gmail, Outlook/Microsoft 365 and IMAP/SMTP accounts | An organization holds any number of `email_accounts`. Gmail and Microsoft connect by OAuth; IMAP/SMTP by server details that are tested before saving. Credentials are stored encrypted. All three sit behind one adapter interface (section 6.1). |
| Unified inbox | One query over `conversations` for the organization, across all its email accounts, newest first, paged by cursor. |
| Send, Reply, Reply All, Forward, Attachments | The API saves the message as queued; a `send` job hands it to the provider adapter. Reply headers keep the thread together at the provider. Attachments are stored outside the row data (question 6). |
| Search, filters, labels, folders, email status | Search starts on MySQL full-text behind one service so it can be replaced. Labels belong to the organization; folders mirror each provider's own. Status is a column on the conversation (its values are PRD question 5). |

**Mail in:** a `sync` job pulls changes through the adapter, groups messages into conversations, writes them to MySQL, and announces a `message.received` event. **Mail out:** the reverse, ending in `message.sent`. Changes made in the product (read, star, archive, label) are written to MySQL and queued to be applied at the provider.

### 5.2 Teams and collaboration (Phase 2) · Roles built, the rest not

| Proposal item | Design |
|---------------|--------|
| Users and roles | Built: one role per user per organization, checked in the API. Permissions for mail actions are added here (PRD question 7). |
| Teams | `teams` and `team_members`: groups of users inside an organization. A team is also one of the four settings levels. |
| Email assignment | A conversation has an assignee: a user, a team, or nobody. Each change is recorded. |
| Internal notes | `notes` on a conversation; never sent to the provider. |
| Notifications | `notifications` per user, created by events (assigned, mentioned, rule fired) and delivered in the app and by email through the `notifications` queue. |

### 5.3 AI features (Phase 3; auto-reply Phase 4) · Not built

| Proposal item | Runs as |
|---------------|---------|
| AI email summarization | An `ai` job per conversation, on request or on arrival |
| AI-generated replies | An `ai` job on request; the result is a draft a person edits and sends |
| Email classification | An `ai` job on arrival; the result can drive rules |
| Priority and sentiment detection | The same |
| Smart email routing | An `ai` job that proposes an assignee or team; applied by a rule or a person |
| AI-powered auto-reply | Phase 4: a draft built by an `ai` job, then sent or held for approval (section 5.5) |

Every feature is written against one AI provider interface (section 6.2), so the provider is a setting, not code. Results are stored in `ai_results` with the model used and the amount consumed, which feeds usage limits.

### 5.4 Automation (Phase 2; workflows Phase 4) · Not built

A rule is data: **when** a trigger happens, **if** conditions match, **do** actions.

| Proposal item | Design |
|---------------|--------|
| Rule-based email filters | Conditions on sender, recipient, subject, body, mailbox, label, and later AI results |
| Auto assignment | Action: assign to a user or team |
| Auto labels and priority | Actions: add label, set priority |
| Automatic notifications | Action: notify a user or team |
| Auto-reply workflows | Phase 4: action "reply with", chained into multi-step workflows |
| Scheduled actions | `scheduled_actions` with a run time; Celery beat queues the ones that are due |
| Webhooks | `webhooks` per organization; each event is delivered as a signed request by the `webhooks` queue, with retries and a delivery log |

The rule engine listens to the internal events (section 6.3). Each run is recorded in `rule_runs`, which is what "last executed" and "test rule" read.

### 5.5 Full Control · Not built

The proposal: "All AI and automation features will have ON/OFF settings at organization, email-account, team and user levels."

**Switches.** One table, `feature_settings`: the organization, the level (`organization`, `email_account`, `team` or `user`), the id at that level, the feature, on or off, and optional configuration. The features are the proposal's own lists:

| AI | Automation |
|----|------------|
| Summarization · Generated replies · Classification · Priority and sentiment · Smart routing · Auto-reply | Rule-based filters · Auto assignment · Auto labels and priority · Automatic notifications · Auto-reply workflows · Scheduled actions · Webhooks |

**One resolver.** A single function answers "is this feature on here?" for a given organization, email account, team and user. Workers call it before every AI or automation action; the API calls it to tell the screens what to show. No other code reads the switches. If the answer is off, nothing runs and no message content leaves the system. How the four levels combine is PRD requirement FR-18 and question 2 in section 16.

**Configuration.** The proposal lists seven things the customer controls:

| Item | Where it lives |
|------|----------------|
| AI provider and API credentials | `ai_provider_configs`, per organization, key encrypted |
| AI prompts | `ai_prompts`, per feature, overridable at a lower level |
| Auto-reply rules | `auto_reply_rules` |
| Approval requirements | A setting per level; replies that need approval wait in `auto_reply_approvals` until a person decides |
| Notification rules | `notification_rules` per user and team |
| Usage limits | Limits in `feature_settings`; consumption counted in `ai_usage` and checked before each AI job |
| Automation rules | `rules` |

---

## 6. Built to Be Extended

The proposal requires that more email providers, AI providers and automation features can be added later. Each has one extension point, and the rest of the system only knows the interface.

### 6.1 Email providers

One interface: connect and verify, list changes since a position, fetch a message and its attachments, send, change flags and labels, list folders. One adapter each for Gmail (Gmail API), Microsoft 365 (Microsoft Graph) and IMAP/SMTP, registered by name. Sync, the inbox, sending and rules never mention a provider. **Adding a provider = one new adapter and one connect screen.**

### 6.2 AI providers

One interface: send a prompt with content, get text or structured output back, report what was consumed. One adapter per provider, registered by name and chosen per organization along with its credentials. The AI features in section 5.3 call the interface. **Adding a provider = one new adapter.** Which provider comes first is PRD question 8.

### 6.3 Automation features

Internal events are the join between mail and everything built on it: `message.received`, `message.sent`, `conversation.assigned`, `note.added` and so on. The code that causes an event announces it once; rules, AI, notifications and webhooks each subscribe and queue their own jobs.

Triggers, conditions and actions are each registered by a key, and a rule stores those keys with their parameters. **Adding an automation feature = registering one new trigger, condition or action.** Existing rules and the engine do not change.

---

## 7. Data Model

All primary keys are auto-incrementing `BIGINT`. Times are `DATETIME(6)` in UTC, returned by the API as ISO 8601 with a trailing `Z`. Every table below except `users`, `sessions` and `password_reset_tokens` carries `workspace_id`.

### 7.1 Built

**users**

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| id | BIGINT | PK | |
| email | VARCHAR(320) | NOT NULL, UNIQUE | Always stored lower-case |
| password_hash | VARCHAR(255) | NOT NULL | argon2id |
| first_name, last_name | VARCHAR(100) | NOT NULL | |
| timezone | VARCHAR(64) | NULL | IANA name, taken from the browser at sign-up |
| password_changed_at | DATETIME(6) | NOT NULL | |
| last_login_at | DATETIME(6) | NULL | |
| created_at, updated_at | DATETIME(6) | NOT NULL | |

**workspaces** — the organization

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| id | BIGINT | PK | |
| name | VARCHAR(120) | NOT NULL | |
| domain | VARCHAR(255) | NULL | |
| timezone | VARCHAR(64) | NOT NULL | Defaults to the creator's |
| allow_invitations | BOOLEAN | NOT NULL | Stored now, used when invitations exist |
| created_by_user_id | BIGINT | FK users, SET NULL | |
| created_at, updated_at | DATETIME(6) | NOT NULL | |

**workspace_members** — a user in an organization, with a role

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| id | BIGINT | PK | |
| workspace_id | BIGINT | FK workspaces, CASCADE | |
| user_id | BIGINT | FK users, CASCADE | |
| role | VARCHAR(20) | NOT NULL | owner, admin, manager, agent or viewer |
| created_at | DATETIME(6) | NOT NULL | |
| | | UNIQUE (workspace_id, user_id) | |

**sessions** — one row per signed-in browser

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| id | BIGINT | PK | |
| user_id | BIGINT | FK users, CASCADE | |
| workspace_id | BIGINT | FK workspaces, SET NULL | The organization this session works in |
| token_hash | VARCHAR(64) | NOT NULL, UNIQUE | SHA-256 of the cookie value |
| remember | BOOLEAN | NOT NULL | |
| user_agent, ip_address | VARCHAR | NULL | Shown under "Where you're signed in" |
| created_at, last_used_at, expires_at | DATETIME(6) | NOT NULL | |
| revoked_at | DATETIME(6) | NULL | Set on sign-out |

**password_reset_tokens:** id, user_id (FK, CASCADE), token_hash (UNIQUE), created_at, expires_at, used_at.

**audit_events:** id, workspace_id (FK, CASCADE, NULL before an organization exists), actor_user_id (FK, SET NULL), action, summary, ip_address, created_at. Rows are only ever added.

### 7.2 Not built, by phase

Outlines only. Each is designed in detail, with its migration, when its phase starts.

**Phase 1 — Core Email & Unified Inbox**

| Table | Holds |
|-------|-------|
| email_accounts | Provider (`gmail`, `microsoft`, `imap`), address, display name, status, encrypted credentials, sync position, last sync, last error |
| folders | A provider's folders for one email account, with their kind (inbox, sent, drafts, trash, archive, custom) |
| conversations | Email account, provider thread id, subject, last message time, read, starred, status |
| messages | Conversation, provider message id, direction, sender, subject, text and HTML body, sent time, threading headers, state (draft, queued, sent, failed) |
| message_recipients | Message, kind (to, cc, bcc), address, name |
| attachments | Message, file name, type, size, where the file is stored |
| labels, conversation_labels | Organization labels and what they are applied to |

**Phase 2 — Teams & Automation**

| Table | Holds |
|-------|-------|
| teams, team_members | Groups of users |
| invitations | Email, role, token hash, expiry, who invited |
| assignment on conversations | Assignee user or team, plus `assignment_events` for the history |
| notes | Conversation, author, text |
| notifications, notification_rules | What a user should know, and who wants to hear about what |
| rules, rule_runs | Trigger, conditions, actions, on/off, scope; one row per run |
| scheduled_actions | What to do and when, with its state |
| webhooks, webhook_deliveries | Address, signing secret (encrypted), events; one row per delivery attempt |
| feature_settings | The ON/OFF switches at the four levels (section 5.5) |

**Phase 3 — AI Features**

| Table | Holds |
|-------|-------|
| ai_provider_configs | Provider, model, encrypted API key, per organization |
| ai_prompts | Prompt text per feature and level |
| ai_results | Summary, classification, priority, sentiment, routing suggestion or draft reply for a message or conversation, with the model used |
| ai_usage | Consumption per organization, counted against usage limits |

**Phase 4 — Auto-Reply & Smart Workflows**

| Table | Holds |
|-------|-------|
| auto_reply_rules | When to reply automatically and with what |
| auto_reply_approvals | Replies waiting for a person, and who decided |
| workflows, workflow_runs | Multi-step workflows and their progress |

**Phase 5 — SaaS Billing, Analytics & Enterprise Features**

The proposal gives only the title. Expected: plans, subscriptions, usage counters, analytics summaries. To be specified (PRD questions 9 to 11).

### 7.3 Indexes

Built: unique indexes on `users.email`, `sessions.token_hash`, `password_reset_tokens.token_hash` and `workspace_members (workspace_id, user_id)`; indexes on every foreign key; `sessions.expires_at`; `audit_events (workspace_id, created_at)`.

Planned: the inbox is "conversations of an organization, filtered, newest first", so `conversations (workspace_id, last_message_at)` plus the filter columns is the index that matters most. `messages` needs a unique index on `(email_account_id, provider_message_id)` so that re-running a sync cannot store a message twice.

### 7.4 Retention

Not decided. Nothing is deleted automatically today. Expired sessions and used reset tokens accumulate until the cleanup job exists (Phase 1).

---

## 8. Queue Design (Redis + Celery) · Not built

Separate queues, so that slow work cannot hold up urgent work: an AI job must never delay sending a reply.

| Queue | Jobs | Phase |
|-------|------|-------|
| `sync` | First import of a mailbox; ongoing sync; applying read, star, archive and label changes at the provider | 1 |
| `send` | Send a message; retry on a temporary failure | 1 |
| `maintenance` | Started by beat: poll mailboxes, refresh provider tokens, remove expired sessions and tokens | 1 |
| `automation` | Evaluate rules for an event and run their actions | 2 |
| `notifications` | Create notifications and send their emails | 2 |
| `webhooks` | Deliver an event to a customer's address; retry with growing delays | 2 |
| `scheduled` | Started by beat: run scheduled actions that are due | 2 |
| `ai` | Summaries, classification, priority and sentiment, routing, draft replies | 3 |
| `auto_reply` | Build an automatic reply, hold it for approval or send it | 4 |

Rules for every job:

1. **A job receives ids, not content,** and loads what it needs from MySQL. The organization comes from the record, never from the caller.
2. **A job can run twice without harm.** Sync and send use the provider's own ids to detect what is already done.
3. **A job checks the settings resolver first** when it is an AI or automation job (section 5.5).
4. **Failures retry with growing delays,** then mark the record as failed with a message a person can read.
5. **One sync per mailbox at a time,** enforced by a Redis lock.

---

## 9. API

### 9.1 Conventions · Built

- **Base URL:** `/api/v1/`. The health check lives outside the version at `/api/healthz`.
- **Sign-in:** a session cookie named `em_session`. There is no `Authorization` header.
- **Success:** `{"data": ...}`. Sign-out and password actions return `204` with no body.
- **Failure:** `{"error": {"code": "...", "message": "...", "details": [{"field": "...", "message": "..."}]}}`. `message` is written for the person using the app.
- **Status codes in use:** `401 NOT_SIGNED_IN`, `403 FORBIDDEN` and `ORIGIN_NOT_ALLOWED`, `409 EMAIL_TAKEN`, `WORKSPACE_REQUIRED` and `WORKSPACE_EXISTS`, `422 VALIDATION_ERROR`, `429 TOO_MANY_ATTEMPTS` (with `Retry-After`), `503 EMAIL_NOT_CONFIGURED`.
- **Lists:** mail lists page by cursor on the sort key (planned); the audit log takes `limit`.
- **Slow actions return at once.** "Connect", "sync now" and "send" queue a job and return the record with its status; the screen shows the status as it changes.
- **Reference:** interactive docs at `/api/docs` when `APP_ENV` is not `production`.

### 9.2 Endpoints · Built

Paths other than the health check are relative to `/api/v1`.

| Method | Path | Who | Description |
|--------|------|-----|-------------|
| GET | /api/healthz | Anyone | Liveness check |
| GET | /auth/options | Anyone | Whether password reset by email is available |
| POST | /auth/register | Anyone | Create an account and sign in |
| POST | /auth/login | Anyone | Sign in; `remember` controls the session length |
| POST | /auth/logout | Anyone | End the current session |
| GET | /auth/me | Signed in | The user, their organization and role |
| POST | /auth/password/forgot | Anyone | Email a reset link (same answer whether or not the address has an account) |
| POST | /auth/password/reset | Anyone with a token | Set a new password; signs out everywhere |
| POST | /auth/password/change | Signed in | Change password; signs out other browsers |
| GET | /auth/sessions | Signed in | Where this person is signed in |
| POST | /auth/sessions/revoke-others | Signed in | Sign out every other browser |
| PATCH | /users/me | Signed in | Update name and time zone |
| POST | /workspaces | Signed in, no organization yet | Create an organization; the caller becomes owner |
| PATCH | /workspace | Owner or admin | Update the current organization |
| GET | /workspace/members | Member | List the people in it |
| GET | /workspace/audit-events | Owner or admin | Newest audit events |
| GET | /email-accounts/providers | Member | Whether Google sign-in is set up, and the redirect address to register |
| POST | /email-accounts/oauth/google/start | Owner or admin | Record a sign-in attempt and return the Google address to open |
| GET | /email-accounts/oauth/google/callback | The browser, sent back by Google | Finish the attempt, store encrypted tokens, redirect to Email accounts |

### 9.3 Endpoint groups · Not built

| Phase | Groups |
|-------|--------|
| 1 | `/email-accounts`, `/folders`, `/conversations`, `/messages`, `/attachments`, `/labels`, `/search` |
| 2 | `/teams`, `/invitations`, `/assignments`, `/notes`, `/notifications`, `/rules`, `/scheduled-actions`, `/webhooks`, `/settings/features` |
| 3 | `/ai/provider`, `/ai/prompts`, `/ai/summaries`, `/ai/replies`, `/ai/usage` |
| 4 | `/auto-reply/rules`, `/auto-reply/approvals`, `/workflows` |
| 5 | `/billing`, `/usage`, `/analytics` |

---

## 10. Sign-in and Permissions · Built

### 10.1 Sign-in

1. The browser posts email and password.
2. The API checks the rate limit, then verifies the password against the argon2id hash. An unknown email costs the same time as a wrong password.
3. On success it creates a random 256-bit token, stores only its SHA-256 hash in `sessions`, and returns the token in an `HttpOnly`, `SameSite=Lax` cookie (`Secure` when `APP_ENV=production`).
4. Each later request looks the session up by the cookie's hash and rejects it if revoked or expired.

Sessions last 24 hours by default and 30 days with "Remember me". Sign-out revokes one session; changing the password revokes the others; a password reset revokes all. Sessions are kept on the server rather than in a self-contained token so that signing out really ends access.

### 10.2 Roles

One role per user per organization, enforced in the API (`backend/app/api/deps.py`), never only in the screens.

| Action | Owner | Admin | Manager | Agent | Viewer |
|--------|-------|-------|---------|-------|--------|
| Sign in and see the organization | ✓ | ✓ | ✓ | ✓ | ✓ |
| See the people in it | ✓ | ✓ | ✓ | ✓ | ✓ |
| Change organization settings | ✓ | ✓ | ✗ | ✗ | ✗ |
| Read the audit log | ✓ | ✓ | ✗ | ✗ | ✗ |

What each role may do with mail, teams, rules and AI is defined in Phase 2 (PRD question 7).

---

## 11. Security

| Threat | Protection | Status |
|--------|------------|--------|
| One organization reading another's data | The organization always comes from the session or the job's record; every query filters on it; tested | Built |
| Stolen database | Passwords are argon2id hashes; session and reset tokens are stored only as hashes | Built |
| Password guessing | Rate limits on sign-in, sign-up and reset; one message for wrong password and unknown email | Built (counters move to Redis in Phase 1) |
| Forged requests from another site | `SameSite=Lax` cookie; state-changing requests are refused unless their `Origin` is the app; no CORS | Built |
| Session theft by a script | The cookie is `HttpOnly` | Built |
| Leaked mailbox passwords or provider tokens | Encrypted at rest with a key held outside the database; narrowest provider access | Phase 1 |
| Hostile content in an email | HTML is cleaned on the server and shown isolated from the app; remote images load only when the user asks | Phase 1 |
| Mail content sent to an AI provider without consent | The settings resolver is checked before every AI job; off means nothing is sent | Phase 3 |
| Forged or replayed webhooks at the customer's end | Each delivery is signed with the webhook's secret and carries a timestamp | Phase 2 |
| An automatic reply nobody wanted | Approval requirements; every automatic action is recorded and can be switched off at four levels | Phase 4 |

Also in place: all input validated by Pydantic schemas; database access through the ORM with bound parameters; secrets only in environment variables or the git-ignored `.env`; errors never include stack traces; an audit log of sign-ins and changes. Still to do at deployment: HTTPS everywhere, security headers, dependency scanning.

---

## 12. Scalability

- **API:** keeps no state of its own once rate limits are in Redis, so it scales by adding processes behind a load balancer.
- **Workers:** scale per queue. A large customer importing a mailbox adds load to `sync` workers only; `send` stays fast.
- **Fairness between organizations:** imports run in pages, newest first, so one large mailbox cannot occupy a worker for hours, and each organization's jobs are limited in how many run at once.
- **MySQL:** scales up first. Next steps when needed: read replicas for the inbox and search, and moving message bodies and attachments out of the main tables (question 7).
- **Search:** behind one service, so MySQL full-text can be replaced by a search engine without touching callers.
- **New mail without polling the provider:** Gmail and Microsoft can push changes; IMAP is polled. Push needs a public HTTPS address (question 5).

No load targets exist yet (PRD question 11).

---

## 13. Development Phases

The proposal's five phases, with what each adds to the architecture.

| Phase | Proposal | Adds |
|-------|----------|------|
| Foundation | (groundwork, done) | React app, FastAPI layers, MySQL, accounts, organizations, roles, audit log. **Built.** |
| 1 | Core Email & Unified Inbox | Redis + Celery; `providers/`, `events/`, `tasks/`; queues `sync`, `send`, `maintenance`; the mail tables; inbox, conversation, compose and search screens |
| 2 | Teams & Automation | Teams, invitations, assignment, notes, notifications; `automation/` and the rule engine; queues `automation`, `notifications`, `webhooks`, `scheduled`; `feature_settings` and the resolver |
| 3 | AI Features | `ai/` with the provider interface; queue `ai`; provider configuration, prompts, results, usage and limits |
| 4 | Auto-Reply & Smart Workflows | Auto-reply rules, approvals, workflows; queue `auto_reply` |
| 5 | SaaS Billing, Analytics & Enterprise Features | Plans, subscriptions, usage, analytics; enterprise features to be specified |

Phase 1 is broken into tasks in [tasks.md](tasks.md).

---

## 14. Running and Deploying

### 14.1 Local development · Built

- **Runtimes:** Python 3.12 or newer for the backend; Node.js 22.9 or newer to build and serve the React app.
- **Packages:** pip with `backend/requirements.txt` in `backend/.venv`; pnpm for the frontend.
- **Database:** `pnpm db:start` runs MySQL with its data in `./local-mysql`, on `127.0.0.1:3308` only. Databases: `email_management` for development and `email_management_test` for tests.
- **Everything at once:** `pnpm dev` starts MySQL if needed, applies migrations, and runs the API (port 5000) and the web app (port 5173). The web dev server forwards `/api` to the API, so the browser sees one origin. From Phase 1 it also starts Redis, a worker and beat.
- **Settings:** a `.env` file in the repo root; `.env.example` lists every setting.

### 14.2 Deployment · Not decided

Whatever is chosen must provide: a host for the built React app with `/api` routed to the API on the same origin; a Python host for the API; MySQL 8; Redis; hosts for the Celery workers and one beat process; file storage for attachments. Checks on every push: `pnpm typecheck`, `pnpm build`, `pnpm test`.

---

## 15. Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Google treats full mailbox access as a restricted permission; releasing to the public needs Google's review, which can include an outside security assessment | High | High | Check Google's current requirements before promising a Gmail date; develop against test users meanwhile |
| Microsoft 365 organizations may require their administrator to approve the app | Medium | Medium | Document the admin-consent step for customers |
| IMAP servers behave differently; threading without provider thread ids is imprecise | High | Medium | Thread by `References` and `In-Reply-To`; test against several servers |
| Importing a very large mailbox overloads workers or the database | Medium | High | Import in pages, newest first, with a limit per mailbox (PRD question 4) |
| Redis and Celery are not supported natively on Windows, the development machine | High | Low | Decide the local setup before Phase 1 (question 3); confirm they support the Python version in use |
| An automatic reply or rule acts wrongly on customer mail | Medium | High | Off by default; approval requirements; test a rule before switching it on; every run recorded |
| AI cost grows without control | Medium | Medium | Usage limits per organization, checked before each job |
| MySQL full-text search is not good enough for mail | Medium | Medium | Keep search behind one service so it can be replaced |

---

## 16. Open Technical Questions

| # | Question | Decision needed |
|---|----------|-----------------|
| 1 | The proposal says "organization"; the code and screens say "workspace". Rename, or keep workspace as the product's word? | Before Phase 2, when the levels become visible in settings |
| 2 | How do the four ON/OFF levels combine? The PRD says the most specific level wins. The alternative is that "off" at a higher level cannot be switched back on lower down, which gives the organization the final say. | Before Phase 2 |
| 3 | How do Redis and Celery run on the Windows development machine: WSL, Docker or a Windows-compatible Redis? | Start of Phase 1 |
| 4 | Which team and user apply to a message that has just arrived and is not assigned yet, when the settings are checked? | Before Phase 2 |
| 5 | New mail by provider push (Gmail Pub/Sub, Graph subscriptions) or by polling? Push needs a public HTTPS address. | Start of Phase 1 |
| 6 | Where do attachments live: object storage or disk? | Start of Phase 1 |
| 7 | Are message bodies stored in MySQL or outside it? | Start of Phase 1 |
| 8 | Where does the key that encrypts mailbox credentials and API keys live, and how is it rotated? | Start of Phase 1 |
| 9 | How does the browser learn about new mail: asking every few seconds, or a pushed stream? | Phase 1 |
| 10 | Where is it hosted, and what monitors it? | Before the first deployment |
