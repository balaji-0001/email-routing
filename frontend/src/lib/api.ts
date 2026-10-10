// The one place the app talks to the backend. Every call returns the payload
// from the response's `data` field or throws an ApiError.

export type User = {
  id: number;
  email: string;
  first_name: string;
  last_name: string;
  name: string;
  timezone: string | null;
  created_at: string;
  password_changed_at: string;
};

export type Workspace = {
  id: number;
  name: string;
  domain: string | null;
  timezone: string;
  allow_invitations: boolean;
  created_at: string;
};

export type Role = 'owner' | 'admin' | 'manager' | 'agent' | 'viewer';

export type Me = {
  user: User;
  workspace: Workspace | null;
  role: Role | null;
  password_reset_available: boolean;
};

export type Member = {
  id: number;
  user_id: number;
  name: string;
  email: string;
  role: Role;
  is_you: boolean;
  joined_at: string;
  last_active_at: string | null;
};

export type Invitation = {
  id: number;
  email: string;
  role: Role;
  invited_by_name: string | null;
  invite_url: string;
  expires_at: string;
  created_at: string;
};

export type PublicInvitation = {
  workspace_name: string;
  inviter_name: string | null;
  email: string;
  role: Role;
  is_expired: boolean;
};

export type MyWorkspace = {
  id: number;
  name: string;
  role: Role;
  is_current: boolean;
  created_at: string;
};

export type EmailAccount = {
  id: number;
  provider: 'imap' | 'gmail' | 'microsoft';
  /** 'oauth' when the mailbox was connected by signing in at the provider. */
  auth_type: 'basic' | 'oauth';
  email_address: string;
  display_name: string;
  status: 'connected' | 'syncing' | 'error' | 'needs_reconnect';
  incoming_host: string;
  outgoing_host: string;
  last_sync_at: string | null;
  last_error: string | null;
  message_count: number;
  /** Older mail being brought in after connecting. */
  import_state: 'pending' | 'running' | 'done';
  import_total: number | null;
  /** Open to the whole workspace, or limited to chosen people. */
  access_mode: 'everyone' | 'restricted';
  /** What the signed-in person may do with this mailbox. */
  my_permission: 'read' | 'send';
  created_at: string;
};

export type MailboxPermission = 'read' | 'send';
export type MailboxAccessMember = { user_id: number; name: string; email: string; role: Role; always: boolean; permission: MailboxPermission | null };
export type MailboxAccessRole = { role: Role; name: string; description: string; always: boolean; permission: MailboxPermission | null; people: number };
export type MailboxAccess = { access_mode: 'everyone' | 'restricted'; roles: MailboxAccessRole[]; members: MailboxAccessMember[] };

export type EmailProviders = {
  /** False until the server has Google sign-in set up. */
  google_oauth: boolean;
  google_redirect_uri: string;
};

export type ConnectAccountData = {
  provider: 'imap' | 'gmail' | 'microsoft';
  email_address: string;
  display_name?: string;
  incoming_host: string;
  incoming_port?: number;
  incoming_security?: 'ssl' | 'starttls';
  incoming_username: string;
  incoming_password: string;
  outgoing_host: string;
  outgoing_port?: number;
  outgoing_security?: 'ssl' | 'starttls';
  outgoing_username: string;
  outgoing_password: string;
};

export type Recipient = {
  kind: 'to' | 'cc' | 'bcc';
  email: string;
  name: string | null;
};

export type Attachment = {
  id: number;
  filename: string;
  content_type: string;
  file_size: number;
};

export type Message = {
  id: number;
  direction: 'inbound' | 'outbound';
  sender_name: string | null;
  sender_email: string;
  subject: string;
  body_text: string | null;
  body_html: string | null;
  sent_at: string;
  is_read: boolean;
  is_starred: boolean;
  /** The email's own Message-ID; a reply points at it. */
  provider_message_id: string | null;
  recipients: Recipient[];
  attachments: Attachment[];
};

export type LabelColor = 'blue' | 'green' | 'amber' | 'red' | 'violet' | 'teal' | 'grey';
export type Label = { id: number; name: string; color: LabelColor };
export type LabelWithCount = Label & { conversation_count: number };
export type ConversationStatus = 'open' | 'pending' | 'closed';
export type Priority = 'low' | 'normal' | 'high' | 'urgent';
export type MailCounts = { inbox_unread: number; inbox_unread_by_account: Record<string, number> };
export type SyncMailbox = { email_address: string; state: 'importing' | 'done' | 'problem'; stored: number; total: number | null };
export type SyncSummary = {
  state: 'none' | 'syncing' | 'complete' | 'attention';
  stored: number;
  total: number | null;
  percent: number | null;
  mailboxes: SyncMailbox[];
  last_synced_at: string | null;
};
export type Overview = {
  sync: SyncSummary;
  connected_inboxes: number;
  inboxes_needing_attention: number;
  messages_stored: number;
  open_conversations: number;
  waiting_on_team: number;
  unread_conversations: number;
  needs_attention: Conversation[];
};
export type OutgoingAttachment = { filename: string; content_type: string; content_base64: string };

export type Conversation = {
  id: number;
  email_account_id: number;
  account_email: string;
  account_provider: string;
  subject: string;
  snippet: string | null;
  is_read: boolean;
  is_starred: boolean;
  is_archived: boolean;
  is_deleted: boolean;
  status: ConversationStatus;
  last_message_at: string;
  last_sender_name: string | null;
  last_sender_email: string | null;
  has_attachments: boolean;
  message_count: number;
  labels: Label[];
  assignee_user_id: number | null;
  assignee_name: string | null;
  priority: Priority;
};

export type Note = { id: number; conversation_id: number; author_user_id: number | null; author_name: string | null; is_yours: boolean; body: string; created_at: string };
export type RecentNote = Note & { conversation_subject: string };
export type ComposeMode = 'new' | 'reply' | 'replyAll' | 'forward';
export type DraftBody = {
  email_account_id: number;
  mode: ComposeMode;
  conversation_id: number | null;
  in_reply_to: string | null;
  forward_of_message_id: number | null;
  to: string;
  cc: string;
  bcc: string;
  subject: string;
  body_text: string;
};
export type SavedDraft = DraftBody & { id: number; account_email: string; updated_at: string };
export type AppNotification = { id: number; kind: 'assigned' | 'mentioned' | 'note' | 'rule' | 'reminder'; title: string; body: string | null; conversation_id: number | null; actor_name: string | null; is_read: boolean; created_at: string };
export type Notifications = { unread: number; items: AppNotification[] };
export type Contact = { email: string; name: string | null; received: number; sent: number; last_message_at: string | null };
export type Template = { id: number; name: string; subject: string; body: string; created_by_name: string | null; updated_at: string };

export type RuleConditions = { account_id: number | null; sender: string; recipient: string; subject: string; body: string; has_attachments: boolean | null; ai_priority: 'low' | 'medium' | 'high' | null };
export type RuleAction =
  | { type: 'add_label'; label_id: number }
  | { type: 'set_priority'; value: Priority }
  | { type: 'set_status'; value: ConversationStatus }
  | { type: 'assign'; user_id: number }
  | { type: 'assign_in_turn'; user_ids: number[] }
  | { type: 'flag' }
  | { type: 'archive' }
  | { type: 'notify'; user_id: number };
export type RuleBody = { name: string; enabled: boolean; conditions: RuleConditions; actions: RuleAction[]; trigger: 'new_mail' | 'waiting'; wait_hours: number | null };
export type Reminder = { id: number; conversation_id: number; subject: string; account_email: string; due_at: string; note: string; only_if_no_reply: boolean; status: 'waiting' | 'done' | 'answered' | 'cancelled'; created_at: string; finished_at: string | null };
export type Rule = RuleBody & { id: number; position: number; run_count: number; failed_count: number; last_run_at: string | null; created_by_name: string | null; summary: string };
export type RuleRun = { id: number; rule_id: number; rule_name: string; conversation_id: number; subject: string; status: 'done' | 'failed' | 'gave_up'; attempts: number; done: string[]; error: string | null; created_at: string };
export type RuleTest = { checked: number; matches: { conversation_id: number; subject: string; sender: string; sent_at: string }[] };
export type AutomationSettings = { enabled: boolean; mailboxes: { account_id: number; email_address: string; enabled: boolean }[] };
export type AutomationSummary = { enabled: boolean; rules_total: number; rules_on: number; runs_today: number; failed_today: number; rules: Rule[]; recent: RuleRun[] };

export type AiAnalysis = {
  id: number; conversation_id: number; message_id: number; account_email: string; subject: string; sender: string;
  status: 'pending' | 'working' | 'done' | 'skipped' | 'failed' | 'gave_up'; attempts: number;
  summary: string | null; intent: string | null; requested_actions: string[]; reply_required: boolean | null;
  priority: 'low' | 'medium' | 'high' | null; confidence: number | null; grounded: boolean | null; risk_flags: string[]; hold_reasons: string[];
  reason: string | null; error: string | null; reply_id: number | null; reply_status: string | null; created_at: string; finished_at: string | null;
};
export type AiReply = {
  id: number; conversation_id: number; account_email: string; to_email: string; subject: string; body: string; body_hash: string; edited: boolean; auto_sent: boolean; auto_note: string[];
  status: 'pending' | 'sending' | 'sent' | 'rejected' | 'failed'; error: string | null; decided_by_name: string | null; provider_message_id: string | null;
  created_at: string; decided_at: string | null; sent_at: string | null; can_send: boolean; analysis: AiAnalysis;
};
export type AiSettings = { configured: boolean; model: string; enabled: boolean; paused: boolean; business_info: string; auto_send_low: boolean; auto_send_medium: boolean; daily_limit: number; auto_sent_today: number; mailboxes: { account_id: number; email_address: string; enabled: boolean; auto_send: boolean }[] };
export type AiStatus = { configured: boolean; enabled: boolean; paused: boolean; waiting_for_approval: number; waiting_for_analysis: number; working_now: number; analysed_today: number; failed_today: number; sent_today: number; auto_sent_today: number };

export type AnalyticsDay = { day: string; received: number; sent: number; rule_runs: number; rule_failures: number };
export type Analytics = {
  days: number; daily: AnalyticsDay[];
  totals: { received: number; sent: number; rule_runs: number; rule_failures: number };
  replies: { count: number; median_hours: number | null; within_a_day: number };
  now: { open: number; pending: number; closed: number; unassigned: number; unread: number; urgent: number; high: number };
  workload: { name: string; open: number }[];
  top_senders: { email: string; name: string | null; received: number }[];
  mailboxes: { email_address: string; received: number; sent: number }[];
  rules: { id: number; name: string; enabled: boolean; runs: number; failed: number; last_run_at: string | null }[];
  ai: { analysed: number; skipped: number; failed: number; waiting: number; reply_needed: number; low: number; medium: number; high: number; drafts_waiting: number; sent_by_people: number; sent_automatically: number; rejected: number };
};

export type ConversationFilters = {
  view?: string;
  account_id?: number;
  search?: string;
  unread?: boolean;
  starred?: boolean;
  has_attachments?: boolean;
  status?: ConversationStatus;
  label_id?: number;
  /** 'me', 'none' or a user id. */
  assignee?: string;
  priority?: Priority;
  limit?: number;
  offset?: number;
};

export type ConversationDetail = {
  conversation: Conversation;
  messages: Message[];
  notes: Note[];
};

export type SendMessageData = {
  account_id: number;
  to: string[];
  subject: string;
  body_text?: string;
  body_html?: string;
  cc?: string[];
  bcc?: string[];
  conversation_id?: number;
  in_reply_to?: string;
  attachments?: OutgoingAttachment[];
  /** Forwarding: the message whose attachments go along. */
  forward_attachments_of?: number;
  /** The saved draft this was written in; it is removed once sent. */
  draft_id?: number;
};

export type SessionInfo = {
  id: number;
  current: boolean;
  user_agent: string | null;
  ip_address: string | null;
  created_at: string;
  last_used_at: string;
  expires_at: string;
};

export type AuditEvent = {
  id: number;
  action: string;
  summary: string;
  actor_name: string | null;
  actor_is_you: boolean;
  ip_address: string | null;
  created_at: string;
};

export type FieldError = { field: string; message: string };

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly details: FieldError[] = [],
  ) {
    super(message);
  }

  /** The message for one form field, if the server complained about it. */
  field(name: string): string | undefined {
    return this.details.find((detail) => detail.field === name)?.message;
  }
}

const BASE = `${import.meta.env.BASE_URL.replace(/\/$/, '')}/api/v1`;

let onSignedOut: () => void = () => {};

/** Called when the server says the session is no longer valid. */
export function setSignedOutHandler(handler: () => void) {
  onSignedOut = handler;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(BASE + path, {
      method,
      credentials: 'same-origin',
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, 'NETWORK', 'Could not reach the server. Check your connection and try again.');
  }

  const payload = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) {
    const error = payload?.error;
    if (response.status === 401 && error?.code === 'NOT_SIGNED_IN') onSignedOut();
    throw new ApiError(response.status, error?.code ?? 'REQUEST_FAILED', error?.message ?? 'Something went wrong. Please try again.', error?.details ?? []);
  }
  return (payload?.data ?? null) as T;
}

const get = <T>(path: string) => request<T>('GET', path);
const post = <T>(path: string, body?: unknown) => request<T>('POST', path, body);
const patch = <T>(path: string, body: unknown) => request<T>('PATCH', path, body);
const del = <T>(path: string) => request<T>('DELETE', path);

export const api = {
  options: () => get<{ password_reset_available: boolean }>('/auth/options'),
  me: () => get<Me>('/auth/me'),
  register: (body: { email: string; password: string; name: string; timezone?: string }) => post<Me>('/auth/register', body),
  login: (body: { email: string; password: string; remember: boolean }) => post<Me>('/auth/login', body),
  logout: () => post<null>('/auth/logout'),
  forgotPassword: (email: string) => post<null>('/auth/password/forgot', { email }),
  resetPassword: (body: { token: string; password: string }) => post<null>('/auth/password/reset', body),
  changePassword: (body: { current_password: string; new_password: string }) => post<null>('/auth/password/change', body),
  sessions: () => get<SessionInfo[]>('/auth/sessions'),
  revokeOtherSessions: () => post<{ ended: number }>('/auth/sessions/revoke-others'),
  updateProfile: (body: { first_name: string; last_name: string; timezone: string | null }) => patch<User>('/users/me', body),
  createWorkspace: (name: string) => post<Workspace>('/workspaces', { name }),
  updateWorkspace: (body: Partial<Pick<Workspace, 'name' | 'domain' | 'timezone' | 'allow_invitations'>>) => patch<Workspace>('/workspace', body),
  members: () => get<Member[]>('/workspace/members'),
  updateMemberRole: (id: number, role: Role) => patch<Member>(`/workspace/members/${id}`, { role }),
  removeMember: (id: number) => del<null>(`/workspace/members/${id}`),
  invitations: () => get<Invitation[]>('/workspace/invitations'),
  createInvitation: (body: { email: string; role: Role }) => post<Invitation>('/workspace/invitations', body),
  revokeInvitation: (id: number) => del<null>(`/workspace/invitations/${id}`),
  viewInvitation: (token: string) => get<PublicInvitation>(`/auth/invitations/${token}`),
  acceptInvitation: (token: string) => post<Me>(`/auth/invitations/${token}/accept`),
  myWorkspaces: () => get<MyWorkspace[]>('/auth/workspaces'),
  switchWorkspace: (workspaceId: number) => post<Me>(`/auth/workspaces/${workspaceId}/switch`),
  emailAccounts: () => get<EmailAccount[]>('/email-accounts'),
  mailboxAccess: (id: number) => get<MailboxAccess>(`/email-accounts/${id}/access`),
  setMailboxAccess: (id: number, body: { access_mode: 'everyone' | 'restricted'; roles: { role: Role; permission: MailboxPermission }[]; members: { user_id: number; permission: MailboxPermission }[] }) =>
    request<MailboxAccess>('PUT', `/email-accounts/${id}/access`, body),
  emailProviders: () => get<EmailProviders>('/email-accounts/providers'),
  startGoogleConnect: () => post<{ authorization_url: string }>('/email-accounts/oauth/google/start'),
  connectEmailAccount: (body: ConnectAccountData) => post<EmailAccount>('/email-accounts/connect', body),
  syncEmailAccount: (id: number) => post<{ account_id: number; synced_messages: number; status: string; error?: string }>(`/email-accounts/${id}/sync`),
  syncAllEmailAccounts: () => post<{ synced_messages: number; errors: string[] }>('/email-accounts/sync-all'),
  disconnectEmailAccount: (id: number) => del<null>(`/email-accounts/${id}`),
  conversations: (params: ConversationFilters = {}) => {
    const q = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== '') q.set(key, String(value));
    }
    const qs = q.toString();
    return get<Conversation[]>(`/conversations${qs ? `?${qs}` : ''}`);
  },
  overview: () => get<Overview>('/conversations/overview'),
  drafts: () => get<SavedDraft[]>('/drafts'),
  createDraft: (body: DraftBody) => post<SavedDraft>('/drafts', body),
  updateDraft: (id: number, body: DraftBody) => request<SavedDraft>('PUT', `/drafts/${id}`, body),
  deleteDraft: (id: number) => del<null>(`/drafts/${id}`),
  addNote: (conversationId: number, body: string) => post<Note>(`/conversations/${conversationId}/notes`, { body }),
  deleteNote: (id: number) => del<null>(`/notes/${id}`),
  recentNotes: () => get<RecentNote[]>('/notes'),
  notifications: () => get<Notifications>('/notifications'),
  markNotificationsRead: (ids: number[] = []) => post<null>('/notifications/read', { ids }),
  contacts: (params: { search?: string; limit?: number; offset?: number } = {}) => {
    const q = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) if (value !== undefined && value !== '') q.set(key, String(value));
    return get<Contact[]>(`/contacts${q.toString() ? `?${q}` : ''}`);
  },
  templates: () => get<Template[]>('/templates'),
  createTemplate: (body: { name: string; subject: string; body: string }) => post<Template>('/templates', body),
  updateTemplate: (id: number, body: { name: string; subject: string; body: string }) => request<Template>('PUT', `/templates/${id}`, body),
  deleteTemplate: (id: number) => del<null>(`/templates/${id}`),
  mailCounts: () => get<MailCounts>('/conversations/counts'),
  labels: () => get<LabelWithCount[]>('/labels'),
  createLabel: (body: { name: string; color: LabelColor }) => post<Label>('/labels', body),
  updateLabel: (id: number, body: { name?: string; color?: LabelColor }) => patch<Label>(`/labels/${id}`, body),
  deleteLabel: (id: number) => del<null>(`/labels/${id}`),
  setConversationLabels: (id: number, label_ids: number[]) => request<Label[]>('PUT', `/conversations/${id}/labels`, { label_ids }),
  /** Where the browser downloads an attachment from. */
  attachmentUrl: (id: number) => `${BASE}/attachments/${id}`,
  conversation: (id: number) => get<ConversationDetail>(`/conversations/${id}`),
  updateConversation: (id: number, body: { is_read?: boolean; is_starred?: boolean; is_archived?: boolean; is_deleted?: boolean; status?: ConversationStatus; assignee_user_id?: number | null; priority?: Priority }) =>
    patch<Conversation>(`/conversations/${id}`, body),
  batchConversations: (body: { conversation_ids: number[]; action: string }) =>
    post<{ updated: number }>('/conversations/batch', body),
  sendMessage: (body: SendMessageData) => post<Message>('/messages/send', body),
  rules: () => get<Rule[]>('/automation/rules'),
  createRule: (body: RuleBody) => post<Rule>('/automation/rules', body),
  updateRule: (id: number, body: RuleBody) => request<Rule>('PUT', `/automation/rules/${id}`, body),
  toggleRule: (id: number, enabled: boolean) => patch<Rule>(`/automation/rules/${id}`, { enabled }),
  deleteRule: (id: number) => del<null>(`/automation/rules/${id}`),
  reorderRules: (rule_ids: number[]) => request<null>('PUT', '/automation/rules/order', { rule_ids }),
  testRule: (body: RuleBody) => post<RuleTest>('/automation/rules/test', body),
  ruleRuns: (ruleId?: number) => get<RuleRun[]>(`/automation/runs${ruleId ? `?rule_id=${ruleId}` : ''}`),
  automationSettings: () => get<AutomationSettings>('/automation/settings'),
  updateAutomationSettings: (body: { enabled?: boolean; mailboxes?: Record<number, boolean> }) => request<AutomationSettings>('PUT', '/automation/settings', body),
  runRulesOnRecent: (per_mailbox: number) => post<{ checked: number; runs: number }>('/automation/run-recent', { per_mailbox }),
  automationSummary: () => get<AutomationSummary>('/automation/summary'),
  emailPreference: () => get<{ available: boolean; enabled: boolean; address: string }>('/notifications/email'),
  setEmailPreference: (enabled: boolean) => request<{ available: boolean; enabled: boolean; address: string }>('PUT', '/notifications/email', { enabled }),
  reminders: (conversationId?: number) => get<Reminder[]>(`/reminders${conversationId ? `?conversation_id=${conversationId}` : ''}`),
  createReminder: (body: { conversation_id: number; due_at: string; note?: string; only_if_no_reply: boolean }) => post<Reminder>('/reminders', body),
  cancelReminder: (id: number) => del<null>(`/reminders/${id}`),
  analytics: (days: number) => get<Analytics>(`/analytics?days=${days}`),
  aiStatus: () => get<AiStatus>('/ai/status'),
  aiSettings: () => get<AiSettings>('/ai/settings'),
  updateAiSettings: (body: { enabled?: boolean; paused?: boolean; business_info?: string; mailboxes?: Record<number, boolean>; auto_send_low?: boolean; auto_send_medium?: boolean; daily_limit?: number; mailbox_auto_send?: Record<number, boolean> }) => request<AiSettings>('PUT', '/ai/settings', body),
  analyseRecent: (per_mailbox: number) => post<{ looked_at: number; queued: number; automated: number; already_done: number }>('/ai/analyse-recent', { per_mailbox }),
  writeWithAi: (body: { instruction: string; current: string; conversation_id?: number }) => post<{ subject: string; body: string }>('/ai/write', body),
  aiActivity: () => get<AiAnalysis[]>('/ai/activity'),
  aiForConversation: (id: number) => get<AiAnalysis | null>(`/ai/conversations/${id}`),
  analyseConversation: (id: number) => post<AiAnalysis>(`/ai/conversations/${id}/analyse`),
  aiReplies: (which: 'waiting' | 'sent' | 'rejected') => get<AiReply[]>(`/ai/replies?which=${which}`),
  editAiReply: (id: number, body: string) => request<AiReply>('PUT', `/ai/replies/${id}`, { body }),
  approveAiReply: (id: number, body_hash: string) => post<AiReply>(`/ai/replies/${id}/approve`, { body_hash }),
  rejectAiReply: (id: number) => post<AiReply>(`/ai/replies/${id}/reject`),
  auditEvents: (limit = 50) => get<AuditEvent[]>(`/workspace/audit-events?limit=${limit}`),
};
