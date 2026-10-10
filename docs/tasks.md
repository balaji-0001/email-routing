# Tasks

What is done, what is next and what comes later, following the five phases of the [proposal](email-saas-project-proposal.pdf). Requirements are in [prd.md](prd.md) (the `FR-` numbers); design decisions and open technical questions are in [architecture.md](architecture.md).

**Keep this file current:** tick a task when it is finished and verified, add tasks you discover, and move anything blocked under "Waiting on the owner" with the reason.

Status: `[x]` done · `[ ]` not started · `[~]` in progress

Sizes are rough, for one developer working with an AI coding agent:

| Size | Meaning |
|------|---------|
| XS | 1 to 2 hours |
| S | Up to a day |
| M | 1 to 3 days |
| L | 3 to 7 days |
| XL | 1 to 3 weeks; break it down before starting |

---

## Waiting on the owner

These block or shape the next work. Each needs an answer, not code.

| # | Decision | Blocks |
|---|----------|--------|
| D-1 | How far back to import mail, and how quickly new mail must appear (PRD question 4) | Sync design |
| D-2 | The set of email statuses (PRD question 5) | P1-63 |
| D-3 | How Redis and Celery run on the Windows development machine (architecture question 3) | P1-01 |
| D-4 | Where attachments are stored (architecture question 6) | P1-25 |
| D-5 | Push or polling for new mail (architecture question 5) | P1-23 |
| D-6 | A Google Cloud project with OAuth credentials for Gmail | P1-13 |
| D-7 | A Microsoft app registration for Microsoft 365 | P1-14 |
| D-8 | SMTP details for outgoing system email | Password reset in real use; Phase 2 invitations |
| D-10 | Commit the work so far? Nothing has been committed since the project was imported. | Safety of everything below |
| D-11 | The proposal says "organization"; the code and screens say "workspace". Rename, or keep "workspace" as the product's word? (architecture question 1) | Phase 2 settings screens |
| D-12 | When the ON/OFF settings at organization, email-account, team and user level disagree, which wins? (architecture question 2) | Phase 2: the settings levels |

D-9 (the look of the app and the sign-in screens) was settled on 2026-10-07: the glass design is used everywhere. See [design.md](design.md).

---

## Done: foundation

- [x] Repo split into `frontend/` (React) and `backend/` (FastAPI); the imported Node/Express and PostgreSQL scaffold removed
- [x] All Replit-specific files, packages and settings removed; runs locally on Windows, macOS and Linux
- [x] One-command development: `pnpm dev` (MySQL, migrations, API, web app); `scripts/tasks.mjs`
- [x] Dedicated local MySQL with development and test databases
- [x] Tables and first migration: users, workspaces, members, sessions, reset tokens, audit events
- [x] Sign up, sign in, sign out, remember me (FR-1)
- [x] Change password; password reset by emailed link (waits on D-8 to be usable)
- [x] Rate limits on sign-in, sign-up and reset
- [x] Create a workspace; owner role; workspace settings (FR-2)
- [x] Team list and roles page from real data
- [x] Session list and "sign out the others"
- [x] Audit log of sign-ins and changes
- [x] Web app: sign-in screens wired to the API, route protection, real name and workspace in the shell
- [x] Every sample dataset removed; unbuilt screens show honest empty states
- [x] Glass design across the app and the sign-in screens; type and controls enlarged; responsive at desktop, tablet and phone widths
- [x] Backend tests (30) against real MySQL; strict typecheck; production build
- [x] Project documents: PRD, architecture, rules, design, tasks, memory

---

## Phase 1: Core Email & Unified Inbox

Goal: a team can connect its mailboxes, read everything in one inbox, and answer from it.

### 1.0 Groundwork

- [ ] **P1-01** Redis and Celery in the backend (`worker.py`, `tasks/`): worker and beat processes started by `pnpm dev`, the queues `sync`, `send` and `maintenance`, and one test task · M · needs D-3
- [ ] **P1-02** Move the sign-in rate limits from API memory to Redis · S · after P1-01
- [x] **P1-03** Encryption for stored mailbox credentials, key from the environment (AES-GCM/Fernet) · S · architecture question 8
- [ ] **P1-04** Job that removes expired sessions and used reset tokens · XS · after P1-01
- [ ] **P1-05** Internal events (`backend/app/events/`): one place where "message received" and "message sent" are announced, so rules, AI, notifications and webhooks can subscribe in later phases without changing sync · S · after P1-01

### 1.1 Connect email accounts (FR-3)

- [x] **P1-10** Table and migration for email accounts · S
- [x] **P1-11** Email provider adapter interface in `backend/app/providers/`, with adapters registered by name, plus a test double used only by the automated tests · M
- [x] **P1-12** IMAP/SMTP: enter server details, verify the login, store encrypted · M · after P1-03
- [x] **P1-13** Gmail: Google sign-in, consent, token storage and refresh · L · done 2026-10-08 and verified with two real Gmail mailboxes; still to check by hand: a reply sent from the app appears in Gmail's Sent
- [ ] **P1-14** Microsoft 365: Microsoft sign-in, consent, token storage and refresh · L · needs D-7
- [x] **P1-15** API: list, connect, disconnect, sync now, status · M
- [x] **P1-16** Screens: Email accounts, Add account, the connect screens, with statuses and plain-language errors · M
- [x] **P1-17** Audit events for connecting and disconnecting · XS

### 1.2 Sync (FR-4)

- [x] **P1-20** Tables and migration: folders, conversations, messages, recipients, attachments · M · architecture question 7
- [x] **P1-21** Import job / sync engine: page through a mailbox newest first, safe to re-run · L
- [x] **P1-22** Threading: Message-ID, `References`, and `In-Reply-To` with subject normalization · M
- [~] **P1-23** Keep in sync: Gmail history (done 2026-10-08, inbox only), Microsoft Graph delta, IMAP polling · L · needs D-5
- [ ] **P1-24** Write changes back to the provider (read, star, archive, delete, label) with retries · L
- [ ] **P1-25** Store and serve attachments · M · needs D-4
- [x] **P1-26** Sync health: status and last sync per mailbox, retry with backoff, error shown to the user · M

### 1.3 Unified inbox (FR-5)

- [x] **P1-30** API: list conversations with paging and filters (mailbox, read, starred, label, view) · M
- [x] **P1-31** Inbox screen and the Drafts, Sent, Starred, Archive and Trash views · L
- [x] **P1-32** Select several and archive, delete or mark read · M
- [ ] **P1-33** New mail appears without a manual refresh · S

### 1.4 Conversation view (FR-6)

- [x] **P1-40** API: one conversation with its messages and attachments · S
- [ ] **P1-41** Sanitize HTML email on the server and render it isolated from the app; remote images off until the user asks · M
- [x] **P1-42** Conversation screen: thread, attachments, mark read on open, archive, delete, star · M

### 1.5 Compose and send (FR-7)

- [x] **P1-50** Send through SMTP adapter with live delivery, threading headers, audit logging · L
- [x] **P1-51** Reply, reply all with correct headers and quoting · M
- [ ] **P1-52** Drafts: save, list, edit, delete · M
- [ ] **P1-53** Attachment upload · M
- [x] **P1-54** Compose screen (sending mailbox, To, Cc, Bcc, body) and inline thread reply · L

### 1.6 Search, labels, folders, status (FR-8, FR-9)

- [ ] **P1-60** Search across mailboxes, wired to the Search page and the top bar · M
- [ ] **P1-61** Labels: create, rename, colour, remove; apply to conversations; reflect at the provider · L
- [ ] **P1-62** Folders: list per mailbox and open one · M
- [ ] **P1-63** Email status · S to M · needs D-2

### 1.7 Finish the phase

- [ ] **P1-70** Real numbers and a "Needs your attention" list on the overview (FR-10) · S
- [ ] **P1-71** Security review of everything that handles mail and credentials · M
- [ ] **P1-72** Browser checks of the whole flow at desktop, tablet and phone widths · S
- [ ] **P1-73** Remove styles in `index.css` that the finished screens do not use · S

Suggested order: 1.0, then IMAP (P1-10 to P1-12, P1-15, P1-16) to get one provider working end to end through 1.2 to 1.5, then Gmail and Microsoft 365, then 1.6 and 1.7. IMAP first because it needs no outside approval.

---

## Phase 2: Teams & Automation

Detail each item into tasks before the phase starts. PRD questions 2, 6 and 7 and decisions D-11 and D-12 must be answered first. The design is in [architecture.md](architecture.md) sections 5.2, 5.4 and 5.5.

- [x] Invitations with role, shareable URL, token verification, accept flow, and cancellation (FR-2)
- [x] Change a member's role; remove a member with last owner protection
- [x] Permissions for workspace actions and roles enforced in the API for all five roles (owner, admin, manager, agent, viewer)
- [x] Multi-workspace support and workspace switching
- [ ] Teams: groups of users inside an organization; assign a conversation to a team (FR-2, FR-11)
- [ ] Assignment to a user or a team, and the unassigned queue (FR-11)
- [ ] Internal notes (FR-12)
- [ ] Notifications and notification rules; queue `notifications` (FR-13)
- [x] Rule engine in `backend/app/automation/`: conditions and actions, test a rule, run history, retries, one run per email (FR-14). Done 2026-10-09 on the in-process loop; the only trigger so far is new mail, and the `automation` queue waits for Redis + Celery
- [ ] Scheduled actions; queue `scheduled` (FR-15)
- [ ] Webhooks with signed deliveries, retries and a delivery log; queue `webhooks` (FR-15)
- [ ] The ON/OFF switches at organization, email-account, team and user level, and the one resolver every job asks (FR-18) · needs D-12
- [ ] Contacts and templates (FR-19), if wanted in this phase

## Phase 3: AI Features

PRD question 8 (which AI provider) must be answered first. The design is in [architecture.md](architecture.md) sections 5.3 and 6.2.

- [ ] AI provider interface in `backend/app/ai/` and the first provider adapter; queue `ai`
- [ ] AI provider and credentials per organization; prompts; usage tracking and limits (FR-18)
- [ ] Conversation summaries (FR-16)
- [ ] Suggested replies (FR-16)
- [ ] Classification (FR-16)
- [ ] Priority and sentiment (FR-16)
- [ ] Smart routing suggestions (FR-16)
- [ ] On/off settings for each AI feature at all four levels (FR-18)

## Phase 4: Auto-Reply & Smart Workflows

- [ ] Auto-reply rules (FR-17)
- [ ] Approval before an automatic reply is sent (FR-17, FR-18)
- [ ] Auto-reply workflows (FR-17)

## Phase 5: SaaS Billing, Analytics & Enterprise Features

Not specified by the proposal beyond the title. PRD questions 9 to 11 come first.

- [ ] Plans, subscriptions and payment (FR-21)
- [ ] Usage against limits (FR-20)
- [ ] Analytics (FR-20)
- [ ] Enterprise features: to be defined (FR-21)

---

## Before the first public release (any phase)

- [ ] Choose hosting and deploy (architecture question 10)
- [ ] Automated checks on every push: typecheck, build, backend tests
- [ ] HTTPS everywhere and security headers
- [ ] Monitoring and error tracking
- [ ] Dependency scanning
- [ ] Decide the product name (PRD question 1), email verification (question 2) and sign-in with Google or Microsoft (question 3)
- [ ] Performance and scale targets, then test against them (PRD question 11)

## Housekeeping

- [ ] **H-1** Delete `artifacts/mockup-sandbox`, a leftover preview tool from the import that nothing uses (the AI agent was not permitted to delete it)
- [ ] **H-2** Remove the unused ready-made components in `frontend/src/components/ui/` and their packages, once it is clear which ones the real screens need
