# Product Requirements Document (PRD)

**Product:** Email Management SaaS (the interface currently carries the working name "Northstar")
**Version:** 1.0
**Date:** 2026-10-07
**Status:** Draft
**Sources:** [email-saas-project-proposal.pdf](email-saas-project-proposal.pdf) and [original-ui-brief.txt](original-ui-brief.txt). Where this document goes beyond them, it says so.

Related documents: [architecture.md](architecture.md) (how it is built), [tasks.md](tasks.md) (what to build next), [design.md](design.md) (how it looks), [rules.md](rules.md) (how to work in this repo), [memory.md](memory.md) (current state and decisions).

---

## Executive Summary

A web platform where a team connects its Gmail, Microsoft 365 and IMAP/SMTP mailboxes and works all of them from one shared, Outlook-like dashboard. On top of the unified inbox it adds team collaboration (roles, assignment, internal notes), rule-based automation, and AI assistance (summaries, suggested replies, classification, routing, auto-reply), each of which the customer can switch on or off at organization, mailbox, team and user level. It is a multi-tenant SaaS: every customer works in its own workspace. Today the accounts and workspace foundation is built; connecting mailboxes and everything that depends on mail is not.

---

## 1. Problem & Opportunity

### 1.1 Problem Statement

The proposal states the objective: let users connect multiple email accounts and manage all email from one dashboard. The problem behind it, inferred from that objective and the feature list, is that a team with several mailboxes on different providers has no single place to see what came in, who is dealing with it, and what still needs an answer. Triage, assignment and routine replies are done by hand in separate mail clients.

### 1.2 Opportunity

TBD: the proposal does not make a market case. Needed: who the first customers are and what they use today.

### 1.3 User Impact

One queue instead of several inboxes, a visible owner for every conversation, private team context next to customer mail, and repetitive sorting and replying handled by rules and AI that the team controls.

---

## 2. Users & Personas

The original brief names five roles. They are the personas until real customers say otherwise.

### Owner
- **Role:** Created the workspace; accountable for it.
- **Context:** Setting the product up, and later checking that it is under control.
- **Goals:** Connect the team's mailboxes, bring people in, decide which AI and automation features run.
- **Frustrations:** Tools that act on customer mail without a clear off switch.
- **Success looks like:** Every mailbox connected, every teammate in the right role, nothing automatic that was not approved.

### Admin
- **Role:** Runs the workspace day to day with the owner's permissions, except ownership itself.
- **Goals:** Manage accounts, members, labels, rules and settings.
- **Success looks like:** Can do all setup work without the owner.

### Manager
- **Role:** Leads a team of agents.
- **Context:** Watching the queue during the day.
- **Goals:** See what is unassigned or waiting, assign it, spot problems early.
- **Frustrations:** Not knowing who is handling a conversation.
- **Success looks like:** No conversation without an owner; workload visible per person.

### Agent
- **Role:** Reads and answers mail.
- **Context:** Working through assigned and shared conversations.
- **Goals:** Find what needs a reply, answer it well and quickly, leave context for teammates.
- **Frustrations:** Switching between mailboxes; two people answering the same message.
- **Success looks like:** One list to work from, with the history and notes in the same place.

### Viewer
- **Role:** Read-only access.
- **Goals:** Follow conversations without being able to change or send anything.

---

## 3. Goals & Success Metrics

The proposal's goal: "Create a single platform that combines Email Management + Team Collaboration + AI + Automation into one scalable SaaS product."

No measurable targets have been set. TBD: targets and timeframes from the product owner. The measures below are suggestions, not agreed.

| Goal | Suggested metric | Target | Timeframe |
|------|------------------|--------|-----------|
| Teams adopt the shared inbox | Workspaces with at least one connected mailbox and a reply sent in the last 7 days | TBD | TBD |
| Setup is easy | Time from sign-up to first synced message | TBD | TBD |
| Nothing is left unanswered | Share of conversations with an owner; time to first reply | TBD | TBD |
| Automation and AI are trusted | Share of workspaces with at least one rule or AI feature switched on | TBD | TBD |

**North Star Metric:** TBD. Candidate: conversations answered through the platform per week.

---

## 4. Scope

### 4.1 In Scope for the first usable release (foundation plus proposal Phase 1)

1. Accounts: sign up, sign in, sign out, password change and reset. **Built.**
2. Workspaces: create, settings, team list, fixed roles, audit log. **Built.**
3. Connect multiple Gmail, Microsoft 365 and IMAP/SMTP mailboxes.
4. Keep connected mailboxes in sync.
5. Unified inbox across all connected mailboxes.
6. Conversation view.
7. Send, reply, reply all, forward, attachments.
8. Search, filters, labels, folders and email status.

### 4.2 Out of Scope for the first usable release

- Team invitations, assignment, internal notes, notifications, automation (Phase 2).
- All AI features (Phase 3) and auto-reply (Phase 4).
- Billing, analytics, enterprise features (Phase 5).
- Native mobile apps. The web app is responsive.
- Any sample or demo data in the product. Screens show real data or say that a feature is not available yet.

### 4.3 Future Phases (from the proposal)

| Phase | Theme |
|-------|-------|
| 1 | Core Email & Unified Inbox |
| 2 | Teams & Automation |
| 3 | AI Features |
| 4 | Auto-Reply & Smart Workflows |
| 5 | SaaS Billing, Analytics & Enterprise Features |

---

## 5. Functional Requirements

Priority: **P0** must be in the first usable release, **P1** strongly preferred for it, **P2** nice to have, **P3** a later phase. Each requirement also names its proposal phase. Checked boxes are built and covered by automated tests. Requirements for phases 2 to 5 are deliberately coarse and must be detailed before their phase starts.

### FR-1: Accounts and sign-in
**Priority:** P0 · **Phase:** Foundation · **Status:** Built
**Description:** People create an account with an email and password and sign in to use the product.

#### User Stories
- As a new user, I want to create an account with my work email so that I can start a workspace.
- As a returning user, I want to sign in, stay signed in on my own computer, and sign out so that my mail is not open to others.
- As a user who forgot their password, I want a reset link by email so that I can get back in.

#### Acceptance Criteria
- [x] Sign-up needs a name, a valid email and a password of at least 8 characters; an email that already has an account is refused.
- [x] A wrong password and an unknown email give the same message.
- [x] After 8 failed sign-ins in 15 minutes for one email from one address, further attempts are refused until the window passes.
- [x] "Remember me" keeps the session for 30 days; without it the session ends when the browser closes and after 24 hours at most.
- [x] Sign-out ends the session on the server, so a copied cookie stops working.
- [x] Changing the password signs out every other browser.
- [x] A reset link works once, expires after 60 minutes, and signs out every browser when used.
- [x] When outgoing email is not configured, the reset screen says so instead of pretending to send.
- [ ] Outgoing email is configured in a real environment (needs SMTP details).
- [ ] TBD: email address verification. Not built; see Open Questions.

#### Edge Cases
- Session expires while the app is open: the next request sends the person to sign-in and returns them to the page they were on.
- Two sign-ups for the same email at the same moment: one succeeds, the other is refused.

### FR-2: Workspaces, team and roles
**Priority:** P0 (foundation) / P3 (invitations and permissions, Phase 2) · **Status:** Foundation built
**Description:** A workspace is one customer's private space. Everything a team shares belongs to a workspace.

#### User Stories
- As a new user, I want to name my workspace so that my team has a shared home.
- As an owner or admin, I want to manage workspace details so that teammates see the right name and time zone.
- As an owner or admin, I want to invite teammates and give each a role so that they can only do what they should. (Phase 2)

#### Acceptance Criteria
- [x] A signed-in person without a workspace is asked to create one and cannot open the app until they do; the creator becomes its owner.
- [x] Owners and admins can change the workspace name, domain, default time zone and invitation setting; other roles cannot.
- [x] The team page lists the real members with role, join date and last activity.
- [x] One workspace can never read another workspace's members or audit log.
- [x] Sign-ins and changes to the workspace are recorded in an audit log that owners and admins can read.
- [ ] Invite a teammate by email with a role; accept, resend and cancel invitations. (Phase 2)
- [ ] Change a member's role; remove a member. (Phase 2)
- [ ] Teams: owners and admins group members into teams; a conversation can be assigned to a team; a team is one of the four levels at which AI and automation are switched on or off. (Phase 2)
- [ ] Permission matrix for Owner, Admin, Manager, Agent and Viewer covering mail actions. (Phase 2)

#### Edge Cases
- TBD: one person in several workspaces. The data model allows it; there is no switcher. See Open Questions.

### FR-3: Connect email accounts
**Priority:** P0 · **Phase:** 1 · **Status:** Not built
**Description:** A workspace connects any number of Gmail, Microsoft 365 and IMAP/SMTP mailboxes.

#### User Stories
- As an owner or admin, I want to connect a mailbox by signing in with Google or Microsoft, or by entering IMAP and SMTP details, so that its mail appears in the shared inbox.
- As an owner or admin, I want to see each mailbox's status so that I know sync is healthy.

#### Acceptance Criteria
- [ ] Gmail and Google Workspace connect through Google sign-in; Outlook and Microsoft 365 through Microsoft sign-in; any other mailbox through IMAP and SMTP server details that are tested before saving.
- [ ] A workspace can hold several mailboxes, including several from one provider.
- [ ] Each mailbox shows address, provider, status, last sync time and number of messages synced.
- [ ] Available actions: sync now, disconnect, settings.
- [ ] Passwords and provider tokens are stored encrypted and never shown again.
- [ ] A failed connection says why in plain words (wrong password, access refused, server not reachable).

#### Edge Cases
- Access revoked at the provider: the mailbox is marked as needing reconnection, sync stops, mail already synced stays.
- The same mailbox connected twice in one workspace: refused.

### FR-4: Mail sync
**Priority:** P0 · **Phase:** 1 · **Status:** Not built
**Description:** Connected mailboxes stay in step with the provider in both directions.

#### Acceptance Criteria
- [ ] After connecting, existing mail is imported. TBD: how far back.
- [ ] New mail appears without a manual refresh. TBD: maximum delay.
- [ ] Read, star, archive, delete and label changes made in the product reach the provider, and changes made elsewhere reach the product.
- [ ] A failed sync is retried, and a mailbox that keeps failing shows an error status.

#### Edge Cases
- Very large mailbox: the import runs in the background and the inbox is usable while it runs.

### FR-5: Unified inbox
**Priority:** P0 · **Phase:** 1 · **Status:** Not built
**Description:** One list of conversations from every connected mailbox.

#### User Stories
- As an agent, I want one list of everything that came in, so that I do not check mailboxes one by one.

#### Acceptance Criteria
- [ ] Each row shows the mailbox and provider, sender, subject, preview, time, read state, star, labels and an attachment marker.
- [ ] Views for inbox, drafts, sent, starred, archive and trash.
- [ ] Filter by mailbox, read state, label and priority; sort by date.
- [ ] Select several conversations and archive, delete or mark them read in one action.
- [ ] Long lists load in pages or by scrolling.
- [ ] A view with no conversations says so; it never shows placeholder mail.

### FR-6: Conversation view
**Priority:** P0 · **Phase:** 1 · **Status:** Not built

#### Acceptance Criteria
- [ ] Shows the whole thread in order with sender, recipients, time and body.
- [ ] Attachments are listed and can be downloaded.
- [ ] Opening a conversation marks it read.
- [ ] Message content cannot run scripts or change the page around it.
- [ ] Archive, delete, star and label from the conversation.

### FR-7: Compose, reply, forward and attachments
**Priority:** P0 · **Phase:** 1 · **Status:** Not built

#### User Stories
- As an agent, I want to reply from the same mailbox the message came to, so that the customer sees the address they wrote to.

#### Acceptance Criteria
- [ ] New message with a choice of sending mailbox, To, Cc, Bcc, subject, formatted body and attachments.
- [ ] Reply, reply all and forward keep the thread together at the provider.
- [ ] Drafts are saved and appear under Drafts.
- [ ] Sent mail appears under Sent and in the provider's own sent folder.
- [ ] A failed send says why and keeps the draft.

### FR-8: Search and filters
**Priority:** P0 · **Phase:** 1 · **Status:** Not built

#### Acceptance Criteria
- [ ] Search across every connected mailbox by sender, recipient, subject and body.
- [ ] Search combines with the inbox filters.
- [ ] No matches gives a clear empty result.

### FR-9: Labels, folders and email status
**Priority:** P1 · **Phase:** 1 · **Status:** Not built

#### Acceptance Criteria
- [ ] Workspace labels can be created, renamed, coloured and removed, and applied to conversations in any mailbox.
- [ ] Folders from each provider are listed and can be opened.
- [ ] TBD: the set of email statuses (for example open, pending, closed). The proposal names "email status" without defining it.

### FR-10: Dashboard
**Priority:** P1 · **Phase:** 1 · **Status:** Partly built (team count and workspace activity are real)

#### Acceptance Criteria
- [x] Greets the signed-in person by name and shows real team size and recent workspace activity.
- [ ] Real counts for open conversations, conversations waiting on the team, and connected mailboxes.
- [ ] A list of conversations that need attention.

### FR-11: Assignment
**Priority:** P3 · **Phase:** 2 · **Status:** Not built
**Description:** Every conversation can have an owner. Managers assign; agents see what is theirs; a queue shows what has no owner.

### FR-12: Internal notes
**Priority:** P3 · **Phase:** 2 · **Status:** Not built
**Description:** Private notes on a conversation, visible only to the workspace and never sent to the customer.

### FR-13: Notifications
**Priority:** P3 · **Phase:** 2 · **Status:** Not built
**Description:** Tell a person about assignments, mentions and notes addressed to them. Rules can also raise notifications.

### FR-14: Automation rules
**Priority:** P3 · **Phase:** 2 · **Status:** Not built
**Description:** Rules of the form trigger, conditions, actions. From the proposal: rule-based filters, auto assignment, auto labels and priority, automatic notifications. From the brief: each rule shows name, trigger, conditions, actions, on/off and last run, and can be created, edited, deleted and tested.

### FR-15: Scheduled actions and webhooks
**Priority:** P3 · **Phase:** 2 · **Status:** Not built
**Description:** Actions that run at a set time (follow-ups, reminders), and outgoing webhooks that tell a customer's own systems when something happens in the workspace.

### FR-16: AI assistance
**Priority:** P3 · **Phase:** 3 · **Status:** Not built
**Description:** Email summarization, AI-generated replies, email classification, priority and sentiment detection, and smart routing. Suggestions are offered to a person; a person decides.

### FR-17: Auto-reply and smart workflows
**Priority:** P3 · **Phase:** 4 · **Status:** Not built
**Description:** AI-powered auto-reply and auto-reply workflows, governed by auto-reply rules and approval requirements.

### FR-18: Full control over AI and automation
**Priority:** P3 · **Phases:** 2 to 4 · **Status:** Not built
**Description:** The proposal requires that every AI and automation feature has an on/off setting at organization, email-account, team and user level.

#### Acceptance Criteria
- [ ] Each AI and automation feature can be switched on or off at each of the four levels. Working assumption: the most specific level wins. TBD: whether "off" at organization level must be final (question 12).
- [ ] The workspace sets its AI provider and API credentials, its AI prompts, auto-reply rules, approval requirements, notification rules, usage limits and automation rules.
- [ ] A feature that is off does nothing: no message content is sent to an AI provider and no rule runs.

### FR-19: Contacts and templates
**Priority:** P2 · **Phase:** Not placed by the proposal; both pages are in the original brief · **Status:** Not built
**Description:** Contacts gathers the people the team has emailed. Templates are reusable replies.

### FR-20: Usage, limits and analytics
**Priority:** P3 · **Phase:** 5 · **Status:** Not built
**Description:** What each workspace uses against its limits, and analytics on mail and team activity. TBD: which numbers.

### FR-21: Billing and enterprise features
**Priority:** P3 · **Phase:** 5 · **Status:** Not built
**Description:** TBD. The proposal names "SaaS Billing, Analytics & Enterprise Features" without detail.

---

## 6. Non-Functional Requirements

### 6.1 Performance
TBD: no targets set. Needed: acceptable time to open the inbox and a conversation, and the largest mailbox the product must handle.

### 6.2 Security & Privacy
- Multi-tenant isolation: one workspace must never see another's data. (Proposal: "multi-tenant, secure".) Enforced and tested for what is built.
- Passwords are stored as argon2id hashes; session and reset tokens are stored only as hashes.
- Mailbox passwords and provider tokens must be encrypted at rest when FR-3 is built.
- Ask each provider for the narrowest access that still does the job.
- Message content goes to an AI provider only when the workspace has switched that feature on (FR-18).
- TBD: compliance obligations such as GDPR. Depends on where customers are.

### 6.3 Scalability
The proposal asks for an architecture that is scalable and lets more email providers, AI providers and automation features be added later. TBD: expected number of workspaces, mailboxes and messages at launch and after a year.

### 6.4 Availability
TBD: uptime target.

### 6.5 Accessibility
Assumption, not stated by the proposal: readable contrast (WCAG 2.1 AA) and full keyboard access. The existing screens were built to this.

### 6.6 Compatibility
Responsive on desktop, tablet and mobile (original brief). TBD: supported browsers; assumed to be current Chrome, Edge, Firefox and Safari.

---

## 7. Integrations

| System | Type | Direction | Notes |
|--------|------|-----------|-------|
| Gmail / Google Workspace | OAuth 2.0 + Gmail API | Both | Phase 1. Needs a Google Cloud project owned by the product owner. |
| Microsoft 365 / Outlook | OAuth 2.0 + Microsoft Graph | Both | Phase 1. Needs an app registration owned by the product owner. |
| Any mailbox | IMAP + SMTP | Both | Phase 1. |
| Outgoing system email | SMTP | Out | Password reset now; invitations and notifications later. Not configured yet. |
| AI provider | API | Out | Phase 3. TBD: which provider or providers; credentials are set per workspace (FR-18). |
| Customer systems | Webhooks | Out | Phase 2. |
| Payment provider | TBD | Both | Phase 5. |

---

## 8. Data Model (High Level)

Built:
- **User:** email, name, time zone, password hash. Belongs to workspaces through memberships.
- **Workspace:** name, domain, time zone, invitation setting. The tenant.
- **Workspace member:** links a user to a workspace with one role (owner, admin, manager, agent, viewer).
- **Session:** a signed-in browser, tied to a user and the workspace they are working in.
- **Password reset token:** single-use, expiring.
- **Audit event:** who did what in a workspace, when, from which address.

Planned (names may change when designed in detail):
- **Team:** a group of members inside a workspace. Conversations can be assigned to it, and it is one of the four settings levels.
- **Email account:** a connected mailbox with provider, address, status and encrypted credentials. Belongs to a workspace.
- **Conversation:** a thread of messages in one mailbox, with read, star, status, priority and owner.
- **Message:** one email with sender, recipients, subject, body and time. Belongs to a conversation.
- **Attachment:** a file on a message.
- **Label, Folder:** ways to organize conversations.
- **Note:** an internal note on a conversation.
- **Notification:** something a user should know about.
- **Rule, Scheduled action, Webhook:** automation.
- **Contact, Template.**
- **AI and automation settings:** on/off and configuration at organization, mailbox, team and user level.

---

## 9. User Flows

### Flow 1: Sign up and create a workspace (built)
1. A visitor opens the app and is sent to sign-in.
2. They choose "Create an account" and enter name, work email and password.
3. They are signed in and asked to name their workspace.
4. They land on the overview as the workspace owner.

### Flow 2: Connect the first mailbox (Phase 1)
1. The owner opens Email accounts and chooses Gmail, Microsoft 365 or IMAP/SMTP.
2. They sign in at the provider and approve access, or enter server details.
3. The mailbox appears with status "Syncing"; existing mail starts to arrive.
4. The unified inbox fills in; the overview counts become real.

### Flow 3: Answer a conversation (Phase 1)
1. An agent opens the unified inbox and filters to what is unread.
2. They open a conversation and read the thread.
3. They reply from the mailbox the message arrived in, attach a file and send.
4. The reply is in Sent here and at the provider; the conversation leaves the unread view.

### Flow 4: Hand a conversation to a teammate (Phase 2)
1. A manager opens the assignment queue.
2. They assign a conversation to an agent and add an internal note.
3. The agent is notified and finds it under their assigned conversations.

### Flow 5: Automate a repeated step (Phase 2)
1. An admin creates a rule: when a message arrives and the subject contains a word, apply a label and assign it to a person.
2. They test the rule against existing mail and switch it on.
3. The rule's last run is visible; it can be switched off at any time.

---

## 10. Constraints & Assumptions

- **Technical constraints:** The proposal fixes the stack: React, Python + FastAPI, MySQL, Redis + Celery. The architecture must be multi-tenant and allow new email providers, AI providers and automation features later.
- **Product constraint:** No sample data in the product. A feature that is not built says "isn't available yet".
- **Timeline constraint:** None stated.
- **Resource constraint:** A small team working with AI coding agents.
- **Key assumptions (to validate):** first customers are small teams sharing support, sales or operations mailboxes; a person belongs to one workspace; English only; web only.

---

## 11. Open Questions

| # | Question | Owner | Due |
|---|----------|-------|-----|
| 1 | What is the product's name? "Northstar" is only the working name in the interface. | Product owner | Before public release |
| 2 | Must new accounts verify their email address before using the product? | Product owner | Before Phase 2 invitations |
| 3 | Should people be able to sign in with Google or Microsoft, in addition to a password? | Product owner | Before public release |
| 4 | How far back is mail imported when a mailbox is connected, and how quickly must new mail appear? | Product owner | Start of Phase 1 |
| 5 | What are the email statuses? | Product owner | Start of Phase 1 |
| 6 | Can one person belong to more than one workspace? | Product owner | Before Phase 2 |
| 7 | What exactly may each of the five roles do with mail? | Product owner | Start of Phase 2 |
| 8 | Which AI provider or providers are supported first? | Product owner | Start of Phase 3 |
| 9 | Pricing, plans and limits. | Product owner | Start of Phase 5 |
| 10 | Which countries are the first customers in, and which data-protection rules follow from that? | Product owner | Before public release |
| 11 | Performance, availability and scale targets (section 6). | Product owner | Before public release |
| 12 | When the on/off settings at organization, email-account, team and user level disagree, which wins: the most specific level, or does "off" higher up stay off? | Product owner | Before Phase 2 |
| 13 | The proposal says "organization"; the product says "workspace". Keep "workspace" or rename? | Product owner | Before Phase 2 |

---

## 12. Appendix

### Glossary
- **Workspace:** one customer's private space in the product; the tenant. The proposal says "organization".
- **Email account / mailbox:** one connected address at Gmail, Microsoft 365 or an IMAP/SMTP server.
- **Conversation:** a thread of related messages.
- **Unified inbox:** one list of conversations from every connected mailbox.
- **Assignment:** giving a conversation an owner.
- **Internal note:** a comment on a conversation that only the workspace can see.
- **Rule:** a trigger, conditions and actions that run automatically.
