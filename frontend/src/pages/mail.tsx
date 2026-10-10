// The mail screen: folders on the left, the message list in the middle, the
// reading pane on the right, and one command bar above them.
import { useEffect, useMemo, useRef, useState, type ChangeEvent, type FormEvent, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useLocation, useSearch } from 'wouter';
import {
  Archive, ArchiveRestore, ArrowLeft, Check, ChevronDown, CircleDot, Download, FileText, Flag, Forward, Inbox, ListTodo, Mail, MailOpen,
  Paperclip, Pencil, Plus, RefreshCw, Reply, ReplyAll, Search, Send, StickyNote, Tag, Trash2, Undo2, UserRound, X, type LucideIcon,
} from 'lucide-react';
import { Avatar, Button, EmptyState, PageHeading, SkeletonRows, useToast } from '@/components/kit';
import { AiInsight, AiWriter } from './ai';
import { ReminderControl } from './reminders';
import {
  api, ApiError, type Conversation, type ConversationFilters, type ConversationStatus, type EmailAccount, type Priority, type Label, type LabelColor,
  type ComposeMode, type Message, type Note, type OutgoingAttachment, type SavedDraft,
} from '@/lib/api';
import { dateTime, timeAgo } from '@/lib/format';
import { useSession } from '@/lib/session';

export const MAIL_PATHS = ['/inbox', '/starred', '/drafts', '/sent', '/archive', '/trash', '/search', '/folders', '/compose', '/assignment'];

const PAGE_SIZE = 50;
const MAX_ATTACH_BYTES = 18 * 1024 * 1024;

type Folder = { path: string; view: string; name: string; icon: LucideIcon };
const FOLDERS: Folder[] = [
  { path: '/inbox', view: 'inbox', name: 'Inbox', icon: Inbox },
  { path: '/starred', view: 'starred', name: 'Flagged', icon: Flag },
  { path: '/assignment', view: 'inbox', name: 'Unassigned', icon: ListTodo },
  { path: '/drafts', view: 'drafts', name: 'Drafts', icon: Pencil },
  { path: '/sent', view: 'sent', name: 'Sent Items', icon: Send },
  { path: '/archive', view: 'archive', name: 'Archive', icon: Archive },
  { path: '/trash', view: 'trash', name: 'Deleted Items', icon: Trash2 },
];

type Filter = 'all' | 'unread' | 'flagged' | 'files' | 'mine' | 'unassigned' | 'urgent' | 'high' | ConversationStatus;
const FILTERS: [Filter, string][] = [
  ['all', 'All'], ['unread', 'Unread'], ['flagged', 'Flagged'], ['files', 'Has attachments'],
  ['mine', 'Assigned to me'], ['unassigned', 'Unassigned'],
  ['open', 'Status: Open'], ['pending', 'Status: Pending'], ['closed', 'Status: Closed'],
  ['urgent', 'Priority: Urgent'], ['high', 'Priority: High'],
];
const PRIORITY_NAMES: Record<Priority, string> = { urgent: 'Urgent', high: 'High', normal: 'Normal', low: 'Low' };
const PRIORITY_ORDER: Priority[] = ['urgent', 'high', 'normal', 'low'];
const STATUSES: [ConversationStatus, string][] = [['open', 'Open'], ['pending', 'Pending'], ['closed', 'Closed']];
export const LABEL_COLORS: LabelColor[] = ['blue', 'green', 'amber', 'red', 'violet', 'teal', 'grey'];

/** What the composer is working on: a fresh message, an answer to `source`, or a draft saved earlier. */
type Draft = { mode: ComposeMode; source?: Message; saved?: SavedDraft; to?: string };

function fileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/** How Outlook dates a row: the time today, the weekday this week, otherwise the date. */
function rowDate(iso: string): string {
  const date = new Date(iso);
  const days = dayDistance(date);
  if (days === 0) return date.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
  if (days < 7) return date.toLocaleDateString(undefined, { weekday: 'short' });
  return date.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: date.getFullYear() === new Date().getFullYear() ? undefined : 'numeric' });
}

function dayDistance(date: Date): number {
  const start = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  return Math.round((start(new Date()) - start(date)) / 86400000);
}

function dateGroup(iso: string): string {
  const days = dayDistance(new Date(iso));
  if (days <= 0) return 'Today';
  if (days === 1) return 'Yesterday';
  if (days < 7) return 'This week';
  if (days < 14) return 'Last week';
  if (days < 31) return 'This month';
  return 'Older';
}

function htmlToText(html: string): string {
  const doc = new DOMParser().parseFromString(html, 'text/html');
  doc.querySelectorAll('style,script,head').forEach((node) => node.remove());
  return (doc.body.textContent ?? '').replace(/\n{3,}/g, '\n\n').trim();
}

function plainBody(message: Message): string {
  return message.body_text?.trim() || (message.body_html ? htmlToText(message.body_html) : '');
}

function person(name: string | null, email: string): string {
  return name ? `${name} <${email}>` : email;
}

function splitAddresses(value: string): string[] {
  return value.split(/[,;\n]/).map((part) => part.trim()).filter(Boolean);
}

function withPrefix(prefix: 'Re' | 'Fwd', subject: string): string {
  return new RegExp(`^${prefix}:`, 'i').test(subject.trim()) ? subject : `${prefix}: ${subject}`;
}

export function MailPage({ path }: { path: string }) {
  const [, navigate] = useLocation();
  const search = useSearch();
  const params = useMemo(() => new URLSearchParams(search), [search]);
  const client = useQueryClient();
  const toast = useToast();
  const { role } = useSession();
  const readOnly = role === 'viewer';

  const folder = FOLDERS.find((f) => f.path === path) ?? FOLDERS[0];
  const accountId = Number(params.get('a')) || undefined;
  const labelId = Number(params.get('label')) || undefined;
  const openId = Number(params.get('c')) || undefined;
  const query = params.get('q') ?? '';
  const searching = path === '/search' || Boolean(query);

  const [filter, setFilter] = useState<Filter>('all');
  const [checked, setChecked] = useState<number[]>([]);
  const [draft, setDraft] = useState<Draft | null>(path === '/compose' ? { mode: 'new', to: params.get('to') ?? undefined } : null);
  const [searchText, setSearchText] = useState(query);
  useEffect(() => setSearchText(query), [query]);
  useEffect(() => { if (path === '/compose') setDraft({ mode: 'new', to: params.get('to') ?? undefined }); }, [path]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => setChecked([]), [path, accountId, labelId, query, filter]);

  /** Change part of the address, keeping the rest. `null` removes a key. */
  function go(next: { path?: string; a?: number | null; label?: number | null; c?: number | null; q?: string | null }) {
    const p = new URLSearchParams(search);
    const set = (key: string, value: number | string | null | undefined) => {
      if (value === undefined) return;
      if (value === null || value === '') p.delete(key); else p.set(key, String(value));
    };
    set('a', next.a); set('label', next.label); set('c', next.c); set('q', next.q);
    const target = next.path ?? (path === '/compose' || path === '/folders' ? '/inbox' : path);
    const qs = p.toString();
    navigate(`${target}${qs ? `?${qs}` : ''}`);
  }

  const accounts = useQuery({ queryKey: ['email-accounts'], queryFn: api.emailAccounts });
  const labels = useQuery({ queryKey: ['labels'], queryFn: api.labels });
  const counts = useQuery({ queryKey: ['mail-counts'], queryFn: api.mailCounts, refetchInterval: 20000 });
  const drafts = useQuery({ queryKey: ['drafts'], queryFn: api.drafts });
  const team = useQuery({ queryKey: ['members'], queryFn: api.members });

  const filters: ConversationFilters = {
    view: labelId || searching ? 'all' : folder.view,
    account_id: accountId,
    label_id: labelId,
    search: query || undefined,
    unread: filter === 'unread' ? true : undefined,
    starred: filter === 'flagged' ? true : undefined,
    has_attachments: filter === 'files' ? true : undefined,
    status: filter === 'open' || filter === 'pending' || filter === 'closed' ? filter : undefined,
    assignee: path === '/assignment' || filter === 'unassigned' ? 'none' : filter === 'mine' ? 'me' : undefined,
    priority: filter === 'urgent' || filter === 'high' ? filter : undefined,
  };
  const draftsFolder = folder.view === 'drafts' && !labelId && !searching;
  const list = useInfiniteQuery({
    queryKey: ['conversations', filters],
    queryFn: ({ pageParam }) => api.conversations({ ...filters, limit: PAGE_SIZE, offset: pageParam }),
    initialPageParam: 0,
    getNextPageParam: (last, pages) => (last.length === PAGE_SIZE ? pages.length * PAGE_SIZE : undefined),
    refetchInterval: 20000,
    enabled: !draftsFolder,
  });
  const items = useMemo(() => list.data?.pages.flat() ?? [], [list.data]);

  const detail = useQuery({ queryKey: ['conversation', openId], queryFn: () => api.conversation(openId!), enabled: Boolean(openId) });
  const open = detail.data?.conversation;
  // Opening a conversation marks it read on the server; show that in the list and the counts.
  useEffect(() => {
    if (!detail.data) return;
    client.invalidateQueries({ queryKey: ['conversations'] });
    client.invalidateQueries({ queryKey: ['mail-counts'] });
    client.invalidateQueries({ queryKey: ['overview'] });
  }, [detail.data?.conversation.id]); // eslint-disable-line react-hooks/exhaustive-deps

  function refresh() {
    client.invalidateQueries({ queryKey: ['conversations'] });
    client.invalidateQueries({ queryKey: ['conversation'] });
    client.invalidateQueries({ queryKey: ['mail-counts'] });
    client.invalidateQueries({ queryKey: ['overview'] });
    client.invalidateQueries({ queryKey: ['labels'] });
  }
  const fail = (fallback: string) => (err: unknown) => toast(err instanceof ApiError ? err.message : fallback);

  // What the command bar acts on: the ticked rows, or else the open conversation.
  const targets = checked.length ? checked : openId ? [openId] : [];
  const targetRows = items.filter((c) => targets.includes(c.id));
  const allRead = targetRows.length > 0 && targetRows.every((c) => c.is_read);
  const allFlagged = targetRows.length > 0 && targetRows.every((c) => c.is_starred);

  const batch = useMutation({
    mutationFn: (action: string) => api.batchConversations({ conversation_ids: targets, action }),
    onSuccess: (_result, action) => {
      refresh();
      if (['archive', 'unarchive', 'delete', 'restore'].includes(action)) {
        setChecked([]);
        if (openId && targets.includes(openId)) go({ c: null });
        toast({ archive: 'Archived.', unarchive: 'Moved to Inbox.', delete: 'Moved to Deleted Items.', restore: 'Restored.' }[action] ?? 'Done.');
      }
    },
    onError: fail('Could not update the conversation.'),
  });
  const setLabels = useMutation({
    mutationFn: (ids: number[]) => api.setConversationLabels(openId!, ids),
    onSuccess: refresh,
    onError: fail('Could not change the labels.'),
  });
  const sync = useMutation({
    mutationFn: async (): Promise<{ synced_messages: number }> => (accountId ? api.syncEmailAccount(accountId) : api.syncAllEmailAccounts()),
    onSuccess: (result) => {
      refresh();
      client.invalidateQueries({ queryKey: ['email-accounts'] });
      toast(result.synced_messages ? `${result.synced_messages} new message${result.synced_messages === 1 ? '' : 's'}.` : 'Up to date.');
    },
    onError: fail('Could not check for new mail.'),
  });

  const assign = useMutation({
    mutationFn: (userId: number | null) => Promise.all(targets.map((id) => api.updateConversation(id, { assignee_user_id: userId }))),
    onSuccess: (_done, userId) => { refresh(); toast(userId === null ? 'Unassigned.' : 'Assigned.'); },
    onError: fail('Could not assign the conversation.'),
  });

  function startDraft(mode: ComposeMode) {
    if (mode === 'new') { setDraft({ mode }); return; }
    const messages = detail.data?.messages ?? [];
    const source = [...messages].reverse().find((m) => m.direction === 'inbound') ?? messages[messages.length - 1];
    if (source) setDraft({ mode, source });
  }
  function closeDraft() {
    setDraft(null);
    if (path === '/compose') navigate('/inbox');
  }

  const hasAccounts = (accounts.data?.length ?? 0) > 0;
  // Mailboxes this person may send from; some may be read-only for them.
  const sendable = (accounts.data ?? []).filter((a) => a.my_permission === 'send');
  const canReply = !readOnly && sendable.some((a) => a.id === open?.email_account_id);
  const title = labelId ? labels.data?.find((l) => l.id === labelId)?.name ?? 'Label' : searching ? 'Search results' : folder.name;
  const account = accounts.data?.find((a) => a.id === accountId);
  const showReading = Boolean(openId || draft);
  const inTrash = folder.view === 'trash' && !labelId && !searching;
  const inArchive = folder.view === 'archive' && !labelId && !searching;

  if (accounts.isSuccess && !hasAccounts) {
    return (
      <>
        <PageHeading eyebrow="MAIL" title="Mail" description="Work through conversations with your team, all in one place." />
        <EmptyState icon={Mail} title="No email accounts connected">
          Your team’s mail appears here once an email account is connected.
          <div style={{ marginTop: '1rem' }}>
            <Link href="/accounts/add" className="button button-primary" style={{ display: 'inline-flex', textDecoration: 'none' }}><Plus size={17} /> Connect an account</Link>
          </div>
        </EmptyState>
      </>
    );
  }

  return (
    <div className={`ol ${showReading ? 'ol-reading' : ''}`} data-testid="mail-screen">
      <div className="ol-ribbon" role="toolbar" aria-label="Mail commands">
        <button type="button" className="ol-cmd ol-cmd-primary" onClick={() => startDraft('new')} disabled={readOnly || sendable.length === 0} data-testid="button-new-mail"><Mail size={17} /> New mail</button>
        <span className="ol-sep" />
        <Cmd icon={Reply} label="Reply" onClick={() => startDraft('reply')} disabled={!open || !canReply} testId="button-reply" />
        <Cmd icon={ReplyAll} label="Reply all" onClick={() => startDraft('replyAll')} disabled={!open || !canReply} testId="button-reply-all" />
        <Cmd icon={Forward} label="Forward" onClick={() => startDraft('forward')} disabled={!open || !canReply} testId="button-forward" />
        <span className="ol-sep" />
        {inTrash ? (
          <Cmd icon={Undo2} label="Restore" onClick={() => batch.mutate('restore')} disabled={!targets.length || readOnly} testId="button-restore" />
        ) : (
          <>
            {inArchive
              ? <Cmd icon={ArchiveRestore} label="Move to Inbox" onClick={() => batch.mutate('unarchive')} disabled={!targets.length || readOnly} testId="button-unarchive" />
              : <Cmd icon={Archive} label="Archive" onClick={() => batch.mutate('archive')} disabled={!targets.length || readOnly} testId="button-archive" />}
            <Cmd icon={Trash2} label="Delete" onClick={() => batch.mutate('delete')} disabled={!targets.length || readOnly} testId="button-delete" />
          </>
        )}
        <span className="ol-sep" />
        <Cmd icon={allRead ? Mail : MailOpen} label={allRead ? 'Mark unread' : 'Mark read'} onClick={() => batch.mutate(allRead ? 'mark_unread' : 'mark_read')} disabled={!targets.length || readOnly} testId="button-read" />
        <Cmd icon={Flag} label={allFlagged ? 'Unflag' : 'Flag'} onClick={() => batch.mutate(allFlagged ? 'unstar' : 'star')} disabled={!targets.length || readOnly} testId="button-flag" />
        <Menu icon={CircleDot} label="Status" disabled={!targets.length || readOnly} testId="menu-status">
          {(close) => STATUSES.map(([value, name]) => (
            <button key={value} type="button" className="ol-menu-item" onClick={() => { batch.mutate(`status_${value}`); close(); }} data-testid={`status-${value}`}>
              <i className={`ol-status-dot ol-status-${value}`} /> {name}
              {targetRows.length > 0 && targetRows.every((c) => c.status === value) && <Check size={15} />}
            </button>
          )).concat(
            <div key="priority-title" className="ol-menu-title">Priority</div>,
            ...PRIORITY_ORDER.map((value) => (
              <button key={`p-${value}`} type="button" className="ol-menu-item" onClick={() => { batch.mutate(`priority_${value}`); close(); }} data-testid={`priority-${value}`}>
                <i className={`ol-priority-dot ol-priority-${value}`} /> {PRIORITY_NAMES[value]}
                {targetRows.length > 0 && targetRows.every((c) => c.priority === value) && <Check size={15} />}
              </button>
            )),
          )}
        </Menu>
        <Menu icon={Tag} label="Labels" disabled={!open || readOnly} testId="menu-labels">
          {() => <LabelPicker all={labels.data ?? []} applied={open?.labels ?? []} onChange={(ids) => setLabels.mutate(ids)} onCreated={refresh} />}
        </Menu>
        <Menu icon={UserRound} label="Assign" disabled={!targets.length || readOnly} testId="menu-assign">
          {(close) => (
            <>
              <button type="button" className="ol-menu-item" onClick={() => { assign.mutate(null); close(); }} data-testid="assign-none">
                Unassigned{targetRows.length > 0 && targetRows.every((c) => c.assignee_user_id === null) && <Check size={15} />}
              </button>
              {(team.data ?? []).map((m) => (
                <button key={m.user_id} type="button" className="ol-menu-item" onClick={() => { assign.mutate(m.user_id); close(); }} data-testid={`assign-${m.user_id}`}>
                  <Avatar name={m.name} /> {m.name}{m.is_you ? ' (you)' : ''}
                  {targetRows.length > 0 && targetRows.every((c) => c.assignee_user_id === m.user_id) && <Check size={15} />}
                </button>
              ))}
            </>
          )}
        </Menu>
        <span className="ol-grow" />
        <Cmd icon={RefreshCw} label={sync.isPending ? 'Checking…' : 'Sync'} onClick={() => sync.mutate()} disabled={sync.isPending} spin={sync.isPending} testId="button-sync" />
      </div>

      <div className="ol-body">
        <nav className="ol-folders" aria-label="Folders">
          <FolderGroup title="All accounts">
            {FOLDERS.map((f) => (
              <FolderLink key={f.path} icon={f.icon} name={f.name} active={!labelId && !searching && !accountId && folder.path === f.path}
                count={f.path === '/inbox' ? counts.data?.inbox_unread : f.path === '/drafts' ? drafts.data?.length : undefined} onClick={() => go({ path: f.path, a: null, label: null, c: null, q: null })} testId={`folder-${f.path.slice(1)}`} />
            ))}
          </FolderGroup>
          {(accounts.data ?? []).map((acc) => (
            <FolderGroup key={acc.id} title={acc.email_address}>
              {FOLDERS.filter((f) => f.path !== '/drafts' && f.path !== '/assignment').map((f) => (
                <FolderLink key={f.path} icon={f.icon} name={f.name} active={!labelId && !searching && accountId === acc.id && folder.path === f.path}
                  count={f.path === '/inbox' ? counts.data?.inbox_unread_by_account[String(acc.id)] : undefined} onClick={() => go({ path: f.path, a: acc.id, label: null, c: null, q: null })} />
              ))}
            </FolderGroup>
          ))}
          <FolderGroup title="Labels">
            {(labels.data ?? []).map((label) => (
              <button key={label.id} type="button" className={`ol-folder ${labelId === label.id ? 'active' : ''}`} onClick={() => go({ path: '/inbox', label: label.id, c: null, q: null })} data-testid={`label-${label.id}`}>
                <i className={`ol-dot ol-color-${label.color}`} /><span>{label.name}</span>{label.conversation_count > 0 && <b>{label.conversation_count}</b>}
              </button>
            ))}
            <Link href="/labels" className="ol-folder ol-folder-quiet"><Plus size={15} /><span>{labels.data?.length ? 'Manage labels' : 'Create a label'}</span></Link>
          </FolderGroup>
        </nav>

        <section className="ol-list" aria-label="Messages">
          <form className="ol-search" role="search" onSubmit={(e: FormEvent) => { e.preventDefault(); go({ q: searchText.trim() || null, c: null }); }}>
            <Search size={17} />
            <input value={searchText} onChange={(e) => setSearchText(e.target.value)} placeholder="Search mail: sender, subject or text" aria-label="Search mail" data-testid="input-mail-search" />
            {(searchText || query) && <button type="button" className="ol-icon" aria-label="Clear search" onClick={() => { setSearchText(''); go({ q: null }); }}><X size={15} /></button>}
          </form>
          {/* The same choices as the folder pane, for screens too narrow to show it. */}
          <select className="ol-folder-select" aria-label="Folder" value={labelId ? `label:${labelId}` : folder.path}
            onChange={(e) => (e.target.value.startsWith('label:') ? go({ path: '/inbox', label: Number(e.target.value.slice(6)), c: null }) : go({ path: e.target.value, label: null, c: null, q: null }))}>
            {FOLDERS.map((f) => <option key={f.path} value={f.path}>{f.name}</option>)}
            {(labels.data ?? []).map((label) => <option key={label.id} value={`label:${label.id}`}>Label: {label.name}</option>)}
          </select>
          <div className="ol-list-head">
            <div>
              <b data-testid="text-folder-title">{title}</b>
              <small>{account ? account.email_address : 'All accounts'}{query ? ` · “${query}”` : ''}</small>
            </div>
            <label className="ol-filter">
              <span className="sr-only">Filter</span>
              <select value={filter} onChange={(e) => setFilter(e.target.value as Filter)} data-testid="select-filter">
                {FILTERS.map(([value, name]) => <option key={value} value={value}>{name}</option>)}
              </select>
            </label>
          </div>

          <div className="ol-rows">
            {draftsFolder ? (
              drafts.isLoading ? <SkeletonRows rows={3} /> : !drafts.data?.length ? (
                <EmptyState icon={Pencil} title="No drafts" bare>A message you start and don’t send is kept here, so you can finish it later.</EmptyState>
              ) : drafts.data.map((d) => (
                <div key={d.id} className={`ol-row ${draft?.saved?.id === d.id ? 'active' : ''}`} data-testid={`draft-${d.id}`}>
                  <span className="ol-check"><Avatar name={d.to || d.subject || 'Draft'} /></span>
                  <button type="button" className="ol-row-main" onClick={() => setDraft({ mode: d.mode, saved: d })}>
                    <span className="ol-row-top"><span className="ol-sender"><span className="ol-draft-tag">Draft</span> {d.to || '(no recipient)'}</span></span>
                    <span className="ol-row-mid"><span className="ol-subject">{d.subject || '(no subject)'}</span><time>{rowDate(d.updated_at)}</time></span>
                    <span className="ol-preview">{d.body_text.trim().split('\n')[0] || ' '}</span>
                    <span className="ol-chips"><span className="ol-chip ol-chip-account">{d.account_email}</span></span>
                  </button>
                </div>
              ))
            ) : list.isLoading ? (
              <SkeletonRows rows={6} />
            ) : list.isError ? (
              <EmptyState icon={Mail} title="Could not load mail" bare>Check your connection and try again.</EmptyState>
            ) : items.length === 0 ? (
              <EmptyState icon={query ? Search : folder.icon} title={query ? `No results for “${query}”` : filter !== 'all' ? 'Nothing matches this filter' : `${title} is empty`} bare>
                {query ? 'Try a sender’s name or address, a word from the subject, or a word from the message.' : folder.view === 'inbox' && filter === 'all' ? 'New mail from your connected accounts appears here.' : undefined}
              </EmptyState>
            ) : (
              <>
                {items.map((conv, index) => {
                  const group = dateGroup(conv.last_message_at);
                  const first = index === 0 || dateGroup(items[index - 1].last_message_at) !== group;
                  return (
                    <div key={conv.id}>
                      {first && <div className="ol-group">{group}</div>}
                      <Row conv={conv} active={conv.id === openId} checked={checked.includes(conv.id)} showAccount={!accountId && (accounts.data?.length ?? 0) > 1}
                        onOpen={() => { setDraft(null); go({ c: conv.id }); }}
                        onCheck={() => setChecked((prev) => (prev.includes(conv.id) ? prev.filter((id) => id !== conv.id) : [...prev, conv.id]))} />
                    </div>
                  );
                })}
                {list.hasNextPage && (
                  <div className="ol-more">
                    <Button onClick={() => list.fetchNextPage()} disabled={list.isFetchingNextPage} testId="button-load-more">{list.isFetchingNextPage ? 'Loading…' : 'Load more'}</Button>
                  </div>
                )}
              </>
            )}
          </div>
        </section>

        <section className="ol-read" aria-label="Reading pane">
          {draft ? (
            <Composer key={`${draft.mode}-${draft.source?.id ?? 'new'}-${draft.saved?.id ?? ''}`} draft={draft} accounts={sendable} conversation={draft.mode === 'new' ? undefined : open}
              defaultAccountId={accountId} onClose={closeDraft} onSent={() => { refresh(); closeDraft(); }} />
          ) : !openId ? (
            <div className="ol-read-empty"><MailOpen size={54} strokeWidth={1.2} /><b>Select an item to read</b><span>Nothing is selected</span></div>
          ) : detail.isLoading ? (
            <div className="ol-read-pad"><SkeletonRows rows={5} /></div>
          ) : detail.isError || !detail.data ? (
            <EmptyState icon={Mail} title="This conversation is no longer here" bare>It may have been removed.</EmptyState>
          ) : (
            <Reading conversation={detail.data.conversation} messages={detail.data.messages} onBack={() => go({ c: null })}
              notes={detail.data.notes} canNote={!readOnly}
              onAction={(mode, source) => setDraft({ mode, source })} readOnly={!canReply} />
          )}
        </section>
      </div>
    </div>
  );
}

function Cmd({ icon: Icon, label, onClick, disabled, spin, testId }: { icon: LucideIcon; label: string; onClick: () => void; disabled?: boolean; spin?: boolean; testId?: string }) {
  return (
    <button type="button" className="ol-cmd" onClick={onClick} disabled={disabled} title={label} data-testid={testId}>
      <Icon size={17} className={spin ? 'ns-spin' : undefined} /><span>{label}</span>
    </button>
  );
}

function Menu({ icon: Icon, label, disabled, children, testId }: { icon: LucideIcon; label: string; disabled?: boolean; children: (close: () => void) => ReactNode; testId?: string }) {
  const [openMenu, setOpenMenu] = useState(false);
  const [place, setPlace] = useState({ top: 0, left: 0 });
  const ref = useRef<HTMLDivElement>(null);
  const pop = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!openMenu) return;
    const away = (event: MouseEvent) => {
      const target = event.target as Node;
      if (!ref.current?.contains(target) && !pop.current?.contains(target)) setOpenMenu(false);
    };
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') setOpenMenu(false); };
    const close = () => setOpenMenu(false);
    document.addEventListener('mousedown', away);
    document.addEventListener('keydown', escape);
    window.addEventListener('resize', close);
    return () => { document.removeEventListener('mousedown', away); document.removeEventListener('keydown', escape); window.removeEventListener('resize', close); };
  }, [openMenu]);

  function toggle() {
    const box = ref.current?.getBoundingClientRect();
    // Placed against the window, just under its button and never past the right edge.
    if (box) setPlace({ top: box.bottom + 6, left: Math.max(8, Math.min(box.left, window.innerWidth - 268)) });
    setOpenMenu((v) => !v);
  }

  return (
    <div className="ol-menu" ref={ref}>
      <button type="button" className="ol-cmd" onClick={toggle} disabled={disabled} aria-expanded={openMenu} data-testid={testId}>
        <Icon size={17} /><span>{label}</span><ChevronDown size={14} />
      </button>
      {/* Drawn at the top of the page, not inside the command bar: the bar clips what is inside it. */}
      {openMenu && createPortal(
        <div className="ol-menu-pop" ref={pop} style={{ top: place.top, left: place.left }} data-testid={testId ? `${testId}-pop` : undefined}>{children(() => setOpenMenu(false))}</div>,
        document.body,
      )}
    </div>
  );
}

function LabelPicker({ all, applied, onChange, onCreated }: { all: Label[]; applied: Label[]; onChange: (ids: number[]) => void; onCreated: () => void }) {
  const toast = useToast();
  const [name, setName] = useState('');
  const appliedIds = applied.map((l) => l.id);
  const create = useMutation({
    mutationFn: () => api.createLabel({ name: name.trim(), color: LABEL_COLORS[all.length % LABEL_COLORS.length] }),
    onSuccess: (label) => { setName(''); onCreated(); onChange([...appliedIds, label.id]); },
    onError: (err) => toast(err instanceof ApiError ? err.message : 'Could not create the label.'),
  });
  return (
    <>
      {all.length === 0 && <div className="ol-menu-note">No labels yet. Create the first one below.</div>}
      {all.map((label) => {
        const on = appliedIds.includes(label.id);
        return (
          <button key={label.id} type="button" className="ol-menu-item" onClick={() => onChange(on ? appliedIds.filter((id) => id !== label.id) : [...appliedIds, label.id])} data-testid={`pick-label-${label.id}`}>
            <i className={`ol-dot ol-color-${label.color}`} /> {label.name}{on && <Check size={15} />}
          </button>
        );
      })}
      <form className="ol-menu-form" onSubmit={(e) => { e.preventDefault(); if (name.trim()) create.mutate(); }}>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="New label" maxLength={80} aria-label="New label name" data-testid="input-new-label" />
        <button type="submit" className="ol-icon" disabled={!name.trim() || create.isPending} aria-label="Create label"><Plus size={16} /></button>
      </form>
    </>
  );
}

function FolderGroup({ title, children }: { title: string; children: ReactNode }) {
  const [shown, setShown] = useState(true);
  return (
    <div className="ol-folder-group">
      <button type="button" className="ol-folder-title" onClick={() => setShown((v) => !v)} aria-expanded={shown}>
        <ChevronDown size={14} style={{ transform: shown ? undefined : 'rotate(-90deg)' }} /><span>{title}</span>
      </button>
      {shown && children}
    </div>
  );
}

function FolderLink({ icon: Icon, name, active, count, onClick, testId }: { icon: LucideIcon; name: string; active: boolean; count?: number; onClick: () => void; testId?: string }) {
  return (
    <button type="button" className={`ol-folder ${active ? 'active' : ''}`} onClick={onClick} aria-current={active ? 'page' : undefined} data-testid={testId}>
      <Icon size={16} /><span>{name}</span>{count ? <b>{count.toLocaleString()}</b> : null}
    </button>
  );
}

function Row({ conv, active, checked, showAccount, onOpen, onCheck }: { conv: Conversation; active: boolean; checked: boolean; showAccount: boolean; onOpen: () => void; onCheck: () => void }) {
  const sender = conv.last_sender_name || conv.last_sender_email || conv.account_email;
  return (
    <div className={`ol-row ${conv.is_read ? '' : 'unread'} ${active ? 'active' : ''} ${checked ? 'checked' : ''}`} data-testid={`row-${conv.id}`}>
      <label className="ol-check" onClick={(e) => e.stopPropagation()}>
        <input type="checkbox" checked={checked} onChange={onCheck} aria-label={`Select conversation from ${sender}`} />
        <Avatar name={sender} />
      </label>
      <button type="button" className="ol-row-main" onClick={onOpen}>
        <span className="ol-row-top">
          <span className="ol-sender">{sender}{conv.message_count > 1 && <em>{conv.message_count}</em>}</span>
          <span className="ol-row-icons">
            {conv.has_attachments && <Paperclip size={14} aria-label="Has attachments" />}
            {conv.is_starred && <Flag size={14} className="ol-flagged" aria-label="Flagged" />}
          </span>
        </span>
        <span className="ol-row-mid"><span className="ol-subject">{conv.subject || '(no subject)'}</span><time>{rowDate(conv.last_message_at)}</time></span>
        <span className="ol-preview">{conv.snippet || ' '}</span>
        {(conv.labels.length > 0 || conv.status !== 'open' || conv.priority !== 'normal' || showAccount || conv.assignee_name) && (
          <span className="ol-chips">
            {conv.priority !== 'normal' && <span className={`ol-chip ol-chip-priority ol-priority-${conv.priority}`}>{PRIORITY_NAMES[conv.priority]}</span>}
            {conv.status !== 'open' && <span className={`ol-chip ol-chip-status ol-status-${conv.status}`}>{conv.status === 'pending' ? 'Pending' : 'Closed'}</span>}
            {conv.labels.map((label) => <span key={label.id} className={`ol-chip ol-color-${label.color}`}>{label.name}</span>)}
            {conv.assignee_name && <span className="ol-chip ol-chip-assignee"><UserRound size={11} /> {conv.assignee_name}</span>}
            {showAccount && <span className="ol-chip ol-chip-account">{conv.account_email}</span>}
          </span>
        )}
      </button>
    </div>
  );
}

function Reading({ conversation, messages, notes, canNote, onBack, onAction, readOnly }: {
  conversation: Conversation; messages: Message[]; notes: Note[]; canNote: boolean; onBack: () => void; onAction: (mode: ComposeMode, source: Message) => void; readOnly: boolean;
}) {
  const lastId = messages[messages.length - 1]?.id;
  const [expanded, setExpanded] = useState<number[]>(lastId ? [lastId] : []);
  return (
    <div className="ol-read-pad" data-testid="reading-pane">
      <button type="button" className="ol-back" onClick={onBack}><ArrowLeft size={16} /> Back</button>
      <header className="ol-read-head">
        <h1 data-testid="text-subject">{conversation.subject || '(no subject)'}</h1>
        <div className="ol-chips">
          <span className={`ol-chip ol-chip-status ol-status-${conversation.status}`} data-testid="text-status">{STATUSES.find(([v]) => v === conversation.status)?.[1] ?? conversation.status}</span>
          {conversation.priority !== 'normal' && <span className={`ol-chip ol-chip-priority ol-priority-${conversation.priority}`} data-testid="text-priority">{PRIORITY_NAMES[conversation.priority]} priority</span>}
          {conversation.labels.map((label) => <span key={label.id} className={`ol-chip ol-color-${label.color}`}>{label.name}</span>)}
          <span className="ol-chip ol-chip-assignee" data-testid="text-assignee"><UserRound size={11} /> {conversation.assignee_name ?? 'Unassigned'}</span>
          <span className="ol-chip ol-chip-account">{conversation.account_email}</span>
        </div>
      </header>
      <ReminderControl key={`r${conversation.id}`} conversationId={conversation.id} />
      <AiInsight key={conversation.id} conversationId={conversation.id} readOnly={readOnly} />
      {messages.map((message) => {
        const openCard = expanded.includes(message.id);
        const to = message.recipients.filter((r) => r.kind === 'to');
        const cc = message.recipients.filter((r) => r.kind === 'cc');
        return (
          <article key={message.id} className={`ol-message ${openCard ? 'open' : ''}`} data-testid={`message-${message.id}`}>
            <div className="ol-message-head" role="button" tabIndex={0}
              onClick={() => setExpanded((prev) => (openCard ? prev.filter((id) => id !== message.id) : [...prev, message.id]))}
              onKeyDown={(e) => { if (e.key === 'Enter') setExpanded((prev) => (openCard ? prev.filter((id) => id !== message.id) : [...prev, message.id])); }}>
              <Avatar name={message.sender_name || message.sender_email} />
              <div className="ol-message-who">
                <b>{message.sender_name || message.sender_email}{message.direction === 'outbound' && <span className="ol-chip ol-chip-account">Sent from here</span>}</b>
                {openCard ? (
                  <small>To: {to.map((r) => r.name || r.email).join('; ') || conversation.account_email}{cc.length > 0 && <> · Cc: {cc.map((r) => r.name || r.email).join('; ')}</>}</small>
                ) : (
                  <small className="ol-message-peek">{plainBody(message).slice(0, 140)}</small>
                )}
              </div>
              <time>{dateTime(message.sent_at)}</time>
              {openCard && !readOnly && (
                <span className="ol-message-actions" onClick={(e) => e.stopPropagation()}>
                  <button type="button" className="ol-icon" title="Reply" aria-label="Reply" onClick={() => onAction('reply', message)}><Reply size={17} /></button>
                  <button type="button" className="ol-icon" title="Reply all" aria-label="Reply all" onClick={() => onAction('replyAll', message)}><ReplyAll size={17} /></button>
                  <button type="button" className="ol-icon" title="Forward" aria-label="Forward" onClick={() => onAction('forward', message)}><Forward size={17} /></button>
                </span>
              )}
            </div>
            {openCard && (
              <>
                {message.attachments.length > 0 && (
                  <div className="ol-files">
                    {message.attachments.map((file) => (
                      <a key={file.id} className="ol-file" href={api.attachmentUrl(file.id)} download={file.filename} data-testid={`attachment-${file.id}`}>
                        <FileText size={18} /><span><b>{file.filename}</b><small>{fileSize(file.file_size)}</small></span><Download size={15} />
                      </a>
                    ))}
                  </div>
                )}
                <MessageBody message={message} />
              </>
            )}
          </article>
        );
      })}
      <Notes conversationId={conversation.id} notes={notes} canNote={canNote} />
    </div>
  );
}

/** Private notes on a conversation. They are shown here only and never go out with any email. */
function Notes({ conversationId, notes, canNote }: { conversationId: number; notes: Note[]; canNote: boolean }) {
  const client = useQueryClient();
  const toast = useToast();
  const [text, setText] = useState('');
  const done = () => { client.invalidateQueries({ queryKey: ['conversation', conversationId] }); client.invalidateQueries({ queryKey: ['recent-notes'] }); };
  const add = useMutation({
    mutationFn: () => api.addNote(conversationId, text),
    onSuccess: () => { setText(''); done(); },
    onError: (err) => toast(err instanceof ApiError ? err.message : 'Could not save the note.'),
  });
  const remove = useMutation({
    mutationFn: (id: number) => api.deleteNote(id),
    onSuccess: done,
    onError: (err) => toast(err instanceof ApiError ? err.message : 'Could not delete the note.'),
  });
  return (
    <section className="ol-notes" data-testid="notes">
      <h2><StickyNote size={16} /> Internal notes <small>Only your team sees these. They are never sent.</small></h2>
      {notes.map((note) => (
        <div className="ol-note" key={note.id} data-testid={`note-${note.id}`}>
          <div className="ol-note-head"><b>{note.author_name ?? 'Someone'}</b><time>{timeAgo(note.created_at)}</time>
            {note.is_yours && <button type="button" className="ol-icon" aria-label="Delete note" title="Delete note" onClick={() => remove.mutate(note.id)}><Trash2 size={14} /></button>}
          </div>
          <p>{note.body}</p>
        </div>
      ))}
      {canNote && (
        <form className="ol-note-form" onSubmit={(e) => { e.preventDefault(); if (text.trim()) add.mutate(); }}>
          <textarea value={text} onChange={(e) => setText(e.target.value)} placeholder="Add a note for your team. Type @ and a name to let someone know." rows={2} maxLength={5000} aria-label="Internal note" data-testid="input-note" />
          <Button type="submit" disabled={!text.trim() || add.isPending} testId="button-add-note">{add.isPending ? 'Saving…' : 'Add note'}</Button>
        </form>
      )}
    </section>
  );
}

/** Email HTML is untrusted. It is shown in a frame that cannot run scripts, with remote content off until asked for. */
function MessageBody({ message }: { message: Message }) {
  const frame = useRef<HTMLIFrameElement>(null);
  const [images, setImages] = useState(false);
  const html = message.body_html;
  const hasRemoteImages = Boolean(html && /<img[^>]+src=["']?https?:/i.test(html));
  const srcDoc = useMemo(() => {
    if (!html) return '';
    const policy = `default-src 'none'; style-src 'unsafe-inline'; img-src data: cid:${images ? ' https: http:' : ''}; font-src data:`;
    return `<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="${policy}"><base target="_blank">`
      + '<style>html{color-scheme:light}body{margin:0;font:14.5px/1.6 Manrope,"Segoe UI",Arial,sans-serif;color:#26324f;overflow-wrap:anywhere}img{max-width:100%;height:auto}table{max-width:100%}blockquote{margin:0 0 0 8px;padding-left:12px;border-left:3px solid #d5dbe8;color:#56627a}a{color:#14599a}</style>'
      + `</head><body>${html}</body></html>`;
  }, [html, images]);

  function fit() {
    const doc = frame.current?.contentDocument;
    if (frame.current && doc) frame.current.style.height = `${Math.max(doc.documentElement.scrollHeight, 40)}px`;
  }

  if (!html) return <div className="ol-text">{message.body_text?.trim() || '(This message has no text.)'}</div>;
  return (
    <>
      {hasRemoteImages && !images && (
        <div className="ol-images-note">Pictures in this message are not shown, to protect your privacy. <button type="button" onClick={() => setImages(true)}>Show pictures</button></div>
      )}
      <iframe ref={frame} className="ol-html" title="Message" sandbox="allow-same-origin allow-popups allow-popups-to-escape-sandbox" srcDoc={srcDoc} onLoad={fit} />
    </>
  );
}

function readFile(file: File): Promise<OutgoingAttachment & { size: number }> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error);
    reader.onload = () => resolve({ filename: file.name, content_type: file.type || 'application/octet-stream', content_base64: String(reader.result).split(',')[1] ?? '', size: file.size });
    reader.readAsDataURL(file);
  });
}

/** The part of a message someone is writing, and the quoted or forwarded original under it. */
function splitQuote(text: string): [string, string] {
  const at = text.search(/\n\n(?:On .+ wrote:\n>|-{10} Forwarded message -{10})/);
  return at < 0 ? [text, ''] : [text.slice(0, at), text.slice(at)];
}

function Composer({ draft, accounts, conversation, defaultAccountId, onClose, onSent }: {
  draft: Draft; accounts: EmailAccount[]; conversation?: Conversation; defaultAccountId?: number; onClose: () => void; onSent: () => void;
}) {
  const toast = useToast();
  const client = useQueryClient();
  const { user } = useSession();
  const { mode, source, saved } = draft;
  const own = (conversation?.account_email ?? '').toLowerCase();
  const initial = useMemo(() => {
    if (saved) return { to: saved.to, cc: saved.cc, subject: saved.subject, body: saved.body_text };
    if (!source || mode === 'new') return { to: draft.to ?? '', cc: '', subject: '', body: '' };
    const quoted = plainBody(source);
    if (mode === 'forward') {
      const header = ['---------- Forwarded message ----------', `From: ${person(source.sender_name, source.sender_email)}`, `Date: ${dateTime(source.sent_at)}`, `Subject: ${source.subject}`,
        `To: ${source.recipients.filter((r) => r.kind === 'to').map((r) => person(r.name, r.email)).join(', ')}`].join('\n');
      return { to: '', cc: '', subject: withPrefix('Fwd', source.subject), body: `\n\n${header}\n\n${quoted}` };
    }
    const others = (kind: 'to' | 'cc') => source.recipients.filter((r) => r.kind === kind && r.email.toLowerCase() !== own).map((r) => r.email);
    // Answering our own sent message goes to the people it was sent to.
    const to = source.direction === 'inbound' ? [source.sender_email] : others('to');
    const cc = mode === 'replyAll' ? [...(source.direction === 'inbound' ? others('to') : []), ...others('cc')].filter((address) => !to.includes(address)) : [];
    const body = `\n\nOn ${dateTime(source.sent_at)}, ${person(source.sender_name, source.sender_email)} wrote:\n${quoted.split('\n').map((line) => `> ${line}`).join('\n')}`;
    return { to: to.join(', '), cc: [...new Set(cc)].join(', '), subject: withPrefix('Re', source.subject), body };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const answering = mode === 'reply' || mode === 'replyAll';
  // What ties this message to an earlier one: taken from the saved draft, or from the message being answered.
  const conversationId = saved ? saved.conversation_id : answering ? conversation?.id ?? null : null;
  const inReplyTo = saved ? saved.in_reply_to : answering ? source?.provider_message_id ?? null : null;
  const forwardOf = saved ? saved.forward_of_message_id : mode === 'forward' ? source?.id ?? null : null;
  const originals = source?.attachments ?? [];
  const hasOriginals = mode === 'forward' && (originals.length > 0 || Boolean(saved?.forward_of_message_id));

  const [accountId, setAccountId] = useState<number | undefined>(saved?.email_account_id ?? conversation?.email_account_id ?? defaultAccountId ?? accounts[0]?.id);
  const [to, setTo] = useState(initial.to);
  const [cc, setCc] = useState(initial.cc);
  const [bcc, setBcc] = useState(saved?.bcc ?? '');
  const [showCc, setShowCc] = useState(Boolean(initial.cc || saved?.bcc));
  const [subject, setSubject] = useState(initial.subject);
  const [body, setBody] = useState(initial.body);
  const [files, setFiles] = useState<(OutgoingAttachment & { size: number })[]>([]);
  const [withOriginals, setWithOriginals] = useState(hasOriginals);
  const [error, setError] = useState<string | null>(null);
  const bodyRef = useRef<HTMLTextAreaElement>(null);
  useEffect(() => { if (!answering || saved) return; bodyRef.current?.focus(); bodyRef.current?.setSelectionRange(0, 0); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // --- saving the draft as it is written ---
  const [draftId, setDraftId] = useState<number | undefined>(saved?.id);
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved' | 'failed'>(saved ? 'saved' : 'idle');
  const idRef = useRef(draftId);
  const latest = useRef({ accountId, to, cc, bcc, subject, body });
  latest.current = { accountId, to, cc, bcc, subject, body };
  const queue = useRef<Promise<void>>(Promise.resolve());
  const pending = useRef(false);
  const finished = useRef(false); // sent or discarded: nothing more to save

  function saveNow(): Promise<void> {
    pending.current = false;
    queue.current = queue.current.then(async () => {
      const now = latest.current;
      if (finished.current || !now.accountId) return;
      const payload = { email_account_id: now.accountId, mode, conversation_id: conversationId, in_reply_to: inReplyTo, forward_of_message_id: forwardOf,
        to: now.to, cc: now.cc, bcc: now.bcc, subject: now.subject, body_text: now.body };
      setSaveState('saving');
      try {
        const result = idRef.current ? await api.updateDraft(idRef.current, payload) : await api.createDraft(payload);
        idRef.current = result.id;
        setDraftId(result.id);
        setSaveState('saved');
        client.invalidateQueries({ queryKey: ['drafts'] });
      } catch {
        setSaveState('failed');
      }
    });
    return queue.current;
  }

  const firstRun = useRef(true);
  useEffect(() => {
    if (firstRun.current) { firstRun.current = false; return; }
    pending.current = true;
    const timer = setTimeout(saveNow, 1200);
    return () => clearTimeout(timer);
  }, [accountId, to, cc, bcc, subject, body]); // eslint-disable-line react-hooks/exhaustive-deps
  // Leaving the composer (opening another message, another page) keeps what was typed.
  useEffect(() => () => { if (pending.current && !finished.current) saveNow(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const originalBytes = withOriginals ? originals.reduce((sum, f) => sum + f.file_size, 0) : 0;
  const totalBytes = files.reduce((sum, f) => sum + f.size, 0) + originalBytes;

  async function addFiles(event: ChangeEvent<HTMLInputElement>) {
    const picked = Array.from(event.target.files ?? []);
    event.target.value = '';
    try {
      const read = await Promise.all(picked.map(readFile));
      setFiles((prev) => [...prev, ...read]);
    } catch {
      toast('Could not read that file.');
    }
  }

  const templates = useQuery({ queryKey: ['templates'], queryFn: api.templates });
  function applyTemplate(template: { subject: string; body: string }) {
    const recipient = source?.sender_name || splitAddresses(to)[0]?.split('@')[0] || '';
    const fill = (text: string) => text.replaceAll('{{recipient_name}}', recipient).replaceAll('{{my_name}}', user.name);
    setBody((current) => `${fill(template.body)}${current ? `\n${current}` : ''}`);
    if (!subject.trim() && template.subject) setSubject(fill(template.subject));
  }

  const send = useMutation({
    mutationFn: async () => {
      await queue.current; // a save in flight finishes first, so its draft id is known
      finished.current = true;
      return api.sendMessage({
        account_id: accountId!,
        to: splitAddresses(to),
        cc: splitAddresses(cc).length ? splitAddresses(cc) : undefined,
        bcc: splitAddresses(bcc).length ? splitAddresses(bcc) : undefined,
        subject: subject.trim(),
        body_text: body,
        conversation_id: conversationId ?? undefined,
        in_reply_to: inReplyTo ?? undefined,
        attachments: files.map(({ filename, content_type, content_base64 }) => ({ filename, content_type, content_base64 })),
        forward_attachments_of: withOriginals && forwardOf ? forwardOf : undefined,
        draft_id: idRef.current,
      });
    },
    onSuccess: () => { client.invalidateQueries({ queryKey: ['drafts'] }); toast('Sent.'); onSent(); },
    onError: (err) => { finished.current = false; setError(err instanceof ApiError ? err.message : 'Could not send the message.'); },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (!accountId) return setError('Choose the mailbox to send from.');
    if (!splitAddresses(to).length) return setError('Add at least one recipient.');
    if (totalBytes > MAX_ATTACH_BYTES) return setError('The attachments are too large to send. Keep them under 18 MB in total.');
    send.mutate();
  }

  async function discard() {
    finished.current = true;
    await queue.current;
    if (idRef.current) {
      try { await api.deleteDraft(idRef.current); } catch { /* already gone */ }
      client.invalidateQueries({ queryKey: ['drafts'] });
    }
    onClose();
  }

  const heading = saved ? 'Draft' : { new: 'New message', reply: 'Reply', replyAll: 'Reply all', forward: 'Forward' }[mode];
  return (
    <form className="ol-compose" onSubmit={submit} data-testid="composer">
      <div className="ol-compose-bar">
        <button type="submit" className="ol-cmd ol-cmd-primary" disabled={send.isPending} data-testid="button-send"><Send size={16} /> {send.isPending ? 'Sending…' : 'Send'}</button>
        <label className="ol-cmd"><Paperclip size={16} /><span>Attach</span><input type="file" multiple hidden onChange={addFiles} data-testid="input-attach" /></label>
        <Menu icon={FileText} label="Templates" testId="menu-templates">
          {(close) => (templates.data?.length ? templates.data.map((template) => (
            <button key={template.id} type="button" className="ol-menu-item" onClick={() => { applyTemplate(template); close(); }} data-testid={`use-template-${template.id}`}>{template.name}</button>
          )) : <div className="ol-menu-note">No templates yet. <Link href="/templates" className="text-link">Create one</Link></div>)}
        </Menu>
        <b className="ol-compose-title">{heading}</b>
        <span className="ol-save-state" data-testid="text-draft-state">{saveState === 'saving' ? 'Saving…' : saveState === 'saved' ? 'Draft saved' : saveState === 'failed' ? 'Draft not saved' : ''}</span>
        <span className="ol-grow" />
        <button type="button" className="ol-cmd" onClick={discard} data-testid="button-discard"><Trash2 size={16} /><span>Discard</span></button>
      </div>
      {error && <div className="form-error" role="alert" data-testid="notice-compose-error">{error}</div>}
      <label className="ol-line"><span>From</span>
        <select value={accountId ?? ''} onChange={(e) => setAccountId(Number(e.target.value))} disabled={answering} data-testid="select-from">
          {accounts.map((acc) => <option key={acc.id} value={acc.id}>{acc.display_name && acc.display_name !== acc.email_address ? `${acc.display_name} <${acc.email_address}>` : acc.email_address}</option>)}
        </select>
      </label>
      <label className="ol-line"><span>To</span>
        <input value={to} onChange={(e) => setTo(e.target.value)} placeholder="name@example.com, another@example.com" autoFocus={!answering && !saved} data-testid="input-to" />
        {!showCc && <button type="button" className="ol-link" onClick={() => setShowCc(true)}>Cc Bcc</button>}
      </label>
      {showCc && <label className="ol-line"><span>Cc</span><input value={cc} onChange={(e) => setCc(e.target.value)} data-testid="input-cc" /></label>}
      {showCc && <label className="ol-line"><span>Bcc</span><input value={bcc} onChange={(e) => setBcc(e.target.value)} data-testid="input-bcc" /></label>}
      <label className="ol-line"><span className="sr-only">Subject</span><input className="ol-subject-input" value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="Add a subject" data-testid="input-subject" /></label>
      {(files.length > 0 || hasOriginals) && (
        <div className="ol-files">
          {hasOriginals && (
            <label className="ol-file ol-file-option">
              <input type="checkbox" checked={withOriginals} onChange={(e) => setWithOriginals(e.target.checked)} data-testid="check-forward-attachments" />
              <span><b>Include the original {originals.length === 1 ? 'attachment' : originals.length ? `${originals.length} attachments` : 'attachments'}</b><small>{originals.map((f) => f.filename).join(', ')}</small></span>
            </label>
          )}
          {files.map((file, index) => (
            <span key={`${file.filename}-${index}`} className="ol-file">
              <FileText size={18} /><span><b>{file.filename}</b><small>{fileSize(file.size)} · not kept in the draft</small></span>
              <button type="button" className="ol-icon" aria-label={`Remove ${file.filename}`} onClick={() => setFiles((prev) => prev.filter((_, i) => i !== index))}><X size={15} /></button>
            </span>
          ))}
        </div>
      )}
      <AiWriter conversationId={conversation?.id} current={splitQuote(body)[0].trim()}
        onResult={(r) => { setBody(r.body + splitQuote(body)[1]); if (r.subject && !subject.trim()) setSubject(r.subject); }} />
      <textarea ref={bodyRef} className="ol-body-input" value={body} onChange={(e) => setBody(e.target.value)} placeholder="Type your message" aria-label="Message" data-testid="input-body" />
    </form>
  );
}

export function LabelsPage() {
  const client = useQueryClient();
  const toast = useToast();
  const { role } = useSession();
  const readOnly = role === 'viewer';
  const labels = useQuery({ queryKey: ['labels'], queryFn: api.labels });
  const [name, setName] = useState('');
  const [color, setColor] = useState<LabelColor>('blue');
  const done = () => { client.invalidateQueries({ queryKey: ['labels'] }); client.invalidateQueries({ queryKey: ['conversations'] }); };
  const fail = (fallback: string) => (err: unknown) => toast(err instanceof ApiError ? err.message : fallback);
  const create = useMutation({ mutationFn: () => api.createLabel({ name: name.trim(), color }), onSuccess: () => { setName(''); done(); toast('Label created.'); }, onError: fail('Could not create the label.') });
  const update = useMutation({ mutationFn: ({ id, ...body }: { id: number; name?: string; color?: LabelColor }) => api.updateLabel(id, body), onSuccess: done, onError: fail('Could not change the label.') });
  const remove = useMutation({ mutationFn: (id: number) => api.deleteLabel(id), onSuccess: () => { done(); toast('Label deleted.'); }, onError: fail('Could not delete the label.') });

  return (
    <>
      <PageHeading eyebrow="ORGANIZE" title="Labels" description="One vocabulary for organizing mail across all accounts." />
      {!readOnly && (
        <form className="panel ol-label-form" onSubmit={(e) => { e.preventDefault(); if (name.trim()) create.mutate(); }}>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="New label name" maxLength={80} aria-label="New label name" data-testid="input-label-name" />
          <ColorPicker value={color} onChange={setColor} />
          <Button kind="primary" type="submit" disabled={!name.trim() || create.isPending} testId="button-create-label">{create.isPending ? 'Creating…' : 'Create label'}</Button>
        </form>
      )}
      <section className="panel table-panel" style={{ marginTop: '1rem' }}>
        {labels.isLoading ? <SkeletonRows rows={3} /> : !labels.data?.length ? (
          <EmptyState icon={Tag} title="No labels yet">Labels group conversations across every account. Create one above, then apply it from the Labels button in the mail screen.</EmptyState>
        ) : (
          <div className="data-table-wrap">
            <table className="data-table">
              <thead><tr><th>Label</th><th>Colour</th><th>Conversations</th><th /></tr></thead>
              <tbody>
                {labels.data.map((label) => (
                  <tr key={label.id} data-testid={`label-row-${label.id}`}>
                    <td>
                      <input className="ol-label-name" defaultValue={label.name} maxLength={80} disabled={readOnly} aria-label={`Name of label ${label.name}`}
                        onBlur={(e) => { const next = e.target.value.trim(); if (next && next !== label.name) update.mutate({ id: label.id, name: next }); else e.target.value = label.name; }}
                        onKeyDown={(e) => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }} />
                    </td>
                    <td><ColorPicker value={label.color} onChange={(next) => update.mutate({ id: label.id, color: next })} disabled={readOnly} /></td>
                    <td><Link href={`/inbox?label=${label.id}`} className="text-link">{label.conversation_count.toLocaleString()}</Link></td>
                    <td style={{ textAlign: 'right' }}>
                      {!readOnly && <Button onClick={() => { if (confirm(`Delete the label “${label.name}”? Conversations keep their mail; only the label is removed.`)) remove.mutate(label.id); }} disabled={remove.isPending}>Delete</Button>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}

function ColorPicker({ value, onChange, disabled }: { value: LabelColor; onChange: (color: LabelColor) => void; disabled?: boolean }) {
  return (
    <span className="ol-colors" role="radiogroup" aria-label="Label colour">
      {LABEL_COLORS.map((color) => (
        <button key={color} type="button" role="radio" aria-checked={value === color} aria-label={color} disabled={disabled}
          className={`ol-dot ol-color-${color} ${value === color ? 'picked' : ''}`} onClick={() => onChange(color)} />
      ))}
    </span>
  );
}
